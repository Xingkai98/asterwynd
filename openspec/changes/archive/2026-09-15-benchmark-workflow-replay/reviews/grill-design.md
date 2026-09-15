# Grill: benchmark-workflow-replay 设计追问

## Reviewer

- run id: grill-benchmark-workflow-replay-2026-09-15
- 时间: 2026-09-15
- 对象: `openspec/changes/benchmark-workflow-replay/design.md` D1–D6
- 基线: C4 `workflow-budget-attribution` 已合入（`agent/subagent/{scheduler,manager,workflow,patterns}.py`、`agent/config.py`、`agent/subagent/context.py`、`benchmarks/{runner,agent_runner,models,report,compare,statistics,gate}.py`、`agent/tools/builtin/subagents.py`）

## Confirmed Decisions

以下 14 条是本审阅员**读代码后可自行收敛**的结论（不需要用户拍板），实现时必须按此写，否则会与既有代码/测试事实冲突。（原 13 条 + meta-review 复核补入 1 条：`workflow_cost_usd` 依赖 benchmark 路径缺挂的 `cost_ledger`。）

- **决策**: **design.md 里的 file:line 断言整体不准，实现时一律以当前代码行为准，不要按 design 里的数字定位。** 逐条核对结果（design 引用 → 当前实际）：`agent/subagent/workflow.py:253-257` 的 `spec_hash` → 实际是 `WorkflowSpec.spec_hash` property，在 `agent/subagent/workflow.py:287-291`（253-257 行现在是 `data_incoming`/`data_outgoing` 的返回语句）；`agent/subagent/workflow.py:236-251` 的 `to_dict()` → 实际 `agent/subagent/workflow.py:270-285`；`agent/subagent/workflow.py:25` 的 `SCHEMA_VERSION` → **正确**（`SCHEMA_VERSION = "workflow.v1"`）；`benchmarks/models.py:61-99` 的 `TaskResult` → 实际 dataclass 体是 `benchmarks/models.py:60-108`（`from_dict` 在 `:93-102`，design 的「约 :98」指的应是这里）；`agent/subagent/scheduler.py` 的 `_steps` → 初始化在 `:370`、envelope 暴露在 `:2041`。唯一**逐字正确**的是 `SCHEMA_VERSION`。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **采集到的 workflow 字段不能只加到 `TaskResult`——`AgentRunResult` 也必须同批增字段，否则跨不过 `AgentRunner` 边界。** 采集点在 `AsterwyndRunner.run`（`benchmarks/agent_runner.py:284-385`），它的返回类型是 `AgentRunResult`（`benchmarks/models.py:45-57`，当前 11 个字段里没有任何 workflow 字段）；而 `TaskResult` 是在 `benchmarks/runner.py` 侧构造的（`runner.py:308-318`、`:377-398`、`:446-468`、`:530-552`）。两个 dataclass 之间没有其它通道，字段必须成对新增（`AgentRunResult` 侧至少要有 `workflow_mode`/`workflow_spec_hash`/`scheduler_version`/`node_count`/`run_count`/`peak_active`/`queue_wait_s`/`critical_path_s`/`workflow_cost_usd` 与一个携带原始 envelope 的 `workflow_envelope: dict | None`）。`AgentRunner` 是 ABC（`agent_runner.py:24-37`），`FakeAgentRunner`（`:41-104`）、`ShellCommandRunner`（`:107-163`）、`ClaudeCodeRunner`（`:166-243`）都不构造 manager，所以新增字段必须**全部带默认值 `None`**，否则这三个 runner 立刻构造失败。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **`runner.py` 的 `run_task` 会在 3 处用新对象覆盖 `result`，workflow 字段必须在这 3 处都带上，否则被静默丢弃。** 三处重建点：docker「无改动」早返回（`benchmarks/runner.py:377-398`）、docker verifier 分支（`:446-468`）、本地 test_command 分支（`:530-552`）——每处都是 `result = TaskResult(...)` 完整重建，只列出它自己知道的字段。唯一「安全」的路径是 `except Exception`（`:556-559`），它是**原地**改 `result.status`/`duration_seconds`/`reason`。所以实现必须二选一：把 workflow 字段塞进这 3 个重建调用，或改成 `dataclasses.replace(result, ...)` 的增量写法。只改 `:308` 的初始构造是最容易踩的坑——本地任务（`execution_environment != "docker"`，`runner.py:319`）会走到 `:530` 把你刚写进去的字段全抹掉。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **旁路采集的挂点是 `AsterwyndRunner.run` 内 `await agent.run(...)` 返回之后，数据源是 `manager.list_workflows()` 枚举到的 scheduler。** 依据：`subagent_manager` 在 `benchmarks/agent_runner.py:312-318` 构造，`await asyncio.wait_for(agent.run(...))` 在 `:336-345`，之后到 `:369` 的 `await mcp_manager.aclose()` 之间 manager 仍在作用域里；调度器实例经 `manager.register_workflow(scheduler)` 注册（`agent/tools/builtin/subagents.py:484`、`:761`，`agent/subagent/manager.py:549-550`），且 `scheduler.run()` 的 `finally` 只调 `release_workflow_bucket` **不反注册**（`agent/subagent/scheduler.py:574-583`），所以 workflow 终结后仍可从 `manager.list_workflows()`（`manager.py:555-556`）拿到 id、经 `get_workflow()`（`:552-553`）拿到 scheduler、再读 `scheduler.status()`（`scheduler.py:527-529`）或 `parent_envelope()`（`:2065-2087`）。**注意超时分支**（`agent_runner.py:346-360`）会在 `agent.run` 被取消时直接 return `AgentRunResult`——它绕过了上述采集点，实现必须在这里也采一次（或显式把 workflow 字段留 `None` 并在 report 里标「超时未采集」），否则超时任务的 workflow 字段会「假装不存在」而不是「采集失败」。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **`queue_wait_s` 不需要改 scheduler——排队时长数据今天就在 run record 上，design D3/Risks 里「可能需新增字段、改动面扩大到 scheduler」的前提不成立。** `SubagentRunRecord.created_at` 在 `agent/subagent/manager.py:91`（`field(default_factory=time.time)`），`started_at` 在 `:92`，赋值点是 `_start_task` 里的 `run.started_at = time.time()`（`manager.py:817`）；而 scheduler 自持这些 run record 的引用（`self._run_refs`，初始化 `scheduler.py:379`，登记 `:1564`）。所以 `queue_wait_s` 可以在 scheduler 内直接算成 `sum(r.started_at - r.created_at for r in self._run_refs if r.started_at)`，零新字段、零新分支。唯一要拍板的是聚合口径（见 Q4）。这条同时约束实现：**不要**为此去动 manager/scheduler 的字段定义。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **`workflow_cost_usd` 用 `manager.cost_ledger` 时，benchmark 路径今天根本没挂 ledger——它会在全部 C5 任务里恒为 0，实现必须先接上 ledger 才能取数。** `AsterwyndRunner.run`（`benchmarks/agent_runner.py:312-318`）构造 `SubAgentManager` 时**没有**传 `cost_ledger`，`SubAgentManager.__init__` 的 `cost_ledger` 默认 `None`（`manager.py:345`，`self.cost_ledger = cost_ledger` 在 `:358`），`_build_subagent_loop` 把它原样透传（`:1150`），`AgentLoop._record_llm_cost` 里 `if self.cost_ledger:` 于是整段跳过（`agent/loop.py:1090`）——`CostLedger` 完全没被写入任何条目。而 scheduler 的 `_ledger_total()` 读的就是 `manager.cost_ledger.total()`（`scheduler.py:1945-1952`），`_attribution_bill()` 同样依赖 `manager.cost_ledger`（`:915-919`）。所以 benchmark 场景下 envelope 的 `total_cost` / `attribution` / `workflow_cost_usd` 都为 0/空。**结论**：C5 必须给 `AsterwyndRunner` 注入一个 `CostLedger` 实例（并经 manager 透传到 loop），否则 `workflow_cost_usd` 指标是假的 0；报告里要把「ledger 未挂」与「真 0 成本」区分开，不能都显示 0。 来源: grill-benchmark-workflow-replay-2026-09-15（审阅员补充，已核 `agent_runner.py:312-318` / `manager.py:345,358` / `loop.py:1090` / `scheduler.py:1945-1952`）

