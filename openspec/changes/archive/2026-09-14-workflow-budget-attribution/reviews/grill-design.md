# Grill: workflow-budget-attribution 设计追问

## Reviewer

- run id: grill-workflow-budget-attribution-2026-09-14
- 时间: 2026-09-14
- 对象: `openspec/changes/workflow-budget-attribution/design.md` D1–D7
- 基线: C3 `workflow-result-aggregation` 已合入（`agent/subagent/{workflow_budget 未建,aggregation,workflow_store,scheduler,manager}.py`、`agent/cost_tracker.py`、`agent/config.py`、`agent/tools/builtin/subagents.py`、`tests/agent/subagent/*`）

## Confirmed Decisions

以下 9 条是本审阅员**读代码后可自行收敛**的结论（不需要用户拍板），实现时必须按此写，否则会与既有代码/测试事实冲突。

- **决策**: **design.md 里的 file:line 断言整体是 C3 落地之前的旧行号，实现时一律以当前代码行为准，不要按 design 里的数字定位。** 逐条核对结果（design/prompt 引用 → 当前实际）：`budget.py:86-94` `after_llm_call` → 正确（`agent/subagent/budget.py:86-94`）；`scheduler.py:517` 的 `self._runs + cost > spec.max_runs` → 实际在 `agent/subagent/scheduler.py:716`（517 行现在是 `run()` 里 `except GraphRecursionError` 的注释）；`scheduler.py:1092-1126` `_envelope` → 实际 `agent/subagent/scheduler.py:1502-1556`；`scheduler.py:182-197` `matches_route` → 实际 `agent/subagent/scheduler.py:208-223`；`scheduler.py:200-223` `extract_collection` → 实际 `agent/subagent/scheduler.py:226-249`；`scheduler.py:1051` `_route_verdict` → 定义在 `agent/subagent/scheduler.py:1420-1430`、调用点在 `:894`；`manager.py:585-595` `_new_run` 固定身份字段 → 实际 `agent/subagent/manager.py:629-632`（函数体 605-635）；`manager.py:57-62` `SubagentRunUsage` → 实际 `agent/subagent/manager.py:73-79`；`manager.py:935` `session_id=session.subagent_id` → 实际 `agent/subagent/manager.py:972`；`loop.py:680-687` `cost_ledger.record` → 实际 `agent/loop.py:679-687`。唯一仍然准确的旧引用是 `workflow.py:574-578`（`_parse_cases` 的 when/to 校验）与 `workflow.py:535-536`（`_parse_max_items`）。来源: grill-workflow-budget-attribution-2026-09-14

- **决策**: **D2 的「stop_new 复用 C2 `_accepting` 语义」在代码里不成立——`_accepting` 今天不 gate 派发，只 gate 级联复位。** `_accepting` 的全部读点只有一处：`_on_node_finished` 里 `if not self._accepting: return`（`agent/subagent/scheduler.py:813`），作用是阻止节点收尾时把下游从终态复活；它的写点是 `cancel()`（`:473`）、`run()` 的异常分支（`:519`）、`_teardown()`（`:556`）、`_drive`/`_run_node` 的图级闸门分支（`:614`、`:783`）。主循环 `_drive` 的派发路径是 `ready = self._ready_nodes()` → `for state in ready: self._dispatch(state)`（`agent/subagent/scheduler.py:585-602`），`_ready_nodes`（`:674-693`）与 `_dispatch`（`:711-761`）都不读 `_accepting`；真正能停派发的现成闸是 `_cancelled`（`:581` 在循环顶部、`:1254`/`:1258` 在 `_acquire_slot`）。所以预算超限的 stop_new 必须显式新增一处检查（在 `_drive` 顶部或 `_dispatch` 开头），不能只置 `_accepting=False` 就以为停了。来源: grill-workflow-budget-attribution-2026-09-14

- **决策**: **cost 维度不能从 `SubagentRunRecord.usage` 反算——run 记录今天丢掉了 cache tokens。** `SubagentRunUsage` 只有 `total_tokens`/`tool_calls`/`input_tokens`/`output_tokens` 四个字段（`agent/subagent/manager.py:73-79`），而 `compute_cost_cached` 的签名要求 `cache_read_tokens` + `cache_write_tokens`（`agent/cost_tracker.py:66-72`）。上游其实有数据：`RunResult.cache_read_input_tokens` / `cache_creation_input_tokens`（`agent/result.py:30-31`）在 `_complete_run` 里被显式丢弃（`agent/subagent/manager.py:1079-1084` 只取 total/input/output），`Loop` 自己也在 `token_counters["cache_read"]`/`["cache_creation"]` 累加（`agent/loop.py:674-678`）。更糟的是 `budget_exceeded` 收尾路径只回填 `total_tokens`，input/output 直接写 0（`agent/subagent/manager.py:1194-1195`）。结论：要么扩 `SubagentRunUsage` 带上 cache 两字段并在 `_complete_run`/`_mark_budget_exceeded` 一起填，要么把 cost 记账放在能同时拿到 `response.usage` 与 `Usage.cache_read_input_tokens`（`agent/llm.py:51-52`）的 loop 层。走「run 终态后读 run.usage」这条路在当前代码上算出来的 cost 一定偏低。来源: grill-workflow-budget-attribution-2026-09-14

- **决策**: **归因键不需要「跨 manager 反查 run」，`SubagentSessionRecord` 本身就带全了 workflow_id/node_id/depth。** design D3 说「`session_id` 就是 `subagent_id`，再反查 run 的身份字段」——实际 `session_id` 传的就是 `session.subagent_id`（`agent/subagent/manager.py:972`），而 `SubagentSessionRecord` 自带 `parent_run_id`/`workflow_id`/`node_id`/`depth`（`agent/subagent/manager.py:148-163`），在 `create_subagent` 里一次性从 contextvar 固定（`agent/subagent/manager.py:450-453`）。run 记录上同样的四个字段是 `_new_run` 里独立复制的（`agent/subagent/manager.py:629-632`）。所以取键函数是「`subagent_id` → `manager._sessions[...]` → 三个身份字段」的**一次查表**，不需要遍历 `session.runs` 找 active run——后者在 foreach 场景下还有「一次展开 N 个 session，每个 session 只有一条 run」的额外复杂度。附注：foreach 展开项复用容器节点的 `node_id`（`_launch_run` 里 `set_node_id(node.id)`，`agent/subagent/scheduler.py:1129`；`_run_foreach_item` 传 `reuse_state=None`，`:977-983`），所以 N 个展开项的 `node_id` 都等于 foreach 节点 id。来源: grill-workflow-budget-attribution-2026-09-14

- **决策**: **`depth` 维度今天在 workflow 内必然退化成单一桶——调度器从不设 `spawn_depth`，所有节点拿到的 `depth` 是同一个值。** `set_spawn_depth` 在全仓的非测试代码里只有两个调用点：`agent/subagent/manager.py:786`（`_execute_run_in_context`，用 run 自己的 depth）和定义处 `agent/subagent/context.py:41`；`agent/subagent/scheduler.py` 一次都没调。`_new_run` 的 depth 是 `current_spawn_depth() + 1`（`agent/subagent/manager.py:632`），`_launch_run` 只 set 了 workflow/node/bus 三个 contextvar（`agent/subagent/scheduler.py:1128-1130`）。因此一个从主 loop（depth=0）拉起的 workflow，其**所有**节点的 run.depth 都是 1，嵌套 spawn 再逐层 +1。design D3 想用 by_depth 回答「哪层重复 token 最多」，在当前字段上只会得到「全部 token 都在 depth=1」这一个桶。要做真图深，必须由调度器按执行计划给每个节点设 spawn_depth（可复用 C3 的 `ExecutionPlan` 距离/档位），但那会连带影响 `max_depth` 深度闸（`agent/subagent/manager.py:1051` 按 `run.depth >= max_depth` 摘 spawn 类工具）——这条留给用户拍板口径。来源: grill-workflow-budget-attribution-2026-09-14

- **决策**: **`edge` 无法像 workflow_id/node_id 那样在 `_new_run` 靠 contextvar 推出——没有「上游节点」的 contextvar。** `_new_run` 能固定身份是因为 `agent/subagent/manager.py:629-632` 读的是 `current_workflow_id()`/`current_node_id()`/`current_spawn_depth()` 三个已存在的 contextvar（`agent/subagent/context.py:30-34`）；调度器只 set 了 workflow/node/bus（`agent/subagent/scheduler.py:1128-1130`）。「上游是谁」只在派发点可知：`_execute_subagent`/`_execute_aggregate` 之前是 `self._plan.data_incoming(node.id)`（`agent/subagent/scheduler.py:1364`、`:1386`），foreach 展开项的上游是容器节点的数据入边。所以 tasks 2.3 写的「`_new_run` 时固定」在实现上必须变成「调度器算出 `edge` 字符串、经 `run_subagent(edge=...)` 透传」或「`_new_run` 后由 `_launch_run` 回填」，不能只加 contextvar 了事。来源: grill-workflow-budget-attribution-2026-09-14

- **决策**: **`budget_exceeded` 已经是 envelope 的顶层 int 键，D7 的新 `budget` 键必须与它共存、不能改名或复用该键。** `_envelope` 顶层已有 `"budget_exceeded": units["budget_exceeded_units"]`（`agent/subagent/scheduler.py:1531`，计数来自 `_unit_counts` 的 `agent/subagent/scheduler.py:1494-1495`），既有断言 `assert result["budget_exceeded"] == 0` 写在 `tests/agent/subagent/test_aggregation_runtime.py:461`。同时 `_unit_counts` 已经预留了节点级 `budget_exceeded` 分支，但当前代码**从不**把 `state.status` 写成 `"budget_exceeded"`（全部赋值点：`agent/subagent/scheduler.py:480/561/563/657/743/774/779/785/828/889/909/948/961/964/967/1196/1198/1201/1228`），因为 `_apply_run_status` 把非 completed/cancelled 的 run 状态一律映射成节点 `failed`（`agent/subagent/scheduler.py:1193-1202`），而 run 级的 `budget_exceeded` 确实存在（`agent/subagent/manager.py:1187`）。所以「run 被预算杀」今天在节点层表现为 `failed`，C4 要新增的「节点级 budget_exceeded」是一个全新状态，别忘了把它加进 `TERMINAL_NODE_STATUSES`（`agent/subagent/scheduler.py:64` 目前只有 completed/failed/cancelled/blocked），否则被标 budget_exceeded 的上游会让下游永远 `_data_deps_satisfied == False`（判据在 `agent/subagent/scheduler.py:661-668`）。来源: grill-workflow-budget-attribution-2026-09-14

- **决策**: **D6 的配置必须照 `aggregation` 的先例「嵌套 dataclass + 逐字段 `mapping.get`」落，并且 `_parse_positive_float` 在数值层就拒绝 0。** `WorkflowLimitsConfig` 是 frozen dataclass，`aggregation: AggregationConfig = field(default_factory=AggregationConfig)` 在 `agent/config.py:293`，解析入口 `_parse_workflow_limits` 在 `agent/config.py:1440-1457` 逐字段取值，嵌套解析 `_parse_aggregation` 在 `agent/config.py:1460-1516`（docstring 明写「只给 dataclass 默认值不会让 yaml 生效」）。`max_total_tokens`/`max_total_runs` 走 `_validate_positive_int`（`agent/config.py:1556-1565`，`raw < 1` 直接 ConfigError），`max_total_cost_usd`/`max_wall_time_s` 走 `_parse_positive_float`（`agent/config.py:1568-1585`，int 可被拓宽成 float，但 `value <= 0` 一律 ConfigError）。所以 `max_total_cost_usd: 0` 或 `0.0` 会被配置层直接拒绝——「把某维度设 0 来关掉它」这个用法今天不存在，要支持得改校验。另外 `_parse_workflow_limits` 目前的 `mapping.get("max_runs", 300)` 与 `WorkflowLimitsConfig.max_runs = 300`（`agent/config.py:292`）是两处独立默认值，C4 再引入 `budget.max_total_runs` 就是**第三处 300**，必须一起对齐。来源: grill-workflow-budget-attribution-2026-09-14

