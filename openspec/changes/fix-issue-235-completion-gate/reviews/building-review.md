# Building Review: fix-issue-235-completion-gate (Round 2)

## Reviewer

- run id: r2-6b1c9f24（独立零记忆 subagent，未继承开发上下文；结论仅来自实读代码 / 实跑输出 / change 文档）
- 时间: 2026-09-23
- base: `4424f54882179ef1ec53d2eaa1a7d373280b91fb`（origin/master） head: `396bd44d3725737f5aae866c99a1e3c94198b7c4`
- 本轮针对: R1（run `3ce1e878`）的 4 个 issue（M1 / low-1 / low-3 / info）
- 审阅方法（全部实跑，作者自述一律不作依据）：
  - 5 个 `git init` 探针仓库（`/tmp/p235_{normal,missing,empty,prose,docsmissing}`）复现「归档目录缺/空/散文式 tasks.md」，用 **CI 第一步真实参数** `--base-ref <sha> --require-base` 端到端跑 `scripts/check_openspec_artifacts.py`
  - 8 个 low-1 边界探针（`/tmp/low1_*`）覆盖 `archive/.gitkeep`、`archive/notes.md`、真正的无日期目录、既有非规范目录内新增文件、嵌套目录等
  - 3 个**真实 clone**（`/tmp/pmclean`、`/tmp/pmfut`、早前的 `/tmp/pm3`，非 `cp -a`）模拟「归档 move 后」「本 PR 合入后未来 PR 触碰 docs/known-debt.md」「origin/master 不可解析」三种状态
  - 变异测试 4 条（M1 回退 / low-1 回退 / low-1 过度收敛 / 去掉自己的 protected 事件），`cp` 备份 + `diff -q` 核对还原，`git status` 干净
  - 边界探针：M1 的 docs 豁免、all-post-merge tasks.md、checkbox 语法变体、`--skip-protected-paths` 是否关掉 M1
  - 实跑 `pytest tests/test_openspec_artifact_checker.py`（118 passed）、`tests/agent/workflow/ + test_workflow_guard.py + test_flow_policy.py`（165 passed）、全量 `uv run pytest -q`（6 failed，全为已知环境失败）、OpenSpec strict validate（30/30）、`--check-archived --skip-protected-paths --skip-backlog`（归档段 exit 0）
  - 93 个历史归档的 tasks.md 证据形态全量扫描

> **关于 HEAD 变动与并发未提交改动**：进入审阅时 HEAD = `177041d`，审阅期间作者并发提交了 `396bd44`（修 backlog 重复标题 + 加锁，未触碰 `scripts/`）。本报告**以 `396bd44` 为准**。审阅末期，作者又在工作区留下**未提交**的改动（`scripts/check_openspec_artifacts.py` +45/-15、`tests/…` +108/-18），内容正是对本报告两条 medium 的修复——属并发在途修复，**尚未进入被审阅的 HEAD**，故不计入 verdict；但我独立验证了它的效果（见文末「并发在途修复」节）。

## Verdict

**CHANGES_REQUESTED**

理由：R1 的 **4 项修复本身全部成立**——M1 的三形态端到端报错、low-1 收敛且不 fail-open、low-3 有自己的事件且测试判别、info 已写入开发指南，四者均有实跑证据（见下）。**但修复新增的第 5 条测试 `test_own_change_explains_protected_artifact_with_its_own_event` 是一个必炸的 landmine**：它硬编码 `openspec/changes/fix-issue-235-completion-gate/`（active 路径）且无存在性保护，而 `docs/known-debt.md` 内容永久留在 master 上。后果是——**本 change 自己在归档时刻**（AGENTS.md 强制的归档 move）该测试即 `FileNotFoundError` 转红，CI `pytest` 必挂；且此后**任何**触碰 `docs/known-debt.md` 的未来 PR 也会因 `origin/master...HEAD` 的 diff 非空而触发同一条红。这是新引入的中等缺陷（red CI，不是 fail-open），按 Verdict 规则判 CHANGES_REQUESTED。另有一条 M1 边界（全部标 post-merge、零勾选仍可关闸）在其修复范围内未覆盖。