- **决策**: **`node_count`/`run_count` 在 envelope 里没有现成键，取值口径必须写死；尤其不能用 `total` 或 `self._runs` 顶替。** envelope 顶层能用的只有：`nodes`（节点列表，`scheduler.py:2026`，长度 = `len(plan.nodes)`，**含自动插层**）、`total`（`_unit_counts` 的**逻辑执行单元**计数，`scheduler.py:1970-2001` + `_logical_units` `:1960-1968`，foreach 一个容器算「展开项数+1」）、`completed`/`failed`（**run 口径**，从 `_run_refs` 统计，`:2009-2018`）。所以：`node_count := len(envelope["nodes"])`；`run_count` 需要新暴露一个键（建议在 `_envelope` 里加 `"run_count": len(self._run_refs)`），**不要**用 `completed + failed`（漏掉 queued 中被取消且未进 `_run_refs` 的情形、语义也混淆），**更不要**用 `self._runs`——它是派发前**预扣**的累计值，`_budget_summary` 的 docstring 明写它可能大于实际派发数（`scheduler.py:999-1003`），`_check_foreach_budget` 的预扣路径（`:1470-1493`）正是为此存在。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **`_run_refs` 只登记「派发成功」的 run，`queue_full` 的 run 不在其中——任何以它为分母的指标天然排除被拒 spawn，这与 D4 要单独计数的「拒绝降级」是两回事，不能混算。** 依据 `scheduler.py:1552-1564`：`launched["status"] == "queue_full"` 时直接 `return {...}`，**不执行** `self._run_refs.append(...)`（append 在 `:1564`，只在非 queue_full 路径到达）。所以冗余度分母、`queue_wait_s`、`run_count` 都以 `_run_refs` 为准时，「被拒的 spawn」不会污染它们——但也意味着拒绝计数必须**独立**统计，无法从 `_run_refs` 反推。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **D4 的「不新增执行路径分支」与「拒绝降级计数四类来源」在今天的代码上只对得上 1 类——四类里三类没有现成信号，必须新加计数器（这是 instrumentation，不是执行分支，但确实要改 manager/scheduler）。** 逐类核点：
  - **queue_full**：`manager._take_back_if_queue_full` 把 `run.status = "queue_full"`（`manager.py:864-884`），scheduler 在 `:1553-1563` 接住并返回同名字段，但随后 `_apply_run_status` 把「非 completed/cancelled」一律折成节点 `failed`（`scheduler.py:1592-1601`），`queue_full` 字样不进任何计数。另外 scheduler 头部 docstring 明确「准入背压让 workflow **永不**触发 queue_full」（`scheduler.py:10-13`），所以这一类在 workflow 内**预期恒为 0**——实现要能诚实报 0，而不是给个看着像有数据的数。
  - **深度撤工具**：`manager._build_subagent_loop` 里 `if depth is not None and depth >= self.max_depth: hidden_tools = SPAWN_TOOL_NAMES`（`manager.py:1130-1138`），**既无计数也无回传**，scheduler 完全不知道发生过。
  - **spawn 预算拒绝**：`_check_spawn_budget` 抛 `RuntimeError`（`manager.py:1440-1457`，经 `_check_admission` 在 `:596`/`:642` 调用），被 scheduler 的兜底 `except Exception`（`scheduler.py:1163-1166`）折成节点 `failed` + `state.error` 文本——只能靠字符串匹配认出，脆弱。
  - **图级超限**：`GraphRecursionError` → `self._diagnostics = exc.to_dict()` + `self._status = "graph_recursion_exceeded"`（`scheduler.py:564-568`、`:682-688`），是**唯一**有结构化信号的（`exc.to_dict()` 带 `steps`/`limit`/`current_nodes`/`reason`）。
  结论：实现要给 manager 加两个计数器（spawn 拒绝次数、depth 撤工具次数）并在 `_check_spawn_budget`（自增点 `manager.py:1453-1457` 的 raise 前）与 `_build_subagent_loop`（自增点 `:1136-1137` 的 `hidden_tools = SPAWN_TOOL_NAMES` 分支内）的既有分支里自增；scheduler 侧把 queue_full（`:1553-1563`）与 graph 超限（`:564-568`/`:682-688`）计数落到既有出口。这不动执行流，但会改 `manager.py` 的**三处**函数体——即 `_check_spawn_budget`、`_build_subagent_loop`、以及承载两个新计数器的写入点（建议与 `_count_spawn` `:1459-1474` 同款：`current_workflow_id()` 分桶 + 无 workflow 时落 manager 生命周期计数）。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **`$/resolved-task` 的分母必须复用既有的 `PASS_STATUSES` + `is_valid_round` 口径，不能自造。** `benchmarks/report.py:36` 定义 `PASS_STATUSES = {"passed", "passed_with_warnings"}`，`report.py:80-90` 的 `_is_pass`/`_valid_results` 与 `benchmarks/statistics.py:60-71` 的 `is_valid_round` 共同决定「哪些轮次进分母」（`unsupported` 与 `INVALID_ROUND_REASONS` 一律剔除）。`benchmarks/compare.py:20` 的 `RESULT_ORDER` 只有 5 个状态、**没有** resolved 概念。所以摘要里的 `$/resolved-task` 必须是 `总成本 / _is_pass 且 _valid_results 的条数`，与 pass@k 同源；拿 `compare.py` 的 `stats[name]["passed"]` 当分母会与 report.py 的 pass@k 对不上（`passed_with_warnings` 会被漏算）。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **compare.py 存在，扩展点固定是 3 个函数 + 两类读法，且必须保持「raw dict 宽松读」的既有风格。** 文件 `benchmarks/compare.py` 的入口是 `load_run`（`:92-102`，直接读 `result.json` 成 raw dict，**不经** `TaskResult`）、`build_summary`（`:105-212`）、`build_html`（`:282-408`），配对分析另走 `_paired_data`（`:215-231`）→ `TaskResult.from_dict`。关键事实：`build_summary`/`build_html` 一律用 `r.get("input_tokens", 0) or 0` 这类宽松取值（`:183-190`、`:338-345`），新增 workflow 字段必须照抄这个风格（`r.get("workflow_mode")` + `None` 分支），否则读旧 artifact 会 KeyError；而经 `TaskResult.from_dict` 的路径会**静默吞掉**未知键（`benchmarks/models.py:93-102` 只保留 `__dataclass_fields__` 里的键），所以 `_paired_data` 那条路不需要额外容错。`compare.py` 的主入口 `main()`（`:411-459`）会把结果写到 `benchmarks/reports/comparison.md`/`.html`，且**跳过 `truncated` 的 run**（`:428-434`）——新增口径段要落在这两个文件的渲染函数里。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **`max_active`/`max_spawns` 是配置文件字段而非 benchmark CLI 参数——「小 k vs 大 N」对照臂今天无法从命令行表达，必须新增通道。** `max_active=5` / `max_queued_runs=20` / `max_spawns=200` 是 **`SubagentsConfig`** 的字段（`agent/config.py:336-338`，解析在 `_parse_subagents_config` 的 `:1423-1458`，走 `_validate_positive_int`）；`WorkflowLimitsConfig`（`agent/config.py:299-313`）装的是三闸 `recursion_limit`/`max_nodes`/`max_runs`，解析在 `_parse_workflow_limits`（`:1460-1478`）。两者都嵌在 `subagents` 下（`workflow` 挂在 `SubagentsConfig.workflow`，`:342`）。而 benchmark 侧的构造入口 `_build_benchmark_runner`（`agent/main.py:929-1023`）只接收单个 `config_path`（`:934`），**没有任何 workflow 开关**；`benchmark` 命令的参数表（`agent/main.py:701-713`）也只有 `--agent`/`--runs-dir`/`--parallel` 等既有项。所以 D5 的对照臂最少要新增两个 CLI 标志（如 `--workflow-max-active` / `--workflow-max-spawns`）或约定「两次跑用两份 config yaml」，这条通道的选择见 Q5。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **dynamic-replay 的「不重跑规划模型」在代码里 = 绕开工具层直接构造 `WorkflowScheduler`；并且 parse 时必须带 `_spec_bounds` 以复现 record 时的三闸默认值。** 三个工具入口 `DeclareWorkflow`（`agent/tools/builtin/subagents.py:468-499`）、`StartWorkflow`（`:524-542`）、`RunWorkflow`（`:749-775`）全部由模型调用驱动，replay 不能走它们。可复用的现成先例是 `agent/subagent/patterns.py:409-443` 的 `run_pattern`：`compile_pattern(...)` → `WorkflowScheduler(manager, bus=bus)`（`scheduler.py:345-351`）→ `manager.register_workflow(scheduler)` → `await scheduler.run(spec)`。另外 **spec 的解析必须走 `parse_spec_for_manager`**（`subagents.py:415-417`，它注入 `_spec_bounds`，`:405-412`），否则 `recursion_limit`/`max_nodes`/`max_runs` 会退回模块常量（`agent/subagent/workflow.py:35-37`）而不是 record 时的 `subagents.workflow.*` 配置——同一份 spec dict 会算出不同的运行期上限，违反 D1「两者 spec_hash 必须一致」的验收。 来源: grill-benchmark-workflow-replay-2026-09-15

