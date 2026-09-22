# Grill: fix-issue-232-archived-manifest-gate 设计追问

## Reviewer

- run id: grill-fix-issue-232-archived-manifest-gate-2026-09-22-001（独立零记忆 subagent，未继承开发上下文）
- 时间: 2026-09-22
- 复核方式:
  - 读:
    - `openspec/changes/fix-issue-232-archived-manifest-gate/{proposal.md,design.md,tasks.md,specs/dev-workflow-state-machine/spec.md}`（全文）
    - `agent/workflow/review_manifest.py`（重点 `verify_review_manifest` :135-175、`tasks_hash` 比较 :169-170、`_verify_git_span` :209-232、`artifact_hash` :183-195）
    - `scripts/check_openspec_artifacts.py`（`_check_review_manifests` :1009-1051、`iter_change_dirs` :1277-1284、`--check-archived` 分支 :1425-1435、main 的 errors→exit 1 :1456-1459、`_changed_paths_since_base` :1352-1379）
    - `scripts/check_phase_done.py`（:255-278，**第三个生产调用方**）
    - `.github/workflows/ci.yml`（`validate` job :9-66，checker 步骤 :57-66，`fetch-depth: 0` :13-17）
    - `openspec/specs/dev-workflow-state-machine/spec.md`（「Review evidence manifest」:140-158）
    - `tests/agent/workflow/test_review_manifest.py`（:111-142）、`tests/test_openspec_artifact_checker.py`（:1663-1706）、`tests/test_workflow_archive_write_channel.py`（:137-184）
    - `docs/openspec-change-backlog.md`、`AGENTS.md` 相关段落（受保护 artifact/审阅闭环）
  - 实跑（全部只读或落 `/tmp`；最后一次 `git status --porcelain` 为空，无残留）:
    - `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived` → **15 条 `ERROR: tasks hash mismatch`，exit 1**（复现 design 断言）
    - 自写只读探针（`/tmp/grill_probe*.py`）逐条复算 15 条失败 change 的 `tasks.md` 历史版本与 manifest `tasks_hash` 的匹配版，再与归档版逐行 diff → **15/15 命中历史版本，非 checkbox 差异行合计 0**
    - A′ 模拟补丁（改 `/tmp` 脚本注入，**不落仓库**）→ 全仓 `--check-archived` **exit 0**，耗时 8.9s
    - 在真实仓库临时打 A′ 补丁跑相关 pytest 后**立即 `git checkout --` 还原**（`git status` 已确认干净）→ 见下 Confirmed Decision 2 的既有测试冲突
    - revision-bound 替代方案探针：用 `git show <head_sha>:<tasks.md>` 复算 → **32 过 / 10 红 / 1 head_sha 无 blob**，证明该替代不可行
    - `head_sha == HEAD` 影响面探针：43 个归档 manifest 中 **0 个 `head_sha == HEAD`**（36 个是 HEAD 祖先，7 个不可达）
    - `/tmp` 冷状态 demo：把 note 追加进 `list[str]` 返回值 → checker `ERROR: note: ...` + **exit 1**
    - `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → 30 passed / 0 failed
    - 归档统计：90 个归档目录、88 个含 `specs/`、44 份 `*-review.md`、**0 份缺 manifest**；`--check-archived` 循环因 `parse_change_type` 为 None 跳过 4 个 2026-06-21 老目录（均无 `reviews/`，当前不构成盲区）

## Confirmed Decisions

- **决策**: 接受 D1「15 条漂移全部良性」的**结论**，但纠正其**刻画**：漂移不是「勾选翻转」，而是**同名 checkbox 行上的实质性文本编辑**（测试数 1813→1814、`76 passed`→`77 passed`、追加「归档后复跑通过」「PR #142 双 check 均 SUCCESS」等证据、以及 `fix-issue-110` 整条新增任务行）。「零条非 checkbox 行」成立仅因这些编辑**恰好发生在以 `- [ ]` 开头的行内**；它**不**等于「无实质内容变更」。因此 A′ 放弃的是「归档语境下检测任何 post-PASS 的 tasks.md 编辑（含恶意描述篡改）」的能力——这一点必须在 spec 的降级理由里写明，而不是笼统称「良性」；理由: 独立复算 15/15 命中历史版本且非 checkbox 差异行为 0，证实「非篡改」；但 diff 原文显示描述级编辑真实存在，故结论成立、措辞需收紧；来源: grill-fix-issue-232-archived-manifest-gate-2026-09-22-001
- **决策**: A′ 是当前可选方案中的**唯一可行解**，但**必须同步修改既有测试** `tests/test_openspec_artifact_checker.py::test_verify_review_manifest_archived_path`（:1663-1706，其 :1700-1706 断言「归档态改 tasks.md → `tasks hash mismatch`」）。实跑证据：打上 A′ 后该测试 **FAILED**（`assert any("tasks hash mismatch" in e for e in errors)` 为 False），而 `tests/agent/workflow/test_review_manifest.py` 与 `tests/test_workflow_archive_write_channel.py` 全过。design/tasks.md 现有条目**只列了新增用例，未列此既有用例的改写**，属实现前必须补的遗漏；理由: 该文件不在本 change 的 tasks 影响面内，遗漏会让实现者要么被红测试卡住、要么私自删断言而不留判别性对照；来源: grill-fix-issue-232-archived-manifest-gate-2026-09-22-001
- **决策**: 「降级可见」的 note **绝对不得混入 `verify_review_manifest` 的 `list[str]` 返回值**。实跑 `/tmp` 冷状态 demo：返回值含 note 时，`_check_review_manifests` 的 `errors.extend(...)`（:1050）→ main 的 `for error in errors: print("ERROR: ...")`（:1456-1458）→ **checker 直接红、exit 1**，A′ 的「可见」立刻退化为「误伤」，且 4 个 `assert ... == []` 的既有断言（`test_review_manifest.py:108`、`test_workflow_state_cli.py:367`、`test_workflow_protected_write_channel.py:169`、`test_workflow_archive_write_channel.py:147`）会被污染。推荐落点见 Open Question Q1；理由: 该函数语义是 pure predicate（错误列表），note 不是 error；调用点必须能区分；来源: grill-fix-issue-232-archived-manifest-gate-2026-09-22-001
- **决策**: spec delta 完整性**核对属实**：当前正式 spec `openspec/specs/dev-workflow-state-machine/spec.md:140-158` 的「Review evidence manifest」Requirement 恰含 **2 条** Scenario（`review report 缺少 manifest`、`manifest 字段和 hash 校验`），delta 含 **4 条**（上述 2 条**逐字相同**，实测归一化后 `identical: True`；新增「归档 change 的 manifest 校验不因 tasks_hash 漂移而失败」+「active change 的 tasks_hash 漂移仍判失败」）。故 **「保留 2 + 退役 0」属实**。但 `design.md` D6 写「新增 **1** 条归档 Scenario」与 delta/tasks.md（「新增 2 条」）不符——**D6 计数错误，需改为 2**；理由: 逐条数出并与 delta 做文本归一化比对；来源: grill-fix-issue-232-archived-manifest-gate-2026-09-22-001
- **决策**: D5 的「spec 措辞说不做之事」比 design 承认的更严重——`head_sha == HEAD` 这条**在结构上不可满足**。证据：43 个归档 manifest **0 个**满足 `head_sha == HEAD`；且 manifest 自身所在 commit 必然改变 HEAD（实例如 `2026-09-14-subagent-concurrency-queue`：manifest `head_sha=ea22b65c`，而写入该 manifest 的 commit 是 `357cec0`；`fix-issue-110`：`8e732b4b` vs `6cd4451`）。即「生成 manifest」这个动作本身就把 HEAD 推离记录的 `head_sha`，除非把 manifest amend 进同一 commit。故 spec 正文保留「checker SHALL 验证 `head_sha` 匹配当前 `HEAD`」不是「先记债后补」，而是**把一个永不成立的断言固化成规格**；理由: 影响面实测 43/43 + 提交拓扑证据；来源: grill-fix-issue-232-archived-manifest-gate-2026-09-22-001
- **决策**: 「manifest 最后生成」纪律（D3）在当前流程下**是必要且充分的**，但仅靠文档不够——本 change 自身就是反例压力测试：本 change 的 `reviews/building-review.md` 一旦落盘，active 语境就会经 `_check_review_manifests` 的 `glob("*-review.md")` 循环（:1046-1050，**与 tasks 是否全勾无关**）调 `verify_review_manifest(archived=False)`，此时 `tasks_hash` 仍强校验；若审阅后再勾 tasks 或补证据行，active 门即红。故本 change 的 manifest 必须在其 `tasks.md` 全 `[x]` **之后**生成，且归档 move 之后不得再改 `tasks.md`/`reviews/building-review.md`（`report_hash` 仍校验）；理由: 代码路径实读 + 本仓库历史 15 条正是踩了这条；来源: grill-fix-issue-232-archived-manifest-gate-2026-09-22-001

## Open Questions

- **Q1**: 「归档语境跳过 `tasks_hash`」的可见性落在哪里、何时输出？（design D2「待 grill 确认」；硬约束：`verify_review_manifest` 签名与 `list[str]` 返回契约不变）

  **具体例子**: 现仓 `--check-archived` 有 43 个归档 change。若采用「每次归档校验都输出一行 note 且塞进返回值」，实跑 `/tmp` demo 得到 `ERROR: note: archived change — tasks_hash drift ignored` + **exit 1**——即本 change 想修的那 15 条红会一条不少地继续红，只是错误文案从 `tasks hash mismatch` 变成 `note: ...`（A′ 完全失效）。若改为「无条件 stderr 每 change 一行」，则每次 CI 刷出 43 行 `NOTE: archived ... tasks_hash skipped`，噪音会让真信号被淹没；而只在「确有漂移被抑制」时输出，又出现「无漂移时看不出 tasks_hash 到底校验没校验」。可机械验证的第三种落点：在 `scripts/check_openspec_artifacts.py` 的 `--check-archived` 分支（:1425-1435）**按归档 change 计数并汇总一行**，例如 `print("[archived manifest check] tasks_hash 已按归档语境跳过（N 个 change；其余 hash 仍校验）", file=sys.stderr)`，`verify_review_manifest` 保持纯 predicate。验证方式：`--check-archived` 仍 exit 0，且 stderr 恰含 1 行该汇总；`assert verify_review_manifest(..., archived=True) == []` 四条既有断言不受影响。

  **推荐答案**: 落点在**调用方**（`--check-archived` 分支，或 `_check_review_manifests` 内 `archived=True` 时），输出**汇总一行**到 stderr，不逐 change、不进返回值、不改签名。同时把 spec Scenario（delta :29-35）的措辞从「SHALL 在输出中说明归档语境跳过 tasks_hash」放宽为「SHALL 在归档校验输出中可见地说明 tasks_hash 已跳过（可为汇总行）」，避免 spec 逼出 43 行噪音。

- **Q2**: D3「manifest 在 tasks 最终化后生成」的落点与强度——只管文档，还是收尾脚本/CI 机械强制？

  **具体例子**: 取 `2026-09-14-subagent-concurrency-queue`。它的 manifest 记 `tasks_hash=sha256:4fcc…`，对应 `1a59099a`/`defc184e` 等历史版本；最终归档版多了一条纯新增 checkbox 行 → 现仓校验红。若只有文档纪律：下一个 agent 仍可能在「跑 `/review-loop` → PASS 写 manifest → 收尾再补一条 tasks 证据行」后归档，复现同样的 15 条红（A′ 会兜住，但 active 语境在收尾 PR 里会先红一次）。若上机械强制：可在 `/opsx:archive`（命令文件/收尾脚本）加一步「归档 move 前对每个 `reviews/*-review-manifest.json` 跑一次 `verify_review_manifest`（active 口径），任一 mismatch 则要求重绑 manifest 或补事件再归档」。注意这里有个**真实的先后顺序陷阱**：`docs/openspec-change-backlog.md` 的移除、spec sync 都是收尾动作，而它们本身**不改** `change_dir/tasks.md`，所以只要 manifest 在「最后一次 tasks.md 编辑之后」生成即可——CI 门（D4）兜得住「active 语境 tasks_hash 已强校验」，兜不住的是「manifest 生成后、归档前又改了 tasks.md 而该 PR 的 CI 因某种原因没跑到」。

  **推荐答案**: 文档纪律（`docs/development-guide.md` 收尾清单）+ spec 新增 Scenario **+ 本 change 的 CI 门（D4）三者都留**，但**不新增收尾脚本强制**（收益小、会引入新的写通道/事件面）。理由：active 语境 `tasks_hash` 已被 CI 强制，D4 又让归档语境有非静默降级，二者叠加已闭环；再加脚本层只会重复并增加归档摩擦。**若用户要求更强**，则最小增量是在 `/opsx:archive` 命令文件里加一条「归档前跑 `verify_review_manifest(..., archived=False)`」的手动步骤说明（非脚本）。

- **Q3**: D4 的 CI 步骤归属与参数——放 `validate` job 还是独立 job？要不要 `--skip-protected-paths` / `--skip-backlog`？

  **具体例子**: 现在 `validate` job 的 checker 步骤（`.github/workflows/ci.yml:57-66`）是 `--base-ref "${{ github.event.pull_request.base.sha }}" --require-base`。若新增一步写成 `/ `uv run python scripts/check_openspec_artifacts.py --check-archived`（不带 `--skip-*`、不带 `--base-ref`），则第二步会用**默认** `--base-ref master`：PR 检出（actions/checkout fetch-depth:0）只保证被检出 ref 与其历史，本地 `master` 分支通常不存在 → `git diff --name-only master --` 退出 128 → 打印 `WARNING: could not resolve base ref 'master' ...`（**仅警告不红**，因为第二步没带 `--require-base`）。同时它会**重跑**一遍 active change 检查与 backlog 检查（main() 全流程），与第一步重复报错。实测本工作区里 `master` 可解析（`git rev-parse --verify master` 成功），所以**本地跑不出这个警告，只有 CI 才会现形**——这正是要提前钉参数的原因。

  **推荐答案**: 放**同一个 `validate` job** 的新 step（不新开 job：复用已装好的 uv/依赖与 `fetch-depth: 0`，独立 job 要再装一遍 env，纯浪费）。该 step 显式写 `uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog`：`--skip-protected-paths` 避免 master 解析失败的无意义 WARNING（受保护路径检查已由第一步的 `--require-base` 版本负责），`--skip-backlog` 避免重复的 backlog 一致性检查。`fetch-depth: 0` **够**：`validate` job 已是 `fetch-depth: 0`（:13-17），git span 校验需要 `base_sha`/`head_sha` 的 commit 对象存在，且 `_verify_git_span` 本就是 best-effort（:219-226 找不到对象即跳过，不会误红）。不阻塞无关 PR：实测 A′ 后全仓 exit 0（9s），且历史归档目录的既有红正是本 change 要消掉的 15 条。

- **Q4**: D5——本 change 到底修不修 `head_sha == HEAD` 的口径债？spec 重写时「逐字保留」该句，还是顺手改措辞？

  **具体例子**: 两种写法对比。**保留**（design 现案）：delta 的「manifest 字段和 hash 校验」Scenario（:21-27）继续写「checker SHALL 验证 `head_sha` 匹配当前 `HEAD`」，而实现 `_verify_git_span`（`review_manifest.py:209-232`）从无此逻辑 → 规格继续声明一个不存在的检查，且**它在本 change 里被再次批准**。**改措辞**：把该 AND 子句改为与实现一致的「`base_sha` / `head_sha` 均为 commit，且 `diff_hash` 匹配 `git diff --binary <base_sha> <head_sha>` 的 sha256」，把「head_sha 应匹配当前 HEAD」的**意图**写入 `docs/known-debt.md`。风险对比：改措辞会让 spec 少一条「期望」，但 spec 与实现一致；保留则 spec 长期失真。**反向修实现不可行**：实测 43/43 归档 manifest 的 `head_sha` 都不等于当前 HEAD，且 manifest 自身提交必然移动 HEAD（`357cec0` vs `ea22b65c`），强制它会让全部历史 manifest 转红。

  **推荐答案**: **顺手改措辞**，不保留假句子。理由：本 change 已经整段重写该 Requirement（`openspec archive` 是整段替换，delta 就是变更后全文），此刻改是零边际成本；留到以后要再走一次 spec delta。同时把「本想校验 head_sha==HEAD，但该断言在『归档与实现同 PR + manifest 自提交』下不可满足」的结论记入 `docs/known-debt.md`，让意图不丢。若用户坚持最小改动面，**次优**是在 spec 该句后**显式标注当前未实现**——但不要什么都不写地逐字保留（那是把失真固化成规格）。

- **Q5**: D1 的接受口径——「15 条全部良性」是否只接受「非篡改」这一半，而明确接受「归档语境不再能发现 checkbox 行内的描述级篡改」这一残余风险？（并确认 A′ 相较于其他候选的取舍）

  **具体例子**: 取 `fix-issue-110` 的真实 diff：`- [x] uv run pytest -q 全量通过（1813 passed，7 skipped）` → `（1814 passed，7 skipped）`，以及新增整行 `- [x] 审阅收尾：新增 test_reset_removes_session_from_store…`。这些**全在 checkbox 行内**，若有人把某条任务描述改成与事实不符的表述，tasks_hash 在归档语境下**不再报警**。另外两种「保住检查力」的候选已实测排除：①「忽略勾选」归一化 → 剥离后只剩 8–18 行标题（假绿）；②「绑定 head_sha 处的 blob」→ 实测 **32 过 / 10 红 / 1 个 head_sha 无 blob**（manifest 用工作区而非提交时刻的 tasks.md 计算哈希，10 条仍红）→ 同样不可行。

  **推荐答案**: 接受。理由：`spec_hash` 与 `report_hash`（15 条全过、且 A′ 后仍校验）才是「审阅了什么」的实质证据，`tasks.md` 在归档语境是活文档；三种替代方案已实测排除，A′ 是唯一不制造假绿又能让门诚实的解。**附加要求**：把「已接受残余风险 = 归档语境不检测 tasks.md 描述级编辑」一句写进 spec 的降级理由段与 `docs/known-debt.md`，避免后人误以为归档 tasks 仍受保护。

## 风险

- **既有测试会被 A′ 打红（已实测，非推测）**：`tests/test_openspec_artifact_checker.py::test_verify_review_manifest_archived_path`（:1663-1706）在 A′ 下 FAILED。tasks.md 未列该文件的改写任务 → 实现者可能被迫临时删断言，**恰好抹掉「归档态仍检测 spec/report 漂移」的判别性对照**。必须在 tasks.md 增列：改写该测试为「归档态 tasks 漂移不报错 + 归档态 spec/report 漂移仍报错」，并由新用例承担对照。
- **note 进返回值 = A′ 失效（已实测）**：见 Confirmed Decision 3 与 Q1 的 `/tmp` demo。若实现时图省事写成 `return errors + [note]`，本 change 的端到端验收（`--check-archived` exit 0）会直接失败——好在 tasks.md 已列该端到端项，属可自曝的失败模式；但**必须**在实现前钉死落点，否则容易先红后乱改。
- **`check_phase_done.py:276` 是未被提及的第三个调用方**：design 的 Context 称调用方「两处」（checker :1050 + `--check-archived` 归档分支），实际是 `scripts/check_openspec_artifacts.py:1050` 与 `scripts/check_phase_done.py:276`（后者恒以 `archived=False` 调用，A′ 不影响其行为）。结论不变（签名不能动），但 design 的事实描述需更正，否则实现者可能漏检该文件的回归。
- **`--check-archived` 的循环对「无 `Change Type` 的归档目录」整段跳过**（`scripts/check_openspec_artifacts.py:1428-1433`）：实测 90 个归档目录中 4 个（均为 `2026-06-21-*` 老世代）因 `parse_change_type` 返回 None 被 `continue`。当前这 4 个都没有 `reviews/`，**不构成盲区**；但这是「归档校验覆盖面」的隐含上界（老世代目录即使有 manifest 也不会被查）。建议在 design 的风险表补一句记录，不必本 change 处理。
- **D6 计数错误会误导实现者核对**：D6 说「新增 1 条」，delta/tasks 说「新增 2 条」，实际是 2。归档前若照 D6 的 1 去核对 Scenario 数会出现假差异，浪费一轮。
- **CI 第二 step 的 `--base-ref master` 警告只在 CI 现形**：本地 `master` 可解析（实测 `git rev-parse --verify master` 成功），本地跑 `--check-archived` **看不到**该 WARNING。若按 design 现文「与既有 `--base-ref` 步骤并列」实现而不加 `--skip-protected-paths`，CI 日志会出现一个来源不明的 base-ref 警告（虽不红），容易在后续被误读为门禁退化。按 Q3 推荐钉参数即可消除。
- **本 change 自身的归档闭环无死锁，但有两条前提**：归档后 `change_dir` 变为 `archive/<date>-<id>`，其中 `specs/` 随目录一并移动（实测 88/90 归档目录含 `specs/`，且 43 个归档 manifest 的 `spec_hash` 全过）→ `spec_hash` 不失真、`report_hash` 因 `building-review.md` 随目录移动亦不失真；`tasks_hash` 由 A′ 兜住。**前提 A**：A′ 必须与归档在同 PR 落地，否则归档后 `--check-archived` 仍红（这正是本 change 的目标）。**前提 B**：本 change 的 manifest 必须在 `tasks.md` 全勾**之后**生成——因为 active 语境（本 PR 的 CI）仍强校验 `tasks_hash`，而 `reviews/building-review.md` 一旦落盘就会触发 :1046-1050 的循环（与 tasks 是否全勾无关）。**归档 move 之后**再改 `tasks.md` 或 `building-review.md` 会分别被 A′（跳过）与 `report_hash`（仍校验 → 红）处理：故归档后**不要**再编辑该 change 的 `reviews/building-review.md`。

## User Confirmation

- **Q1**: 用户答复：**调用方汇总一行 stderr**——`verify_review_manifest` 保持纯 predicate（note 不塞返回值、签名不变）；在 `scripts/check_openspec_artifacts.py` 的 `--check-archived` 分支按归档 change 计数并输出一行汇总；spec Scenario 措辞放宽为「SHALL 在归档校验输出中可见地说明 `tasks_hash` 已跳过（可为汇总行）」，避免逐 change 噪音。；确认时间: 2026-09-22
- **Q2**: 用户答复：维持「文档纪律（`docs/development-guide.md`）+ spec 新增 Scenario + CI 门（D4）」三者叠加，**不新增收尾脚本强制**（与 grill 推荐一致，用户原指令的 D3 落点即为文档纪律，未要求脚本层强制）。；确认时间: 2026-09-22
- **Q3**: 用户答复：**同 `validate` job 新增 step**，参数钉死为 `--check-archived --skip-protected-paths --skip-backlog`（消除 CI 才现形的 base-ref WARNING 与重复检查）；不新开 job。；确认时间: 2026-09-22
- **Q4**: 用户答复：**顺手改措辞**——delta 里把该 AND 子句改为与实现一致的「`base_sha`/`head_sha` 均为 commit，且 `diff_hash` 匹配 `git diff --binary <base_sha> <head_sha>` 的 sha256」，删掉「匹配当前 `HEAD`」；原始意图（本应校验 `head_sha == HEAD`，在「归档与实现同 PR + manifest 自提交」下不可满足）写进 `docs/known-debt.md`。；确认时间: 2026-09-22
- **Q5**: 用户答复：**接受**「15 条全部良性」的结论（非篡改已复算证实），并把残余风险（A′ 放弃在归档语境检测 `tasks.md` 的任何编辑，含 checkbox 行内的描述级编辑）**同时写进 spec 降级理由段与 `docs/known-debt.md`**。；确认时间: 2026-09-22