> **重要**：审阅末期我观察到作者已在工作区写下**未提交**的修复，同时覆盖上述两条 medium 与一条 low；我独立复跑验证其确实成立（见文末「并发在途修复」节）。若按该草稿提交，本报告的两条 medium 即消解，verdict 可转 PASS（届时需以含该提交的新 head 重新确认）。

## R1 Issues 复核

- **M1（medium，fail-open）— 已修复**。
  证据（CI 第一步真实参数，探针仓库 `--base-ref <sha> --require-base`）：
  - `/tmp/p235_missing`（无 tasks.md）→ `ERROR: 2026-09-23-demo-gate: tasks.md 缺失或无任何 checkbox 行 ……`，**EXIT=1**
  - `/tmp/p235_empty`（0 字节 tasks.md）→ 同上，**EXIT=1**
  - `/tmp/p235_prose`（散文式，零 checkbox）→ 同上，**EXIT=1**
  - `/tmp/p235_normal`（正常归档，`- [x]` + `- [ ] (post-merge)`）→ `OpenSpec artifact checks passed`，**EXIT=0**
  - `/tmp/p235_docsmissing`（docs-only 归档，无 tasks.md）→ `passed`，**EXIT=0**（M1 只作用于非 docs，边界正确）
  - `--skip-protected-paths --skip-backlog` 下 M1 仍报错（EXIT=1）——门不在可关的分支里。
  单测侧直接调用 `_check_archived_completion_gate`：缺/空/散文三形态全部报 `tasks.md 缺失或无任何 checkbox 行`。实现位置 `scripts/check_openspec_artifacts.py:1065`（`_tasks_missing_evidence`）+ `:1608`（非 docs 判定）。
  **但**：修复只堵住了「无 checkbox 行」这一面，`tasks.md` **有** checkbox 行、却**全被 `(post-merge)` 标掉、零勾选**时门仍静默通过（`all_tagged_none_checked` 探针：`missing_evidence=False`、`untagged=[]`、`gate_errors=[]`）。见 Issues M2。

- **low-1（假阳性）— 已修复，且未修成 fail-open**。
  证据（`/tmp/low1_*`，`_new_archive_dirs_since_base` 实跑）：
  - `archive/.gitkeep` + `archive/notes.md`（归档根下普通文件）→ `non_conforming=[]` ✅（R1 的假阳性已消）
  - `archive/foo/proposal.md`（真正无日期目录）→ `non_conforming=['openspec/changes/archive/foo/proposal.md']` ✅（仍报错）
  - `archive/2026-9-23-foo/`（月份未补零）→ 仍进 `non_conforming` ✅（正则边界未松）
  - `archive/2026-09-23-bar/reviews/building-review.md` → `new_dirs=['2026-09-23-bar']` ✅（正常归档未受影响）
  - 既有非规范目录内新增文件（`archive/foo/NEW.md`）→ 仍进 `non_conforming`（R1 记录的「不受 base 树条件约束」仍在，属既有严格化，非新增缺陷）
  实现位置 `scripts/check_openspec_artifacts.py:108`（`ARCHIVE_DIR_SEGMENT_RE`）+ `:1512`（收敛守卫）。**注意其收敛面**：`archive/<seg>/` 只要有目录段就评命名，故 `archive/unknown-1.0/file.md` 这类非 change 目录会被标为命名不合规（当前语料 0 命中），见 Issues L1。

- **low-3（证据污染）— 已修复（本 change 侧）+ 机制弱点已记账**。
  证据：`git show HEAD:openspec/changes/fix-issue-235-completion-gate/workflow-events.jsonl` 第 2 条 = `seq 2, protected_artifact_explained, artifact_path=docs/known-debt.md, reason_len=179, approved_by=human` ✅；`docs/known-debt.md`「既存机制弱点」小节已写入（rglob 全仓命中的描述准确）。新测试判别性**已实测**：`cp` 备份事件日志 → 删掉本 change 的 `protected_artifact_explained` 行 → `test_own_change_explains_protected_artifact_with_its_own_event` **1 failed** → 还原 `diff -q` 一致。**但该测试本身有致命脆性**，见 M1′（列在 Issues）。

