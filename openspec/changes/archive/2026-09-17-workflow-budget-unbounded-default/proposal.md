# Proposal: workflow 四维预算默认无上限（workflow-budget-unbounded-default）

关联跟踪 issue：[#196](https://github.com/Xingkai98/asterwynd/issues/196)。参照先例：issue #192（AgentLoop 迭代默认无上限，PR #192 已合入）。

## Change Type

- primary: feature
- secondary:
  - agent-runtime
  - subagent

## Why

C4 `workflow-budget-attribution`（#185，已合入归档 2026-09-14）给 workflow 级加上了四维度总预算，默认值 **200000 tokens / 5.0 USD / 300 runs / 1800 s**。这组默认值对「代码体检」这类 token 消耗大的任务**偏紧**：实测一条 12 文件 foreach 体检在约 18 万 token 处触发 `budget_exceeded`，调度器按 stop_new + drain 语义中止派发，任务被腰斩——而用户从未显式要求设上限。

同一类问题在 AgentLoop 层已经用「默认无上限、显式才设限」解决过一次（#192：`max_iterations` 默认 `None`，只有显式 `--max-iterations` 才设上限，避免计次上限把正常长任务掐断）。本 change 把同一口径应用到 workflow 四维预算：**默认不设上限，只有显式在配置文件（`subagents.workflow.budget.*`）或 CLI 入参里指定才设上限。**

关键事实：四维预算的「不限」语义**已经存在**——C4 grill Q11 确认「四字段均 `0 = 不限`」，`WorkflowBudget.exceeded_dimension` / `reserve_runs` / `_remaining_expansion_capacity` 都按真值判定跳过 0。因此本 change 不需要新增机制，**只改默认值**：把「未配置」从「200k/5.0/300/1800」改成「0（不限）」。

## What Changes

- `WorkflowBudgetConfig` 四字段默认值由 `200000 / 5.0 / 300 / 1800` 改为 `0 / 0 / 0 / 0`（`0 = 不限`，沿用既有 Q11 哨兵）。
- `_parse_workflow_budget` 的逐字段 `mapping.get(key, <default>)` 默认值同步改为 0；显式 `null` 仍拒绝（缺值不得静默关闸的口径改为「缺值即不限，但显式 null 仍是配置错误」），负值仍拒绝，显式数值（含显式 0）仍生效。
- `WorkflowBudget.__init__` 的 `getattr(config, ..., <fallback>)` 兜底同步改为 0（配置链路缺失时 = 不限，与默认语义一致）。
- （待拍板）CLI 是否新增 `--workflow-budget-*` 系列入参，参照 `--max-iterations` 先例。
- spec delta：MODIFIED 既有 Requirement「workflow 级四维度总预算」的默认值表述。

**不变**：C2 三闸（`recursion_limit` / `max_nodes` / `max_runs`）是**声明期结构闸**，与本 change 无关，仍按原默认值兜底（C4 Q14 既有口径：`max_total_runs=0` 不解除 C2 的 `max_runs`）。超限状态机（stop_new + 取消 queued + drain + 根节点 `budget_exceeded`）不变——它只在「显式配置了上限且被突破」时才触发。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `multi-agent-collaboration`: 既有 Requirement「workflow 级四维度总预算」的**默认值语义**由「默认 200k / 5.0 / 300 / 1800」改为「默认不限（0），显式配置才设上限」。enforcement 机制、超限出口、C2 结构闸关系均不变。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 常规功能增强——把本仓已在 AgentLoop 层验证过的「成熟模式的局部应用」（#192：默认无上限、显式才设防死循环上限）搬到 workflow 四维预算；不引入新框架/新协议，不新增能力面，enforcement 机制与超限语义完全复用 C4 已合入的实现。命中 `light` 判据。
- findings:
  - **本仓先例（强证据）**：#192 已把 AgentLoop `max_iterations` 默认改为 `None`（无上限），只有显式 `--max-iterations` 才设上限，并保留显式上限时的 `stop_reason=max_iterations` 防死循环路径（`agent/loop.py`、`agent/main.py`、`docs/agent-internals.md`）。该先例的 spec（`openspec/specs/agent-runtime/spec.md` 的「达到 max_iterations」Scenario）**未钉任何默认数值**，因此无需 spec delta、可直接提交；本 change 的差异点在于 `openspec/specs/multi-agent-collaboration/spec.md:190` **显式钉了「默认 200k / 5.0 / 300 / 1800」**，所以必须走 OpenSpec change + spec delta 修正该口径。
  - **业界口径**：主流编排框架对「资源上限」一律采取「显式声明才生效」——LangGraph 的 `recursion_limit` 必须由调用方在 `config` 里显式传入（默认值仅作为库级兜底常量，不是产品级强制预算）；OpenAI Agents SDK 的 `MaxTurns` / 成本上限同样默认为「不限」，由调用方按需注入。业界共识是**框架不替使用者决定花多少钱**，安全阀由部署方显式配置。C4 的「默认 200k」恰恰相反，与本仓自身 #192 的口径也不一致，属于需要修正的默认值选择。
  - **本地参考仓库**：本工作区未配置 `.dev/reference-repos.txt`（该文件不存在），因此本 change 无本地参考仓库对比层；findings 完全基于本仓先例与既有 spec/实现。
- design impact: 见 design.md D1–D3（默认值落点）+ D4（CLI 待拍板）。不改 `WorkflowBudget` 的判定逻辑、不改调度器接线、不改 envelope schema。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（workflow 级四维预算的默认值语义）。
- **代码**: `agent/config.py`（`WorkflowBudgetConfig` 字段默认值 + `_parse_workflow_budget` 的 `mapping.get` 默认值）；`agent/subagent/workflow_budget.py`（`WorkflowBudget.__init__` 的 `getattr` 兜底）；（若拍板加 CLI）`agent/main.py` + `agent/config.py` 的 `ConfigOverrides`/`_apply_cli_overrides`。
- **测试**: 更新断言默认值的既有测试（`tests/agent/subagent/test_workflow_budget.py`、`test_workflow_budget_config.py`）；新增回归测试覆盖「默认不限不掐断长任务」「显式配置上限仍生效」「显式 0 仍生效」「显式 null 仍拒绝」；兼容回归确认 C2 `max_runs` 结构闸在预算不限时仍兜底。
- **文档**: `openspec/specs/multi-agent-collaboration/spec.md`（current spec 同步）、`docs/openspec-change-backlog.md`（change 状态）；`asterwynd.example.yaml` 若含 workflow budget 示例需同步（当前该文件未含 budget 段，预期无改动）。
- **流程（process）**: 本 change 触及受保护路径 `openspec/specs/**`，需 `current_spec_synced` 结构化事件 + grill 证据 + building review；收尾按 OpenSpec archive 流程归档。
- **未知/待确认**: CLI 入参是否纳入本 change 由 grill 停轮确认（design.md D4）。
