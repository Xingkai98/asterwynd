# Design: Workflow 级预算与成本归因

## Context

C1 给了「单 run 预算」（`BudgetTracker`，`agent/subagent/budget.py`），C2 给了「图级结构闸」（`recursion_limit`/`max_nodes`/`max_runs`，`agent/subagent/workflow.py`），C3 给了「result_ref 落盘 + 分层汇聚」。但一个 workflow run 的**总 token / 总成本 / 总 wall-time** 仍无上限——模型自由声明上百个 subagent 时，这是真实的烧钱面。同时成本不可归因（`CostLedger` 只有 by_session/by_phase/by_tool 三维）。

本 change 落地 G5 #176 决议：workflow 级四维度总预算（token / cost_usd / runs / wall_time_s）+ 成本归因四维度（by_workflow / by_node / by_depth / by_edge），并补齐 G3 #174 遗留的动态 route/foreach（route 条件源 `$ref` 引用 + foreach 跨层 source）。依赖 C2 的调度器 + C1 的身份字段 + C3 的 result_ref 落盘。

## Goals / Non-Goals

**Goals**

1. workflow 级四维度总预算：`max_total_tokens`（默认 200k）/ `max_total_cost_usd`（默认 5.0）/ `max_total_runs`（默认 300）/ `max_wall_time_s`（默认 1800）。
2. 超限策略：停新 + 取消排队 + drain 在跑 + 根节点 budget_exceeded；LLM 调用前原子预留、完成后结算。
3. 成本归因四维度：by_workflow / by_node / by_depth / by_edge。
4. 动态 route：`when` 支持 `$ref` 引用上游结果槽（不执行模型生成代码）。
5. 动态 foreach：`source` 跨层递归解析（环回边拒绝）；`max_items=0` = 「展开到预算耗尽为止」。

**Non-Goals**

- 不做每个 subagent 单独设模型（wayfinder #170 已搁置）。
- 不做跨进程/跨机器分布式预算账本（单机 asyncio，前序 #79 同口径）。
- 不做预算的跨 workflow run 持久化/恢复（进程重启后预算账本不恢复，归 C5 replay 范畴）。
- 不做动态 route/foreach 的「运行时生成新节点 id」（foreach 展开项仍走 `_run_foreach_item` 的 session 命名，不产生声明面新节点）。

## Decisions

### D1 — 四维度预算账本（`workflow_budget.py`，独立于单 run BudgetTracker）

新增 `WorkflowBudget`（`agent/subagent/workflow_budget.py`）：一个 workflow run 一份账本，调度器在 `run()` 开头创建、`_teardown()` 结算。四维度：

| 维度 | 记账点 | 超限动作 |
|------|--------|---------|
| `max_total_tokens` | 每次 LLM 调用完成后累加 input+output | 触发 stop_new |
| `max_total_cost_usd` | 同 LLM 调用，用 `compute_cost_cached` | 触发 stop_new |
| `max_total_runs` | 每次派发 run（含 foreach 展开项） | 触发 stop_new |
| `max_wall_time_s` | 挂钟时间（`_started_at` 起算） | 触发 stop_new（drain 在跑） |

**原子预留/结算**：LLM 调用前 `reserve(tokens_estimate)`、完成后 `settle(actual)` 是**账本内同步操作**（单事件循环，asyncio 协作调度下无真并发写），token/cost 维度没有「预留不足」语义——token 预算本身是**完成后累加**判定（`after_llm_call` 已有 usage），cost 同源同判定。**token/cost 记账点选 loop 层**（Q6 确认，方案 B）：在 `agent/loop.py` 的 `cost_ledger.record` 同位置读 `response.usage`（含 cache 全字段）记入 workflow 账本——这是唯一能拿到 `cache_read_input_tokens`/`cache_creation_input_tokens` 的位置（`SubagentRunUsage` 无 cache 字段，见 grill 决策 3）。排队期不产生 token/cost，resume 新建 run 按实际新 LLM 调用再次计入。

`max_total_runs` 在派发前**预扣**——**复用 C2 `_dispatch` 的 `self._runs` 作为唯一计数器**（Q4 确认，另起计数器会在 foreach 预扣路径漂移）。运行期 C4 检查置于 C2 `max_runs` 检查**之前**：同值 300 时由 C4 触发 `budget_exceeded`（drain），只有 C2 显式更小时才走 `graph_recursion_exceeded`。**`WorkflowBudgetExceeded` 不得未捕获逃出 `run()`**——`run()`/`_drive()` 今天只 catch `GraphRecursionError`，C4 超限必须映射为 stop_new + drain + `_status="budget_exceeded"` envelope，否则父 agent 收到异常而非 envelope（审阅员修订）。