- **决策**: **`max_items=0` 在今天的代码里有两个硬阻拦，且 D5 的跨层 source 只校验「节点存在」，不校验数据可达。** 一：`_parse_max_items` 直接复用 `_positive_int`（`agent/subagent/workflow.py:535-536`），而 `_positive_int` 对 `value < 1` 抛 `WorkflowValidationError`（`agent/subagent/workflow.py:400-403`），所以 `max_items: 0` 现在进不了调度器；二：即便放进来，`_resolve_items` 的返回是 `items[: node.max_items]`（`agent/subagent/scheduler.py:1440`），`[:0]` 是空集而不是「不限」。跨层 source 方面，`_validate_kind_specific` 只做 `node.source not in index` 的存在性检查（`agent/subagent/workflow.py:739-743`），环检测函数 `_strongly_connected_components` 已经是现成的 stdlib Tarjan（`agent/subagent/workflow.py:638-687`），`_validate_cycles` 用它判「环上必须有 route」（`agent/subagent/workflow.py:618-635`）——环回边检测如果需要，应复用这两个而不是新写图算法。来源: grill-workflow-budget-attribution-2026-09-14

## Open Questions

- **Q1**: D4 的 `$ref` 到底**跟什么比**？design.md:68 写「`when: "$ref:node_id:slot"` → 读取已落盘/已声明的上游结果槽，与 case 的期望值**精确字符串相等**判定」，但 `RouteCase` 只有 `when` 和 `to` 两个字段（`agent/subagent/workflow.py:83-91`），**没有第三个「期望值」字段**；spec delta 的 Scenario 也只说「`when` 为 `$ref:reviewer:verdict` 且上游 verdict 槽为 "APPROVED" → 命中该 case 的目标边」。
  **场景**: 一张 peer-review 图，`reviewer` 节点产出 `verdict` 槽，`gate` 节点是 route：
  ```json
  {"id": "gate", "kind": "route",
   "cases": [{"when": "$ref:reviewer:verdict", "to": "done"}],
   "default": "producer"}
  ```
  三种读法的行为完全不同：
  - **读法 A（槽值当期望标签）**：解析出的槽值 `"APPROVED"` 作为 `label` 传进 `matches_route(raw_upstream_text, "APPROVED")`（`agent/subagent/scheduler.py:208-223`），即「用上游产出的一个字段决定按哪条标签匹配」。此时 `$ref` 是「条件源的动态化」，`gate` 仍需有上游文本可比。
  - **读法 B（槽值即判定）**：槽值非空/等于某枚举即命中，`state.verdict` 直接写槽值。那 `cases` 列表里多个 case 谁先命中？`to` 又表达什么？
  - **读法 C（缺第三个字段）**：需要把 `RouteCase` 扩成 `{when, expect, to}` 或把 `$ref` 写成 `$ref:node:slot:期望值`，spec 的 `{"when","to"}` 二字段约束（`agent/subagent/workflow.py:570` 的 `set(item) != {"when", "to"}` 是硬校验）要一起改。
  请拍板 `$ref` 的判定语义（A/B/C 哪个），以及 `$ref` case 与字面标签 case 混排时的命中优先级。

- **Q2**: 「`$ref` 解析出的值**先走 `WorkflowAggregator.bounded`** 再做相等判定」（design.md:70）在长值上会**必然判不中**。
  **场景**: `reviewer` 的 `verdict` 槽实际内容是 6000 字的评审意见，第一行是 `APPROVED — 但有三点建议`。`gate` 的 case 期望 `"APPROVED"`。
  - 若**先 bounded 再等值**：`bounded` 按 `plan.budget_for(route_node) * CHARS_PER_TOKEN` 截断（`agent/subagent/aggregation.py:94-101`、`agent/subagent/scheduler.py:1406-1418` 的用法），假设预算 800 token = 3200 字符，截断后文本 = 前 3200 字 + `\n…[bounded; read the full result via result_ref]`，**永远不等于** `"APPROVED"` → 每次都落到 default。
  - 若**先等值再 bounded**（或对短值才等值）：短标签场景正确，但「bounded」就只是给诊断用的展示裁剪。
  - 若**只取首行/首 token 再等值**：需要定义「取哪一段」。
  请拍板 bounded 与相等判定的先后顺序，以及是否需要在相等前做「取首个非空行」之类的归一化（注意 `_first_non_empty_line` 已在 `agent/subagent/scheduler.py:291-297` 存在）。

- **Q3**: `$ref` 的**校验边界**：`parse_workflow_spec` 校验期该查什么、不查什么？design.md:68 说「`node_id`/`slot` 都必须是已声明节点/槽（`parse_workflow_spec` 校验期可查）」。
  **场景**: `{"id": "gate", "kind": "route", "cases": [{"when": "$ref:planner:items", "to": "done"}], "default": "done"}`，其中 `planner` 是已声明节点但其 `outputs` 是 `["plan"]`（没有 `items` 槽），且 `planner` 与 `gate` 之间**没有任何数据边**（`planner` 在另一条支线上）。
  - **只查节点存在**：`planner` 在 `index` 里 → 通过校验。运行时 `NodeState.slots` 里没有 `items` → 按 D4「无键命中 = 不匹配」→ 永远走 default，模型拿不到任何错误信号。
  - **查节点存在 + 槽在该节点的 `outputs` 里**：上例在 `_validate_kind_specific` 的 route 分支（`agent/subagent/workflow.py:729-738`）就能拒绝，反馈明确。但 `outputs` 只是「声明写哪些槽」，aggregate 的实际槽来自上游合并（`agent/subagent/scheduler.py:1321-1339`），可能合法地写出未在 `outputs` 里的槽。
  - **再查数据可达**（`$ref` 的源节点必须是 route 节点的数据上游）：最严格，但路由节点的数据入边集合在 `_validate_kind_specific` 阶段只有 `index` 没有 `edges`（该函数签名是 `_validate_kind_specific(index)`，`agent/subagent/workflow.py:722`），要改签名或在 `parse_workflow_spec` 里另加一道（调用点 `agent/subagent/workflow.py:345`）。
  请拍板校验强度（存在 / 存在+槽 / 存在+槽+可达）与「无键命中静默走 default、还是校验期报错」。

- **Q4**: `max_total_runs`（C4，默认 300）与 `max_runs`（C2，默认 300）**在默认配置下谁先触发**？design.md:50 说两者「默认值一致（300），但一个在声明期 fail-fast、一个在运行期 drain」——可 `max_runs` 的运行期检查也在派发点。
  **场景**: 一张 4 个 subagent 节点的图，`max_runs` 与 `max_total_runs` 都用默认 300，`recursion_limit` 默认 25。跑到第 301 个 run 时（例如 route 回边循环）：
  - `_dispatch` 第一件事就是 `if self._runs + cost > spec.max_runs: raise GraphRecursionError(reason="max_runs")`（`agent/subagent/scheduler.py:716-726`）→ 整图 `_accepting=False` + `_cancel_all_in_flight()` → `_status="graph_recursion_exceeded"`（`:613-619`）。
  - 于是 **C4 的 runs 维度永远没有机会触发** stop_new（drain 语义），envelope 报的是 `graph_recursion_exceeded` + `reason="max_runs"`，不是 `budget_exceeded`。`tests/agent/subagent/test_scheduler.py:506-516`（`test_max_runs_caps_total_runs`，`max_runs=2` + 4 个节点）就是这条路径的既有断言。
  - 另外「两个计数器」还是「一个计数器」也要定：`self._runs` 在 `_dispatch` 按 `cost` 累加（`:746`），并在 `_check_foreach_budget` 里按展开增量预扣（`:1098-1100`，覆盖 `_run_foreach_item` 不经 `_dispatch` 的情形）；若 C4 另起一个 `WorkflowBudget.runs`，两者会在 foreach 预扣路径上漂移。
  请拍板：runs 维度是复用 `self._runs` 还是独立计数器；默认值是否错开（例如 `max_total_runs` 只在显式配置时生效，或抬高默认）；超限出口走 `graph_recursion_exceeded` 还是 `budget_exceeded`。

- **Q5**: 超限后「根节点标 `budget_exceeded` 终态」（design.md:48）与 `_teardown` 的「pending → blocked」**是两条互相覆盖的路径**，且 `_status` 由谁写没定义。
  **场景**: 一个 3 层图，token 预算在第 2 层某节点后耗尽，此时第 3 层的 2 个节点还在 `pending`、有 1 个在 `started`。
  - `_teardown`（`agent/subagent/scheduler.py:554-572`）会把 `queued`/`started` 取消、把 `pending` 全部标 `blocked` 并写 reason「workflow ended before the node became ready」。如果根节点此刻是 `pending`，它会被写成 `blocked`，`budget_exceeded` 根本没机会落。
  - `_unit_counts` 把 `blocked` 与 `budget_exceeded` 分开计（`agent/subagent/scheduler.py:1494-1497`，`tests/agent/subagent/test_aggregation_runtime.py:461-466` 断言这两个键都存在），所以最终父 agent 会在 envelope 里同时看到 `blocked: 3` 和 `budget_exceeded: 0`——与 spec delta「根节点 SHALL 标记 `budget_exceeded`」的措辞不符。
  - `_status` 也没定：D2 末尾说「envelope 里 `status="budget_exceeded"`」，但 `_drive` 的收敛出口有两条会覆盖它——`dispatched == 0 and self._in_flight_nodes == 0 → self._status = "completed"`（`:608-611`）与 `_cancelled → "cancelled"`（`:581-583`）。
  请拍板：`budget_exceeded` 标在**哪个**节点（根/所有未派发节点/最后一个完成的节点）；它与 `_teardown` 的 `blocked` 谁优先；`_status` 在 `_drive` 收敛时如何保持成 `"budget_exceeded"`。

- **Q6**: token/cost 预算的**记账点**选哪个 hook？design.md:39 提到复用 `BudgetHook.after_llm_call`，但那是 per-run hook。
  **场景**: 一个 5 节点图，每个节点的 run 内 LLM 调 3 次，共 15 次调用，每次都产生 `usage`（input/output/cache_read/cache_creation，`agent/llm.py:47-52`）。
  - **方案 A（复用 `BudgetHook`）**：`BudgetHook` 由 `_build_subagent_loop(..., budget=tracker)` 挂到子 loop（`agent/subagent/manager.py:1043-1045`），tracker 是 **run 级** `BudgetTracker`（`agent/subagent/manager.py:960-964`）。要让 workflow 账本也在 `after_llm_call` 里累加，就得把 workflow 账本对象也传进 `_build_subagent_loop`——但那时子 loop 跑在 run 的上下文中，`current_workflow_id()` 可用（contextvar 经 `copy_context()` 传递，`agent/subagent/manager.py:666`），勉强可行，代价是 manager 要知道 workflow 账本（新增耦合）。
  - **方案 B（loop 层记账）**：在 `agent/loop.py:679-687` 的 `cost_ledger.record` 旁边同步累加——这里同时有 `response.usage`（含 cache tokens）与 `self.subagent_manager`（`agent/loop.py:151`），`session_id` 就是 subagent_id，且 workflow 身份可由 `current_workflow_id()` 得到。改动面最小、口径与 `record` 完全一致，但要注意根 loop（workflow_id 为 None）不能误记账。
  - **方案 C（run 终态结算）**：在调度器 `_await_run` 拿到 envelope 后读 `run.usage` 累加。**这条路当前算不了 cost**——见 Confirmed Decision 第 3 条（cache tokens 被丢弃）；且 `budget_exceeded`/`cancelled` 收尾的 run 的 usage 是残缺的（`agent/subagent/manager.py:1194-1195`）。
  另需一并拍板：**排队中的 run 与 resume 的 run** 是否计入 workflow 预算（`run_subagent(wait=false)` 的排队窗口不烧 token，但 resume 会重跑整段 transcript）。
  请拍板记账点（A/B/C）与四个维度的记账语义（是否含排队期、resume 是否重复计入）。

