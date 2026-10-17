# Tasks: 轮次口径对齐 witnessloop——有界批次 × 20 轮上限（round-model-align）

> **本 change 无运行时行为改动**：只改规则文档、规格与 `scripts/check_openspec_artifacts.py`
> 的三处提示字符串（判定逻辑一行不改）。因此测试是**文档守卫 + 既有门禁回归**，不是运行时单测。
>
> **前置门（第 0 节）不完成不得开工**：grill 由独立零记忆 subagent 执行，产出
> `reviews/grill-design.md`；随后跑设计阶段对抗闭环，产出 `reviews/grill-adversarial.md`。
>
> **结算说明（收尾次序）**：本文件在**最后一个内容提交**上落定，随后执行机械收尾：
> **① 归档 move（独立提交）→ ② witnessloop manifest 用归档目录名、asterwynd manifest 用裸 id 重建 → ③ 机械门复核**。
> closeout 类任务（合入后动作）标 `(post-merge)`。

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 `grilling` skill（独立零记忆 subagent）对 `design.md` 做设计追问，产出结构化决策记录到 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含**同行裸** `来源:`；`## Open Questions`、`## User Confirmation` 小节无条件存在）。
- [x] 0.2 逐项核对 grill 的 7 个维度，重点是第 7 条（触发与门禁）：witnessloop 恒要求 `grill`，本 change 改 `scripts/**` ⇒ 另触发 `grill-adversarial` 与 `building`，共三份 witnessloop manifest；确认建立 change 目录 + 三份 manifest 后能判绿。
- [x] 0.3 跑**设计阶段对抗闭环**（与 `/review-loop` 同构但审设计而非代码）→ `reviews/grill-adversarial.md`；按批次模型执行：开批只列 medium+、全修、只验证、验证期新问题 deferred；最多 20 个已收口轮，超限 ⇒ 超上限 `BLOCKED` + 「建议推倒重开（revise the design）」。
- [x] 0.4 **停轮检查**：确认 `grill-design.md` 没有需要用户拍板的 Open Question，且设计对抗环的出口是 `PASS`（或 `BLOCKED` + 成因 + 用户明确裁决继续）。两者都满足 ⇒ 进入实现；任一不满足 ⇒ 停下报告，不代拟答案。`BLOCKED` 本身 SHALL NOT 作为写码许可。
- [x] 0.5 把 grill 与对抗闭环的结论回填 `design.md` 的 `## Pre-Implementation Review`。
- [x] 0.6 把用户已拍板的四个参数（轮 = 非空 medium+ 批次、20 上限、medium+/low 口径、两环共用）记入 `reviews/grill-design.md` 的 `## User Confirmation`。

## 1. 先写红测试（TDD）

- [x] 1.1 新增 `tests/test_round_model_alignment.py`：显式 allowlist 扫描 `AGENTS.md`、`README.md`、`README_EN.md`、`docs/requirements-process.md`、`docs/interview-script/questions/Q14-dev-process.md`、两份当前规格、`scripts/check_openspec_artifacts.py`。
- [x] 1.2 断言 **per-file 映射**：`AGENTS.md` 覆盖轮定义 + 批次冻结 + deferred + 20 + 三出口；两份规格覆盖轮定义 + 批次冻结 + deferred + 20 与收口确认 + 三出口 + 两环共用；README / README_EN 覆盖批次模型 + 20 + 建议重开；requirements-process 覆盖轮定义 + 20 + 两环共用；Q14 覆盖轮定义 + 20 + 三出口。
- [x] 1.3 断言旧口径词表不在规范面：`无轮数上限`、`最近两轮`、`3 轮封顶`、`轮数封顶`、`round cap`、`no fixed round limit`、`no round limit`、`再审直到收敛`、`until convergence`、`收敛即停`；历史归档与历史 review 不在扫描面，本 change delta 的 `REMOVED/Reason` 解释段豁免。
- [x] 1.4 断言 `scripts/check_openspec_artifacts.py` 三处**新**提示文案在场、**旧**提示文案不在场；判定逻辑未变由 building review 逐行核对 + witnessloop 证据承担（不用对 `origin/master` 的 diff 做长期断言）。
- [x] 1.5 跑指定测试确认**红**，把原始输出记入 `reviews/building-review.md` 的测试节。
- [x] 1.6 变异验证：临时把 `AGENTS.md:104` 改回旧口径，指定测试至少 1 failed；恢复后复绿（变异不提交）。