**token/cost 预算超限不会中途取消单个 LLM 调用**（调用已发出、usage 到手才判定），只触发 `stop_new`。

### D2 — 超限状态机：stop_new → drain → budget_exceeded

`WorkflowBudget` 是一个 flag + 状态，不是杀器。超限后：

1. **stop_new 显式闸**：`_accepting` 今天**不 gate 派发**（唯一读点是 `_on_node_finished` 的级联复位门，见 grill 决策 2），所以预算超限必须在 `_drive` 顶部或 `_dispatch` 开头**显式新增检查**（置 `budget_exceeded` 粘性状态后拒绝派发），不能只置 `_accepting=False`。
2. 取消 queued（在 `manager` 队列里排队但未执行的 run 标 cancelled——复用 C2 `_cancel_node` 的惰性取消）。
3. drain 在跑：已 `started` 的节点跑完（token/cost 预算超限**不取消**在跑 run；wall_time 超限**也不取消**在跑 run，只停止派发）。
4. **根节点标 `budget_exceeded`（Q5 确认）**：非根 pending 仍 `blocked`；根节点（`plan.terminal`，即「无下游数据边的节点」，fan-out 图是多个）未完成则改 `budget_exceeded`、已完成不覆盖。**节点级 `budget_exceeded` 是新状态，必须加进 `TERMINAL_NODE_STATUSES`**（否则被标的上游让下游永远 `_data_deps_satisfied == False`）。最终 workflow `status` 优先保持 `budget_exceeded`（`_drive` 收敛的 `completed`/`cancelled` 出口不覆盖粘性预算状态）。`status()` envelope 增 `budget: {dimensions, exceeded, exceeded_dimension}`。

**语义边界（区别于 C2 的结构闸）**：`max_total_runs` 与 C2 的 `max_runs` 语义重叠，本 change **不删 C2 的 `max_runs`**——C2 的 `max_runs` 是**声明期可校验的结构闸**（`parse_workflow_spec` 就能拒绝超限 spec），C4 的 `max_total_runs` 是**运行期动态预算**（foreach 展开项数声明期不可知时，运行期才累计）。两者默认值一致（300），但一个在声明期 fail-fast、一个在运行期 drain。超限报错走 `WorkflowBudgetExceeded`（区别于 `GraphRecursionError` 的 `reason="budget_exceeded"`），envelope 里 `status="budget_exceeded"`。

### D3 — 成本归因：扩 CostLedger 四维 + run 记录带归因键

`CostLedger.record` 增可选参数 `workflow_id` / `node_id` / `depth` / `edge`；`bill()` 增 `by_workflow` / `by_node` / `by_depth` / `by_edge` 四维分桶。归因键来源：

- `workflow_id`：`SubagentSessionRecord` 已有的 `workflow_id`（C1 身份字段，`create_subagent` 时从 contextvar 固定）。
- `node_id`：同上的 `node_id`。
- `depth`：**`by_depth` 用独立 workflow 图距字段**（Q7/Q13 确认），**不复用/不改 `spawn_depth`**（现状 workflow 内所有节点 `depth` 恒为同一个值，见 grill 决策 5）。口径：0=leaf / 1=shard / 2=domain / 3+=root（复用 C3 `budget_for_distance`）。落点：新增 `graph_distance` contextvar（`agent/subagent/context.py`），调度器在 `_launch_run` 既有 set 点一并 set（值从 `plan.budgets`/图距算），`manager._new_run` 读进 `SubagentRunRecord.graph_distance`（与 `depth` 并列）。
- `edge`：**新增**，按「实际触发该 run 的拓扑来源」生成（Q8 确认）——多数据入边按 source id 排序拼接 `a|b|c->join`；foreach 展开项共享 `planner->fan`；入口 `"<root>->node"`；route 控制边触发的下游记 `route->target`（控制激活优先）。**取值在调度器派发点算出**（`_new_run` 时不可得——无「上游节点」contextvar，见 grill 决策 6），经 `run_subagent(edge=...)` 透传或 `_launch_run` 回填。

**关键设计**：归因不是记账点的责任，而是**身份字段的下游投影**。归因键在 `loop.py` 的 `cost_ledger.record` 调用点读取并传入。`session_id` 传的就是 `session.subagent_id`（`manager.py`），而 `SubagentSessionRecord` 已带全 workflow_id/node_id/depth，所以取键是「`subagent_id` → `manager._sessions[...]` → 身份字段」的**一次查表**，不需遍历 `session.runs`（grill 决策 4）。