- **Q7**: `by_depth` 的「depth」是**spawn 嵌套深度**还是**图距 leaf 层数**？（现状见 Confirmed Decision 第 5 条：workflow 内所有节点的 run.depth 恒为同一个值。）
  **场景**: 一张 leaf→shard→domain→root 的四层汇聚图（C3 的自动分层会真的插出这三层，`agent/subagent/aggregation.py:126-152`）。跑完后查 `bill()["by_depth"]`：
  - **口径 X（现状 spawn depth）**：输出 `{"1": {tokens: 全部, cost: 全部}}`——一个桶，回答不了「哪层重复 token 最多」。
  - **口径 Y（图距）**：输出 `{"0": {...leaf...}, "1": {...shard...}, "2": {...domain...}, "3": {...root...}}`，正好对上 C3 的四档预算 `leaf/shard/domain/root`（`agent/subagent/aggregation.py:144-152` 的 `budget_for_distance` 已经是这个口径）。但实现上要么在 run record 里存一个新字段（不复用 `depth`），要么让调度器按图距离 set `spawn_depth`——后者会改变 `max_depth` 深度闸的行为（`agent/subagent/manager.py:1051`：`depth >= max_depth` 时子 agent 摘掉 spawn 类工具，`SPAWN_TOOL_NAMES` 在 `agent/subagent/manager.py:319-326`）。一张 4 层图会让最深层节点的子 agent 直接失去 spawn 能力（默认 `max_depth=3`，`agent/config.py:319`）。
  请拍板 depth 口径，以及若采用 Y 是否接受「图深影响 spawn 深度闸」这个副作用（或改为独立字段、不动 `spawn_depth`）。

- **Q8**: `edge` 的取值规则：**多数据入边节点取哪条？foreach 展开项的 source 是谁？入口节点怎么写？**
  **场景 A（多入边）**: `join` 是 aggregate，数据入边有 3 条（`a→join`、`b→join`、`c→join`，`reducer="concat"`）。`SubagentRunRecord.edge` 是**一个**字符串字段（design.md:59、tasks 2.3），那么 join 的那次 run 的 edge 是 `"a->join"` 还是 `"a,b,c->join"` 还是三条边各记一次？
  **场景 B（foreach）**: `fan` 是 foreach，数据入边 `planner→fan`，展开 5 项。5 个展开项各自的 run 记录的 edge 应该都是 `"planner->fan"`，还是 `"planner->fan#3"`（带下标）？注意展开项的 `node_id` 全部等于 `"fan"`（`agent/subagent/scheduler.py:982` 的 `session_name` 只改 session 名，`set_node_id(node.id)` 仍是容器 id，`:1129`）。
  **场景 C（入口）**: 一个没有数据上游的 leaf 节点（`l0` 直连 `root`），design.md:59 说入口节点 source 落 `"<root>"`——那 `by_edge` 分桶里会出现 `"<root>->l0"` 这个字面串。是保留这个哨兵值，还是用空 source + 别的表示（例如 `"->l0"`）？
  **场景 D（route 控制边）**: route 节点的出边是控制边、不传数据（`agent/subagent/workflow.py:209-211`、`agent/subagent/scheduler.py:817-822`），被 route 激活的下游 run 的 edge 是记 route→下游、还是记它的数据上游？
  请拍板四种情形的 edge 取值规则（这会直接决定 `bill()["by_edge"]` 的键集合与可读性）。

- **Q9**: `max_items=0` = 「展开到预算耗尽」的**落地细节**：0 该不该被 `_positive_int` 放行，以及「预算耗尽」以谁为准？
  **场景**: 一个 `foreach(source="planner", source_field="items", max_items=0)` 节点，`planner` 产出 500 项，图级 `max_runs`/`max_total_runs` 默认 300、`max_nodes` 默认 200。
  - `parse_workflow_spec` 今天直接拒：`_positive_int(0)` 抛 `WorkflowValidationError`（`agent/subagent/workflow.py:400-403`、`:535-536`）。放行 0 需要给 `max_items` 单独一个「0 = 不限」的解析函数（不能改 `_positive_int` 的全局语义，它也服务 `max_routes`/`recursion_limit`/`max_nodes`/`max_tokens`）。
  - `_resolve_items` 的 `items[: node.max_items]`（`agent/subagent/scheduler.py:1440`）要改成 0 时不分片。
  - 「预算耗尽」的实际闸在哪？`_check_foreach_budget` 会在展开**前**预检 `self._runs + delta > spec.max_runs` 并直接 `raise GraphRecursionError`（`agent/subagent/scheduler.py:1074-1085`）——也就是说 500 项会**先撞 max_runs 抛异常终止整图**，根本走不到「按 max_total_runs 慢慢 drain」的语义。若要让 `max_items=0` 真的「展开到预算耗尽为止」，得让预检在 `max_items=0` 时退化为「按剩余预算截断 items」而不是抛错（`delta` 与 `max_nodes` 复检同理，`:1086-1097`）。
  - 另注意 `max_items` 的默认值是 20（`agent/subagent/workflow.py:116`、`:469`），所以「用户不写 max_items」= 20 而不是无限，`max_items=0` 是唯一的无限通道。
  请拍板：`max_items` 是否放行 0；`max_items=0` 时预检是「抛错」还是「按剩余预算截断」；以及无限展开的最终上限由 `max_total_runs` 还是 `max_runs` 兜底。

- **Q10**: D5 的「跨层递归解析」**递归到什么深度、取哪个槽**？
  **场景**: `planner` → `fan`（foreach，`source="planner"`, `source_field="items"`）→ `join`（aggregate）→ `fan2`（第二个 foreach，`source="join"`, `source_field="items"`）。
  - 现状 `_resolve_items` 只取 `self._states[node.source]` 的直接产出（`agent/subagent/scheduler.py:1437-1439`），而 `_node_output` 对非 subagent 节点优先返回它自己的 `state.slots[slot]`，否则**向下回退到它上游的槽**，最后才回退到 `state.summary`（`agent/subagent/scheduler.py:1341-1349`）——也就是说「一层跨层」今天已经靠这个 fallback 偶然生效了（`tests/agent/subagent/test_scheduler.py:768-796` 的 `test_foreach_consumes_upstream_collection` 走的是直接上游）。
  - 设计说的「先递归 resolve 上游的 `result` 槽再取 `source_field`」（design.md:74）到底指：沿数据边一路向上直到找到第一个有该槽的节点？还是只向上走一层？递归的终止条件是什么（无数据入边？还是遇到环）？
  - 环回边检测放哪：`_validate_kind_specific` 只有 `index` 没有 `edges`（`agent/subagent/workflow.py:722`），要用 SCC 就得改签名或挪到 `parse_workflow_spec` 的 `_validate_cycles` 附近（`agent/subagent/workflow.py:343-345`）；而且 `_validate_cycles` 今天允许「环上有 route」，所以「source 在 route 参与的环里」要单独判定。
  - `extract_collection`（`agent/subagent/scheduler.py:226-249`）对 `None` 返回 `[]`、对 dict 会挑 `items/results/tasks/list` 四个键——递归解析出来的值交给它时，`source_field` 还要不要二次应用（今天 `_resolve_items` 同时把 `source_field` 传给 `_node_output` 和 `extract_collection`，两处都用了它）？
  请拍板递归定义（终止条件、取哪个槽）、环检测的位置与判据、以及 `source_field` 的应用次数。

- **Q11**: 四维预算的**「关闭/0 值」语义**：`max_total_cost_usd` 与 `max_wall_time_s` 能不能设 0 表示「不限」？
  **场景**: 本地跑 benchmark 时用 `deepseek-v4-flash`（价格表里四档全 0，`agent/cost_tracker.py:32`，注释明写「all zeros -> reported as $0.00」），用户想把 cost 维度关掉，写：
  ```yaml
  subagents:
    workflow:
      budget:
        max_total_cost_usd: 0
        max_wall_time_s: 0
  ```
  今天的配置层会直接拒绝：`_parse_positive_float` 对 `value <= 0` 抛 `ConfigError`（`agent/config.py:1582-1584`）；`max_total_tokens: 0`/`max_total_runs: 0` 同理走 `_validate_positive_int` 拒绝（`agent/config.py:1562-1564`）。
  - **方案 A（不支持 0）**：四个维度恒为强约束，用户只能填极大值来「近似关闭」。
  - **方案 B（0 = 不限）**：需要为这四个字段单独写解析函数（不能改 `_validate_positive_int`/`_parse_positive_float` 的全局语义，它们还服务 `subagents.budget.*`、`subagents.workflow.*` 等既有键），并让 `WorkflowBudget` 的判定把 0 当「维度关闭」。
  - **方案 C（用 null/缺省 = 不限）**：不写该键 = 关掉；要区分「不写」与「写默认值」就得让 dataclass 的默认值变成 `None`，与 D6 表里给的 200000/5.0/300/1800 默认值冲突。
  请拍板 0 / null 的语义，以及四个维度的默认值是否仍然全部生效（尤其 cost：`max_total_cost_usd=5.0` 对一个 100-leaf 的 claude-opus 图，5 美元大约只够跑几十万 token，可能一上来就触发 stop_new）。

### 审阅员补充的 Open Questions（Q12–Q16）

以下 5 条是审阅员在核对 design/tasks/spec 与代码事实时发现的**「该问但原 grill 没问」**的设计点，均为原 11 条未覆盖的完整性缺口。每条同样配具体场景与推荐（标注「审阅员补充」），最终仍需用户在 `## User Confirmation` 拍板。

- **Q12（审阅员补充）**: 成本归因的**记账口径一致性**——C4 的 workflow 账本（Q6 方案 B，从 `response.usage` 全额记 input/output/cache）与**既有的 per-run `SubagentRunUsage`**（无 cache 字段，且 `budget_exceeded` 收尾把 input/output 写 0）会给出**两套不一致的 cost**；以及 `CostLedger.record` 今天**不带 cache 参数**（`compute_cost` 是 input/output 二档，`agent/cost_tracker.py:58-63`），Q6 方案 B 要记 cache-aware cost 就得改 `record` 签名。
  **场景**: 一个 5 节点图，某 run 在 LLM 调用后被预算杀（`_mark_budget_exceeded`），它实际烧了 input=12000 / output=800 / cache_read=40000。三种口径的 cost：
  - **workflow 账本（Q6 方案 B）**：按 `response.usage` 四档全算 → 正确值。
  - **run.usage（今天的 `SubagentRunUsage`）**：`_mark_budget_exceeded` 写 `input_tokens=0, output_tokens=0`（`agent/subagent/manager.py:1194-1195`），`_complete_run` 也丢 cache（`:1079-1084`）→ cost 严重偏低甚至为 0。
  - **`CostLedger.record`**：今天签名只有 `model`/`input_tokens`/`output_tokens`（`:141-150`），走 `compute_cost` 二档 → cache 部分被忽略，cost 偏低。
  结果：**同一张 envelope 里会同时出现两个互相打架的数字**——D7 的 `budget.dimensions.cost_usd.used`（来自按 `response.usage` 记账的 workflow 账本，= 正确值）与 D7 的 `attribution.by_node[...].cost`（来自 `CostLedger.bill()`，cache 被忽略 + 被预算杀的 run 记 0，= 偏低值）。两处都写「cost_usd」，父 agent 无法判断该信哪个。
  请拍板：① workflow 账本与 `CostLedger` 是**同一份**还是**两份**账（若是两份，envelope 里以谁为准、是否要显式标注）；② `CostLedger.record` 是否扩 cache 参数以对齐四档定价；③ `_mark_budget_exceeded` 是否补填真实 input/output/cache（今天写 0 是 C3 遗留）；④ 若坚持两份账，D7 是否需要在 envelope 里显式区分（如 `cost_usd_budgeted` vs `cost_usd_attributed`）。

