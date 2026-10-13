# Grill 设计追问：witnessloop-adoption

## Reviewer

- **run id**: `grill-witnessloop-adoption-2026-10-13`（独立零记忆设计评审 subagent；不继承任何开发上下文；仓库只读，唯一写入 = 本文件）
- **时间**: 2026-10-13
- **对象**: `openspec/changes/witnessloop-adoption/{proposal.md, design.md, tasks.md, specs/dev-workflow-gate/spec.md, workflow-events.jsonl, README.md}` + 同期新建的当前规格 `openspec/specs/dev-workflow-gate/spec.md` + `docs/openspec-change-backlog.md` 两节
- **权威输入**: GitHub issue `Xingkai98/asterwynd#305` 全部评论（含动态探测与更正评论）
- **方法**:
  1. 逐份读 change 文档 + 当前规格，核 `platform-gate` 先例的**立项/实现两个 commit**（`cf57a91` / `f7e912b`）；
  2. 读 witnessloop v1 源码（`/home/happy/witnessloop`，只读）：`evidence.py` / `contract.py` / `checkcmd.py` / `guardcmd.py` / `policy.py` / `constants.py` / `manifestcmd.py` / `.github/workflows/gate.yml` / `plugin/hooks/*`；
  3. **实测**：在 `/tmp/wl-sim{,2}` 隔离副本（`rm -f .git && git init -q`，不碰被审 worktree）建 asterwynd 形态仓，跑 5 种形态的 `witnessloop check`；
  4. 跑本仓 `npx @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
     凡标「实测」者均为本机真实命令输出；凡引 `文件:行号` 者为本次读取。

---

## Confirmed Decisions

- **决策**: 新能力域 `dev-workflow-gate` 在**立项时**就落进 `openspec/specs/`，**先例成立、做法正确**；「以**未发生**为规范对象的 Requirement」在本仓**确有先例**。
  - **理由**: 作者引用的 `platform-gate` 先例经核对为**同一形态**——它的当前规格就是在**它自己的立项 commit** 里建的，且当时就写了负向占位 Requirement。这同时回答了「有没有先例」的两个子问题（先例存在 ✓、负向规范对象有先例 ✓）。
  - **来源**: `git show --stat cf57a91`（`platform-gate 立项` commit 同一提交内新增 `openspec/changes/platform-gate/specs/platform-gate/spec.md` **与** `openspec/specs/platform-gate/spec.md`）；`git show cf57a91:openspec/specs/platform-gate/spec.md`（含 `### Requirement: platform-gate 当前为预留能力域` + `系统 SHALL NOT 声称已经提供平台闸门配置脚本…`）；`scripts/check_openspec_artifacts.py:703`（`_check_current_spec_mapping`）+ `:1368`（调用点）——delta capability 无对应当前规格即报错；另有 `openspec/specs/tui/spec.md:5,9` 与 `openspec/specs/code-intelligence/spec.md:11` 两条同型负向 Requirement（bootstrap commit `a6a2496`）。
  - **但见 CQ6**：先例的**后半段**（实现时退休占位）本 change 缺了。

- **决策**: 必须 `witnessloop init --policy <seed>` 一次写成完整 policy，不能沿用出厂 policy —— **成立**。
  - **理由**: 出厂 `require_change_for` 是 **8 条目录 glob 的元组**（`src/**`、`lib/**`…），对 asterwynd 的 `agent/`/`scripts/`/`web/` 零命中；而 `code_hits` 是 `building` 与 `grill-adversarial` 两条 stage 判定的**共用**触发。实测：仅在 diff **既触及 `require_change_for` 又触及 change 目录**时才追加这两条（我的 /tmp 实测中，只改 `agent/x.py` 不动 change 目录 ⇒ `0 个 change 目录`，两条 stage 判定不出现）。
  - **来源**: `src/witnessloop/constants.py:43-52`（`DEFAULT_REQUIRE_CHANGE_FOR`）、`checkcmd.py:77`（`code_hits = _code_hits(...)`）、`checkcmd.py:96`（`if code_hits:`）、`checkcmd.py:169-176`（`_code_hits` docstring「什么算代码的唯一口径」）、本次 `/tmp` 实测输出。