**记账口径一致性（Q12 确认）**：workflow 账本是权威口径（Q6 方案 B 从 `response.usage` 四档全算 cache-aware cost），`CostLedger` 是跨 workflow 历史财务记录、不追求逐 run 相等；但 `CostLedger.record` 应**扩 cache 参数**（`compute_cost_cached` 需要 cache_read/cache_write）对齐四档定价，否则 `bill()` 的 by_node/by_edge 与 workflow 账本对不上。`_mark_budget_exceeded` 写 0 的 input/output 属 C3 遗留，本次一并修（补填 usage 或标注「usage 不完整」），否则被预算杀的 run 在 by_node 里 cost 为 0。

### D4 — 动态 route：`$ref` 引用（不执行模型生成代码）

route 的 `when` 从「纯文本标签」扩展为两种匹配源：

- **字面标签**（C2 语义保留）：`when: "APPROVED"` → 行首匹配（`matches_route` 保留）。
- **`$ref` 引用**（新增）：`when: "$ref:node_id:slot"` → 读取已落盘/已声明的上游结果槽。语法 `$ref:<node_id>:<slot>`，`node_id`/`slot` 都必须是已声明节点/槽（`parse_workflow_spec` 校验期可查），运行时解析只读 `NodeState.slots`（不落盘、不读文件）。

**判定语义（Q1/Q2 联合确认）**：`$ref:node_id:slot` 解析出槽值 → **取首个非空行（`_first_non_empty_line` + strip）→ 作为期望标签 → `matches_route(上游数据文本, 该标签)`**。即「用上游一个字段的值，决定按哪条标签去匹配上游产出」；`$ref` 与字面标签 case 按声明顺序匹配。**判定前不调 `WorkflowAggregator.bounded`**（`bounded` 会追加 `…[bounded...]` 让标签永远不命中），`bounded` 只用于诊断展示。

**安全边界**：`$ref` 的值必须来自**已声明的 result_ref 键或 slots**，校验强度为「节点存在 + 槽已声明（含隐式 `result` 槽）」，**不把数据可达性作 schema 硬条件**（Q3 确认）；运行时槽缺失**静默视为未命中走 default**，不报错，但 diagnostics 记录 ref 未命中原因——保持 C2 的「受限可校验、不执行模型生成代码」边界。

### D5 — 动态 foreach：跨层 source + max_items=0

- **跨层 source**：`source` 从「一层上游」（C2 的 `_validate_kind_specific` 只查 `source in index`）扩展为「沿数据边递归解析」（Q10 确认）。**只沿数据边递归**；优先读 source 节点自身 `result` 槽，没有才在**唯一数据上游**时继续向上；多入边无物化 result = schema 歧义拒绝；递归在无上游/已访问/环处终止。环回边检测复用现成的 Tarjan SCC（`_strongly_connected_components`），在 `parse_workflow_spec` 校验期（`_validate_cycles` 附近，需要 `edges`，不能只在 `_validate_kind_specific(index)`）。**`source_field` 只应用一次**——解析得到基础值后只调用一次 `extract_collection(value, source_field)`，不再同时传给 `_node_output` 和 `extract_collection`（否则二次取字段）。
- **max_items=0**（Q9 确认）：语义从「空集合」改为「**不静态截断，展开到预算耗尽为止**」。需要给 `max_items` 单独的非负解析函数（不能改 `_positive_int` 的全局语义）。foreach 预检**按剩余容量截断而非抛 C2 异常**，且**只对 `max_items==0` 生效**（`max_items>0` 保留 C2 fail-fast，否则会静默删除结构闸并打破既有断言）；**截断发生在 `_expand_plan` 之前**（`_execute_foreach` 次序是 `_resolve_items`→`_expand_plan`→`_check_foreach_budget`）。可展开数取「C4 `max_total_runs` / C2 `max_runs` / C2 `max_nodes`」三者剩余上限的**最小值**。**校验期仍要求 `items`/`source` 二选一**（`max_items=0` 不等于「无集合」）。

### D6 — 配置：`WorkflowBudgetConfig` 嵌套挂 `workflow` 下

新增 frozen `WorkflowBudgetConfig`（`max_total_tokens` / `max_total_cost_usd` / `max_total_runs` / `max_wall_time_s`），挂 `WorkflowLimitsConfig.budget`；`_parse_workflow_limits` 增 `_parse_workflow_budget` 逐字段解析（复用 C3 的 `_parse_aggregation` 同款纪律）。默认值：200000 / 5.0 / 300 / 1800。**`max_total_runs` 默认值与 C2 `max_runs` 一致（300）**，避免「声明期 300 但运行期 200」的误伤。