- **决策**: **`WorkflowSpec.to_dict()` 是自包含可还原的，foreach 的 `items` 与 route 的 `$ref` 都能 replay；但 replay 重跑的是「节点内的模型调用」，不是「零 LLM 重放」，这一点必须在验收口径里说清。** 序列化面：`to_dict()`（`workflow.py:270-285`）→ `node.to_dict()`（`:156-189`），foreach 分支写 `items`（`:182-183`，parse 期静态列表，`_parse_items` `:604-609`）、`source`/`source_field`（`:184-187`）；route 分支写 `cases`（`:177`，`$ref` 是纯字符串，`parse_route_ref` 在 `:94-105` 还原，运行期只读 `NodeState.slots` `:1845-1850`）；`parse_workflow_spec` 能把这份 dict 完整还原（`:304-417`）。**但**：replay 时每个 subagent/aggregate 节点仍会真实调用 LLM（`scheduler._launch_run` → `manager.run_subagent`，`:1537-1546`），只有「规划模型生成 spec 的那一次调用」被省掉。所以 D6 的「两次跑可比」只可能成立于 **fake LLM** 场景；真实 LLM 下 cost/token 不会相等，见 Q6。 来源: grill-benchmark-workflow-replay-2026-09-15

## Open Questions

- **Q1**: dynamic-record 的采集点是「**一个任务可能有 0 个、1 个或多个 workflow**」，落盘文件名 `workflow_record.json`（design D2，单数）该怎么对上？
  **场景**: benchmark 任务 `asterwynd-009` 用 `asterwynd` runner 跑，模型在一个 turn 里先 `DeclareWorkflow` + `StartWorkflow` 跑了一张「调研 3 个文件 → 汇聚」的图，第二个 turn 又 `RunWorkflow` 起了第二张图；或者模型压根没起 workflow，只调了普通 `SpawnSubagent`。
  - **现状**：两处 scheduler 实例都在 `manager._workflows`（`manager.py:399`）里，`manager.list_workflows()`（`:555-556`）会返回 2 个 id；没起 workflow 时返回空列表。
  - **写法 A（单文件取最后一个）**：`workflow_record.json` 只存 `list_workflows()[-1]` 的 spec。第二张图覆盖第一张 → replay 只能重放半段行为，且「同任务两次跑」会因为图的顺序不稳定而不可比。
  - **写法 B（一任务一记录、含 workflow 列表）**：`workflow_record.json` 顶层变 `{"workflows": [ {spec, spec_hash, ...}, ... ]}`，replay 时按序重放全部。文件名不变但 schema 与 design D2 的示例（单对象）不符，spec delta 的 Scenario 也要改。
  - **写法 C（一次 run 一条记录，按 workflow_id 命名）**：`workflow_records/<workflow_id>.json`，另在 `result.json` 记 `workflow_ids: [...]`。最忠于事实但改了 design D2 的落盘约定。
  另外要一并拍板：**没起 workflow 的任务，`workflow_mode` 记什么**——`"dynamic-record"`（模式确实启用了）+ 全字段 null，还是干脆不记 mode？以及**超时路径**（`agent_runner.py:346-360`）采集失败时，是记「模式已启用但采集为空」还是「采集失败 + 原因」。
  请拍板落盘粒度（A/B/C）与空/失败时的字段语义。

- **Q2**: D4 的**「有用产出」用什么信号判定**？现有代码里**没有**「这个 run 的结果被下游消费了」这个标记，必须新定义。
  **场景**: 一张 `planner → fan(foreach, source=planner, source_field=items) → join(aggregate) → root(aggregate)` 的图，`fan` 展开 5 项。5 个展开项里 4 个被 `join` 的 `_collect_slots`（`scheduler.py:1720-1740`）读走，第 5 个因为 route 走了另一条分支、`join` 的 reducer 是 `first_non_empty`（`workflow.py:31`）而被丢弃。同时模型额外起过一个「探路」的 subagent，它的结论只是被模型自己读进上下文，**没有进任何 workflow 的槽**。
  - **口径 A（结构口径，现有信号即可算）**：`有用产出 := status == "completed" 且 (该节点有数据出边 或 在 plan.terminal 里) 的 run 数`。上例中第 5 个展开项仍算「有用」（它有出边），探路 subagent 因不在 workflow 内直接不计入分子也不计入分母。**零新代码**，但答不出「冗余」。
  - **口径 B（消费口径）**：`有用产出 := 该 run 的结果槽真的被某个下游节点的 slots 合并读过`。需要新增「槽被读」的记录点（`_collect_slots`/`_node_output` 里打标），上例第 5 项判为无用。更准，但要动 `scheduler.py` 的汇聚路径——与 D4「不新增执行路径分支」的措辞有张力（加标记不改流程，但确实改函数体）。
  - **口径 C（终端口径）**：只有进入 `plan.terminal` 节点最终结果的 run 才算有用。上例 `fan` 的 5 项全被算成无用（它们是中间产物），冗余度会虚高到吓人。
  - **分母还要定**：`spawn 总数` 取 `manager.spawn_count()`（`manager.py:573-578`，按 workflow 桶计数、每次 create + 每次 run 各计 1，见 `_count_spawn` `:1459-1474`）还是 `len(_run_refs)`（`scheduler.py:379`）？两者口径不同：前者含 `create_subagent`（`scheduler.py:1529-1534`），后者只含真实 run，且**同一个量在 D4 里既当分子分母又当「spawn 拒绝」的对象**。注意 `spawn_count()` 的内部实现是 `manager._workflow_spawn_counts.get(workflow_id, 0)`（`:578`），桶在 `scheduler.run()` 的 finally 里被 `release_workflow_bucket`（`scheduler.py:582` → `manager.py:569-571`）**清掉**——所以 run 结束后再调 `spawn_count()` 会返回 0，采集必须在 `run()` 返回前或改从 envelope 取值（现 envelope **没有** spawn 计数字段，需要新加）。
  请拍板「有用产出」口径（A/B/C）与分母定义，并确认 spawn 计数是否新暴露进 envelope。

- **Q3**: D4 的**「深度撤工具」计数按什么计**？四个计数器里只有这一个的计数点是「能力被摘掉」而不是「一次拒绝/降级事件」。
  **场景**: 一张 4 层图（leaf→shard→domain→root），`max_depth` 默认 3（`agent/config.py:339`）。跑完后第 4 层有 8 个 subagent 节点，每个节点的 run 深度都是 4，于是 `manager._build_subagent_loop` 在 8 次子 loop 构造时都走进 `depth >= self.max_depth` 分支把 4 个 spawn 工具摘掉（`manager.py:1130-1138`，`SPAWN_TOOL_NAMES` 定义在 `:326`）。
  - **口径 X（按构造次数计）**：`withdrawn_tools_count = 8`。度量的是「多少次子 agent 被降级」，与「模型撞了几次护栏」的直觉不完全一致——这 8 个 agent 可能一次都没想 spawn。
  - **口径 Y（按实际尝试计）**：需要被摘工具的 agent 真的调用了 spawn 工具才算一次。但工具**已被摘掉**，模型调用只会拿到「未知工具」错误，拦不到信号 → 要在工具注册层加兜底才能计数，改动面明显更大。
  - **口径 Z（按深度超限的 run 数计，即 X 的别名但语义写明为「被降级的 run 数」）**：与 X 数值相同但口径诚实，文档与报告字段名直接叫 `depth_capped_runs` 而不是 `rejected_*`。
  请拍板用哪个口径，以及这个计数是并进总的「拒绝降级计数」还是单列一个指标。