- **决策**: `protected_paths` **不列** `openspec/changes/archive/**` —— **成立，且原因比 design 写的更紧**。
  - **理由**: witnessloop 的归档豁免只认 **`R100` 纯改名**（状态码 + 无内容改动三重条件）。实测两种形态：**(a)** `git mv` 单独成一个 commit ⇒ `check：通过 ✓`（7 变更文件、0 change 目录）；**(b)** `git mv` 与同 commit 内一处内容改动并用 ⇒ 3 条红（`change 目录不存在` + `缺少 review manifest` + `无 stage=grill 的 manifest`）。
  - **来源**: `src/witnessloop/contract.py:38-55`（`is_archive_move`，`change.status != "R100"` 即 False）、`contract.py:58-86`（`changed_change_ids` 排除 move 两端）、本次 `/tmp` 实测 (a)/(b) 输出。

- **决策**: 「归档天然安全」的前提是 **move 两端都被排除** —— **成立**，但附带一条 design 未写的**操作约束（见 CQ3）**。
  - **来源**: `contract.py:58-86`；`/tmp` 实测 (a) `check：通过 ✓`。

- **决策**: 「本地守卫能力退步」的陈述**属实且方向正确**（asterwynd 解析 Bash，witnessloop 只看 `Write|Edit`）。
  - **理由**: witnessloop `guard` 只判「写目标是否命中 `require_change_for` 且当前 change 的 grill 证据是否完备」，其 hook matcher 确为 `Write|Edit`；而 asterwynd 现守卫的 matcher 含 `Bash`。
  - **来源**: `src/witnessloop/guardcmd.py:16-17`（诚实边界自陈）、`guardcmd.py:71-79`+`:105-106`（只判 `require_change_for` 命中）、`plugin/hooks/hooks.json`（`"matcher": "Write|Edit"`）、`scripts/workflow_guard.py:5`（`"matcher": "Write|Edit|Bash"`）。

- **决策**: 立项态的机械门禁是**绿的**（无既存违规）。
  - **来源**: 本次实跑 `openspec validate --all --strict` ⇒ `30 passed, 0 failed`；`uv run python scripts/check_openspec_artifacts.py` ⇒ `OpenSpec artifact checks passed`。

- **决策**: `## Open Questions` 三条（Q1 事件类型名 / Q2 `require_change_for` 面 / Q3 `specs/**` 是否 protected）**本身成立且正确**——它们确为「项目配置」而非上游缺能力，且 `Q1` 的推荐 (a) 经实测可让本 change 自身的 `openspec/specs/**` 与 backlog 写入免红（本 change 的 `workflow-events.jsonl` 已含 `current_spec_synced` / `backlog_updated` 两条事件）。
  - **来源**: `openspec/changes/witnessloop-adoption/workflow-events.jsonl:2-3`；`src/witnessloop/policy.py:30-52`（三字段均 policy 可覆写）；issue #305 更正评论「三条决策全部是『项目配置』」。
  - **但见 CQ4 / OQ1-OQ3**：这**不是**完整的三条——至少还缺两个该问的配置/设计决策。

---

## Code-Resolved Questions