- **info（写法提示）— 已落地**。
  证据：`git show HEAD:docs/development-guide.md` 第 269 行「**标记必须紧邻复选框**（中间只允许编号/粗体）。行尾追加的写法**不**被识别，例如 `- [ ] 收尾：关 issue。(post-merge)` ✗、`- [ ] 5.5 收尾 (post-merge)` ✓」；第 271 行补了「`tasks.md` 必须存在且含 ≥1 条 checkbox 行」。方向为 fail-closed（行尾追加会报错不静默），与 `POST_MERGE_TAG_RE` 口径一致。

## Tasks Verification

### R1 修复小节（`tasks.md:65-85`）逐条核对——5 条 `[x]` 全部真实落地

- [x] `tasks.md:69` **M1**：`_tasks_missing_evidence`（`:1065`）+ 归档门接线（`:1608`）②三条回归测试（`:2536` / `:2555`）**真实存在且判别**（变异 1 转红 3 条）。
- [x] `tasks.md:74` **low-1**：`ARCHIVE_DIR_SEGMENT_RE`（`:108`）+ 守卫（`:1512`）②两条回归测试（`:2568` / `:2587`）**真实存在且判别**（变异 2 转红 1 条；变异 4「过度收敛」转红 2 条，说明两侧都锁住了）。
- [x] `tasks.md:79` **low-3**：自己的事件（`seq 2`）+ 回归测试（`:2604`）**真实存在且判别**（变异 3 转红）。
- [x] `tasks.md:84` **info**：开发指南两段 **真实存在**（`docs/development-guide.md:269` / `:271`）。

### 前序实现任务（`tasks.md` 实现/测试/文档节）——逐条抽查，无「`[x]` 无实现」

- [x] `tasks.md:5-6` 设计追问证据 — `reviews/grill-design.md` 存在（R1 已核，本轮未变）。
- [ ] `tasks.md:17-28`（仍未勾，属收尾前正常）— 实现**均存在**：归档点求值 `:1691-1698`、`_new_archive_dirs_since_base:1464`、`ARCHIVE_PATH_RE:103`、非规范进 errors `:1639-1643`、`--require-base` 消费 `:1635-1638`、`_check_archived_completion_gate:1545`、building-review 只做存在性 `:1596-1604`、A′ 参数 `:529`/`:739` + 三处判据 `:612`/`:763`/`:782`、`check_change` 一行未动（`git diff origin/master...HEAD -- scripts/check_openspec_artifacts.py | grep check_change` 只命中注释 `:257`）。
- [ ] `tasks.md:32-47` 测试项 — 全部存在于 `tests/test_openspec_artifact_checker.py`；本轮实跑 118 passed。
- [ ] `tasks.md:52-58` 文档 — `AGENTS.md` 触发点改挂归档点 + `(post-merge)` 段；`docs/development-guide.md`；`docs/known-debt.md` 残余面；spec delta；backlog。

### 新增第 6 条测试（`tasks.md` 之外的 `396bd44`）

- [x] `test_backlog_has_no_duplicate_section_headings`（`:2640`）— 真实存在，锁住立项提交误伤的 `### 3. X### 3. X`。属合理附带修复（本 change 自己弄脏的 backlog 行）。

**未勾且未实现**：无。

## Issues