- **Q13（审阅员补充）**: `by_depth` 的**图距字段落在哪、由谁算**（Q7 已定「用独立图距字段」，但没定实现路径）。
  **场景**: 一张 leaf→shard→domain→root 图，`ExecutionPlan` 已经为每个节点算好 `budgets[node_id]`（`agent/subagent/aggregation.py:451` 经 `budget_for_distance` 得到），图距是**调度器侧**的知识；而 Q6 的记账发生在 **loop 层**（`agent/loop.py:679-687`），loop 层只有 contextvar（workflow_id/node_id/depth），**没有图距**。
  - **路径 X（`SubagentRunRecord` 增字段）**：在 `manager._new_run` 读一个新 contextvar `graph_distance`（由调度器在 `_launch_run` 里 set，与 `set_node_id` 同处，`scheduler.py:1128-1130`）——需要新增一个 contextvar + 调度器 set 点，改动面同 C1 身份字段的既有模式（`agent/subagent/context.py:30-34`）。
  - **路径 Y（账本按 node_id 反查）**：loop 层记账时用 `current_node_id()` 反查 `ExecutionPlan.budgets`——但 `ExecutionPlan` 属调度器私有，loop/manager 拿不到，需要把 plan 或「node_id → 图距」映射挂到 manager（新增耦合）。
  请拍板路径 X 还是 Y（推荐 X：与 C1 三个身份 contextvar 同模式，落点最清晰、不动 manager↔scheduler 的依赖方向）。

- **Q14（审阅员补充）**: **`max_total_runs=0`（Q11 的「不限」）与 C2 `max_runs` 的叠加语义**——Q4 已定「复用 `self._runs` 作唯一计数器」，因此 C4 的 runs 维度设 0 时，C2 的 `max_runs`（默认 300）**仍然生效并独自兜底**；这会不会与用户「设 0 = 无限跑」的直觉冲突？
  **场景**: 用户想跑一个「预算只卡 token、不管 run 数」的图，写：
  ```yaml
  subagents:
    workflow:
      budget:
        max_total_runs: 0      # 期望：不卡 run 数
        max_total_tokens: 200000
  ```
  但 spec 里 `max_runs` 缺省仍是 300（`agent/subagent/workflow.py:37` 的 `DEFAULT_MAX_RUNS`），`_dispatch` 仍会在第 301 个 run 抛 `GraphRecursionError(reason="max_runs")`（`scheduler.py:716-726`），envelope 报 `graph_recursion_exceeded`——用户的「不限」并没有实现。
  - **选项 A**：文档明写「`max_total_runs=0` 只解除 C4 的 runs 维度，C2 `max_runs` 仍是结构闸；要真不限须同时调大 `spec.max_runs`」（最诚实，改动最小）。
  - **选项 B**：`max_total_runs=0` 时若 spec 未显式写 `max_runs`，则把生效上限抬到无界（改 `_dispatch` 判定）——语义更顺，但引入「配置隐式改写 spec 结构闸」的特例。
  请拍板 A/B（推荐 A，并在 spec 场景写明「0 不解除 C2 结构闸」）。

- **Q15（审阅员补充）**: D7 的「`GetWorkflow` detail 返回完整 attribution（走 result_ref 落盘）」——**谁在何时把 attribution 写成落盘件？** design D7 / tasks 5.2 只写了「返回完整 attribution」，没写落盘载体与时序。
  **场景**: 一个 workflow 结束后，父 agent 调 `GetWorkflow(detail=...)` 想看完整 by_node 账单。现状：`GetWorkflow` 的 `_DETAILS = ("summary", "nodes", "events")`（`agent/tools/builtin/subagents.py:644`）**没有 attribution 档**；attribution 来自 `CostLedger.bill()`（内存）而非 `WorkflowStore`（落盘），而 `WorkflowStore` 只有 `save_result`/`save_summary`/`save_transcript`/`append_event`（`agent/subagent/workflow_store.py:106-126`），**没有 save_attribution**。且 `CostLedger` 是**跨 workflow 共享**的实例（`manager.cost_ledger`，`manager.py:1065` 传给每个子 loop），不按 workflow 隔离。
  - **方案 A（新增落盘件）**：`_teardown()` 结算时把本 workflow 的 attribution 快照经 `WorkflowStore.save_attribution(...)` 落盘，`GetWorkflow` 新增 `detail="attribution"` 返回 result_ref。
  - **方案 B（不落盘、实时算）**：`GetWorkflow` 直接读 `CostLedger.bill()` 并按 workflow_id 过滤——但 `bill()` 今天**没有 by_workflow 维度**（`agent/cost_tracker.py:168-187` 只有 by_session/by_phase/by_tool），且共享 ledger 需要按 workflow 过滤，D3 的 by_workflow 分桶正是为此——需确认 by_workflow 的键来源。
  请拍板落盘时机（workflow 结束时一次性 / 实时）与载体（新增 store 文件 / 复用 bill 过滤），并确认 `detail` 的合法值集合是否扩到含 `attribution`。

- **Q16（审阅员补充）**: 归因/预算数值的**精度、单位与确定性**——by_edge/by_node/by_depth 的分桶值 round 到几位？tokens 是否含 cache？cost 是 USD 还是别的单位？与 C3 既有口径是否一致？
  **场景**: 同一个 workflow 的结果里，父 agent 同时看到：
  - envelope 顶层 `total_cost`：`round(self._ledger_total() - self._cost_before, 9)`（`agent/subagent/scheduler.py:1540`）——**9 位小数**。
  - `_envelope` 的 `critical_path_s`：`round(..., 6)`（`:1539`）——**6 位**。
  - D7 的 `attribution` 摘要：design.md:85 写「值 round 到 **6 位**小数」——**6 位**，与同 envelope 的 `total_cost` 不一致。
  - `CostLedger.bill()` 今天的桶值是 `{"tokens": int, "cost": float}`，cost 是 `compute_cost` 的原始 float（无 round，`agent/cost_tracker.py:168-187`）。
  三个字段三种精度，且 D7 的 attribution 是**新口径**，父 agent 若做 `sum(by_node.cost)` 与 `total_cost` 对账会因 round 位不同而出现 ±1e-6 级差异。
  请拍板：① 四维分桶值的 round 位数（与 `total_cost` 的 9 位对齐还是保持 6 位）；② tokens 口径是否 = input+output（**不含** cache read/write，与 `bill()` 今天的 `tokens` 口径一致）还是含 cache；③ cost 单位（USD，与 `format_cost` 一致）与「模型未知时 `CostEstimate.known=False`」的桶如何标注（今天 `bill()` 把 `cost is None` 的记录跳过，`agent/cost_tracker.py:181-182`；`compute_cost_cached` 则用表均值估算并标 `known=False`，`agent/cost_tracker.py:86-92`——两者语义不同）。

## Codex Recommendations（codex 独立评审，2026-09-14）

以下 11 条是 codex 独立评审（agent `bd89981d`）对 Q1–Q11 的**推荐答案**。主 agent 已把它们作为「codex 推荐」标注进停轮确认，最终以用户在 `## User Confirmation` 的逐条答复为准。

**审阅员 meta-review 注记（2026-09-14）**：本审阅员（独立 grill meta-review，零记忆）已逐条核对 Q1–Q11 推荐与代码事实，并在每条下补「审阅核实」注记（引用的 file:line 均已先 Read 再写）。Q4/Q9 两条推荐做了**自洽性修订**（标注「审阅员修订」，只改推荐之间的内部一致性，未替用户拍板）。另补充 Q12–Q16 五条遗漏的 Open Question 及推荐（见本节末尾）。

**自洽性结论（修订版）**：11 条推荐**除 Q1↔Q2 外**互相自洽（交叉点核验见各条注记与「审阅员交叉核验小结」）。**Q1 与 Q2 之间存在一处真实的语义冲突**（`$ref` 槽值当 label 还是当被匹配文本），它不是任一单条推荐能自愈的，已标注为「必须由用户在 Q1 拍板后统一」，并连同 design D4 一起列入「待用户确认后回写」清单。

- **Q1 推荐（选 A）**：`$ref` 槽值作为**期望标签**，传入 `matches_route`（`RouteCase` 仍只 `when`/`to` 两字段，`workflow.py:83-91`）；`$ref` 与字面标签 case 按声明顺序匹配。代价：`$ref` 不表达「槽值即布尔判定」，多 `$ref` case 优先级须用户显式排列。
  - 审阅核实（审阅员）：`_execute_route` 确按 `node.cases` 声明序逐个 `matches_route`、命中即 `break`（`agent/subagent/scheduler.py:891-909`）→「按声明顺序匹配」与现状一致；`RouteCase` 确为 `{when, to}`，`_parse_cases` 硬校验 `set(item) != {"when", "to"}`（`agent/subagent/workflow.py:83-91`、`:570`）→ 读法 C 需要改 schema，读法 A 不需要。**补充待写明的一点**：读法 A 下被匹配的文本仍来自 `_route_verdict` 的「数据上游 `result` 槽拼接」（`scheduler.py:1420-1430`），`$ref:node:slot` 的 `slot` 只提供 label——即 `$ref` 的 slot 不必是 `result`，但被比对的文本必须是数据上游的 `result`/summary。这层语义 design D4 只写了「读取上游结果槽」，建议确认 Q1 后一并写死。自洽性判定：与 Q3 兼容（Q3 校验的是 `$ref` 的 node/slot 存在性，与操作数无关）；**与 Q2 冲突**——见下方「Q1/Q2 的联合语义」，两条必须一起拍板。
- **Q2 推荐**：先解析并**首行归一化** `$ref` 值（`_first_non_empty_line` + `strip`），再做 `matches_route` 行首匹配；**判定前不调 `bounded`**（`bounded` 追加 `…[bounded...]` 会让标签永远不命中），`bounded` 只用于诊断展示。
  - 审阅核实（审阅员）：`WorkflowAggregator.bounded` 超限时确追加 `_BOUNDED_MARKER = "\n…[bounded; read the full result via result_ref]"`（`agent/subagent/aggregation.py:67`、`:94-101`）→「先 bounded 再等值」在长值上必然判不中，属实。`_first_non_empty_line` 存在于 `agent/subagent/scheduler.py:291-297`，可直接复用。`matches_route` 是「行首 startswith、大小写无关」（`:208-223`）。
  - **Q1/Q2 的联合语义（审阅员发现的设计矛盾，必须在拍板 Q1 后统一）**：`matches_route(verdict, label)` 有两个操作数——被匹配文本（raw）与期望标签（label）。Q1 读法 A 把 **`$ref` 槽值当 label**（`when` 即 `$ref` 表达式，无独立期望字段）；而 Q2 的场景（`verdict` 槽 = 6000 字长文、期望命中 `"APPROVED"`）把 **`$ref` 槽值当被匹配文本**、`"APPROVED"` 当 label。**两者不能同时成立，且在 Q1 读法 A 下 Q2 的推荐会产出无意义结果**：`$ref:reviewer:verdict` 解析出长文、首行归一化后当作 label 传给 `matches_route`，于是判定变成「上游 `result` 文本是否以 `APPROVED — 但有三点建议` 开头」——几乎必然不命中。design D4 的字面表述（design.md:68「与 case 的**期望值**精确字符串相等」+ design.md:70「slot 值先走 `bounded` 再做相等判定」）预设的则是第三种读法：存在一个独立的「期望值」字段（= Q1 读法 C）。**结论**：Q1（选 A）、Q2（判定前不 bounded）、design D4 三者目前不自洽，**这一项不能各自独立答**——停轮确认时应作为 Q1 的必答子项一并抛出。若采纳读法 A，Q2 的「不 bounded」退化为无对象（raw 仍是 `_route_verdict` 的拼接文本 `scheduler.py:1420-1430`），应改写为「label 归一化」；若采纳读法 C，Q2 保持原义但需扩 schema（`RouteCase` 加 `expect`，并松开 `_parse_cases` 的 `set(item) == {"when","to"}` 硬校验 `workflow.py:570`）。