- **Q4**: `queue_wait_s` 的**聚合口径**（数据已确定在 `run.created_at`/`run.started_at`，见 Confirmed Decision 5，不用再讨论「能不能采」）。
  **场景**: 一张 6 节点的图，`max_active=5`（`agent/config.py:336`），6 个 run 的排队时长分别是 `[0.01, 0.02, 0.03, 0.04, 0.05, 210.0]` 秒——最后一个因为前排 run 慢而排了 3.5 分钟。
  - **sum = 210.15s**：报的是「所有 run 的排队时间总和」。图规模一大这个数会线性膨胀，跨图不可比。
  - **max = 210.0s**：报的是「最长的单次排队」。对「并发配置是否卡住关键路径」最敏感，但忽略了大面积小排队的累积。
  - **p50/均值 ≈ 35s**：被长尾拉偏或淹没，两者都有。
  - 另需定：**被取消的 run 要不要计入**（`run.started_at` 为 `None` 的 run 在表达式里被无条件跳过，`manager.py:92`/`:817` 决定这个分支）——即「排了队但没跑成就被取消」的 run 在 `queue_wait_s` 里应该沉默消失还是单独计数进 Q3 的拒绝降级。
  请拍板聚合口径（sum/max/p50）与取消 run 的处理。

- **Q5**: D5 的**对照臂「小 k 高质量 vs 大 N 暴力」用什么通道表达**，以及具体的配置取值是什么？
  **场景**: 想跑一组对比：臂 A 想表达「同时最多 3 个 subagent、但总共允许 60 次 spawn」，臂 B 想表达「同时最多 16 个、总共只允许 24 次 spawn」。两次都要用同一个 benchmark 任务集、同一份 LLM 配置。
  - **通道 X（两份 config yaml + 两次 `asterwynd benchmark`）**：写 `configs/small-k.yaml` 与 `configs/large-n.yaml`，各含 `subagents.workflow.max_active`/`max_spawns`（`agent/config.py:293` 的 `WorkflowLimitsConfig` 嵌在 `subagents.workflow` 下，解析在 `:1430-1445`），分别 `--config` 跑。零代码改动，但「对照臂」只是**跑法约定**、不是代码保证的能力——没人跑第二遍就没有对照。
  - **通道 Y（新增 CLI 标志）**：`benchmark` 命令加 `--workflow-max-active` / `--workflow-max-spawns`，`_build_benchmark_runner`（`agent/main.py:929-1023`）把它们覆盖进 config。好处是单条命令能完整表达臂；代价是新增 CLI 面 + 要处理与 yaml 的优先级（既有 `--parallel` 的先例在 `:998-1006`，yaml 优先于推导值）。
  - **通道 Z（任务级字段）**：在 `task.json` 里加 workflow 覆盖字段（`benchmarks/task_schema.py:9-33` 的 `TaskSpec`）。最贴近「同一任务集跑不同编排策略」，但 `TaskSpec` 是 frozen dataclass 且 `from_dict` 是显式白名单（`:37-70`），加字段要动 schema + 所有 75 个 task.json 的兼容性。
  - **取值也要定**：`max_spawns` 的 workflow 桶上限被 scheduler 校准为 `spec.max_runs * 2`（`scheduler.py:573` → `manager.register_workflow_bucket`，`manager.py:558-567`，注释解释「每次真实 run 计 2 次 spawn」）——如果臂 A 想「总共 60 次 spawn」，在默认 `max_runs=300` 下桶是 600，**用户配置的 `max_spawns=60` 会被 `min(60, 600)` 生效**没问题；但反过来臂 B 写 `max_spawns=24` 时，24 < 2×图规模，会让图在第 12 个 run 就炸 `spawn budget exceeded`，而 D5 想要的可能是「并发高、但总配额低」而不是「图跑不完」。这条要在取值说明里写清。
  请拍板通道（X/Y/Z）与两组具体数值。

- **Q6**: D6 的 **record→replay 可比性断言，容差怎么定**——尤其 `cost` 与 `run_count` 在真实 LLM 下**本来就不会相等**。
  **场景**: 同一份 `workflow_record.json`，`dynamic-replay` 重放。规划模型确实没跑（省了那几次调用），但 `_launch_run` → `manager.run_subagent`（`scheduler.py:1537-1546`）会照常为每个 subagent/aggregate 节点发起真实 LLM 调用。
  - `spec_hash`：**必然相等**（同一份 spec dict 走同一个 `parse_workflow_spec` + `spec_hash`，`workflow.py:287-291`）。这是唯一可以硬断言的字段。
  - `node_count`：相等（`len(plan.nodes)` 只取决于 spec 与配置；但注意自动插层由 `_build_plan` 决定，若聚合阈值配置不同会插出不同的层）。
  - `run_count`：**通常相等但不保证**——若某个节点在 record 时因预算/超时 failed、replay 时成功（或反之），route 的 `$ref` 分支会走不同路径，`foreach` 的 `max_items` 截断与 `_reset_subtree` 的级联重跑（`scheduler.py:1196-1215`）都会改变实际 run 数。
  - `cost`：**必然不等**。真实 LLM 每次的 token 数不同；replay 只省掉规划调用这一项。若把容差定成「±10%」而 record 那次规划调用恰好占总成本 30%，就必然失败。
  - `peak_active`/`critical_path_s`：受机器负载与 LLM 延迟影响，属 wall-clock 噪声，**不适合做可比性断言**。
  所以「可比性」到底断什么，直接决定这个验收能不能稳定跑绿。
  - **口径甲（结构可比）**：只硬断言 `spec_hash` 相等 + `node_count` 相等；`run_count` 报差异不判失败；`cost` 只报不判。真实 LLM 下能稳定跑，但验不到「行为一致」。
  - **口径乙（fake 定可比）**：可比性断言全部放在 fake LLM 场景（同一 fake 输出 → `run_count`/`node_count`/`cost` 全等），真实 LLM 场景只做「spec_hash 相等 + 无异常完成」，不做数值断言。
  - **口径丙（真实 LLM + 宽容差）**：全部字段都断言但要给容差（如 cost ±30%、run_count ±1）。看起来最完整，实际最容易 flaky。
  请拍板可比性断言的口径（甲/乙/丙）与各字段的容差数值。

- **Q7**: D6 的**降级记录写在哪、用什么措辞**，才既能被 CI/artifact checker 接受、又不被当成「占位文本」？
  **场景**: 本地 LLM 不可用（比如 `build_llm` 拿不到 key），端到端真实 LLM 验证跑不了，于是按 D6 降级为 fake round-trip。
  - **落点 A**：写进 benchmark run 的 `result.json` / `run.json`（新增字段如 `e2e_llm_verified: false` + `e2e_llm_skip_reason: "..."`）。**不进** artifact checker 的扫描面（checker 只扫 `openspec/changes/**` 的 proposal/design/tasks/reviews/specs，判定逻辑见 `scripts/check_openspec_artifacts.py:715-762`、`_is_placeholder_body` 在 `:325`、`PLACEHOLDER_ONLY_TOKENS` 在 `:126-129`），所以安全。
  - **落点 B**：写进 `reviews/building-review.md` 或 `design.md` 的一段结论。**有风险**：`_is_placeholder_body`（`:325-...`）会对整节正文做占位判定，而占位 token 表含「待确认/未确认/待定/未决/待补充/占位」等（`:126-129`），且 checker 对其他节还有「section is empty or placeholder-only」的报错（`:427-428`）。整节只写「未验证」三个字确实可能被判空。
  - **落点 C**：写成 `docs/known-debt.md` 条目。最正式，但那是受保护路径（AGENTS.md「受保护 artifact 证据」），需要 `workflow-events.jsonl` 结构化解释事件 + review manifest，成本最高。
  - **措辞**：无论落哪，都不该写成「暂未验证」这种单句；要写成「X 未执行，原因是 Y，替代验证是 Z（fake round-trip 断言了 spec_hash/node_count），缺口是 W」的完整陈述。
  请拍板落点（A/B/C 或组合）与是否接受「本次 C5 只能在 fake 场景硬断言可比性、真实 LLM 侧降级」这个完成口径。