- **medium** `tests/test_openspec_artifact_checker.py:2604-2637`（`test_own_change_explains_protected_artifact_with_its_own_event`）— **本 change 归档即转红，且会误伤未来触碰 `docs/known-debt.md` 的 PR**。测试第 `:2614` 行硬编码 active 路径 `openspec/changes/fix-issue-235-completion-gate`，并**无存在性保护**地读 `…/workflow-events.jsonl`（`:2625`）；而 `:2617` 的触发条件是 `git diff --name-only origin/master...HEAD -- docs/known-debt.md` 非空——该文件内容永久留在 master 上，故**任何后续 PR 只要再动一次 `docs/known-debt.md`**，条件即为真。实测（真实 clone，非 `cp -a`）：
  - `/tmp/pmclean`：`git mv` 本 change 到 `archive/2026-09-23-…`（AGENTS.md 强制的归档收尾步）后 → `FileNotFoundError: …/openspec/changes/fix-issue-235-completion-gate/workflow-events.jsonl`，**1 failed**。
  - `/tmp/pmfut`：把本 change 合入 master（含归档 move）后，再模拟一个**无关未来 PR** 追加一行 `docs/known-debt.md` → diff 非空 → **同样 FileNotFoundError 1 failed**。
  - `/tmp/noremote235`（`origin/master` 不可解析，如某些 CI 检出形态）→ 该测试 **silently skip**（`1 skipped`），判别力归零。
  **期望**：触发条件改为「本 change 自己的 `workflow-events.jsonl` **在本树**存在」时才有意义地断言，且路径要**同时**支持 active 与 archive 两形态（例如 `change_dir` 取 `openspec/changes/<id>`，若不存在再回退到 `openspec/changes/archive/*-<id>`，两者都缺则跳过或直接失败），并去掉对 `origin/master` 硬编码（它只在开发者本地存在，CI 上是 `github.event.pull_request.base.sha`）。当前写法把「一次性证据校验」写成了「永久地在 master 上必炸的测试」。
  **（工作区已有未提交修复，见我独立复跑验证。）**

- **medium** `scripts/check_openspec_artifacts.py:1608`（`_tasks_missing_evidence` 判定过窄）— M1 只堵住「tasks.md 无 checkbox 行」，**未堵住「有 checkbox 行但零勾选」**。实测：`tasks.md` 内容仅 `- [ ] (post-merge) 只有 closeout 项` 时，`_tasks_missing_evidence=False`、`_untagged_unchecked_tasks=[]`、`_check_archived_completion_gate` 返回 `[]`（静默通过）——即「把所有任务都标成 post-merge、一个都不勾」仍可关闸，与 M1 描述的「靠不勾 checkbox 自我关闸」是同一类结构性绕开。该形态在历史归档中**真实存在**：93 个归档里有 **8 个** tasks.md 有 checkbox 行但零勾选（`2026-07-08-multi-agent-dev-workflow`、`2026-07-09-add-persistent-cross-session-memory`、`2026-07-09-add-semantic-code-search`、`2026-07-09-improve-agent-execution-foundation`、`2026-07-12-add-context-builder-architecture`、`2026-07-12-add-context-compression-strategies`、`2026-07-12-implement-context-injection-pipeline`、`2026-07-12-improve-system-prompt-architecture`）。本 PR 的实际语料不受影响（本 change 的 tasks.md 有大量 `[x]`），故非阻塞。**期望**：非 docs 归档在 `_tasks_missing_evidence` 之外补一条「≥1 条 checkbox 被勾选」的下限（即复用 `_tasks_all_complete` 语义的 `checked > 0` 部分），或至少写入 `docs/known-debt.md` 残余面清单（当前 D7/known-debt 只列了「完全不归档」「无日期前缀」两条）。**（工作区已有未提交修复，见我独立复跑验证。）**

- **low** `scripts/check_openspec_artifacts.py:1608`（对称性）— 非 docs 新增了「缺 tasks.md 即报错」，但 **docs-only 归档缺 `tasks.md` 一律豁免**（实测 `/tmp/p235_docsmissing` EXIT=0、直接调用返回 `[]`）。这在「docs 无实现」口径下自洽；但需注意 `tasks.md` 存在时 docs 归档的未勾任务**仍会**报错（实测 `docs + untagged unchecked` → 报错），即 docs 归档缺 tasks.md 放行、有未勾 tasks.md 报错，是一条**隐含的「删掉 tasks.md 即可关闸」**路径。触发条件极窄（仅 docs + 同时需要删文件、且归档路径须在 `docs/` 下），且与 R1 记录的 8 条历史形态不冲突，不阻塞；建议在 known-debt 提一句或把 docs 也纳入「缺 tasks.md 报错」的统一口径。**（工作区已有未提交修复，见我独立复跑验证。）**