- **Q3 推荐**：校验「节点存在 + 槽已声明」（含隐式 `result` 槽），**不**把数据可达性作 schema 硬条件；运行时槽缺失**静默视为未命中走 default**，但在 diagnostics 记录 ref 未命中原因。
  - 审阅核实（审阅员）：「槽已声明」可落在 `_validate_kind_specific` 的 route 分支（`agent/subagent/workflow.py:729-738`，签名只有 `index`、没 `edges`），与「可达性不作硬条件」自洽——若坚持可达性就得改签名或挪到 `parse_workflow_spec`（调用点 `workflow.py:345`），推荐已避开。「静默未命中」需在 `_execute_route` 落一处 diagnostics（今天 `_execute_route` 只写 `state.verdict`/`state.raw`，无「未命中原因」字段，`scheduler.py:891-909`）——实现时新增，属可维护性项。**注意**：`slot in node.outputs` 是「声明」，而 aggregate 的实际槽可来自上游合并（`_collect_slots`，`scheduler.py:1321-1339`），推荐采取「声明即可通过」是宽松的保守选择，与「无键命中=不匹配」互补，不冲突。
- **Q4 推荐**：**复用 `self._runs` 作唯一 runs 计数器**（另起会在 foreach 预扣路径漂移）；运行期 C4 检查置于 C2 检查**之前**，同值 300 时由 C4 触发 `budget_exceeded`；只有 C2 显式更小时才走 `graph_recursion_exceeded`。**（审阅员修订）**C4 超限的出口必须与 spec delta 的 envelope 口径一致：`_dispatch` 预扣拒绝**不得让 `WorkflowBudgetExceeded` 未捕获地逃出 `run()`**——`run()` 与 `_drive()` 今天只 catch `GraphRecursionError`（`agent/subagent/scheduler.py:516`、`:613`），照 design D1 字面 `raise` 会让父 agent 收到异常而不是 envelope，直接违反 spec Scenario「envelope SHALL 报 `budget.exceeded = true`」。实现必须二选一：显式 catch 后映射为 stop_new + drain + `_status="budget_exceeded"`，或直接置标志不抛。
  - 审阅核实（审阅员）：预扣路径属实——`_dispatch` 抛 C2（`agent/subagent/scheduler.py:716-726`）并在 `:746` 累加 `self._runs`；`_check_foreach_budget` 按增量预扣（`:1098-1100`，超限抛于 `:1074-1085`）；`_run_cost` 只有 subagent 与 llm-aggregate 计 1、route/collect/foreach 容器计 0（`:702-709`）。因为 C2 与 C4 共用 `self._runs`，生效上限恒为 `min(max_runs, max_total_runs)`，而 workflow spawn 桶按 `spec.max_runs * 2` 校准（`scheduler.py:512` → `manager.register_workflow_bucket`，`manager.py:491-500`；检查点 `_check_spawn_budget` `manager.py:1337-1354`）：每次真实 run 计 2 次 spawn（create + run），所以桶上限 `2*max_runs` 在共用计数器下恒 ≥ 生效上限的 2 倍，不会先于预算炸；**若 C4 改用独立计数器**，生效上限可能高于 `spec.max_runs`，桶（仍按 `spec.max_runs*2` 校准）就可能先炸——这是复用 `self._runs` 的又一理由（与 Q4 推荐第一句同向）。
  - 与 Q9 的边界（审阅员收口）：Q4 的「C2 显式更小 → `graph_recursion_exceeded`」只管 `_dispatch` 的普通节点派发；`max_items=0` 的 foreach 展开走 Q9 的截断退化（不抛），两者作用在不同路径，不矛盾——该限定已写进 Q9 推荐。
- **Q5 推荐**：预算超限设 workflow 级粘性 `budget_exceeded` 状态；`_teardown` 时**非根 pending 仍 `blocked`，根节点（无下游数据边）未完成则改 `budget_exceeded`，已完成不覆盖**；最终 workflow `status` 优先保持 `budget_exceeded`（`_drive` 收敛不覆盖）。
  - 审阅核实（审阅员）：`_teardown` 确实把 `pending` 一律写 `blocked`（`agent/subagent/scheduler.py:562-564`），且 `_drive` 收敛出口会无条件把 `self._status = "completed"`（`:608-611`）——推荐要求的「粘性 status」必须在 `_drive` 这两处加条件，属实。`_unit_counts` 已分桶 `blocked`/`budget_exceeded`（`:1494-1497`），父 agent 今天看到 `blocked: N, budget_exceeded: 0`（既有断言 `tests/agent/subagent/test_aggregation_runtime.py:461`），属实。
  - **新增机械约束（审阅员）**：要让节点能落 `budget_exceeded` 终态，必须把 `"budget_exceeded"` 加进 `TERMINAL_NODE_STATUSES`（`agent/subagent/scheduler.py:64` 现为 completed/failed/cancelled/blocked）。否则标了 `budget_exceeded` 的根节点不会被视为终态，`_data_deps_satisfied`（`:661-668`）会对它的下游永远返回 False，`_unit_counts` 也会把它算进 `pending_units`（`:1498-1499`）而非 `budget_exceeded_units`——D7 的计数与 spec 的「根节点标 budget_exceeded」双双落空。这条属实现必须照做的事实（已并入 Confirmed Decisions 第 7 条口径）。
  - 「根节点」定义需落地口径（审阅员）：`plan.terminal` 已在执行计划里算好（`agent/subagent/aggregation.py:342` 透传 `spec.terminal`，spec 缺省时按「无出边」推导 `agent/subagent/workflow.py:363-366`）。推荐实现取 `plan.terminal`，避免再写一遍图推算。**注意**：fan-out 图的 `terminal` 是**多个**叶子节点（如 `_fanout_spec` 的 a/b/c，`tests/agent/subagent/test_scheduler.py:177-198`），所以「根节点标 budget_exceeded」在 fan-out 场景会命中多个未完成叶子——实现与 spec 措辞需要明确是「全部未完成 terminal 节点」还是「其中某一个」，建议前者（与 `_teardown` 的「未派发 → blocked」逐节点语义一致，且在 `_unit_counts` 里逐节点计数才自洽）。
- **Q6 推荐（选 B）**：在 `loop.py` 的 `cost_ledger.record` 同位置记 workflow token/cost（`response.usage` 含 cache 全字段）；排队期不产生 token/cost，runs 派发时计入，wall_time 从 workflow 创建起算；resume 新建 run 按实际新 LLM 调用再次计入。
  - 审阅核实（审阅员，全部属实）：`loop.py` 的 record 点确实同时持有 `response.usage`（含 `input_tokens`/`output_tokens`/`cache_read_input_tokens`/`cache_creation_input_tokens`，`agent/llm.py:46-52`）与 `self.cost_ledger`（`agent/loop.py:679-687`；`self.subagent_manager` 在 `agent/loop.py:151`，`self.cost_ledger` 在 `:145`）；身份 contextvar 在 run 执行期可用（`set_spawn_depth`/`set_current_run_id` 于 `agent/subagent/manager.py:786-787`）——但 **`current_node_id()`/`current_workflow_id()` 是随 `copy_context()` 入队快照固定**（`_enqueue_run`，`manager.py:666`），执行期不再重设；该快照经 `asyncio.create_task(..., context=item.context)` 回放（`_start_task`，`manager.py:745`），因此 loop 层读 `current_workflow_id()` 得到的就是调度器派发时 set 的值，正确（`_execute_run_in_context` 只额外覆盖 `spawn_depth`/`current_run_id`，`manager.py:786-787`）。`self.subagent_manager` 的 `find_run(subagent_id, run_id)`（`manager.py:470-478`）按 `session_id`/`run_id` 可反查归因键（C3 已就位）。**注意**：根 loop（无 workflow）下 `current_workflow_id()` 为 None，方案 B 必须显式跳过（推荐已写）。
  - **与 Confirmed Decision 3 的一致性（审阅员）**：决策 3 指出「run.usage 反算 cost 偏低」，正是方案 B 绕过 `SubagentRunUsage` 的动机；B 与决策 3 自洽。方案 C（run 终态结算）不可行也由决策 3 证成。**实现须与决策 3 的结论绑定**：走 B 时 `SubagentRunUsage` 不必须扩 cache 字段（B 直接从 `response.usage` 记账），但 C3 遗留的 `_mark_budget_exceeded` 把 input/output 写 0（`manager.py:1194-1195`）会让「按 run.usage 的 cost 报告」仍偏低——若 C4 同时要求 envelope 的 per-run cost 与 workflow 账本一致，需一并修（此点列入新增 Q12）。
  - wall_time 归因来源（审阅员）：`scheduler._started_at` 与 `_finished_at` 已存在（`scheduler.py:356-357`、`run()` 设 `_started_at` 于 `:507`、`_finished_at` 于 `:528`），envelope 的 `critical_path_s` 已按 `round(finished - started, 6)` 输出（`:1539`），可作为 wall_time 归因的同源口径。
- **Q7 推荐**：`by_depth` 用**独立 workflow 图距字段**（0=leaf / 1=shard / 2=domain / 3+=root，复用 C3 `budget_for_distance` 口径），**不复用/不改 `spawn_depth`**、不让图距影响 `max_depth` 深度闸。
  - 审阅核实（审阅员，全部属实）：`set_spawn_depth` 的非测试调用点只有 `agent/subagent/manager.py:786`（`_execute_run_in_context`，用 run 自己的 depth），定义在 `agent/subagent/context.py:41`，`scheduler.py` 一次都没调 → 调度器从不按图距设 spawn_depth，属实（`grep -rn set_spawn_depth` 结果）。`run.depth = current_spawn_depth() + 1`（`manager.py:632`）→ workflow 内所有 run.depth 同值，属实。深度闸在 `manager.py:1051`（`depth >= self.max_depth` 摘 `SPAWN_TOOL_NAMES`，名单在 `:319-326`，默认 `max_depth=3` 在 `agent/config.py:319`）。C3 的 `budget_for_distance`（0=leaf/1=shard/2=domain/≥3=root）在 `agent/subagent/aggregation.py:144-152`，且 `ExecutionPlan` 已为每个节点算好 `budgets[node_id]`（`aggregation.py:451`）——图距字段可直接复用该 plan 计算，无需新图算法。
  - 与 Q4/Q6 的自洽性（审阅员）：Q7 引入的图距字段与 Q6 的 cost 记账同源自 loop 层（账本在记账时读该字段），不冲突；与 Q4 的 `self._runs` 无关。**新增落点明确性**：字段落在 `SubagentRunRecord`（与 `depth` 并列，`manager.py:104`）还是只在账本侧按 node_id 查 plan——推荐写死为「`SubagentRunRecord` 新增 `graph_distance` 字段，由 `_new_run` 从 contextvar 读」需要新 contextvar（因为 plan 在调度器、`_new_run` 在 manager）——若选「账本按 node_id 反查 `ExecutionPlan.budgets`」则无需新字段。**这条实现路径的分歧列为新增 Q13**（属实现细节，不阻塞 Q7 口径拍板）。
