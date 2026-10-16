# Tasks: 阶段 C 翻开关的记录与规格对账（stage-c-required-switch）

> **本 change 无代码面**（见 `design.md` Decision 5）：diff 只落在 `openspec/**` 与 `docs/**`。因此没有「测试先行」一节，也没有 benchmark smoke——不排它们**是判据的结果，不是漏排**。
>
> **前置门（第 0 节）不完成不得开工**：grill 由独立零记忆 subagent 执行（`/grill`），产出 `reviews/grill-design.md`；随后按 issue #298 跑设计阶段对抗闭环，产出 `reviews/grill-adversarial.md`。
>
> **停轮口径**：本 change 记录的是**已经拍过板且已经落地**的决定（issue #305 阶段 C）。设计里**不应有需要用户拍板的 Open Question**；被挑战出来的待定项必须用仓库内事实（`gh api` 输出、`--verify` 输出、规格行号）当场判掉。**若确实冒出一个只有用户能拍的问题，就停下来写清楚留给他，绝不代拟答案、也不用占位文本糊过去。**

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 `grilling` skill（独立零记忆 subagent）对 `design.md` 做设计追问，产出结构化决策记录到 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含**决策 / 理由 / 来源**三字段）。
- [x] 0.2 逐项核对 grill 的 7 个维度，**重点是第 7 条（触发与门禁）**：本 change 自身的写操作会不会被 witnessloop 的 `building` / 受保护写入门禁拦下（它只改 `openspec/**` 与 `docs/**`，不触达 `require_change_for`）；以及它建立 change 目录后能否让 `gate / check` 判绿。
- [ ] 0.3 跑**设计阶段对抗闭环**（与 `/review-loop` 同构但审设计而非代码）→ `reviews/grill-adversarial.md`；对 Decision 1（`process` + `exempt` 的档位选择）与 Decision 3（REMOVED 的爆炸半径）做专门挑战，能由仓库事实判定的当场判掉、移出停轮队列。
- [ ] 0.4 **停轮检查**：确认 `design.md` 没有需要用户拍板的 Open Question。若无 ⇒ 直接进入实现；若有 ⇒ **停下来报告**，不开 PR。
- [ ] 0.5 把 grill 与对抗闭环的结论回填 `design.md` 的 `## Pre-Implementation Review`。
- [x] 0.6 **grill 记录的格式契约**（`design.md` Decision 11，v1.7.0 实测）：`reviews/grill-design.md` SHALL 含 `## Confirmed Decisions`（每条决策块内有**同行裸** `来源:`）、`## User Confirmation`（**无条件存在**，零 Open Question 也要有）、以及与逐字标题一致的 Open Questions 小节。用 v1.7.0 的 `grill_evidence_findings` 实测应为 **0 findings**。

## 1. 规格同步（本 change 的实质改动）

- [ ] 1.1 `openspec/changes/stage-c-required-switch/specs/platform-gate/spec.md`：写 delta——`## MODIFIED Requirements` 覆盖重写 `### Requirement: 合入平台闸门`（required 由两项改为唯一 `gate / check`，Scenario 由「benchmark-gate 为 required check」改为 witnessloop `gate / check` 为唯一 required + 三 job 照跑）与 `### Requirement: 平台闸门复用 GitHub branch protection 语义`（Scenario「平台配置走 PR review」里的 CI 列举）；`## ADDED Requirements` 增 `### Requirement: 降级为非必过的检查仍须运行`。
- [ ] 1.2 `openspec/changes/stage-c-required-switch/specs/dev-workflow-gate/spec.md`：写 delta——`## REMOVED Requirements` 登记 `### Requirement: 影子接入阶段不改变任何既有强制`（带 Reason / Migration）；`## ADDED Requirements` 增 `### Requirement: 阶段 C 翻开关后的 required 形态`。
- [ ] 1.3 **把 change 的 spec delta 同步进当前规格**：`openspec/specs/platform-gate/spec.md` 与 `openspec/specs/dev-workflow-gate/spec.md` 就地覆盖（Purpose 段一并按阶段 C 实况改写）。同步后核对：Requirement 条数前后计数如实记入 `workflow-events.jsonl` 的 `current_spec_synced` 事件；**`dev-workflow-gate` 的其余 10 条 Requirement 逐条保留**（Decision 3 的爆炸半径约束）。
- [ ] 1.4 `docs/development-guide.md`：订正 witnessloop 节里阶段 A 遗留的两条 bullet（「已知红…② 本 change 自己」与「`reviews/` 的一致状态…2 条拉到 14/16 条」），使它们指向已归档的 `witnessloop-adoption` 而不是一个不存在的「本 change」。
- [ ] 1.5 **Purpose / 「阶段划分」段的人手就地改写**（`design.md` Decision 10）：两份规格的 `## Purpose` 段与 `dev-workflow-gate` 的「阶段划分」段按阶段 C 实况改写；**顺带修掉 `openspec/specs/dev-workflow-gate/spec.md` Purpose 段内的死链**（`openspec/changes/witnessloop-adoption/reviews/acceptance-stage-a.md` → 归档路径）。改写前后的差异记入 `current_spec_synced` 事件（该段**无 delta 载体**，只能就地改）。
- [ ] 1.6 `README.md` + `README_EN.md`：「用 Agent 开发 Agent」流水线图里「CI 门禁（… + benchmark-gate）」一行改为反映阶段 C 的实况（required 只有 `gate / check`，其余照跑不拦）。**两条必须同改**（AGENTS.md 的 README 同步规则）。
- [ ] 1.7 `docs/interview-script/questions/Q12-ci-testing.md`（job 数量与树图）与 `Q13-benchmark.md`（「自动拦截」）按阶段 C 实况订正——这两处是本次变更**直接造成/直接证伪**的事实变化。

