# Proposal: 阶段 C 翻开关（required 只留 witnessloop 的 `gate / check`）

关联跟踪 issue：[#305](https://github.com/Xingkai98/asterwynd/issues/305)（【feature】把 asterwynd 自己的流程门禁切换成「接入 witnessloop」（盘点 + 迁移计划））。本 change 是该 issue **阶段 C** 的正式记录。

## Change Type

- primary: process
- secondary: []

## Why

**阶段 C 的**行为**已经发生，但它的**记录**不存在，并且留下两处事实漂移。**

1. **行为已落地**：PR [#311](https://github.com/Xingkai98/asterwynd/pull/311)（merge `4b5cc7d1a49d06caa94fe2c35aae2ccfce778e23`）已把 `master` 的 `required_status_checks.contexts` 从 `["validate", "benchmark-gate"]` 改为 **`["gate / check"]`**，caller 由 `@v1` 迁到 `@v1.7.0`，并在合入后执行了 `platform_gate.py --apply`（`--verify` 实测「全部一致」）。
2. **两处规格在说谎**：
   - `openspec/specs/platform-gate/spec.md:11` 与 `:13-17` 仍写 required = `validate` + `benchmark-gate`（含名为「benchmark-gate 为 required check」的 Scenario）；
   - `openspec/specs/dev-workflow-gate/spec.md:7` 的 Purpose 段把「阶段 A、只跑不拦、required 仍为两项」写成**现状**。
3. **翻开关的代价已由 PR #311 自己证明**：该 PR 的 `gate / check` 判红 **2 项**（`scripts/platform-gate.json` 属于 `require_change_for` 但 diff 里没有 change 目录；`.witnessloop/init-manifest.json` 是受保护写入但没有解释事件）。**两条都属实**，当时**没有**为了让门变绿去放宽 `require_change_for` 或删 protected path——代价是「翻开关这件事本身没有 change 记录」。
   > **出示该证据时要引 PR 的 head sha `18d5bfbf2aa16f1994b1fa2bb7de1f7b8bd42d20`，不是 merge sha。** 实测：在 head 上 `gate / check` 为 `failure` 且 `validate` / `benchmark-gate` / `windows-platform` 三项同时 `success`（这正是「照跑但不拦」的形态）；而在 merge commit `4b5cc7d1` 上 `gate / check` 这个 check-run **根本不存在**（只剩三个 success）。引错 sha 会把结论说反。

⇒ 结论：阶段 C 这件事**本身就该有一条 change 记录**。而这条 change 恰好是 `openspec/specs/**`（受保护路径，需 `current_spec_synced` 解释事件）同步的**合法载体**——把规格从「阶段 A 的过渡态」改写为「阶段 C 的实况」。

## 需求

1. **为阶段 C 补一条正式的 change 记录**（本 change）：proposal / design / tasks / spec delta + grill / 对抗 / 实现后审阅证据，按本仓流程走完并归档。
2. **同步 `platform-gate` 规格**：required 集合由两项改为**唯一** `gate / check`；Scenario 名与断言随之改写；补上「本仓自建 job 照跑但不拦」这条不变量。
3. **同步 `dev-workflow-gate` 规格**：Purpose 段与「阶段划分」段由阶段 A 口径改写为阶段 C 口径；阶段 A 专属的那条 Requirement（「影子接入阶段不改变任何既有强制」）按 **REMOVED** 处置并新增阶段 C 的对应条目。
4. **钉住「降级不是关闭」**：新增一条 Requirement，把 `.github/workflows/ci.yml` 的三个 job 继续运行、不得因不再 required 而被停用/删除写成规范约束。
5. **簿记**：backlog 登记与结算、受保护写入的解释事件（`backlog_updated` / `current_spec_synced` / `change_archived`）。
6. **顺手修掉上一轮留下的陈旧段落**：`docs/development-guide.md` 的 witnessloop 节里仍有一段「已知红（预期）…本 change 自己」的阶段 A 文案，且 `specs/dev-workflow-gate` 的同步要与之同向。
7. **把「翻开关这一动作自身必须具备 change 记录」写成规范义务**（`design.md` Decision 9）：关闭某个阶段的动作本身 SHALL 由一条 OpenSpec change 承载并归档，且其 `proposal.md` SHALL 如实写明「行为已先落地、本 change 只做记录与规格对账」。这条约束**正是本 change 自己的形态**——翻开关之后任何触达受管路径的改动都必须挂 change，若翻开关自己的动作不挂，它就在用自己的豁免把新规则挡在门外。
8. **补齐设计追问（grill）指出的文档影响面**：`README.md` / `README_EN.md` 的 CI 流水线图、`docs/interview-script/` 里被本次变更证伪的两处 CI 口径（Q12 的 job 数量与树图、Q13 的「自动拦截」）、`docs/openspec-change-backlog.md` 里阶段 C 仍是未来式的条目。

## 非目标

- **不下掉任何本仓检查**。`validate` / `benchmark-gate` / `windows-platform` 三个 job 继续在每个 PR 上照跑；「逐项下掉旧件」（原阶段 C 的 C.2）由**后续独立 change** 承载。
- **不改 `.github/workflows/ci.yml`**（一行都不改）、**不关任何 workflow**、**不删任何检查**。
- **不改 `scripts/platform-gate.json`**：它的目标状态已由 PR #311 落地并 `--apply`，本 change 只同步**规格**。
- **不改 `agent/**` / `scripts/**` / `web/**`**：本 change 的 diff 只落在 `openspec/**` 与 `docs/**`，不引入任何运行时行为变化，因此**没有代码测试面**。
- **不统一 manifest schema**（N.4）；**不处理** `add-minimal-tui-runtime-view` 的已知红（K1）；**不碰 witnessloop 仓与 `v1` / `v1.7.0` tag**。
- **不重新讨论**「required 该不该只留 `gate / check`」：该决策已由用户在 issue #305 的阶段 C 讨论中拍板，本 change 只做记录与对账。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `platform-gate`：合入门禁的 required 集合由「`validate` + `benchmark-gate`」改为**唯一** `gate / check`（strict 模式不变）；新增「**降级不关闭**」不变量——不再 required 的检查 SHALL 继续运行。
- `dev-workflow-gate`：接入形态由「阶段 A：影子接入、只跑不拦」改写为「阶段 C：`gate / check` 是唯一 required，本仓自建门禁照跑但不拦」；阶段 A 专属的「不改变任何既有强制」Requirement 退场。

## Impact Analysis

- **影响规格（生产面：本 change 的全部实质改动）**：
  - `openspec/specs/platform-gate/spec.md`：Purpose 段的 required 列举（**人手就地改写，无 delta 载体**——见 `design.md` Decision 10）；Requirement「合入平台闸门」的正文与首个 Scenario（`benchmark-gate 为 required check` → witnessloop `gate / check` 为唯一 required）；Requirement「平台闸门复用 GitHub branch protection 语义」的 Scenario「平台配置走 PR review」里对 CI 的列举；**新增**「降级为非必过的检查仍须运行」Requirement。
  - `openspec/specs/dev-workflow-gate/spec.md`：Purpose 段（现状改写，**含一条死链修正**——它引用的 `openspec/changes/witnessloop-adoption/reviews/acceptance-stage-a.md` 已随归档移到 `archive/2026-10-13-witnessloop-adoption/` 之下）与「阶段划分」段，两者**均为人手就地改写**；Requirement「影子接入阶段不改变任何既有强制」**REMOVED**；Requirement「grill 报告正文判据的已知不兼容」**MODIFIED**（补记 v1.7.0 对 `## User Confirmation` 的**无条件存在性**判据，并订正原「结构性不可能判绿」的断语——阶段 B 实测 63 份归档中 39 份零 finding）；**新增**两条 Requirement（阶段 C 的 required 形态；翻开关这一动作自身必须具备 change 记录）。
- **影响本 change 自身文档**：`openspec/changes/stage-c-required-switch/**`（proposal / design / tasks / specs deltas / reviews / workflow-events.jsonl）。
- **影响文档**：
  - `docs/openspec-change-backlog.md`（登记 + 结算，受保护路径，配 `backlog_updated` 解释事件；第十七批的阶段 C 条目由未来式改为已完成口径）。
  - `docs/development-guide.md`（witnessloop 节里阶段 A 遗留的两条 bullet 的订正）。
  - `README.md` + `README_EN.md`（「用 Agent 开发 Agent」的流水线图里「CI 门禁（… + benchmark-gate）」一行的口径；**两条必须同改**，见 AGENTS.md 的 README 同步规则）。
  - `docs/interview-script/questions/Q12-ci-testing.md`（「CI 有两个 job」与实际三个 job 不符，且阶段 C 后三个都不拦合并；树图同）与 `docs/interview-script/questions/Q13-benchmark.md`（「benchmark-gate 接 CI…**自动拦截**」在阶段 C 之后不再成立）——两处均为本次变更**直接造成/直接证伪**的事实变化，就地订正。
- **明确不影响的文档**：`docs/known-issues.md` / `docs/known-debt.md`（本次不新增债务条目——grill 发现的 D1–D8 全部在本 change 内就地处置，不转债务）。
- **不影响**：`.github/workflows/ci.yml`、`.github/workflows/witnessloop.yml`、`.witnessloop/**`、`scripts/**`、`agent/**`、`web/**`、`benchmarks/**`、branch protection 实况（本 change 合入后**不需要**再 `--apply`——目标状态与实况都已一致）。
- **行为变更（用户可见）**：**无**。本 change 只改规格文本与文档；`master` 的合入门禁形态在本 change 前后**逐字段一致**（`--verify` 已实测「全部一致」）。
- **不新增外部依赖**。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 上游决策锁定——本 change **不引入任何新能力面、没有任何待定设计项**：required checks 的最终形态（只留 witnessloop 的 `gate / check`）由用户在 issue #305 的阶段 C 讨论中拍板，其分阶段顺序与「阶段 A 不勾 required」的设计依据记录在已归档 change `openspec/changes/archive/2026-10-13-witnessloop-adoption/`（Decision 4 的阶段表、Decision 5 的「保留为本仓的八项」、tasks C.1）；实现本体已随 PR #311 合入并 `--apply` 落地。本 change 的实质是**簿记 + 规格对账**，改动面只有 `openspec/**` 与 `docs/**`，不触达任何运行时代码，因此没有可供业界对比的设计空间（有设计空间的新功能不在豁免之列，本 change 不属于该类）。

## 用户故事

- 作为本仓维护者，我读 `openspec/specs/platform-gate/spec.md` 时看到的是**实况**（required 只有 `gate / check`），而不是阶段 A 的过渡态——我不需要再去 `gh api` 才能确认门禁形态。
- 作为本仓维护者，我读 `openspec/specs/dev-workflow-gate/spec.md` 时能一眼看出**当前**承载分工与三个阶段走到了哪一步，而不是读到一段把「阶段 A 只跑不拦」写成现状的 Purpose。
- 作为后续接手「逐项下掉旧件」的人，我有一条可追溯的 change 记录说明「翻开关时哪些检查被降级为非必过、每个还在不在跑」。
- 作为流程 owner，我在本 change 自己的 PR 上看到 `gate / check` **绿**——证明这条 change 记录确实满足了 witnessloop 的契约（而非又一次「没有 change 目录」的红）。