- **Q8 推荐**：`edge` 按「实际触发该 run 的拓扑来源」生成——多数据入边按 source id 排序拼接 `a|b|c->join`；foreach 展开项共享 `planner->fan`；入口 `"<root>->node"`；route 控制边触发的下游记 `route->target`（控制激活优先）。
  - 审阅核实（审阅员）：与 Confirmed Decision 6 一致——`_new_run` 只有 workflow/node/depth 三个 contextvar 可读（`agent/subagent/manager.py:629-632`），调度器 set 的三个身份不含 edge（`scheduler.py:1128-1130`），所以 edge 必须在调度器派发点算出并经 `run_subagent` 透传或 `_launch_run` 回填，属实。多入边拼接的**稳定性**：`data_incoming` 按 `spec.edges` 声明序返回（`workflow.py:213-219` 用元组推导，保序）；推荐「按 source id 排序」比声明序更稳（同一张图的两种等价声明序会得到同一键），**建议实现严格按 `sorted(source_ids)`**——若按声明序，`a|b|c->join` 与 `b|a|c->join` 会成两个桶，`by_edge` 可读性下降（这正是 Q8 场景 A 要回答的）。foreach 展开项共享容器 edge 与既有「展开项 `node_id` 全等容器 id」一致（`set_node_id(node.id)`，`scheduler.py:1129`；`_run_foreach_item` 传 `reuse_state=None`，`:977-983`），属实。route 控制边不传数据（`workflow.py:209-211`），被 route 激活的下游其「数据上游」可能为空，推荐记 `route->target` 与「控制激活优先」自洽。
  - **与 Q4 的交叉（审阅员）**：edge 拼接键的稳定性不依赖 `self._runs`，与 Q4 无冲突；但**多入边节点（如 join）只产生一次 run、记一条拼接 edge**，而 `by_edge` 若想回答「哪条边最贵」，聚合边（`a|b|c->join`）的语义是「这次 run 由 a/b/c 共同触发」——推荐已明确，无矛盾。**残留实现点**：调度器在 `_execute_aggregate` 派发前能拿到 `data_incoming(node.id)`（`scheduler.py:1364`、`:1386`），但 foreach 容器的 edge 需在 `_execute_foreach` → `_run_foreach_item` 链路透传（`:977` 目前不传 edge）——属实现面，Q8 口径已覆盖取值规则。
- **Q9 推荐**：放行 `max_items=0`（定义为「不做静态截断」，需给 max_items 单独的非负解析函数）；foreach 预检**按剩余容量截断**而非抛 C2 异常；可展开数取「C4 `max_total_runs` / C2 `max_runs` / C2 `max_nodes`」三者剩余上限的**最小值**。**（审阅员修订）**「截断而非抛错」**只对 `max_items == 0` 的节点生效**；`max_items > 0` 保留今天的 C2 fail-fast 抛错，否则会静默删除 C2 的结构闸语义（D2 明确「本 change 不删 C2 的 `max_runs`」）并打破既有断言（`test_foreach_run_budget_reports_graph_recursion_exceeded`，`tests/agent/subagent/test_scheduler.py:855-877`；`test_auto_aggregates_consume_max_runs`，`tests/agent/subagent/test_aggregation_runtime.py:123-130`）。另：截断必须发生在 `_expand_plan` **之前**（见下方审阅核实）。
  - 审阅核实（审阅员）：`_parse_max_items` 复用 `_positive_int`（`agent/subagent/workflow.py:535-536`、`:400-403`、调用点 `:469`）今天直接拒 0，属实；`_resolve_items` 的 `items[: node.max_items]` 在 `agent/subagent/scheduler.py:1440`，`[:0]` 是空集而非不限，属实；`max_items` 默认 20（`workflow.py:116`、`:469`），所以「不写」= 20 而非无限，属实。
  - **顺序约束（机械事实，非决策）**：`_execute_foreach` 的次序是 `_resolve_items()` → `_expand_plan(node.id, len(items))` → `_check_foreach_budget()`（`agent/subagent/scheduler.py:928-935`）。若不在 `_resolve_items`/`_expand_plan` 之前截断，500 项会先经 `_expand_plan` 撞 `max_nodes` 抛 `GraphRecursionError`（`:1021-1032`），根本走不到截断——设计 D5「跳过 `items[:max_items]` 截断」这个说法会落空。截断点必须选在 `_resolve_items` 内。
  - **两个「0」不是同一对象（防混淆）**：本条的 0 是**节点字段** `max_items`（= 不做静态截断，展开量由预算兜底）；Q11 的 0 是**workflow 预算字段**（= 该维度关闭/不限）。两者独立、可同时出现；同时为 0 时展开上限仍由 C2 的 `max_runs`/`max_nodes` 剩余量兜底。
  - 与 D5/spec 的冲突（待用户确认后回写）：design D5 写「跳过截断，改由 `max_total_runs` 预算做唯一上限（stop_new 在预算耗尽时停止派发）」= 先全量展开再被 stop_new 拒绝；本推荐 = 先按剩余容量截断再展开。两者在「最终执行多少个 run」上收敛（都是 min(项数, 预算)），但在 `state.items` 记录值、`_expand_plan` 插层规模与 envelope 计数上不同。spec delta Scenario「max_items=0 展开到预算耗尽」写的是「SHALL 展开全部集合项」，与本推荐冲突——待确认 Q9 后一并回写 design D5 + spec Scenario（见「待用户确认后回写」清单）。
- **Q10 推荐**：只沿**数据边**递归；优先读 source 节点自身 `result` 槽，没有才在**唯一数据上游**时继续向上；多入边无物化 result = schema 歧义拒绝；递归在无上游/已访问/环处终止；环检测复用 Tarjan SCC（在 `parse_workflow_spec` 校验期）；`source_field` 只应用**一次**（不再同时传 `_node_output` 和 `extract_collection`）。
  - 审阅核实（审阅员）：`_resolve_items` 今天只取 `self._states[node.source]` 的直接产出（`agent/subagent/scheduler.py:1437-1439`），属实；`_node_output` 对非 subagent 节点优先返回自己 `state.slots[slot]`，否则**向下回退到上游槽**、最后 `state.summary`（`:1341-1349`）——「一层跨层」今天靠此偶然生效，属实（`test_foreach_consumes_upstream_collection` 走的是直接上游，`tests/agent/subagent/test_scheduler.py:767-796`）。`extract_collection` 对 `None` 返 `[]`、对 dict 挑 `items/results/tasks/list`（`scheduler.py:226-249`），属实。Tarjan SCC 是现成 stdlib 实现（`agent/subagent/workflow.py:638-687`），`_validate_cycles` 已用它（`:618-635`），属实。「唯一数据上游才继续向上」是推荐新增的**终止判据**——今天代码里没有，属设计新增，无矛盾。**注意**：`_node_output` 的 fallback 与推荐「source_field 只应用一次」有交互——推荐落地时要改 `_resolve_items`，不再经 `_node_output` 的隐式 fallback，否则「只应用一次」会被 `_node_output` 内部的第二次取槽破坏。
  - **与 Q8/Confirmed Decision 6 无冲突**（审阅员）：`source` 递归解析发生在 `_execute_foreach` 内部（同步），与 edge 记录（派发时）是两条独立路径。
- **Q11 推荐**：四维预算字段**均 `0 = 不限`**（新增 workflow-budget 专用非负解析函数，不改全局 `_validate_positive_int`/`_parse_positive_float`）；缺省用 D6 默认值（200000/5.0/300/1800）；显式 `null` **拒绝**（避免 YAML 缺值意外关闭安全闸）。
  - 审阅核实（审阅员）：`_validate_positive_int` 对 `raw < 1` 抛 ConfigError（`agent/config.py:1556-1565`）、`_parse_positive_float` 对 `value <= 0` 抛（`:1568-1585`），属实；`WorkflowLimitsConfig` 是 frozen dataclass 且嵌套配置走「逐字段 `mapping.get`」（`agent/config.py:293`、`_parse_workflow_limits` `:1440-1457`、`_parse_aggregation` `:1460-1516`），推荐「照 `_parse_aggregation` 纪律落」有先例，属实。成本价表 `deepseek-v4-flash` 四档全 0（`agent/cost_tracker.py:32`），属实。
  - **两个「0」的消歧（审阅员）**：本条 0 = **workflow 预算维度关闭**；Q9 的 0 = **节点 `max_items` 不做静态截断**。两者是不同对象、独立语义，**不会互相污染**（一个在 `WorkflowBudgetConfig`、一个在 `WorkflowNode`），但文档/实现注释需显式区分，否则读者会把「`max_total_runs: 0`（关掉 runs 维度）」误读成「无限跑」。**建议实现时对 `max_total_runs=0` 特别注释**：它关闭 C4 的 runs 维度，但**不**关闭 C2 的 `max_runs`（C2 仍是结构闸）。
  - **自洽性判定（审阅员）**：Q11 与 Q4/Q6/Q9 均无矛盾。补充两点事实：① 自托管零价模型（`deepseek-v4-flash`，`agent/cost_tracker.py:32`）下 cost 恒为 0，`used >= limit` 永不成立，所以「不关 cost 维度」也不会被它触发——需要 `0=不限` 的是「成本模型未配置/价格未知」场景，不是零价模型场景；② `compute_cost_cached` 对未知模型走表均值估算并标 `known=False`（`agent/cost_tracker.py:86-92`），因此「未知模型 → cost 恒 0」不成立，0 语义不能靠「价格未知」蒙混。
  - **校准风险（审阅员，列新增 Q14）**：`max_total_runs=0`（不限）与 C2 `max_runs`（默认 300）叠加时，runs 的实际上限仍是 C2 的 300（因为 Q4 复用了 `self._runs`）——即「C4 关了 runs 维度、C2 还在兜底」，D6 的「两者默认一致避免误伤」在 0 语义下变成「C4=0 时 C2 独自兜底」。这是可接受的（C2 是结构闸），但 spec 需要写明 `max_total_runs=0` 不解除 C2 上限，否则用户会以为「设 0 = 无限跑」。见「待用户确认后回写」清单。

### 审阅员补充推荐的 Q12–Q16

以下 5 条是审阅员（meta-review）对补充 Open Question 的推荐答案（codex 未覆盖这些点）。与其他推荐同权限：标注为「推荐」，最终以用户确认为准。