**0/null 语义（Q11 确认）**：四个预算字段**均 `0 = 不限`**——需要新增 workflow-budget 专用的非负解析函数（`_validate_positive_int`/`_parse_positive_float` 在数值层拒绝 0，不能改全局语义）；缺省用 D6 默认值；显式 `null` **拒绝**（避免 YAML 缺值意外关闭安全闸）。**`max_total_runs=0` 只解除 C4 的 runs 维度，C2 `max_runs` 仍是结构闸**（Q14 确认），要真正放宽须同时调 `spec.max_runs`。

### D7 — 归因与 envelope 暴露

`status()` envelope 增：
- `budget`: `{dimensions: {tokens: {limit, used}, cost_usd: {...}, runs: {...}, wall_time_s: {...}}, exceeded: bool, exceeded_dimension: str|null}`。
- `attribution`: 四维账单的 bounded 摘要（每维 top-k，k=5）——**不整表返回**（100 节点的 by_node 整表会撑爆父上下文，与 C3 的 bounded envelope 同口径）。

**精度/单位/确定性（Q16 确认）**：① 分桶值 round 位数**与 envelope `total_cost` 对齐为 9 位**；② tokens 口径 = **input + output（不含 cache）**（与 `CostLedger.bill()` 今日 `tokens` 口径一致），cache 单独可选暴露；③ cost 单位 USD；未知模型（`CostEstimate.known=False`）加 `estimated: true` 标记，不静默混入已知模型桶。

**attribution 落盘（Q15 确认）**：`_teardown()`/`run()` 结算时把本 workflow 的 attribution 快照经新增 `WorkflowStore.save_attribution(workflow_id, payload)` **一次性落盘**；`GetWorkflow` 的 `_DETAILS` 扩为含 `"attribution"`，返回 `attribution_ref`，父按需 `ReadWorkflowResult` 读（与 C3 的 bounded/result_ref 口径一致）。

## Pre-Implementation Review

> 本 change 为架构级改造（预算 enforcement 跨 manager/scheduler/loop 三层 + 成本归因 schema 扩展），实现前需按 AGENTS.md 走 `batch-grill-me`（或等价独立 subagent 设计追问）审视本 design.md 的 D1–D7，逐项确认实现细节、依赖、风险与测试策略，产出结构化决策记录到 `reviews/grill-design.md`，并经停轮确认（grill-confirmation-gate）。本节为占位声明，实际 review 记录以 `reviews/grill-design.md` 为准。

## Risks / Trade-offs

- **风险**:token/cost 预算超限是「完成后判定」，单个超大 LLM 调用可能突破预算上限 → 接受（调用已发出无法中途掐断；单 run `max_tokens` 仍可兜底单个调用的上限）。
- **风险**:四维预算与 C2 三闸（`max_runs`/`max_nodes`/`recursion_limit`）量纲重叠 → 明确分工：C2 三闸是声明期结构闸（fail-fast），C4 四维是运行期资源预算（drain）；`max_total_runs` 与 `max_runs` 语义分开、默认值一致。
- **风险**:`$ref` 引用让 route 判定依赖跨节点的状态 → 只读 `NodeState.slots`（已落盘/已声明），不读文件、不执行代码，保持受限边界。
- **Trade-off**:归因四维让 `CostLedger.record` 签名变长 → 归因键全可选（默认 None 不改变既有三维护账单，向后兼容）。
- **Trade-off**:budget envelope 只给 top-k 摘要 → 完整归因走 result_ref，父按需 inspect（复用 C3 的 `ReadWorkflowResult`）。

## Testing Strategy

- 四维度预算：token 超限 stop_new、cost 超限 stop_new、runs 超限预扣拒绝、wall_time 超限 drain；每维超限后根节点 `budget_exceeded`。
- 归因：by_workflow 一个 workflow 聚合、by_node 找出最贵节点、by_depth 找出重复 token 最多的层、by_edge 找出最贵拓扑边。
- 动态 route：`$ref` 命中/未命中/default 兜底；slot 无键不报错。
- 动态 foreach：跨层 source 解析、环回边拒绝、`max_items=0` 展开到预算耗尽。
- 兼容：`CostLedger.record` 不带归因键时 by_session/by_phase/by_tool 三维不变；C2 的 `max_runs` 声明期校验不变。
- 全量 pytest 绿 + benchmark smoke + OpenSpec validate + artifact checker。