- **CQ1（原被 design 定性为「纯机械修正」）→ code-resolved：`review_manifest_glob` 不是问题所在；真正的不匹配是 manifest 的**字段 schema**，不是文件名。**
  - **结论（实测 + 读码）**：asterwynd 的 manifest 生成器写 `"phase"`，witnessloop 要求 `"stage"`，且 asterwynd 的 manifest **没有** `author_run_id` / `report_path` 两个必填字段。⇒ 把 glob 改成 `reviews/*-manifest.json` **一条红都消不掉**。
  - **实测证据**：在 `/tmp/wl-sim` 放一份真实 asterwynd 形态 manifest（`phase: "building"`、无 `stage`/`author_run_id`/`report_path`），`witnessloop check` 出 **6 条**：
    `manifest 缺字段：stage, author_run_id, report_path` · `reviews/building-review.md 孤儿报告` · `reviews/grill-design.md 孤儿报告` · `无 stage=grill 的 manifest（现有 stage：?）` · `无 stage=grill-adversarial 的 manifest` · `无 stage=building 的 manifest（现有 stage：?）`。
    换成 witnessloop 形态（有 `stage`/`author_run_id`/`report_path`）后，**「缺字段」与「无 stage=building」两条消失**，`现有 stage` 由 `?` 变为 `building`。
  - **来源**: `agent/workflow/review_manifest.py:93-104`（写 `"phase"`、无 `author_run_id`/`report_path`；路径 `reviews/<phase>-review-manifest.json`，见 `:65-69`）vs `src/witnessloop/constants.py:95-105`（`REVIEW_MANIFEST_REQUIRED_FIELDS` = stage/reviewer_run_id/**author_run_id**/base_sha/head_sha/tasks_hash/spec_hash/report_hash/**report_path**）、`contract.py:240-248`（缺字段即 finding 并 early-return）、`contract.py:173-182` + `:185-219`（`report_path` 缺失 ⇒ 绑定集为空 ⇒ **每个** `reviews/*.md` 都成孤儿）、`evidence.py:197-208`（按 `doc["stage"]` 匹配）。
  - **连带影响**：① `design.md:63-69` 的 Decision 2 定性错误（这不是机械修正，是**迁移工程**）；② `design.md:120-124` 的 Decision 7「已知红」范围错误——不是只有 `add-minimal-tui-runtime-view` 一条，而是**所有用 asterwynd 生成器产 manifest 的 change（含本 change 自己）**；③ 与 Non-Goal「`agent/**` 一行不改」**直接冲突**（生成器就在 `agent/workflow/review_manifest.py`）。详见 **OQ2**。

- **CQ2 → code-resolved：glob 放宽**会**造成「影子遮蔽」，design 的「无害」判断不成立。**
  - **结论（实测 + 读码）**：`stage_manifest_findings_in_change` 用 `matching[0]`（按路径字典序取**第一份**同 stage manifest）；而 `validate_review_manifests` 会**逐份**校验所有匹配文件。⇒ 一是「多份同 stage 时只有字典序第一份被当证据、其余静默忽略」（可**错绑**到悬空报告），二是「任何一份坏 manifest 都会独立报红」（**宁多勿漏**，非无害）。
  - **实测证据**：在 change 的 `reviews/` 同时放 `aaa-manifest.json`（`stage=building`，`report_path` 指向不存在的文件）与合法的 `building-manifest.json`，`check` 报 `stage=building 的 manifest 的 report_path 解析不到报告`，即**坏的那份因字典序在前而顶替了合法的那份**。
  - **来源**: `src/witnessloop/evidence.py:197-210`（`matching` + `matching[0]`）、`contract.py:127-149`（`for manifest_path in manifests: _validate_one(...)` 逐份 + `bound` 集合并）、`contract.py:185-219`（孤儿规则）；`/tmp` 实测 RUN B。
  - **对 asterwynd 的实际含义**：因为 CQ1 已使 asterwynd 的 manifest 不含 `stage`（恒不匹配任何 stage），这条**在阶段 A 不单独致命**，但它证伪了 `design.md:69` 的推理（「glob 只负责找到候选文件、stage 名由内部字段承载」），因此不能拿它当作「不用管命名差异」的理由。

- **CQ3 → code-resolved：归档 move 必须是一个**独立的纯改名 commit**，否则新门禁会红。**
  - **结论（实测）**：把「归档 move」与「同一 commit 内的内容改动」并用，git 记作 `A`/`D`（非 `R100`）⇒ `is_archive_move` 为假 ⇒ `changed_change_ids` 把**旧 active 路径**当 change id ⇒ 三条红。**asterwynd 的收尾（`tasks.md:74` Z.5）若把归档 move 与其它改动并入同一 commit，就会踩这条。**
  - **来源**: `contract.py:38-55`（`R100` 硬条件）、`contract.py:58-86`；`/tmp/wl-sim2` 实测 (b)：`change 目录不存在（diff 里出现了它的文件，但目录不在工作树中）` + `缺少 review manifest` + `无 stage=grill 的 manifest`。

- **CQ4 → code-resolved：Decision 1 的 policy 片段与 Q1 的事件类型表**自相矛盾**。**
  - **结论**：`design.md:51` 的 `protected_paths` = `["openspec/specs/**", ".witnessloop/**"]`（= witnessloop 出厂默认），**不含** `docs/openspec-change-backlog.md` / `docs/known-issues.md` / `docs/known-debt.md`；而 `design.md:57-58` 的 Q1 推荐把 `backlog_updated` / `protected_artifact_explained` 填进 `protected_write_event_types`。⇒ 这两个事件类型在 policy 里**没有对应的受保护路径**，是**死配置**（列了也不会被消费）。
  - **来源**: `design.md:49-60` vs `scripts/flow-policy.json`（现有受保护集含 `docs/known-debt.md` / `docs/known-issues.md` / `docs/openspec-change-backlog.md`，`event_types` 含 `backlog_updated` / `protected_artifact_explained`）；`checkcmd.py:206-215`（`_protected_writes` 先按 `protected_paths` 命中、才查事件）。
  - **含义**：`protected_paths` 是 asterwynd 现有受保护集的**真子集**。阶段 A 无损失（旧 checker 仍在跑），但这是迁移路径上一个**未登记的静默收窄**——见 **OQ3**。

- **CQ5 → code-resolved：引用的 witnessloop 行号大体准确，两处需修。**
  - **不准确 1**：`design.md:41` 与 `proposal.md:93` 引 `src/witnessloop/constants.py:40`，实际 `DEFAULT_REQUIRE_CHANGE_FOR` 在 **`:43`**（`:40` 是上方注释行）。
  - **不准确 2**：`proposal.md:93` 把出厂值写成**单串** `src/lib/app/apps/packages/server/cmd/internal`，实际是 **8 条 glob 的元组**（`constants.py:43-52`）。`specs/dev-workflow-gate/spec.md:11` 的 8 条目写法才对——同一事实在 change 内**两种写法并存**，是一致性瑕疵。
  - **核对无误**：`constants.py:11`（`DEFAULT_GATE_REF`）、`:27`（`ADOPTER_TESTS_PATH`）、`checkcmd.py:77/96/169`、`guardcmd.py:16-17`、`gate.yml:29/47/83`、`cli.py:49-54`。
  - **诚实记录属实**：`.dev/reference-repos.txt` 确不存在（`proposal.md:101` 的自述准确）；`cli.py` 的 `--policy` 确为「轻校验、语义由 `check` 兜底」。

- **CQ6 → code-resolved：新建的当前规格里有**两条 Requirement 会被本 change 自己的实现证伪**，而 delta 没有退休它们的步骤。**
  - **结论**：`openspec/specs/dev-workflow-gate/spec.md:15` 写 `系统 SHALL NOT 声称已经接入 witnessloop：仓库中 SHALL NOT 存在 .witnessloop/policy.json … .github/workflows/witnessloop.yml …`，`:22` 写 `.github/workflows/ 下 SHALL 只有 ci.yml`；而本 change 的阶段 A（`tasks.md:32` A.3.1、`:33` A.3.2）**恰好创建** `.witnessloop/policy.json` 与 `.github/workflows/witnessloop.yml`。delta 只有 `## ADDED Requirements`，`tasks.md:71` 的 Z.2 只说「把 **ADDED** Requirements 合并进」⇒ 占位 Requirement 会**存活**并与实现自相矛盾。
  - **先例给出的正确形态**：`platform-gate` 的实现 commit `f7e912b` 明确「**同步 current spec（覆盖占位，SHALL 目标语言）**」，把 `openspec/specs/platform-gate/spec.md` 从 28 行重写为 65 行——**占位 Requirement 在现行规格里已不存在**（`openspec/specs/platform-gate/spec.md:9` 起直接是「合入平台闸门」，无「预留能力域」条目）。
  - **来源**: `openspec/specs/dev-workflow-gate/spec.md:15,22`、`openspec/changes/witnessloop-adoption/tasks.md:71`、`git show --stat f7e912b`（`openspec/specs/platform-gate/spec.md | 65 ++-`）、`openspec/specs/platform-gate/spec.md`（HEAD 全量）。
  - **修法**：Z.2 增一步「退休占位 Requirement」（delta 用 `## REMOVED Requirements`，或实现时按 platform-gate 先例直接覆盖当前规格），否则归档后规格自相矛盾。

---

## Open Questions

> 本节是**补充的**停轮项——编号从 **Q4** 起，与 design 既有的 Q1/Q2/Q3（事件类型名 / `require_change_for` 面 / `specs/**` 是否 protected，**三条仍然成立**，见 Confirmed Decisions 末条）连续、不重号。三个新问题均**不可由代码定**（都依赖用户取舍），每条附具体例子 + ➡️ 推荐。
>
> 格式说明：条目用 `- **Q<n>**` 列表项（**不是** `### Q<n>:` 小标题）——本仓 checker 的 `_extract_open_question_indexes`（`scripts/check_openspec_artifacts.py:816-841`）只认行首 `Q<n>`/数字，`### Q<n>:` 形式实测抽取为 **0 条**（见风险 R7）。用列表项才能让 `## User Confirmation` 门真正生效。

- **Q4（`--test-command` 测试执行点该填什么——design 三条里没有这一条，是真的缺）**
  - **背景**：`tasks.md:32`（A.3.1）只要求「取本仓现有 CI 的测试口径、必须真实可跑、不得留哨兵」，但**本仓 CI 的测试口径是 4 件事，不是 1 条命令**；而 witnessloop 的执行点是**一行**、在**另一个 job** 里跑。
  - **具体例子**：本仓 `validate` job 是四步——`uv run pytest -q`（`ci.yml:48`）+ 编码 warn-as-error 变体（`ci.yml:62-74`：`PYTHONWARNDEFAULTENCODING=1`、`-W error::EncodingWarning:agent/web/benchmarks`、只跑 5 个文件）+ `openspec validate --strict`（`:77`）+ `check_openspec_artifacts.py`（`:88`）。而 witnessloop 的执行点由 `sh -c "$CMD"` 跑（`gate.yml:100`），所在 job **只做** checkout + `setup-uv`（`gate.yml:40-45`），**没有** `uv sync --extra dev`、**没有** `playwright install chromium`。⇒ 若填 `uv run pytest -q`：能跑（`uv run` 会自建环境），但 `tests/web_tests/test_workflow_graph_browser.py` 等浏览器用例会**静默 skip**——正是 `ci.yml:41-45` 注释所说「等于白跑」的形态；编码门也不会执行。
    - **选 (a)**：只填 `uv run pytest -q`。→ 覆盖主回归面；浏览器/编码两类信号**不进** witnessloop 执行点。
    - **选 (b)**：填 `uv run pytest -q && PYTHONWARNDEFAULTENCODING=1 uv run pytest -q -W "error::EncodingWarning:agent" …`（把编码门串进去）。→ 信号更全，但一行变长、失败归因变差，且仍缺浏览器依赖。
    - **选 (c)**：不启用执行点（`tests.disabled: true`）。→ **否决**：等于放弃 witnessloop 的测试门，与接入目的背离。
  - **➡️ 推荐 (a)**：填 `uv run pytest -q`，把「编码门 / 浏览器用例 / openspec validate / artifact checker 不进 witnessloop 执行点」写成**已知边界**记入阶段 B 报告。理由：与 `gate.yml` 的 job 环境匹配，失败归因最清晰；其余三类信号在本仓 `validate` job 里**继续存在**，阶段 A 不丢信号。

- **Q5（manifest schema 迁移归谁——CQ1 的决策面）**
  - **背景**：`check` 认 `stage`/`author_run_id`/`report_path`，asterwynd 生成器写 `phase` 且缺后两个字段（CQ1）。不改生成器，用 asterwynd 工具链产的 manifest **永远过不了** `check`。
  - **具体例子**：阶段 B（`tasks.md:57` B.2）要在真实小需求的 change 里落 grill / grill-adversarial / building **三份**审阅证据。用 asterwynd 现有工具，`/review-loop` 只能产 `reviews/building-review-manifest.json`（`phase: "building"`，无 `stage`）⇒ `check` 必出 CQ1 那 6 条红（我的 /tmp 实测就是这个结果），**跑不绿**；那样阶段 B 的「值不值得真打开」就失去对照基线（没有「绿」的一侧）。
    - **选 (a)**：改 `agent/workflow/review_manifest.py` 让它输出 `stage`/`author_run_id`/`report_path`。→ 与本 change Non-Goal「`agent/**` 一行不改」**冲突**，但一劳永逸。
    - **选 (b)**：阶段 B **改用 witnessloop 自带的 `manifest build`**（`manifestcmd.py:33-`，支持 `--stage`/`--report`/`--reviewer-run-id`/`--author-run-id`）产三份 manifest，旧生成器本 change 不动。→ 不动旧件；代价是阶段 B 流程与 asterwynd 现有 `/review-loop` 分叉（须写明）。
    - **选 (c)**：不解决，把阶段 A 出口判据从「跑绿」降级为「跑出 findings 即算」，schema 迁移整体推给阶段 C。→ 阶段 B 变成「看红」，判断依据弱。
  - **➡️ 推荐 (b)**：阶段 B 用 `witnessloop manifest build` 产 witnessloop 形态三份 manifest（不动旧件），把 (a) 登记为阶段 C 迁移任务。理由：与「一行不改旧件」的硬边界一致，且能真正跑出「绿」的一侧作对照。它同时回答了「`grill-design.md` 这个文件名行不行」——`report_path` 是自由字段，且 witnessloop 对 grill 报告正文的判据（`## Confirmed Decisions` / `## User Confirmation`）与本仓现有形状**同构**（/tmp 实测里这两条正是它检查的项），故文件名无碍。

- **Q6（`protected_paths` 是否补齐 asterwynd 现有受保护集——CQ4 的决策面）**
  - **背景**：`design.md:51` 的 `protected_paths` 是 asterwynd 现有受保护集的**真子集**（缺 backlog、known-issues、known-debt），导致 Q1 的 `backlog_updated`/`protected_artifact_explained` 成死配置。
  - **具体例子**：某 PR 改 `docs/known-debt.md`（本仓现为 `event_explained` 档，需 `protected_artifact_explained` 事件）。
    - **选 (a) 补齐**（`protected_paths` 加上 `docs/known-issues.md` / `docs/known-debt.md` / `docs/openspec-change-backlog.md`）：本地 checker 绿 + witnessloop 也绿（事件类型已在 Q1 表里）；两侧一致，阶段 A 零额外动作（本 change 的 backlog 事件已存在）。
    - **选 (b) 不补**：witnessloop 侧不判这三条 → 阶段 A 也没事（旧 checker 仍管），但两侧**分叉**会进阶段 B 的分叉清单，且「旧 checker 下掉后这三条无人管」这个**静默缺口**被提前埋下——正是 `design.md:195`（Q3）自称要避免的形态。
  - **➡️ 推荐 (a)**：补齐三条路径。理由：与 Q3 推荐 (a) 的理由**同构**（「冗余但一致」，代价为零、堵住未来静默缺口）；若不补，请把 Q1 的事件类型表**同时**砍到只留 `current_spec_synced`（否则留死配置误导后续读者）。

---

## 风险

- **R1（最高）— 阶段 B 结构上跑不绿**：CQ1 + OQ2 未决时，用 asterwynd 工具链产的 manifest 必被 `check` 判 6 条红，阶段 B 拿不到「绿」的对照。**这不是执行细节，是本 change 能否产出「值不值得真打开」判断的前提**。→ 先答 OQ2。
- **R2 — 两个守卫并存的行为**：design 只在 `design.md:205`（R3）谈了「能力**变窄**」（丢 Bash 面），**完全没有覆盖「多出一个 block 源」这一面**。实测到的两侧语义：asterwynd 守卫以 `exit 2` 拦（`scripts/workflow_guard.py:615,628,638,654,667`），witnessloop `guard.sh` 把 guard 的 `1` 映射成 `exit 2`（`plugin/hooks/guard.sh:38-41`），**两者都是 CC 的 block 约定、matcher 都含 `Write|Edit`** ⇒ 同一 `Write` 上会**并集式**拦截（任一 exit 2 即拦）。**design 未写**：Claude Code 对「settings 的 hook + plugin 的 hook 同时匹配」的合并/串行/并行语义、报错归属、以及「witnessloop guard 因缺 grill 证据拦下本仓**不**受管路径之外的写」这类**新增**拦截面。→ **待实测**：装好 plugin 后，在一条 `agent/**` 写路径上（该 change 无 `stage=grill` manifest）触发 Write，观察是否两个 hook 都执行、拦下时提示归属哪个守卫；把结果写进阶段 B 报告。这条**必须**在阶段 A 的验收里补上（现在 A.1.1 的 5 条判据完全没有它）。
- **R3 — 归档 move 的提交粒度**：CQ3 实测证明「move + 同 commit 内容改动」会红。`tasks.md:74-75`（Z.5/Z.6）未规定「归档 move 必须是独立纯改名 commit」。→ 在 tasks 里补一条硬约束，否则本 change 自己的收尾就可能踩。
- **R4 — 本 change 自身在 known-red 清单里缺席**：`design.md:120-124`（Decision 7）与 `proposal.md:77` 只点名 `add-minimal-tui-runtime-view`，但本 change 自己（阶段 A 落地后的 PR）同样缺 `reviews/` 下 witnessloop 形态 manifest、且 `code_hits` 为空（diff 不触 `agent/**`/`scripts/**`/`web/**`）。→ 把它一并写进已知红清单，避免阶段 A 验收时把**自己的**红误判为「配置没生效」。
- **R5 — 存在一个「无强制」的形态窗口（design 已部分自认）**：阶段 A 不勾 required ⇒ `gate / check` 全红也**不拦**（`design.md:203` R1 已写）。**但 spec delta 还有一个更细的过度断言**：`specs/dev-workflow-gate/spec.md:36` 写「`master` 上的 PR SHALL 不运行 witnessloop 的 `gate / check` job（GitHub 只对 head 含该 workflow 的 PR 运行它）」——这句在**本 change 合入前**成立（workflow 只在 feature 分支），但**本 change 的产物就是要把它合入 master**（`tasks.md:74` Z.5 归档 + 合入）⇒ 合入之后，源于 master 的新 PR**都会**跑 `gate / check`。该断言须收敛为「**既有 in-flight PR** 不受影响」，否则规格在合入当天即被自己的实现证伪。
- **R7 — （附带发现，非本 change 引入）本仓 grill 报告的「停轮确认门」在 `### Q<n>:` 形式下**静默失效**：`_extract_open_question_indexes`（`scripts/check_openspec_artifacts.py:816-841`）只认**行首**的 `Q<n>`／数字，对 `### Q2: …` 这类小标题式条目抽取结果为 **0 条**。实测：归档 `2026-10-07-grill-flow-hardening/reviews/grill-design.md`（用 `### Q2:`/`### Q3:` 写 Open Questions，且有 `## User Confirmation` 记录）抽取为 `openQ: []`、`confirmed: ['Q2','Q3']` —— **未确认项无从谈起，门等于没开**；同为归档的 `2026-10-03-tool-result-lifecycle` 用 `- **Q1**…` 列表项则正确抽出 8 条。⇒ 本报告因此**改用列表项**（见 Open Questions 节首注）。建议另立债项：要么收紧 checker 兼容小标题形式，要么在 `docs/development-guide.md` 明写「Open Questions 必须用列表项」。
- **R6 — plugin 安装的三处未核实面**（`.claude/` 被 gitignore ⇒ 仓库内无从核实）：① plugin 的 `grill`/`review-loop` 命令名与仓内 `.claude/commands/{grill.md,review-loop.md}` 是否同命名空间冲突（plugin 名为 `witnessloop`，CC 通常命名空间化为 `/witnessloop:grill`，但**未实测**）；② `plugin/hooks/guard.sh:32` 调的是 **PATH 上的 `witnessloop`**（`witnessloop guard --root … --path …`），若机器上是**另一份 `uv-tool` 装的** witnessloop，其版本可能与 policy schema 漂移——与 design 声称的「本地层独立」无关，属**版本耦合**；③ 装/卸/升级步骤只写进 `docs/development-guide.md`（`tasks.md:41` A.4.3），无机械门禁。→ 三项都列入阶段 A 验收的实测项。