- **Q12 推荐（审阅员补充）**：**workflow 账本是权威口径**（Q6 方案 B 从 `response.usage` 四档全算），`CostLedger` 是「跨 workflow 的历史财务记录」（其 `by_workflow` 维来自 D3 的键扩充）；两者**不追求逐 run 相等**，但 `CostLedger.record` **应扩 cache 参数**以对齐四档定价（否则 `bill()` 的 by_node/by_edge 与 workflow 账本对不上，D7 的 attribution 摘要会自相矛盾）。`_mark_budget_exceeded` 写 0 的 input/output 属 C3 遗留，**建议本次一并修**（补填 `tracker.tokens` 口径的 input/output，或至少标注「usage 不完整」），否则被预算杀的 run 在 by_node 里 cost 为 0。**理由**：D7 明说 attribution 是给父 agent 对账用的，三处不同数字会让这个能力不可信。
- **Q13 推荐（审阅员补充）**：**路径 X**——新增 `graph_distance` contextvar（`agent/subagent/context.py` 加一对 getter/setter，与 `_node_id` 同模式），调度器在 `_launch_run` 的既有 set 点（`agent/subagent/scheduler.py:1128-1130`）一并 set（值从 `plan.budgets`/图距算），`manager._new_run` 读进 `SubagentRunRecord.graph_distance`（与 `depth` 并列）。**理由**：与 C1 三个身份 contextvar 的既有落点完全同构（改动最小、评审面最熟）；路径 Y 会让 manager 依赖调度器的 `ExecutionPlan`，违反现有「manager 只管执行、scheduler 掌控图」的分层（`scheduler.py:1-24` 的分工注释）。
- **Q14 推荐（审阅员补充）**：**选项 A**——文档明写「`max_total_runs=0` 只解除 C4 的 runs 维度；C2 `max_runs` 仍是结构闸，要真正放宽须同时调 `spec.max_runs`」，并在 spec delta 的 Scenario 里补一句。**理由**：选项 B 会引入「配置键隐式改写 spec 结构闸」的特例，与 D2「C2 是声明期结构闸、C4 是运行期预算，两者语义分开」的边界冲突；A 保持两层职责清晰。
- **Q15 推荐（审阅员补充）**：**方案 A（结束时一次性落盘）**——`_teardown()`/`run()` 结算时把本 workflow 的 attribution 快照经新增的 `WorkflowStore.save_attribution(workflow_id, payload)` 落盘，`GetWorkflow` 的 `_DETAILS` 扩为含 `"attribution"`，返回 `attribution_ref`（父按需 `ReadWorkflowResult` 读，与 C3 的 bounded/result_ref 口径一致）。**理由**：D7 已定「不整表返回、走 result_ref 落盘」，实时算会绕过落盘边界且需要给共享 `CostLedger` 加 workflow 过滤（今天 `bill()` 无 by_workflow 维），改动更大；结束时落盘是 C3 `_write_root_result` 的既有模式（`scheduler.py:1582-1608`）。
- **Q16 推荐（审阅员补充）**：① 分桶值 round 位数**与 envelope `total_cost` 对齐为 9 位**（`scheduler.py:1540` 已是 `round(..., 9)`），或在 spec 里显式声明二者不同并说明理由（推荐对齐，避免对账差）；② tokens 口径 = **input + output（不含 cache）**，与 `CostLedger.bill()` 今天的 `tokens` 口径一致（`agent/cost_tracker.py:180`），cache 单独可选暴露；③ cost 单位 USD；未知模型（`CostEstimate.known=False`）在桶里加 `estimated: true` 标记，不静默混入已知模型桶。**理由**：Q16 的本质是「父 agent 能否对账」，三个字段（total_cost / critical_path_s / attribution）精度统一是前提。

### 审阅员交叉核验小结（Q1–Q16 自洽性）

逐项核验 prompt 点名的五个交叉点，结论如下（详见各条注记）：

| 交叉点 | 结论 |
|--------|------|
| Q4 ↔ Q9（runs 计数器） | **已收口**。Q4 的「C2 更小 → `graph_recursion_exceeded`」只作用于 `_dispatch` 普通派发；Q9 的「截断不抛」只作用于 `max_items=0` 的 foreach 展开。两条路径不重叠，且 Q9 已加限定语。共用 `self._runs` 由 Q4 决定，Q9 的截断按该计数器的剩余量算，一致。 |
| Q9 ↔ Q11（两个「0」） | **不冲突**。Q9 的 0 是 `WorkflowNode.max_items`（不做静态截断）；Q11 的 0 是 `WorkflowBudgetConfig` 字段（维度关闭）。对象不同、互不污染；已在两条各自加消歧注记。 |
| Q5 ↔ Q7（新增字段） | **不冲突**。Q5 新增的是 `NodeState`/终态集合里的状态值 `budget_exceeded`（`TERMINAL_NODE_STATUSES` + 节点 status）；Q7 新增的是归因用的图距字段（Q13 定落点）。一个在节点状态机、一个在身份/归因投影，无重叠。 |
| Q6 ↔ Q2/Q3（记账 vs 判定） | **互不干扰**。Q6 是 workflow 账本的记账点（loop 层，写 token/cost）；Q2/Q3 是 route 判定与校验（调度器 `_execute_route` + parse 期）。两条路径不共享数据结构，且 Q6 明确「route 纯逻辑节点 `_run_cost=0` 不产生 run」。 |
| Q8 ↔ Q4（edge 拼接键稳定性） | **一致**。edge 由调度器派发点按 `data_incoming` 生成（Q8），与 `self._runs`（Q4）无关；Q8 的「按 source id 排序拼接」保证键稳定（不随声明序漂移），有利于 `by_edge` 可读性。foreach 展开项共享容器 edge，与 `_launch_run` 复用 `node.id` 的既有事实一致。 |
| **Q1 ↔ Q2（`$ref` 操作数）** | **冲突（需用户拍板后统一）**。Q1 读法 A 把 `$ref` 槽值当 label；Q2 的场景把它当被匹配文本。两者不能同时成立；design D4 的字面表述（「与期望值精确字符串相等」+「先 bounded 再等值」）预设的是第三种读法（独立期望字段 = Q1 读法 C）。**已标注为必须一起答，并列入回写清单。** |

**新增发现（原 11 条未覆盖，已转成 Q12–Q16）**：记账口径一致性（Q12）、图距字段落点（Q13）、`max_total_runs=0` 与 C2 叠加（Q14）、attribution 落盘时机/载体（Q15）、数值精度与单位（Q16）。

## User Confirmation

- **Q1**: 用户答复：按 codex 推荐 A——`$ref` 槽值取首个非空行作为期望标签，传入 `matches_route`；`$ref` 与字面标签 case 按声明顺序匹配；确认时间: 2026-09-14
- **Q2**: 用户答复：判定前先首行归一化（`_first_non_empty_line` + strip）再走 `matches_route` 行首匹配，判定前不调 `bounded`（bounded 只用于诊断展示）；与 Q1 联合语义为「解析槽值→取首个非空行→作期望标签→匹配上游数据文本」；确认时间: 2026-09-14
- **Q3**: 用户答复：校验「节点存在 + 槽已声明」（含隐式 result 槽），不把数据可达性作 schema 硬条件；运行时槽缺失静默视为未命中走 default，diagnostics 记录 ref 未命中原因；确认时间: 2026-09-14
- **Q4**: 用户答复：复用 `self._runs` 作唯一 runs 计数器；运行期 C4 检查置于 C2 检查之前，同值 300 时由 C4 触发 `budget_exceeded`；`WorkflowBudgetExceeded` 不得未捕获逃出 `run()`，必须映射为 stop_new+drain+`_status="budget_exceeded"` envelope；确认时间: 2026-09-14
- **Q5**: 用户答复：非根 pending 仍 `blocked`，根节点（`plan.terminal`，无下游数据边）未完成则改 `budget_exceeded`、已完成不覆盖；最终 workflow `status` 优先保持 `budget_exceeded`；节点级 `budget_exceeded` 加进 `TERMINAL_NODE_STATUSES`；确认时间: 2026-09-14
- **Q6**: 用户答复：选 B——在 `loop.py` 的 `cost_ledger.record` 同位置记 workflow token/cost（`response.usage` 含 cache 全字段）；排队期不产生 token/cost，runs 派发时计入，wall_time 从 workflow 创建起算；resume 新建 run 按实际新 LLM 调用再次计入；确认时间: 2026-09-14
- **Q7**: 用户答复：`by_depth` 用独立 workflow 图距字段（0=leaf / 1=shard / 2=domain / 3+=root，复用 C3 `budget_for_distance` 口径），不复用/不改 `spawn_depth`、不让图距影响 `max_depth` 深度闸；确认时间: 2026-09-14
- **Q8**: 用户答复：edge 按「实际触发该 run 的拓扑来源」生成——多数据入边按 source id 排序拼接 `a|b|c->join`；foreach 展开项共享 `planner->fan`；入口 `"<root>->node"`；route 控制边触发的下游记 `route->target`（控制激活优先）；确认时间: 2026-09-14
- **Q9**: 用户答复：放行 `max_items=0` = 不静态截断（需给 max_items 单独非负解析函数）；foreach 预检按剩余容量截断而非抛 C2 异常，且只对 `max_items==0` 生效、截断发生在 `_expand_plan` 之前；可展开数取「C4 `max_total_runs` / C2 `max_runs` / C2 `max_nodes`」三者剩余上限最小值；确认时间: 2026-09-14
- **Q10**: 用户答复：只沿数据边递归；优先读 source 节点自身 `result` 槽，没有才在唯一数据上游时继续向上；多入边无物化 result = schema 歧义拒绝；递归在无上游/已访问/环处终止；环检测复用 Tarjan SCC（在 `parse_workflow_spec` 校验期）；`source_field` 只应用一次；确认时间: 2026-09-14
- **Q11**: 用户答复：四维预算字段均 `0 = 不限`（新增 workflow-budget 专用非负解析函数，不改全局 `_validate_positive_int`/`_parse_positive_float`）；缺省用 D6 默认值（200000/5.0/300/1800）；显式 `null` 拒绝；确认时间: 2026-09-14
- **Q12**: 用户答复：workflow 账本为权威口径（Q6 方案 B 从 `response.usage` 四档全算），`CostLedger` 为跨 workflow 历史财务记录、不追求逐 run 相等；`CostLedger.record` 扩 cache 参数对齐四档定价；`_mark_budget_exceeded` 写 0 的 input/output 属 C3 遗留，本次一并修；确认时间: 2026-09-14
- **Q13**: 用户答复：路径 X——新增 `graph_distance` contextvar，调度器在 `_launch_run` 既有 set 点一并 set（值从 `plan.budgets`/图距算），`manager._new_run` 读进 `SubagentRunRecord.graph_distance`（与 `depth` 并列）；确认时间: 2026-09-14
- **Q14**: 用户答复：选项 A——文档明写「`max_total_runs=0` 只解除 C4 的 runs 维度；C2 `max_runs` 仍是结构闸，要真正放宽须同时调 `spec.max_runs`」；确认时间: 2026-09-14
- **Q15**: 用户答复：方案 A（结束时一次性落盘）——`_teardown()`/`run()` 结算时把 attribution 快照经新增 `WorkflowStore.save_attribution` 落盘，`GetWorkflow` 的 `_DETAILS` 扩为含 `"attribution"`，返回 `attribution_ref`（父按需 `ReadWorkflowResult` 读）；确认时间: 2026-09-14
- **Q16**: 用户答复：① round 位数与 envelope `total_cost` 对齐为 9 位；② tokens 口径 = input+output（不含 cache），cache 单独可选暴露；③ cost 单位 USD；未知模型（`known=False`）加 `estimated: true` 标记；确认时间: 2026-09-14

## 风险

- **严重: D2 的 stop_new 复用了不 gate 派发的 `_accepting`（带 file:line）**: `_accepting` 的唯一读点是 `_on_node_finished` 的级联复位门（`agent/subagent/scheduler.py:813`），派发路径 `_drive` → `_ready_nodes` → `_dispatch`（`:585-602`、`:674-693`、`:711-761`）完全不读它。照 design.md:45 字面实现（「`_accepting = False`：不再派发新节点」），预算超限后调度器会**继续派发**所有就绪节点——四维度预算是空转的，烧钱面没有任何收敛。必须显式新增派发闸，或复用一个确实被检查的 flag（`_cancelled` 的检查点在 `:581`/`:1254`/`:1258`）。

- **严重: runs 维度在默认配置下永远不会触发（带 file:line）**: `_dispatch` 在派发前先抛 `GraphRecursionError(reason="max_runs")`（`agent/subagent/scheduler.py:716-726`），`_check_foreach_budget` 也会在展开前抛同款异常（`:1074-1085`）。两者与 `max_total_runs` 默认同为 300，且异常路径会走 `_accepting=False` + `_cancel_all_in_flight()` + `_status="graph_recursion_exceeded"`（`:613-619`），完全绕过 `budget_exceeded` 的 drain 语义。spec delta 的 Scenario「runs 预算派发前预扣拒绝 → envelope SHALL 报 `budget.exceeded = true`」在默认配置下不可达。