- **low** `scripts/check_openspec_artifacts.py:108`（`ARCHIVE_DIR_SEGMENT_RE` 收敛面）— 收敛后凡 `archive/<seg>/…`（有目录段）即评命名，故 `archive/unknown-1.0/file.md`、`archive/scratch/x` 这类**非 change 目录**仍会被报「归档目录命名不合规」。当前语料 0 命中，且方向 fail-closed（会报错不静默），属可接受的严格化；仅记录边界。

## Test Results

| 命令 | 结果 |
|---|---|
| `uv run pytest -q tests/test_openspec_artifact_checker.py` | **118 passed**（R1 时 111 → +7：M1×1 + 参数化散文/空×2 + low-1×2 + low-3×1 + backlog×1） |
| `uv run pytest -q tests/agent/workflow/ tests/test_workflow_guard.py tests/test_flow_policy.py` | **165 passed** |
| `uv run pytest -q`（全量） | **6 failed, 2957 passed, 10 skipped** in 458.52s → 6 条**全为已知环境失败**（见下） |
| `npx @fission-ai/openspec@1.4.1 validate --all --strict` | **30 passed, 0 failed** |
| `uv run python scripts/check_openspec_artifacts.py`（`--base-ref <merge-base> --require-base`） | exit 1：`fix-issue-235-completion-gate: review manifest missing`（在途 change 未生成 manifest 的**预期**红，对应未勾任务 `tasks.md:63`） |
| `… --check-archived --skip-protected-paths --skip-backlog`（真实仓库 93 归档） | exit 1：`fix-issue-235-completion-gate: review manifest missing`（文件名来自 **active** 目录；把 active 目录移出后**归档段 exit 0** + stderr「tasks_hash 已按归档语境跳过（45 个）」）。R1 记录的 exit 0 是旧 HEAD 的观测，**非本 change 引入** |
| `R1 关注测试`：`test_partial_change_does_not_require_building_review` | **1 passed**（未反转） |

**已知环境失败（非本 change 引入）**——与已知清单吻合：

- `tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir, test_malformed_git_file_falls_back_to_scan}` — pristine master 已复现。
- `tests/agent/tools/test_factory_sandbox_wiring.py::…::test_docker_backend`、`tests/agent/tools/test_sandbox_backends.py::…::test_docker_backend_available` — 无 docker。
- `tests/web_tests/test_workflow_graph_browser.py::{test_collapsed_group_shows_aggregated_status, test_gestures_pan_after_pinch_release}` — 浏览器 flaky（本次无 chromium）。
- 本次 tree-sitter Java/Kotlin 用例 **未**失败（可能被 skip），不改变结论。

**变异测试 4/4**（`cp` 备份 → 改码 → 跑测试 → 还原，`diff -q` 核对，`git status --porcelain` 干净）：

| 变异 | 结果 |
|---|---|
| 回退 M1（去掉 `_tasks_missing_evidence` 分支） | `test_archived_gate_flags_missing_tasks_md` + `…without_checkbox_lines[2 参数]` 红（3 failed / 115 passed） |
| 去掉 `ARCHIVE_DIR_SEGMENT_RE` 守卫（low-1 回退） | `test_archived_gate_does_not_flag_plain_file_under_archive_root` 红（1 failed / 117 passed） |
| low-1 过度收敛（无日期目录静默丢弃 = fail-open） | `test_archived_gate_reports_non_conforming_archive_dir` + `…still_flags_non_dated_archive_directory` 红（2 failed / 116 passed） |
| 删掉本 change 自己的 `protected_artifact_explained` 事件 | `test_own_change_explains_protected_artifact_with_its_own_event` 红（1 failed） |

## 并发在途修复（未提交，不计入 verdict）

审阅末期工作区出现未提交改动（`git status`：`M scripts/check_openspec_artifacts.py`、`M tests/test_openspec_artifact_checker.py`；`reviews/building-review.md` 的 `M` 是我自己的写入）。我未对它做任何写入，只读地取证并**独立复跑验证**：