## 2. 验证（判据见 `design.md` 的 Testing Strategy）

- [ ] 2.1 **T1**：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → 记原始输出。
- [ ] 2.2 **T2**：`uv run python scripts/check_openspec_artifacts.py --base-ref <base> --require-base` → exit 0。
- [ ] 2.3 **T3**：`uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` → exit 0。
- [ ] 2.4 **T4**：`python scripts/platform_gate.py --verify` → `全部一致`（exit 0）。**本 change 不改平台配置，合入后 SHALL NOT 再跑 `--apply`**（Decision R7）。
- [ ] 2.5 **内容真实性抽查**：规格里每条涉及 required 集合 / job 是否运行 / `--apply` 是否已执行的断言，逐条与 `gh api repos/Xingkai98/asterwynd/branches/master/protection` 的原始 JSON 对上。

## 3. 实现后独立审阅闭环

- [ ] 3.1 跑 `/review-loop stage-c-required-switch`，产出 `reviews/building-review.md` + `reviews/building-review-manifest.json`（**asterwynd 形态**）。CHANGES_REQUESTED 则修复并再审，直到 PASS 或 3 轮封顶。
- [ ] 3.2 收敛后**清理中间轮产物**（如 `building-review-r1.md`）——它们不在任何 manifest 的 `report_path` 上，一旦建了 witnessloop 形态 manifest 就会成孤儿报告。

## 4. witnessloop 证据与出口判据

- [ ] 4.1 在**所有内容提交之后**（含 1.4 与 backlog 清理），用 `witnessloop manifest build` 产三份 witnessloop 形态 manifest（`grill` / `grill-adversarial` / `building`），**绑定的 `report_path` 覆盖 `reviews/` 下每一份 `.md`**（`grill-design.md` / `grill-adversarial.md` / `building-review.md`），否则孤儿规则被激活。
- [ ] 4.2 **T5**：`witnessloop check --root . --base origin/master --head HEAD`（v1.7.0）→ `check：通过 ✓`（0 项）。这是本 change 的出口判据。
- [ ] 4.3 CI 侧复核：PR 的 `gate / check` 判绿；`validate` / `benchmark-gate` / `windows-platform` **照跑**（记录它们的结论，用于佐证 Decision 4 的不变量）。

## 5. 收尾（归档前必须完成，且必须按此顺序）

- [ ] 5.1 `docs/openspec-change-backlog.md`：登记本 change，随后在**证据产出之前**把它结算/移除（backlog 一致性规则机械要求不得引用已归档 change；`docs/` 不属 witnessloop 的 stale 豁免路径）。配 `backlog_updated` 解释事件。
- [ ] 5.2 写 `workflow-events.jsonl`：`change_created` / `backlog_updated` / `current_spec_synced`（两份规格各一条）/ `change_archived`，`approved_by` 非空。
- [ ] 5.3 结算 `tasks.md`：勾掉全部已完成项；closeout 类未完成项标 `(post-merge)`。**未勾且未标 `(post-merge)` 的任务必须为 0 条**。
- [ ] 5.4 归档 move：`git mv` 到 `openspec/changes/archive/2026-10-17-stage-c-required-switch/`，**独立纯 rename 提交**（Decision 6）。
- [ ] 5.5 **归档后**在归档目录上用**归档目录名**重建 witnessloop 三份 manifest 与 asterwynd 形态 manifest（Decision 6 的第 ④ 步）。

## 6. 合入之后（结构上无法在本 PR 内完成）

- [ ] (post-merge) 6.1 在 issue #305 追加 comment：阶段 C 的 change 记录已归档、规格已同步、`gate / check` 在本 change 的 PR 上判绿。**issue 保持 OPEN**（继续跟踪「逐项下掉旧件」）。
- [ ] (post-merge) 6.2 合入后确认：active change 目录不再存在、backlog 干净、本地 `master` 已快进到 `origin/master`；**并复核 `master` 的 required 仍为 `["gate / check"]`**（本 change 不该改变平台实况——这是 R7 的复核动作）。