- **Q8**: 三模式在**接口层怎么接线**：`workflow_mode` 是 `AgentRunner` 的构造参数、`BenchmarkRunner` 的构造参数，还是 `benchmark` 命令的 CLI 标志？以及 **template 模式跑什么**？
  **场景**: 想跑 `uv run asterwynd benchmark benchmarks/tasks --agent asterwynd --workflow-mode template`。
  - **接线的硬约束**：`AgentRunner.run` 的签名是 `(task, problem_statement, workspace, output_dir, trace)`（`benchmarks/agent_runner.py:26-33`）——**没有** mode 参数的位置；`BenchmarkRunner.__init__` 也没有（`benchmarks/runner.py:76-110`）。三模式要么加进构造参数（`AsterwyndRunner(...)` / `BenchmarkRunner(...)`，再透传到 `_build_benchmark_runner` `agent/main.py:929-1023`），要么把 mode 塞进 `TaskSpec`（但那会污染任务语义）。`dynamic-replay` 还多一层：它需要**读一份已有的 `workflow_record.json`**，这个路径从哪来（CLI `--workflow-record <path>`？约定从上次 run 目录读？）。
  - **template 模式的歧义**：`agent/subagent/patterns.py:303-308` 的 `PATTERNS` 只有 4 个模式（`orchestrator-worker` / `peer-review` / `hierarchical` / `bidding`），`compile_pattern`（`:234-243`）需要一个 `task` 字符串和 `params`。所以「template 模式跑 benchmark 任务」有两种读法：
    - **读法 1（pattern 当被测编排）**：把 benchmark 任务的 problem_statement 当 `task` 喂给某个 pattern，跑出来的 envelope 按 benchmark 的 verifier 判分。此时「被测对象」是 pattern 模板本身，`task` 文本要写得很具体才能让叶子节点真去改代码。
    - **读法 2（pattern 当参照系）**：只是拿 4 个固定模板跑同一批任务，作为 dynamic 模式的对照臂（D5 的「固定 baseline」），不追求 pattern 真能解出任务，只比编排指标。
    两者对 verifier 的期望截然不同（读法 1 要求 pass rate 有区分度，读法 2 只要求指标可比）。
  请拍板 `workflow_mode` 的接线位置（构造参数/CLI 标志/task 字段）、`dynamic-replay` 的记录来源通道，以及 template 模式的读法（1/2）。

- **Q9（审阅员补充）**: 渲染层要不要**独立的 workflow 段**，以及三模式各自的 envelope 投影差异怎么在报告里表达？
  **场景**: 一次 dynamic-record 跑完，run 目录里有 75 份 `result.json`；其中 60 份是动态 workflow（有 `node_count`/`run_count`/`redundancy`），10 份「模型没起图」（`collection_status: "no_workflow"`，workflow 字段全 null），5 份 template 模式（只有 pattern 级字段，没有 spec_hash 属主）。渲染时这三种行能不能出现在同一张表里、null 怎么显示，直接决定报告可读性。
  - **现状**：`render_report`/`render_html`（`benchmarks/report.py:172`、`:351`，实现都在 `_render` `:191-349`）按层聚合、只渲染既有列；`render_summary`（`benchmarks/models.py:161-174`）是固定 6 列表格。三处渲染入口都要动，且 null 必须与「没跑 workflow」区分开——D1 的三模式意味着「workflow_mode 字段本身就有三态 + null」，单一张表会有大量空单元格。
  - **选项 α（独立 section）**：在 `_render` 与 HTML 各加一个「Workflow Orchestration」段，只统计**有 workflow 的记录**（`collection_status` 非 `no_workflow`），null 行不进该段；主表只加一列 `workflow_mode` 供区分。
  - **选项 β（统一表格 + null 显示）**：把 9 个 workflow 字段与编排指标全加进主表，null 显示 `-`。
  - **选项 γ（两段式 + 分层）**：有 workflow 的进编排段，没有的进主表，两段共用同一套聚合口径。
  - **审阅员推荐**：**选 α**（独立 section + 主表加一列 mode）。理由：增量最小（不动既有列与 pass@k 聚合）、三态区分天然清晰（没跑 workflow 的任务不污染编排统计的分母）、且与 Confirmed Decision 9（`$/resolved-task` 复用 `PASS_STATUSES` + `is_valid_round` 口径）不冲突——编排段是**旁挂展示**，不参与 pass@k 分母。
  - **待用户拍板**：α/β/γ；以及编排段的层级（按任务 / 按 run / 按层）。

- **Q10（审阅员补充）**: dynamic-replay 与 template 模式的跑法——template 推荐读法 1 已定「走 verifier 判分」，但 **dynamic-replay 跑出来的结果走不走 benchmark verifier**？这决定 replay 是「编排回放验证」还是「任务结果验证」。
  **场景**: 同一份 record 重放。replay 会真跑每个节点的 subagent（真改代码，若任务允许），最终产物可能天然能过 verifier，也可能不能（record 时那条路径就已失败）。两种读法：
  - **读法 A（只比编排，不判分）**：replay 只断言「spec_hash 一致 + 无异常完成 + 编排指标可比」（即 Q6 乙的口径），**不调用** `get_verifier`（`benchmarks/runner.py:403`）。replay 的 `TaskResult.status` 直接由 agent 侧 `AgentRunResult.status` 推出，不写 `passed`/`failed`。
  - **读法 B（照走 verifier）**：replay 与普通任务一样跑 `test_command` + verifier，结果进 pass@k 分母。
  - **审阅员推荐**：**选读法 A**。理由：Q6 推荐已明确「真实 LLM 下 cost/run_count 只报不判」，若 replay 还进 pass@k 分母，会出现「同一任务的 record 与 replay 各算一次 pass」的双重计数，污染 D4 的完成率与 `$/resolved-task`（Confirmed Decision 9）。replay 的定位是**编排协议验证**（G6 #177 的「可重放」），不是独立任务结果。
  - **必须写进 spec 的后果**：若选 A，`result.json` 需要区分「任务结果」与「replay 结果」——建议 replay 任务落 `mode: "dynamic-replay"` 且 `status` 用专用值（如 `replayed`），并让 `is_valid_round`（`benchmarks/statistics.py:60-71`）与 `_valid_results`（`report.py:84-90`）显式排除 replay 记录，否则 pass@k 分母会被 replay 行污染。这是**新 scenario**，spec delta 的「benchmark workflow 三模式」requirement 下要补一条。
  - **待用户拍板**：A/B；若选 A，replay 记录的 `status` 专用值取名与是否进 report 的哪个段。

## Codex Recommendations（codex 独立评审，2026-09-15）

以下 8 条是 codex 独立评审（agent `aa6ed8cc`）对 Q1–Q8 的**推荐答案**。主 agent 已把它们作为「codex 推荐」标注进停轮确认，最终以用户在 `## User Confirmation` 的逐条答复为准。

**meta-review 修订摘要（grill-benchmark-workflow-replay-2026-09-15，独立零记忆审阅员）**：8 条推荐**互不矛盾**，但有 1 处接口歧义（Q8 的 `--workflow-record` 参数形态）、2 处与 design.md 原文的措辞冲突（D2 单对象 schema vs Q1 列表；D3 的 `queue_wait_s` 需新增 vs Confirmed Decision 5 不需要）、以及 3 处必须钉死的实现细节（Q1 过滤未跑的 declared 图、Q3 计数挂 workflow 桶、Q7 落到 `TaskResult`）。修订均以「审阅核实」子项记在各条推荐下，不改推荐方向。另补 Q9/Q10 两个原 grill 遗漏的设计点。

**元结论：`workflow_cost_usd` 在 benchmark 路径今天恒为 0**（benchmark 从未给 manager 注入 `CostLedger`，见 Confirmed Decisions 新增第 14 条）——这是 Q2/Q6 都依赖的取数前提，必须在实现前修，否则整个成本口径是假的。

**交叉一致性核对（meta-review 逐对检查结果）**：