- **M1′ landmine**：新增 `_change_dir_in_any_form(repo_root, change_id)`（active 命中优先，否则 glob `archive/*-<change_id>`，都没有返回 None），测试改为「两形态都不存在才 skip」，**删掉了 `origin/master...HEAD` 依赖**。我把该草稿 overlay 到干净 clone 后双向实跑：active 形态 **1 passed**；执行 AGENTS.md 强制的归档 move 之后 **1 passed**（对照 HEAD 上同一状态是 `FileNotFoundError` 1 failed）；该状态下整份 checker 测试 **121 passed**。
- **M2（零勾选下限）**：`_tasks_missing_evidence` 改为「无 checkbox 行 **或** 零个 `[x]` 即 True」，与 `_tasks_all_complete` 的 `checked > 0` 口径对齐；配两条测试（正例 `test_archived_gate_flags_all_post_merge_zero_checked` + 反例 `test_archived_gate_passes_when_at_least_one_task_checked` 防误红）。
- **low（docs 对称性）**：归档门对 docs 也要求 `tasks.md` 证据（注释引用语料 0/93 无假阳性）；配 `test_archived_gate_docs_only_missing_tasks_md_is_flagged`。
- 工作区实跑：`pytest tests/test_openspec_artifact_checker.py` → **121 passed**（相对 HEAD 的 118 新增 3 条，且原 `…without_checkbox_lines` 参数化用例在改动后仍断言「tasks.md 缺失或无任何 checkbox 行」，与新错误文案一致、未失效）。

**提请作者注意**：这些改动在被审阅的 HEAD（`396bd44`）上尚不存在，审判以 HEAD 为准；提交后本报告两条 medium 与一条 low 即消解，但需以新 head 重新确认（且 `test_own_change_explains_protected_artifact_with_its_own_event` 在归档提交落地后仍应保持绿——这正是 M1′ 要求的行为）。

## 结论

**CHANGES_REQUESTED**，两条中等项需修，其余全部通过。

R1 的四项修复我都用实跑证据确认**真的成立**，而且没有把修复做成新的 fail-open：M1 在缺/空/散文三形态上用 CI 第一步真实参数都报了红、正常归档与 docs-only 归档都仍绿、`--skip-protected-paths` 关不掉；low-1 的收敛既消掉了 `archive/.gitkeep` 假阳性，又保住了「真正的无日期目录仍报错」（变异证明两侧都锁住）；low-3 有了本 change 自己的 `protected_artifact_explained` 事件，判别性测试去掉事件即转红；info 落进了开发指南。核心功能（issue #235 的两条绕开路径）也未被破坏。

保留意见有两条。第一条是**新引入的必炸测试**：`test_own_change_explains_protected_artifact_with_its_own_event` 硬编码 active 目录路径 + `origin/master...HEAD` 触发条件，而 `docs/known-debt.md` 的内容永久留在 master 上——结果是本 change 一执行 AGENTS.md 强制的归档 move，该测试就 `FileNotFoundError` 转红，CI 的 `pytest` 步必挂；此后任何触碰该文档的未来 PR 也会被同一条件误伤（真实 clone 双向实测，且 `origin/master` 不可解析时它还会静默 skip）。这条测试的意图是对的，但写法把一次性证据校验做成了长期 landmine，必须改成 active/archive 双形态 + 存在性保护。第二条是 M1 的边界仍偏窄：「有 checkbox 行但零勾选（全部标 post-merge）」仍能静默关闸，历史归档里这种 tasks.md 真实存在 8 份——按本 change 自己立的标准（静默无门必须消灭或显式记账），应补「≥1 条被勾选」的下限或把该面写进 known-debt。附带两条 low（docs 归档删 tasks.md 的隐含关闸路径、`archive/unknown-1.0/` 类非 change 目录被评命名）当前语料均 0 命中，记录待办即可。

需要说明的是，审阅末期我观察到作者已在工作区写下覆盖这三条的**未提交**修复，并独立复跑验证其成立（active/archive 双形态都绿、零勾选被拦、docs 口径统一，121 passed）。因此本轮的 CHANGES_REQUESTED 是**针对被审阅 HEAD `396bd44` 的状态**；若作者把在途草稿按现状提交，该判决即应随之翻为 PASS（以含该提交的新 head 重新确认为准）。