## 2. 规则与文案改动

- [x] 2.1 `AGENTS.md:18`（设计阶段闭环）改为批次模型。
- [x] 2.2 `AGENTS.md:104`（实现后闭环）改为批次模型，并写清 20 上限、三出口、`CHANGES_REQUESTED` 不是出口。
- [x] 2.3 `README.md:148` + `README_EN.md:148`（同一句流水线图，必须同改）。
- [x] 2.4 `docs/requirements-process.md:45`（实现后闭环）与 `:189`（设计阶段闭环）。
- [x] 2.5 `docs/interview-script/questions/Q14-dev-process.md:13` 与 `:56`；`:17` 的 #99 历史案例保留原文。
- [x] 2.6 `scripts/check_openspec_artifacts.py:1139`、`:1623`、`:1640` 三处提示字符串改为批次模型。**只改字符串，判定逻辑一行不改。**

## 3. 规格

- [x] 3.1 `specs/dev-workflow-state-machine/spec.md` delta：`## REMOVED Requirements` 删除旧「终止条件为收敛，而非轮数上限」；`## MODIFIED Requirements` 把「开发流程精简为 OpenSpec 主干 + 强制审阅闭环」的两处「再审直到收敛」改为批次模型；`## ADDED Requirements` 新增「审阅闭环的轮次模型为有界批次，最多 20 个已收口轮」（含轮定义、批次冻结、验证禁提新问题、deferred、low 重分类、severity、20 上限与收口确认、三出口、两环共用 + frontier 豁免、两侧机械判据不新增正文解析，以及 Scenario）。
- [x] 3.2 `specs/change-documentation/spec.md` delta：`## MODIFIED Requirements` 覆盖 `Pre-implementation design grilling`，把 `no fixed round limit` / `until convergence` 改为批次模型，其余正文与 Scenario 逐字保留。
- [x] 3.3 把两份 delta 施加进 `openspec/specs/dev-workflow-state-machine/spec.md` 与 `openspec/specs/change-documentation/spec.md`（**当前规格同步**），记前后 Requirement 计数，并写 `current_spec_synced` 事件。
- [x] 3.4 用 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 验证 → 记原始输出。

## 4. 验证

- [x] 4.1 `uv run pytest -q`：**4498 passed / 2 failed / 9 skipped**；两条失败均为 `tests/agent/memory/test_persistent.py::TestFindScopeRoot` 的既有 `/tmp` 环境问题（本机 `/tmp` 本身是 git 仓库，`_find_scope_root` 走到 `/tmp`），与本 change 无关；新增文档守卫 28 passed。
- [x] 4.2 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 0 errors（最终读数在 manifest 产出之后）。
- [x] 4.3 `git grep` 复核：规范面再无旧口径；历史归档与历史 review 报告不回填。
- [x] 4.4 同步本地入口（gitignored、不进 PR）：`/home/happy/my-agent/.claude/commands/review-loop.md` 改为批次模型 + 20 上限 + deferred + 三出口；`/home/happy/my-agent/.claude/commands/grill.md` 至少补齐设计阶段对抗环 / frontier 豁免 / 20 上限。逐项登记「已改 / 未改」。

## 5. 实现后独立审阅闭环

- [ ] 5.1 跑 `/review-loop round-model-align`，产出 `reviews/building-review.md` + reviewer run；asterwynd 形态 manifest 只在 7.5 的最终 revision 上生成。按批次模型执行：开批只列 medium+、全修、只验证、验证期新问题 deferred；`CHANGES_REQUESTED` 是轮内状态，不是出口；最多 20 个已收口轮。
- [ ] 5.2 收口后清理中间轮产物，避免孤儿报告。

## 6. witnessloop 证据与出口判据