- **严重: cost 维度在现有数据结构上算不出来（带 file:line）**: `SubagentRunUsage` 没有 cache 字段（`agent/subagent/manager.py:73-79`），`_complete_run` 主动丢弃 `RunResult` 上的 cache tokens（`agent/subagent/manager.py:1079-1084` vs `agent/result.py:30-31`），`_mark_budget_exceeded` 更把 input/output 写成 0（`agent/subagent/manager.py:1194-1195`）。若按 design.md:61「在 loop.py 的 `cost_ledger.record` 调用点读取这些字段并传入」实现，必须同时扩 usage 结构与两条收尾路径，否则 `max_total_cost_usd` 系统性偏低、永远不触发。

- **中: `edge` 在 `_new_run` 不可得（带 file:line）**: tasks 2.3 要求 `_new_run` 时固定 `edge`，但 `_new_run` 只有 workflow/node/depth 三个 contextvar 可读（`agent/subagent/manager.py:629-632`、`agent/subagent/context.py:30-34`），没有「上游节点」contextvar；调度器 set 的三个身份也不含 edge（`agent/subagent/scheduler.py:1128-1130`）。按字面实现会得到 `edge=None` 或需要额外透传参数，`by_edge` 分桶直接失效。

- **中: `by_depth` 在当前字段上是单桶（带 file:line）**: 调度器从不调用 `set_spawn_depth`（全仓非测试引用只有 `agent/subagent/manager.py:786`），所以一个 workflow 内所有节点 run 的 `depth` 相同（`current_spawn_depth() + 1`，`agent/subagent/manager.py:632`）。D3 的「哪层重复 token 最多」在当前实现下回答不了；而改用图距又会通过 `run.depth` 影响 `max_depth` 深度闸（`agent/subagent/manager.py:1051`，默认 `max_depth=3` 见 `agent/config.py:319`）。

- **中: `budget_exceeded` 状态在节点层是新状态，且与 `blocked` 抢位（带 file:line）**: `_unit_counts` 已预留 `budget_exceeded` 分支（`agent/subagent/scheduler.py:1494-1495`），但没有任何赋值点；而 `_apply_run_status` 把 run 级 `budget_exceeded` 映射成节点 `failed`（`:1193-1202`），`_teardown` 把未派发节点写成 `blocked`（`:562-564`）。三种语义在同一张 envelope 里并存（`failed`/`blocked`/`budget_exceeded`），父 agent 很难分辨「谁是被预算杀的」。

- **中: Three-处 300 默认值可能互相漂移（带 file:line）**: `WorkflowLimitsConfig.max_runs = 300`（`agent/config.py:292`）、`_parse_workflow_limits` 的 `mapping.get("max_runs", 300)`（`agent/config.py:1453-1455`）、`parse_workflow_spec` 的 `DEFAULT_MAX_RUNS = 300`（`agent/subagent/workflow.py:37`）已经是三处独立常量，C4 再加 `WorkflowBudgetConfig.max_total_runs = 300` 是第四处。D6 说「避免声明期 300 但运行期 200 的误伤」，但四份字面量各自维护，迟早漂移。

- **低: `$ref` 与 `matches_route` 的语义分叉点必须显式分支（带 file:line）**: `matches_route` 是「行首匹配、大小写无关」的标签比较（`agent/subagent/scheduler.py:208-223`），route 执行时对每个 case 无条件调用它（`_execute_route`，`:896-900`）。若把 `"$ref:node:slot"` 直接喂进去，它会被当作**字面标签**去匹配上游文本（`stripped.startswith("$REF:NODE:SLOT")`），静默永不命中并落到 default——不报错、不日志，是最难查的一类实现 bug。`$ref` 必须在 `_execute_route` 里先分流。

- **严重（审阅员新增）: C4 的 `WorkflowBudgetExceeded` 若按 design D1 字面 `raise`，会逃出 `run()` 未捕获、父 agent 收到异常而非 envelope**: `run()` 与 `_drive()` 今天都只 `except GraphRecursionError`（`agent/subagent/scheduler.py:516`、`:613`），没有任何 `except WorkflowBudgetExceeded`。D1 写「预算超限时 raise `WorkflowBudgetExceeded` 而非 `GraphRecursionError`」——照此实现，`_dispatch` 的预扣拒绝会让异常穿透 `_drive`/`run`，`_teardown` 的 `finally` 虽会执行，但 `run()` 不再返回 envelope，`StartWorkflow`/`RunWorkflow` 工具拿到的是异常。这与 spec delta Scenario「envelope SHALL 报 `budget.exceeded = true`」直接冲突，也让 D2 的「超限 → drain」序列无从发生。**修复**：实现必须显式 catch 并映射为 stop_new+drain+`_status="budget_exceeded"`，或改用语义等价但被捕获的出口（详见 Q4 推荐的审阅员修订）。

- **严重（审阅员新增）: Q9 的「按剩余容量截断」若落在 `_expand_plan` 之后才做，会先撞 `max_nodes` 抛异常、同时破坏既有 C2 断言**: `_execute_foreach` 的次序是 `_resolve_items()` → `_expand_plan(node.id, len(items))` → `_check_foreach_budget()`（`agent/subagent/scheduler.py:928-935`）。若截断发生在 `_check_foreach_budget` 内（Q9 原始推荐的落点），`_expand_plan` 已先按**全量** `len(items)`（500）插层并撞 `max_nodes`（`:1021-1032` 抛 `GraphRecursionError`）——「按剩余容量截断」永远走不到。且「截断而非抛错」若不加限定地施加到 `max_items>0` 的节点，会静默删除 C2 的结构闸语义并打破两条既有断言（`tests/agent/subagent/test_scheduler.py:855-877`、`tests/agent/subagent/test_aggregation_runtime.py:123-130`）。**修复**：截断点必须落在 `_resolve_items` 内（`_expand_plan` 之前），且只对 `max_items == 0` 生效（详见 Q9 推荐的审阅员修订）。

- **严重（审阅员新增）: Q1/Q2/design D4 三者的 `$ref` 判定语义不自洽，必须在拍板 Q1 后统一回写**: design.md:68 要求「与 case 的**期望值**精确字符串相等」并提到 `$ref` 的 `node_id`/`slot`；design.md:70 又说「slot 值先走 `bounded` 再相等判定」。但 `RouteCase` 只有 `{when, to}`（`agent/subagent/workflow.py:83-91`、硬校验 `:570`）——D4 字面预设了第三个「期望值」字段。Q1 推荐选 A（`$ref` 槽值当 label）、Q2 推荐（`$ref` 槽值当被匹配文本做归一化）在操作数上互斥。**修复**：这不是任一单条推荐能自洽的，必须由用户在 Q1 拍板读法后统一回写 Q1/Q2/D4/tasks 3.1（详见 Q2 推荐的审阅员注记与「待用户确认后回写」清单）。

- **中（审阅员新增）: `_mark_budget_exceeded` 把 input/output 写 0，会让被预算杀的 run 在 by_node 里 cost 为 0**: `agent/subagent/manager.py:1194-1195` 写 `SubagentRunUsage(total_tokens=tokens, input_tokens=0, output_tokens=0)`，`_complete_run` 也丢 cache（`:1079-1084`）。C4 的 workflow 账本（Q6 方案 B）与 per-run usage 因此给出两套不一致的 cost（Q12）。**修复**：Q12 建议本次一并补填真实口径，或至少标注 usage 不完整。

## 待用户确认后回写（审阅员标注）

以下不一致点**依赖用户拍板 Q 结论才能定**，审阅员未提前落笔；停轮确认后必须回写对应文件（与 `tasks.md` 2.3 的纯文档 bug 不同——那条已直接修，见下）。

- **Q1 拍板后 → 回写 `design.md` D4（第 68、70 行）+ `tasks.md` 3.1 + `specs/multi-agent-collaboration/spec.md`「动态 route 条件源」Requirement/Scenario**：三处的 `$ref` 语义当前互相打架（D4 预设第三个「期望值」字段，但 `RouteCase` 只有 `{when,to}`；Q1 推荐选 A、Q2 推荐隐含另一读法）。拍板后需统一为同一读法，并在 spec 里写清 `$ref` 的操作数（label 还是 raw）。
- **Q9 拍板后 → 回写 `design.md` D5（第 75 行）+ `tasks.md` 3.3 + spec「动态 foreach 跨层 source」的 `max_items=0` Scenario**：D5/spec 现写「跳过截断、展开到预算耗尽（SHALL 展开全部集合项）」；Q9 推荐改为「按剩余容量截断（只对 `max_items=0`）」。两者在 `state.items`/插层/envelope 计数上不同，须统一。
- **Q11 拍板后 → 回写 `design.md` D6（第 79 行）+ spec「workflow 级四维度总预算」Requirement**：确认「0 = 不限」后，spec 需补一句「`max_total_runs=0` 不解除 C2 `max_runs` 结构闸」（Q14 推荐 A）。
- **Q15 拍板后 → 回写 `design.md` D7（第 87 行）+ `tasks.md` 5.2**：「GetWorkflow detail 返回完整 attribution」需写死落盘载体（新增 `WorkflowStore.save_attribution`）与 `detail` 合法值集合。
- **Q7/Q13 拍板后 → 回写 `design.md` D3（第 58 行）+ `tasks.md` 2.1**：`by_depth` 的图距字段落点（`SubagentRunRecord.graph_distance` + 新 contextvar）需写进任务。
- **Q16 拍板后 → 回写 `design.md` D7（第 85 行）**：attribution 摘要的 round 位数（现写 6 位）与 envelope `total_cost`（9 位）需统一或显式声明差异。
- **Q7/Q13 拍板后 → 回写 `specs/multi-agent-collaboration/spec.md`「成本归因四维账单」Requirement**：该 Requirement 今天只列了 `by_depth` 这个名字，**没有定义 depth 口径**（spawn 深度 vs 图距）——Q7 的结论若不写进 spec，规格与实现之间会缺一层可校验的约束（artifact checker 与后续 change 都可能被误导）。**这是 spec 覆盖缺口，不是矛盾**，建议确认后补一句「`by_depth` 的分层口径为 workflow 图距（0=leaf/1=shard/2=domain/3+=root），与 `spawn_depth` 无关」。
- **Q12/Q16 拍板后 → 回写 `specs/multi-agent-collaboration/spec.md`「成本归因四维账单」Requirement**：该 Requirement 未规定 cost/token 的**记账精度与单位**，也没有约束「workflow 账本与 per-run usage 谁权威」。Q12/Q16 的结论若不落 spec，四维账单与 envelope `total_cost` 的对账关系就没有规格约束。

**spec delta 覆盖复核（审阅员）**：`specs/multi-agent-collaboration/spec.md` 的 4 条 ADDED Requirement（四维预算 / 成本归因四维 / 动态 route 条件源 / 动态 foreach 跨层 source）**已覆盖 Q1–Q11 的大部分结论**，但有 3 处规格缺口（均为「结论没进 spec」，不是内部矛盾）：① `by_depth` 的 depth 口径未定义（见上，Q7/Q13）；② 四维账单的精度/单位与权威口径未定义（Q12/Q16）；③ `max_total_runs=0` 与 C2 `max_runs` 的关系未写明（Q14）。另有 2 处 spec 措辞与 Q 推荐直接冲突，属「待确认后回写」（已在上面第 2、3 条列出）：`max_items=0` Scenario 的「SHALL 展开全部集合项」、`$ref` 的操作数。

**已直接修的纯文档 bug（不依赖用户拍板）**：`tasks.md` 2.3 原写「`edge` 字段 …… `_new_run` 时固定」——与 Confirmed Decision 6（`_new_run` 无「上游节点」contextvar，edge 不可得）直接矛盾，无论 Q8 怎么拍板都错。已改为「取值在调度器派发点算出，经 `run_subagent(edge=...)` 透传或 `_launch_run` 回填，规则见 Q8」。