| 交叉点 | 结论 | 依据 |
|--------|------|------|
| Q1 ↔ Q8（落盘 vs 接线） | **一致（修订后）**：record 写 `<run_dir>/tasks/<task_id>/workflow_record.json`，replay 的 `--workflow-record` 接受同一 run-dir、按 task_id 推导同一路径 | Q8 推荐原写 `--workflow-record <path>`，无法服务 N 个任务，已修订为 run-dir |
| Q2 ↔ Q8（spawn 暴露 vs 接线） | **不冲突**：Q2 的暴露点是 scheduler 的 `_envelope()` 新键（run 时写、AgentRunner 读），Q8 只改 CLI→构造参数；两者不在同一段代码，无先后依赖 | `scheduler.py:575-584` / `agent_runner.py:284-385` / `agent/main.py:971-996` |
| Q2 / Q3 / Q4 计数独立性 | **三者互不重复**：`spawn_count` 是冗余度**分母**；`depth_capped_runs` 是拒绝总量的**加项**；`queue_cancelled_runs` 是**单列分母侧**量。单个指标内无重复计数（一个被降深度的 run 会同时进 spawn 分母与 depth_capped 加项，但这是**跨指标**的正常重叠，不是同一指标内的重复） | `manager.py:573-578` / `:1136-1137` / `scheduler.py:379,1564` |
| Q4 ↔ Q3（取消 vs 拒绝） | **边界清晰**：`queue_cancelled_runs` 明确单列、**不并入**拒绝总量；`depth_capped_runs` 明确**并入**拒绝总量。两条规则已并排写在各自「审阅核实」里，并额外提示 `queue_cancelled_runs` ≠ `queue_full`（语义相反） | 本文件 Q3/Q4 推荐注记 |
| Q6 ↔ Q7（可比口径 vs 降级落点） | **配套**：Q6 乙的「真实 LLM 只断 spec_hash」就是 Q7 要记录的「降级」分支，`e2e_llm_verified` 的 true/false 恰好在这条分支上写 | 本文件 Q6/Q7 推荐注记 |
| Q5 ↔ Q8（对照臂 vs 三模式） | **正交**：Q5 走 config YAML 通道（`_load_cli_config`），Q8 走 CLI→`AsterwyndRunner` 构造参数；两者落在 `_build_benchmark_runner` 的不同段落，前提是 Q8 **不**引入 `--workflow-max-active` 之类 CLI 覆盖 | `agent/main.py:964-969` vs `:986-993` |

- **Q1 推荐（选 B）**：一任务一份 `workflow_record.json`，顶层 `{"workflows": [{spec, spec_hash, scheduler_version, budget_config, ...}], "collection_status": "..."}`，按 `manager.list_workflows()` 注册顺序排列，replay 按序重放全部。没起 workflow 时仍记 `workflow_mode: "dynamic-record"` + `workflows: []` + `collection_status: "no_workflow"`；超时采集失败记 `collection_status: "failed"` + `collection_error` + 已采到的部分列表。
  - **审阅核实**：`manager.list_workflows()` 返回的是 `list(self._workflows)`（`manager.py:555-556`），字典插入序 = `register_workflow` 调用序；`register_workflow` 的调用点有 4 处——`DeclareWorkflow`（`agent/tools/builtin/subagents.py:484`）、`RunWorkflow`（`:761`）、`WorkflowScheduler.run`（`scheduler.py:557`，幂等自注册）、`run_pattern`（`agent/subagent/patterns.py:433`）。因此「注册顺序」实际是**声明顺序**，但 `RunWorkflow` 会在 `run()` 内二次注册同一 id（幂等，不改顺序）。需要钉死：未跑起来的 `DeclareWorkflow` 也会留在 registry 里（`DeclareWorkflow` 只注册不执行，`:480-484`），所以「列表里有 id」≠「该图真跑过」——采集时必须按 `scheduler.status()["status"]` 过滤掉从未 `run()` 的 `declared` 态，否则 `workflows` 列表会把「只声明没跑」的图也记进去，replay 会跑出 record 时并不存在的行为。这条是 Q1 落盘口径的必须补丁。
- **Q2 推荐（选 B + 新暴露 spawn_count）**：「有用产出」用「下游实际消费」判定——`_collect_slots` 合并时打标被消费的 run，terminal 进入 root result 也算一次消费；分母用 workflow 级 `manager.spawn_count()` 快照（含 create_subagent + 真实 run，不含 queue_full），**须在 `scheduler.run()` finally 释放桶前快照并新暴露进 envelope**。spawn 总数为 0 时冗余度记 `None` 不记 0。
  - **审阅核实**：快照点必须落在 `scheduler.py:575-577` 之间——`finally:` 块的第一行是 `await self._teardown()`（`:576`），第二行就是 `self.manager.release_workflow_bucket(self.workflow_id)`（`:577`）。`release_workflow_bucket` 会 `pop` 掉 `_workflow_spawn_counts[workflow_id]`（`manager.py:569-571`），此后 `spawn_count()` 在**无 workflow 上下文**的采集点会退化成返回 manager 生命周期的 `self._spawn_count`（`manager.py:573-578` 的 `current_workflow_id() is None` 分支）——那是「整个任务的全部 spawn」而不是「本 workflow 的 spawn」，口径完全不同。所以：**不能靠采集端事后调 `spawn_count()` 补数**，必须在 `run()` 内、`release` 之前把值写进 `_envelope()` 的新键（与 Confirmed Decision 7 完全一致）。
  - 「打标被消费的 run」的落点在 `_collect_slots`（`scheduler.py:1720-1738`）与 `_node_output`（`:1740-1748`）：当前两者只做纯读取、不写任何 state，加标记需要引入一个 per-run 的 consumed 集合。这是**新增记账状态**、不是新增执行分支，与 D4 措辞相容，但确实改 `scheduler.py` 的汇聚路径函数体（与 Confirmed Decision 8 的「要改 manager/scheduler」同性质）。
  - **与 D4 原文的差异**：D4 写的是「有用产出 = 被下游消费**或**进入最终结果的 run」，Q2 推荐把两个条件合成一个「消费」概念（terminal→root result 也算一次消费）。语义等价，但实现时以 Q2 的单一判定为准，不要写成「或」的双条件（双条件会把「有出边但从没被 reducer 读过」的 run 也算有用，正是口径 A 的问题）。
- **Q3 推荐（选 Z）**：按构造次数计，字段名 `depth_capped_runs`（语义诚实：被能力降级的 run 数，不是模型撞护栏次数）；**单列展示 + 并入总拒绝/降级计数**（D4 总量含 queue_full/深度撤工具/spawn 拒绝/图级超限四类）。
  - **审阅核实（与 Confirmed Decision 8 对齐，实现要改哪）**：计数点唯一，在 `manager._build_subagent_loop`（`manager.py:1104-1152`）的 `if depth is not None and depth >= self.max_depth: hidden_tools = SPAWN_TOOL_NAMES`（`:1136-1137`）分支里自增一个 manager 计数器。该函数是**纯构造函数**（无 IO、无 await），加一行自增不动执行流。注意三点：(a) `depth is None` 的调用路径（历史行为，不摘工具）**不得**计数——`_build_subagent_loop` 的唯一调用点是 `manager.py:1042` 的 `self._build_subagent_loop(session.mode, budget=tracker, depth=run.depth)`，`run.depth` 来自 `SubagentRunRecord.depth`，正常不为 None；(b) 计数器要**挂在 workflow 桶上**才有 per-workflow 口径——直接抄 `_count_spawn`（`:1459-1474`）的 `current_workflow_id()` 分支写法，且同样受「桶在 `run()` finally 被释放」约束，必须在 `release_workflow_bucket` 前快照进 envelope；(c) 一个 run 对应一次 loop 构造（`:1042` 在 `_execute_run` 路径上每个 run 调一次），所以「构造次数」= 「被降级的 run 数」，与推荐字段名 `depth_capped_runs` 严格一致——若无 workflow 上下文（`current_workflow_id() is None`）它也计数，采集时要注意别把「非 workflow 的深度降级」混进 workflow 指标。
