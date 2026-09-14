# Tasks: Workflow 级预算与成本归因

## 0. 设计追问（实现前门禁）

- [ ] 0.1 跑 `batch-grill-me`（或等价设计追问）审视 design.md D1–D7，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）。已产出 9 Confirmed + 16 Open Questions（Q1–Q16 全部确认，见 `## User Confirmation`）。

## 1. 四维度预算账本 + 超限状态机

- [ ] 1.1 `agent/subagent/workflow_budget.py`：`WorkflowBudget` 四维度账本（tokens/cost_usd/runs/wall_time_s）+ `reserve`/`settle`/`exceeded` + `WorkflowBudgetExceeded`。
- [ ] 1.2 调度器接线：`run()` 建账本、`_teardown()` 结算；`_dispatch` 派发前预扣 runs 维度（**复用 `self._runs` 唯一计数器**，C4 检查置于 C2 `max_runs` 之前）；token/cost 维度在 `loop.py` 的 `cost_ledger.record` 同位置记账（Q6 方案 B）。
- [ ] 1.3 超限状态机：stop_new **显式闸**（`_accepting` 不 gate 派发，须在 `_drive`/`_dispatch` 新增检查）+ 取消 queued + drain 在跑 + 根节点 `budget_exceeded`（加进 `TERMINAL_NODE_STATUSES`；`WorkflowBudgetExceeded` 不得逃出 `run()`，映射为 envelope）。

## 2. 成本归因四维

- [ ] 2.1 `CostLedger.record` 增 `workflow_id`/`node_id`/`depth`/`edge` **及 cache 参数**（`cache_read_tokens`/`cache_write_tokens`，对齐 `compute_cost_cached` 四档）；`bill()` 增 by_workflow/by_node/by_depth/by_edge 四维分桶。
- [ ] 2.2 `loop.py` 的 `cost_ledger.record` 调用点读取 run 身份字段并传入（`subagent_id` → `manager._sessions[...]` 一次查表取 workflow_id/node_id/depth/edge）。
- [ ] 2.3 `SubagentRunRecord` 增 `edge` 字段（规则见 Q8）**及 `graph_distance` 字段**（Q7/Q13：新增 `graph_distance` contextvar，调度器 `_launch_run` 既有 set 点一并 set，`_new_run` 读进）。`edge` 取值在调度器派发点算出（`_new_run` 时不可得——无「上游节点」contextvar），经 `run_subagent(edge=...)` 透传或 `_launch_run` 回填。
- [ ] 2.4 修 C3 遗留：`_mark_budget_exceeded` 补填 usage（input/output）或标注「usage 不完整」，避免被预算杀的 run 在 by_node 里 cost 为 0。

## 3. 动态 route + 动态 foreach

- [ ] 3.1 动态 route：`when` 支持 `$ref:<node_id>:<slot>` 语法；`parse_workflow_spec` 校验期查「节点存在 + 槽已声明」（含隐式 result 槽）；运行时判定 = 解析槽值→取首个非空行→作期望标签→`matches_route`（Q1/Q2 联合语义，判定前不调 `bounded`）；槽缺失静默走 default + diagnostics 记原因（Q3）。
- [ ] 3.2 动态 foreach：`source` 跨层递归解析（只沿数据边，优先读自身 result 槽，唯一上游才继续，多入边歧义拒绝；环检测复用 Tarjan SCC 在 `parse_workflow_spec` 校验期）；`source_field` 只应用一次（Q10）。
- [ ] 3.3 `max_items=0` = 不静态截断、展开到预算耗尽（Q9）：单独非负解析函数放行 0；foreach 预检按剩余容量截断（只对 `max_items==0` 生效，发生在 `_expand_plan` 之前），可展开数取「C4 max_total_runs / C2 max_runs / C2 max_nodes」剩余上限最小值。

## 4. 配置

- [ ] 4.1 `WorkflowBudgetConfig`（max_total_tokens/max_total_cost_usd/max_total_runs/max_wall_time_s）+ `_parse_workflow_budget` 逐字段解析，挂 `WorkflowLimitsConfig.budget`；四字段均 `0 = 不限`（专用非负解析函数，不改全局 `_validate_positive_int`/`_parse_positive_float`），显式 `null` 拒绝（Q11）。

## 5. envelope 暴露

- [ ] 5.1 `status()` envelope 增 `budget`（四维度 limit/used + exceeded 标志）+ `attribution`（四维 top-k bounded 摘要，round 对齐 9 位，tokens=input+output 不含 cache，cost USD，未知模型标 estimated）。
- [ ] 5.2 `GetWorkflow` detail 参数：`_DETAILS` 扩含 `"attribution"`，返回 `attribution_ref`；`WorkflowStore.save_attribution` 在 `_teardown()`/`run()` 结算时一次性落盘（Q15）。

## 6. 测试与收尾

- [ ] 6.1 新增四维度预算超限/结算测试（token/cost/runs/wall_time + stop_new/drain/根节点 budget_exceeded）、by_node/by_depth/by_edge 归因测试、动态 route `$ref` 测试（命中/未命中/default）、动态 foreach 跨层 source 测试、max_items=0 截断测试。
- [ ] 6.2 兼容回归：`CostLedger.record` 不带归因键时三维账单不变；C2 `max_runs` 声明期校验不变；`max_items>0` 保留 C2 fail-fast（不破坏 `test_foreach_run_budget_reports_graph_recursion_exceeded`、`test_auto_aggregates_consume_max_runs`）。
- [ ] 6.3 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过。
- [ ] 6.4 同步 current spec：把 spec delta 合入 `openspec/specs/multi-agent-collaboration/spec.md`。
- [ ] 6.5 `uv run pytest -q` 全绿；OpenSpec validate + artifact checker 通过。
