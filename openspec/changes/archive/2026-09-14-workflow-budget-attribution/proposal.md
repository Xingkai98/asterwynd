# Proposal: Workflow 级预算与成本归因（workflow-budget-attribution）

关联跟踪 issue：[#185](https://github.com/Xingkai98/asterwynd/issues/185)。wayfinder 地图：[#170](https://github.com/Xingkai98/asterwynd/issues/170)。决策票：G5 [#176](https://github.com/Xingkai98/asterwynd/issues/176)。依赖 C2 [#181](https://github.com/Xingkai98/asterwynd/issues/181)（已合入）、C3 [#183](https://github.com/Xingkai98/asterwynd/issues/183)（已合入）。

## Change Type

- primary: feature
- secondary:
  - agent-runtime
  - subagent

## Why

C1 给了「单 run 预算」（`max_tokens` / `max_time_s`，`agent/subagent/budget.py`），C2 给了「图级结构闸」（`recursion_limit` / `max_nodes` / `max_runs`），但两者都**不是 workflow 级资源总预算**：

- 一个 workflow run 里几十个 leaf 各自消耗 `max_tokens`，总 token / 总成本没有任何上限——模型自由声明上百个 subagent 时，这是真实的烧钱面（R1 #171 调研：Claude Code #68110/#69206 就是「无硬总上限」翻车烧 1.5M tokens）。
- 成本不可归因：`CostLedger` 现在只有 by_session / by_phase / by_tool 三维（`agent/cost_tracker.py:168-187`），回答不了「哪个节点最贵、哪层重复 token 最多、动态 vs 固定 pattern 差多少」——G5 #176 明确要求 by_workflow / by_node / by_depth / by_edge。
- **动态 route/foreach 是 G3/G7 的遗留**：C2 落地了 route/foreach 的声明面，但 route 的 `when` 只匹配**上游文本拼接**（`scheduler.py:1051` `_route_verdict`），foreach 的 `source` 只支持**一层上游引用**（`workflow.py:739-743` 校验 source 在 index 中）——「动态 route 按上游结构化结果分支」「foreach 跨层递归 source」这两条 G3 #174 口径在 C2 只落地了受限版，完整版随本 change 交付。

G5 #176 已定稿四维度总预算与超限语义；本 change 落地该决议 + 补齐动态 route/foreach。

业界依据（R1 #171 调研）：LangGraph 的图级 `recursion_limit` 只是结构闸、不含 token/成本预算（[token-usage-per-step](https://theneuralbase.com/agent-patterns/learn/advanced/token-usage-per-step/) 需要自行累积 per-node usage）；多 agent 成本归因是当前 FinOps 实践的核心（[superteams.ai cost-attribution-chargeback](https://www.superteams.ai/courses/enterprise-multi-agent-systems/24-cost-attribution-chargeback/)、[clawhub agent-finops](https://docs.clawhub.ai/mirni/skills/greenhelix-agent-finops-playbook)）；本仓已有 `CostLedger` 三维账单 + C3 的 result_ref 落盘作锚点，本 change 在其上扩四维归因，不引新框架。

## What Changes

- **workflow 级四维度总预算**：`max_total_tokens`（200k）/ `max_total_cost_usd`（5.0）/ `max_total_runs`（300）/ `max_wall_time_s`（1800）。超限策略「停新 + 取消排队 + drain 在跑 + 根节点 budget_exceeded」；每次 LLM 调用前原子预留额度、完成后结算。
- **成本归因四维度**：`CostLedger` 增 by_workflow / by_node / by_depth / by_edge；`SubagentRunRecord` 的记录带 workflow_id / node_id / depth / parent_run_id（C1 身份字段已就位，本 change 把它们送进 ledger）。
- **动态 route**：`when` 支持 `$ref` 引用上游结果槽（引用值必须来自已声明的 result_ref 键；无键命中 = 不匹配，保留 default 兜底）。
- **动态 foreach**：`source` 支持跨层（递归解析上游产出，环回边拒绝）；`max_items` 允许 0 表示「展开到预算耗尽为止」。

## Capabilities

### New Capabilities

无新能力域；在既有 `multi-agent-collaboration` 能力域上深化。

### Modified Capabilities

- `multi-agent-collaboration`: 新增 workflow 级总预算 enforcement + 成本归因四维账单；route 条件源、foreach 动态 source 从「受限版」演进为「动态版」。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 架构级改造（预算 enforcement 跨 manager/scheduler/loop 三层 + 成本归因 schema 扩展），走 grill 的非平凡 change，命中 `full` 判据。
- research questions:
  1. 业界多 agent 编排的 workflow 级预算 enforcement 怎么做（LangGraph/GoA/企业 FinOps）？
  2. 成本归因的分桶维度怎么定（by_node/by_depth/by_edge 的语义边界）？
  3. 动态 route/foreach 的「引用/递归」在不执行模型生成代码的前提下怎么受限落地？
- findings: 见 wayfinder R1 #171 决议（已关闭）+ G5 #176 决议（已关闭）。核心结论——
  - **预算 enforcement**（LangGraph）：图级 `recursion_limit` 只数步数、不含 token/成本；per-node usage 靠 step callback 自行累积（并行分支需 step execution id 才能正确归因，见 [theneuralbase](https://theneuralbase.com/agent-patterns/learn/advanced/token-usage-per-step/)）。本 change 用 C1 已就位的显式身份字段（workflow_id/node_id/depth）做归因键，等价于 step execution id，无需 callback。
  - **成本归因**（企业 FinOps 实践）：by team / by artifact / by model 是主流三维；本 change 对齐 G5 #176 的 by_workflow / by_node / by_depth / by_edge（workflow=团队、node=artifact、depth=层级、edge=拓扑边），覆盖「哪个节点最贵、哪层重复 token 最多、动态 vs 固定差多少」三个问题。
  - **动态 route/foreach**（LangGraph `Send`）：动态 fan-out 是编译期「动态图」vs 运行期「状态驱动」的关键差异；本 change 的 `$ref` 引用与跨层 source 都**只解析已落盘的 result_ref / 已声明的 slots**，不执行模型生成代码，保持 C2 的「受限可校验」边界。
- design impact: 见 design.md D1–D7；四维度预算与超限语义来自 G5 #176 决议，动态 route/foreach 补齐 G3 #174 口径。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（workflow 级预算 + 成本归因 + 动态 route/foreach）。
- **代码**: 新增 `agent/subagent/workflow_budget.py`（四维度预算账本 + 预留/结算）；改 `agent/subagent/manager.py`（run 记录带 cost 归因键 + LLM 调用前预留/后结算的 hook 点）、`agent/cost_tracker.py`（`CostLedger.record` 增 workflow_id/node_id/depth/edge + `bill()` 增四维分桶）、`agent/subagent/scheduler.py`（预算闸门 + 动态 route `$ref` + 动态 foreach 跨层 source）、`agent/subagent/workflow.py`（schema 增 `$ref` when 与 max_items=0 语义）、`agent/config.py`（`WorkflowBudgetConfig` + 逐字段解析）、`agent/tools/builtin/subagents.py`（GetWorkflow 暴露 budget/attribution 摘要）。
- **测试**: 新增四维度预算超限/结算测试、by_node/by_depth/by_edge 归因测试、动态 route `$ref` 测试、动态 foreach 跨层 source 测试、max_items=0 展开测试；既有 workflow/scheduler/manager 测试兼容。
- **文档**: `docs/openspec-change-backlog.md`（C4 状态）、wayfinder #170（引用）。
- **流程（process）**: 本 change 是 C4；C5 `benchmark-workflow-replay` 依赖本 change 的预算归因数据（benchmark 报告字段含 workflow_cost_usd / 归因分桶）。