- **Q4 推荐（max + 单列取消数）**：聚合用 `max`（最长单次排队最暴露 max_active 卡关键路径）；`started_at is None` 的取消 run **不计入 queue_wait_s**，但单独记 `queue_cancelled_runs`，不并入 Q3 拒绝计数。
  - **审阅核实（与 Q3 的「并入/不并入」边界）**：文档里两条规则必须并排读才不混——**总拒绝/降级计数（D4 四类）= queue_full + depth_capped_runs + spawn 预算拒绝 + 图级超限**；`queue_cancelled_runs` 与 `spawn_count` 都是**分母侧**的量，**不进**这个总量。特别提醒 `queue_cancelled_runs` 与 `queue_full` 名字都以 queue 开头但语义相反：前者是「排上队了、被 best_effort 截止/取消」，后者是「根本没排上、被队列背压弹掉」，实现时不要合并成一个 `queue_rejected` 之类的字段。
  - 数据面已核：`created_at` 在 `manager.py:91`、`started_at` 在 `:92`、赋值在 `_start_task` 的 `run.started_at = time.time()`（`manager.py:817`）；`self._run_refs` 初始化 `scheduler.py:379`、登记 `:1564`。取 max 的表达式为 `max((r.started_at - r.created_at for r in self._run_refs if r.started_at), default=None)`，`None` 语义 = 「本 workflow 没有任何 run 真的开跑」。
  - **注意分母污染**：被取消但在派发时就已进 `_run_refs` 的 run（`:1564` 在派发成功即 append，`_await_run` 之后才可能取消）会**同时**出现在 Q2 的 spawn 分母（每次 create+run 计 2）和 `queue_cancelled_runs` 里。这不是重复计数错误，但报告解释冗余度时必须知道「被取消的 run 计入分母、不计入分子」会让冗余度偏悲观——建议在渲染层把 `queue_cancelled_runs` 与冗余度并列展示，便于读者自行扣减。
- **Q5 推荐（选 X，两份 config yaml）**：通道用两份 config YAML（零代码改动，贴合 `_build_benchmark_runner` 只收 config_path 的现状）；取值小 k = `max_active=3, max_spawns=60`，大 N = `max_active=16, max_spawns=24`。大 N 臂是「高并发、低总配额」压力臂，`spawn budget exceeded` 是预期结果不是 runner 故障。
  - **审阅核实（与 Q8 正交性）**：Q5 只改 yaml 里的 `subagents.max_active` / `subagents.max_spawns`（`agent/config.py:336-338`，经 `_parse_subagents_config` `:1423-1458` 解析），Q8 只在 `_build_benchmark_runner`（`agent/main.py:929-1023`）的 **runner 构造段**（`:971-996`）与 `benchmark` 命令参数表（`:701-741`）加 workflow 标志；两条改动落在**同一函数的不同段落**（Q5 走 `_load_cli_config` 的 config 文件通道 `:964-969`，Q8 走 `AsterwyndRunner(...)` 构造参数 `:986-993`），**不冲突**。唯一的交叉点是：若 Q8 顺手加了 `--workflow-max-active` 之类的 CLI 覆盖（推荐里没有），才会与 yaml 争优先级——**推荐不引入这些 CLI 标志**，压力臂纯靠 yaml，保持 Q5/Q8 正交。
  - **取值可行性已核**：`max_spawns` 的 workflow 桶上限被调度器校准为 `spec.max_runs * 2`（`scheduler.py:558` → `manager.register_workflow_bucket`，`manager.py:558-567`；默认 `max_runs=300` → 桶 600）。臂 A 的 `max_spawns=60` 生效为 `min(60, 600)=60`；臂 B 的 `max_spawns=24` 生效为 `min(24, 600)=24`——24 < 2×图规模时会在第 12 个 run 前后抛 `RuntimeError: subagent spawn budget exceeded`（`manager.py:1453-1457`），被 scheduler 的兜底 `except Exception`（`scheduler.py:1163-1166`）折成节点 `failed`。这正是 D5 想要的「高并发低配额压力」，但报告必须把这类失败标成**预期压力结果**而不是 runner 故障（否则 bench 结果看起来像基础设施坏了）。
- **Q6 推荐（选乙）**：fake 场景做全等断言（spec_hash/node_count/run_count/cost/status 全等）；真实 LLM 场景只硬断言 `spec_hash` 相等 + record/replay 无异常完成，cost/run_count/peak_active/critical_path_s 只报不判；不引入 ±容差（wall-clock/cost 噪声会 flaky）。
  - **审阅核实（fake 全等的真实含义）**：`ScriptedLLM` 按顺序消费固定响应（`tests/support/llm_harness.py:125-130`，耗尽后返回 `default_response`），是**调用序驱动**、不是「同输入同输出」——fake 全等成立的严格前提是「record 与 replay 的 LLM 调用序列完全相同」。而 replay 省掉的正是「规划那次调用」（record 时模型先调 `DeclareWorkflow`/`RunWorkflow` 工具，再进各节点 run），所以 record 与 replay 从第一次调用起脚本就错位。**结论**：fake 全等断言要求 record 臂与 replay 臂各喂一份**专门编排的 script**（record 脚本含规划调用、replay 脚本不含），且断言的是「两臂都跑完 + `node_count`/`run_count`/`spec_hash` 全等」；`cost` 在 fake 下若 LLM 无 usage 则恒 0（`ScriptedLLM` 的 `LLMResponse.usage` 默认 `None`，`agent/llm.py:61`），`_record_llm_cost` 直接 return（`agent/loop.py:1080-1081`）——所以「cost 全等」在 fake 下是 0==0 的平凡断言，别把它当成有信息量的验证。真正有区分度的 fake 断言是 `node_count`/`run_count`/`spec_hash`/`status`。
  - **与 Q7 配套已核**：Q6 乙的「真实 LLM 侧只断 spec_hash」正是 Q7 选 A 要记的「降级」事实——两者语义一致：真实 LLM 下 `cost` 必然不等（replay 省规划调用、节点 run 的 token 数又逐次抖动），「只报不判」就是降级的定义。Q7 的 `e2e_llm_verified: false` 应恰好在这条分支上写 true/false。
  - **与 Confirmed Decision 13 一致**：`spec_hash` 是纯 `spec.to_dict()` 的哈希（`workflow.py:287-291`），只要 replay 用同一份 record 的 spec dict 走同一个 `parse_workflow_spec`，hash 必然相等——它是唯一可硬断言的字段，与「replay 仍真跑 LLM」不矛盾（hash 断的是图结构、不是 run 结果）。
- **Q7 推荐（选 A）**：降级事实写进每个任务的 `result.json`（机器可读字段 `e2e_llm_verified: false` + `e2e_verification_mode: "fake_round_trip"` + `e2e_skip_reason` + `e2e_assertions`），不在 artifact checker 占位扫描面；措辞完整陈述「未执行+原因+替代验证+缺口」，不写「未验证」单句。与 Q6 乙方案配套。
  - **审阅核实（落点 A 确实安全，且必须落到 `TaskResult`）**：checker 的占位扫描面只覆盖 `openspec/changes/**` 下的 proposal/design/tasks/reviews/specs（`scripts/check_openspec_artifacts.py` 的 `_check_required_sections` `:417-430` 与 `PLACEHOLDER_ONLY` `:109-116`、`_is_placeholder_body` `:325-331`），`benchmark runs` 的 `result.json` 完全不在其中——落点 A 安全，落点 B（写进 `reviews/building-review.md`）确实有被判 `section is empty or placeholder-only` 的风险（`:427-428`）。
  - **实现落点**：`e2e_*` 字段要加进 `TaskResult` dataclass（`benchmarks/models.py:60-108`）才会被 `to_dict()` 写进 `result.json`（`to_dict` 用 `asdict` + 过滤 `None`，`:90-91`）——不能只在 report 里拼字符串。默认 `None`，`to_dict` 自动省略，兼容旧 artifact（与 Confirmed Decision 2 的「成对加默认 None」同规则）。
  - **注意**：`e2e_llm_verified` 是**任务级**还是**run 级**要定——推荐落在任务级 `result.json`，但「LLM 不可用」通常是环境级事实（整轮都降级），每个任务各记一遍会让 run.json 与 result.json 语义重复。建议：任务级 `result.json` 记事实与断言明细，`RunMetadata`（`benchmarks/models.py:111-158`）记一条 run 级 `e2e_verification_mode` 汇总结论，两者不冲突。