- [ ] 6.1 在**所有内容提交之后**（含 backlog 清理），用 `witnessloop manifest build` 产三份 witnessloop 形态 manifest（`grill` / `grill-adversarial` / `building`），`report_path` 覆盖 `reviews/` 下每一份 `.md`。
- [ ] 6.2 `witnessloop check --root . --base origin/master --head HEAD`（v1.7.0）→ `check：通过 ✓`（0 项）。必须在内容提交之后跑。
- [ ] 6.3 CI 侧复核：PR 的 `gate / check` 判绿；`validate` / `benchmark-gate` / `windows-platform` 照跑。

## 7. 收尾（归档前必须完成）

- [ ] 7.1 `docs/openspec-change-backlog.md`：登记本 change，随后在**证据产出之前**移除；配 `backlog_updated` 解释事件。
- [ ] 7.2 确保 `workflow-events.jsonl` 事件齐全（`change_created` 已有 seq 1）：`change_created` / `backlog_updated`（登记）/ `current_spec_synced` × 2 / `backlog_updated`（移除）/ `change_archived`，`approved_by` 非空。
- [ ] 7.3 结算 `tasks.md`：勾掉全部已完成项；closeout 类未完成项标 `(post-merge)`。未勾且未标 `(post-merge)` 的任务必须为 0 条。
- [ ] 7.4 归档 move 前：`git add openspec/changes/round-model-align/reviews/` 并确认 `git ls-files` 包含 `grill-design.md`、`grill-adversarial.md`、`building-review.md`（否则 `git mv` 不会搬走未跟踪报告）；随后手工 `git mv` 到 `openspec/changes/archive/2026-10-17-round-model-align/`，归档 move 独立提交（不跑 `openspec archive`；若同一提交含新增报告，则不是纯 rename，如实记录）；归档后核对归档目录包含三份报告与两套 manifest。
- [ ] 7.5 归档后重建 manifest：**witnessloop 三份**用归档目录名（`--change 2026-10-17-round-model-align`，解析 `archive/<name>`）；**asterwynd 形态**用**裸 id**（`workflow_state.py review-manifest --change round-model-align`，走归档回退；CLI 拒绝日期前缀，见 `scripts/workflow_state.py:375-379`），manifest 写入归档目录。
- [ ] 7.5b 归档提交后重跑 `witnessloop check --root . --base origin/master --head HEAD` → `check：通过 ✓`，留原始输出。
- [ ] 7.6 **合入方式**：本 PR SHALL 用 `--merge` 合入，SHALL NOT squash（否则 manifest 的 `head_sha` 不再是祖先，日后触及本 change 目录的 PR 会判红）。

## 8. 合入之后（结构上无法在本 PR 内完成）

- [ ] (post-merge) 8.1 在 issue #305 追加 comment：轮次口径已镜像到 witnessloop 的批次模型（20 上限 + deferred + 三出口），规格已同步。**issue 保持 OPEN**。
- [ ] (post-merge) 8.2 合入后确认：active change 目录不再存在、backlog 干净、本地 `master` 已快进；并复核 `master` 的 required 仍为 `["gate / check"]`。
- [ ] (post-merge) 8.3 复核本地入口 `/home/happy/my-agent/.claude/commands/review-loop.md` 已同步（4.4 的最终确认）。

## 验收清单（对应 spec）

- [x] V1 规范面能逐条查到新模型七要素；不再有旧口径（历史归档与历史 review 报告除外）。
- [x] V2 `dev-workflow-state-machine` 规格的 Requirement 覆盖：轮定义、批次冻结、验证禁提新问题、deferred、medium+ 全修、low/nit 登记须理由、20 上限与超限建议重开、三出口、两环共用 + frontier 豁免、机械门禁不新增正文解析。
- [x] V3 `change-documentation` 规格不再写 `no fixed round limit` / `until convergence` 作为终止条件，改为引用批次模型。
- [x] V4 OpenSpec strict validate 通过（30 passed）；artifact checker 0 errors；`uv run pytest -q` 为 4498 passed / 2 failed（两条均为 `/tmp` 环境既有失败，与本 change 无关）。
- [ ] V5 三份 witnessloop manifest + asterwynd building manifest 齐全且 `gate / check` 绿。
- [x] V6 本地入口已同步（`review-loop.md` 与 `grill.md` 均已改为批次模型；grep 无旧口径）。
- [ ] V7 PR 已 `--merge` 合入；归档为纯 move；issue #305 已留完成 comment 且保持 OPEN。