- **Q8 推荐（CLI 标志 + 读法 1）**：公开接口用 CLI 标志 `--workflow-mode`（dynamic-replay 另要求 `--workflow-record <run-dir>`），CLI 透传到 `AsterwyndRunner` 构造参数（`AgentRunner.run` 签名不动、不塞 TaskSpec）。template 采用读法 1：pattern 作为**被测编排**，`problem_statement` 当 `compile_pattern(..., task=...)` 的 task，走既有 verifier 判分（baseline 同时衡量任务结果 + 编排指标）。
  - **审阅核实（Q1↔Q8 交叉，meta-review 修订）**：原推荐写的 `--workflow-record <path>` 语义不明——`workflow_record.json` 是**每任务一份**（落在 `<run_dir>/tasks/<task_id>/workflow_record.json`，见 `benchmarks/runner.py:284-292` 的 `task_output` 约定），一个 `--path` 无法服务 N 个任务。修订为 **`--workflow-record <run-dir>`**：replay 模式按 `task_id` 去 `<run-dir>/tasks/<task_id>/workflow_record.json` 取记录（与 record 侧写的是**同一个路径**），缺文件的单任务按 `collection_status: "missing"` 记并跳过重放、不影响其它任务。这个「run-dir + task_id 推导文件名」的约定必须与 Q1 选的落盘粒度一致：若用户选 Q1 写法 C（`workflow_records/<workflow_id>.json`），`--workflow-record` 仍接受 run-dir，内部改为遍历该任务目录下的记录目录。
  - 已核 `benchmarks/agent_runner.py:24-33`（`AgentRunner.run` 五参签名，无 mode 位）、`benchmarks/runner.py:76-110`（`BenchmarkRunner.__init__` 无 mode）、`agent/main.py:701-741`（benchmark 参数表）、`agent/main.py:986-993`（`AsterwyndRunner(...)` 构造点）。

## 待回写清单（用户确认 Q1–Q10 后由主 agent 逐项落笔）

以下点位**不能**在确认前定稿，故只登记位置与依赖，不预先写成结论。已直接修的纯文档 bug 另列于末尾。

| # | 依赖 | 待回写位置 | 要点 |
|---|------|-----------|------|
| 1 | Q1 | `design.md` D2（schema 示例块） | 已按推荐 B 改为 `workflows` 列表；若用户选写法 A（单对象取最后一个）或 C（按 workflow_id 分文件），需按所选粒度再改一次 schema 与「replay 按序重放全部」的措辞。 |
| 2 | Q1 | `specs/benchmark/spec.md`「dynamic-record 落盘可重放记录」Scenario | 补一条「一任务多图 → `workflows` 列表按序落盘 + `collection_status` 三态」的 scenario；当前 Scenario 只写了单份记录，未覆盖 0/多图与采集失败。 |
| 3 | Q2 | `specs/benchmark/spec.md`「编排质量指标」Requirement | 补「冗余度 = 消费口径有用产出 / workflow 级 spawn_count 快照」的 scenario；当前只写「冗余度 SHALL = 有用产出 / spawn 总数」，未定义「有用产出」与分母快照时点。 |
| 4 | Q3/Q4 | `specs/benchmark/spec.md`「编排质量指标」Scenario | 补 `depth_capped_runs`（按构造次数、并入总计数）与 `queue_cancelled_runs`（单列、不并入）两条字段级 scenario；当前只笼统写「拒绝降级计数」。 |
| 5 | Q5 | `design.md` D5 末段 + `tasks.md` 4.2 | 若用户选通道 Y（CLI 标志）或 Z（task 字段）而非 X，需改「配置差异表达」措辞与对照臂任务清单。 |
| 6 | Q6 | `design.md` D6 第一段 + `specs/benchmark/spec.md`「benchmark workflow 三模式」 | 补「fake 场景全等断言、真实 LLM 仅 spec_hash 硬断言」的验收口径 scenario；已改 D6 措辞，spec 侧未落。 |
| 7 | Q7 | `specs/benchmark/spec.md`「workflow 报告字段」或新增 Requirement | 补降级事实的机器可读字段（`e2e_llm_verified` 等）与「SHALL NOT 静默当已验证」的 scenario。 |
| 8 | Q8 | `specs/benchmark/spec.md`「benchmark workflow 三模式」 | 补「`--workflow-mode` CLI 标志 + `--workflow-record <run-dir>` 按 task_id 定位」与「`AgentRunner.run` 签名不变」的 scenario；当前只写模式语义，未写接线契约。 |
| 9 | Q9 | `design.md` D5 第一段 + `tasks.md` 3.4 + spec delta | 补渲染粒度（独立 section / 统一表 / 两段式）的结论与对应 scenario。 |
| 10 | Q10 | `specs/benchmark/spec.md` + `benchmarks/statistics.py:60-71` 的口径说明 | 补「replay 是否走 verifier」结论；若选读法 A，须写明 replay 记录不进 pass@k 分母，并在 `is_valid_round` / `_valid_results` 显式排除。 |

**已直接修复的纯文档 bug（无需用户拍板，已落笔）**：

- `design.md` D2：单对象 schema → `workflows` 列表（与代码事实「一任务可起 0/1/多张图」冲突）。
- `design.md` D3：补 `AgentRunResult` 必须成对增字段（原只写 `TaskResult`）。
- `design.md` D3/D4：补 `CostLedger` 未注入的取数前提、spawn 快照时点、消费口径定义。
- `design.md` D5：compare.py 行号与渲染入口落到实文件；D6：删「cost 在误差内」的旧措辞，改为 Q6 口径。
- `design.md` 行号修正：`workflow.py:253-257` → `:287-291`（`spec_hash`）；`models.py:98` → `:93-102`；`scheduler._steps` 补 `:370`/`:2041`。
- `proposal.md` 行号修正：`workflow.py:253-257` → `agent/subagent/workflow.py:287-291`（两处）。
- `tasks.md`：1.1/1.2/2.0/2.1/2.2/3.1/3.3/3.4/4.1/4.2/5.1/5.2 补实现落点与口径。

## User Confirmation

- **Q1**: 用户答复：按 codex 推荐 B——一任务一份 `workflow_record.json`，顶层 `{"workflows": [...], "collection_status": "..."}` 列表（按注册顺序，replay 全重放）；只记真正 `run()` 过的图；没起 workflow 记 `no_workflow`，超时采集失败记 `failed` + 原因 + 部分列表；确认时间: 2026-09-15
- **Q2**: 用户答复：按 codex 推荐 B——「有用产出」用「下游实际消费」判定（`_collect_slots` 合并打标 + terminal 进 root result 算一次消费）；分母用 workflow 级 `spawn_count()` 快照（含 create+run、不含 queue_full），在 `run()` finally 释放桶前快照并新暴露进 envelope；spawn 为 0 记 None；确认时间: 2026-09-15
- **Q3**: 用户答复：按 codex 推荐 Z——按构造次数计，字段名 `depth_capped_runs`（被能力降级的 run 数），单列展示 + 并入总拒绝/降级计数；确认时间: 2026-09-15
- **Q4**: 用户答复：按 codex 推荐——queue_wait_s 聚合用 `max`（最长单次排队）；`started_at is None` 的取消 run 不计入 queue_wait_s，单独记 `queue_cancelled_runs`、不并入拒绝计数；确认时间: 2026-09-15
- **Q5**: 用户答复：按 codex 推荐 X——通道用两份 config YAML；取值小 k `max_active=3, max_spawns=60`、大 N `max_active=16, max_spawns=24`；大 N 臂 `spawn budget exceeded` 是预期压力结果、报告标注非故障；确认时间: 2026-09-15
- **Q6**: 用户答复：按 codex 推荐乙——fake 场景全等断言（spec_hash/node_count/run_count/status）；真实 LLM 场景只硬断言 spec_hash 相等 + 无异常完成，cost/run_count/peak_active/critical_path_s 只报不判，不设容差；确认时间: 2026-09-15
- **Q7**: 用户答复：按 codex 推荐 A——降级事实写进每个任务 `result.json`（机器可读字段 `e2e_llm_verified: false`/`e2e_verification_mode`/`e2e_skip_reason`/`e2e_assertions`，字段加进 TaskResult）；措辞完整陈述未执行+原因+替代验证+缺口；确认时间: 2026-09-15
- **Q8**: 用户答复：按 codex 推荐——公开接口 CLI 标志 `--workflow-mode`（dynamic-replay 另要求 `--workflow-record <run-dir>`），透传 AsterwyndRunner 构造参数（AgentRunner.run 签名不动、不塞 TaskSpec）；template 读法 1（pattern 当被测编排，problem_statement 作 compile_pattern 的 task，走既有 verifier）；确认时间: 2026-09-15
- **Q9**: 用户答复：按审阅员推荐——渲染层用独立 section（只统计有 workflow 的记录，主表加一列 workflow_mode），避免 null 污染 pass@k 聚合；确认时间: 2026-09-15
- **Q10**: 用户答复：按审阅员推荐读法 A——dynamic-replay 只比编排不判分，replay 记录在 `is_valid_round`/`_valid_results` 显式排除、不进 pass@k 分母；确认时间: 2026-09-15
