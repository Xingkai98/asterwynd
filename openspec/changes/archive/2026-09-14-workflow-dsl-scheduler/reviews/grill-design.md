# Grill: workflow-dsl-scheduler 设计追问

## Reviewer

- run id: grill-workflow-dsl-scheduler-2026-09-14
- 时间: 2026-09-14

## Confirmed Decisions

以下 7 条是本审阅员**读代码后可自行收敛**的结论（不依赖用户拍板），实现时必须按此写，否则会与既有代码/测试事实冲突。

- **决策**: `workflow_id` / `node_id` 必须在**调度器调用 `manager.run_subagent()` 的那个上下文里** set，不能等到节点执行时再设；理由是 C1 已把「上下文捕获」固定在入队点——`_enqueue_run` 用 `copy_context()` 捕获**入队时**的调用方上下文存进 `_QueueItem.context`（`agent/subagent/manager.py:571`），worker 出队后以该 context 执行（`agent/subagent/manager.py:678-693`）。节点 run 排队延迟执行时调度器上下文早已退出，执行期再 set 一律丢失。同时 `_execute_run_in_context` 只补设 `spawn_depth` 与 `current_run_id`（`agent/subagent/manager.py:691-693`），**不**补设 workflow/node 身份——所以这两个值完全由入队上下文决定，`SubagentSessionRecord.workflow_id/node_id`（`agent/subagent/manager.py:127-128`）赋值路径才成立；来源: grill-workflow-dsl-scheduler-2026-09-14
- **决策**: C1 预留的 `set_workflow_id` / `set_node_id` / `set_reset` 系列 contextvar **当前零生产调用点**，C2 必须新建 set/reset 的包裹点（调度器节点派发处 + 取消/异常路径的 finally reset）；理由是 `agent/subagent/context.py:73-95` 定义了 6 个函数（`current_workflow_id`/`set_workflow_id`/`reset_workflow_id`/`current_node_id`/`set_node_id`/`reset_node_id`），全仓 `grep` 只有定义处命中，`agent/subagent/manager.py:26-32` 只 import 了读侧（`current_workflow_id`/`current_node_id`）。`tests/agent/subagent/test_concurrency_queue.py:577-578` 只断言了「无 workflow 时读回 None」，从未验证「设进去以后子 run 能读到」——这条端到端链路是本 change 首次接通，不能假设 C1 已经能用；来源: grill-workflow-dsl-scheduler-2026-09-14
- **决策**: 调度器**不能**把 C1 的队列当自己的数据结构复用，只能把它当物理并发背闸；调度器必须自持 ready 集合 + 依赖门控。理由是 manager 的队列是**单条 FIFO deque**（`agent/subagent/manager.py:317` `self._pending: deque[_QueueItem]`），入队即 append（`:567-574`）、泵出即 popleft（`:620-629`），没有任何按 workflow/节点分组、优先级或依赖语义的入口；「DAG 就绪」这种逻辑条件无法表达在 deque 上。因此 `scheduler.py` 的分工是：持有 node 状态机（`node_queued/started/blocked/completed/failed`）+ 依赖门控 + 准入决策，`manager` 仍是「实际 LLM/tool 执行」的并发上限与排队实现；来源: grill-workflow-dsl-scheduler-2026-09-14
- **决策**: pattern 模板的聚合语义必须是「**每节点取最新一次 run**」而不是「取该节点所有 run」，否则 peer-review 模板一编译就破坏既有断言。理由是 `PeerReviewPattern` 在每轮里**复用同一个 producer/reviewer 子 session**（`agent/subagent/patterns.py:119-149`），`max_rounds=2` 时 producer 实际跑了 2 次、reviewer 2 次，但 `_aggregate` 只喂最后一次的 `last_produced`/`last_review`（`agent/subagent/patterns.py:147-149`），`tests/agent/subagent/test_patterns.py:106-131` 因此断言 `completed == 2` 且每个 worker 都是「真实 run、其 subagent_id 存在于 `manager._sessions`」。若 DSL 的 aggregate 节点按「该节点累计 run 数」聚合，`completed` 会变成 4，该测试直接红；来源: grill-workflow-dsl-scheduler-2026-09-14
- **决策**: bidding 的 `selector` **不能**改成 `aggregate(strategy=llm)` 的内联 LLM 调用，否则 `result["selector"]["subagent_id"]` 无处可来。理由是 `BiddingPattern` 的 selector 是一个**真实子 agent 会话**（`agent/subagent/patterns.py:181-192`），`tests/agent/subagent/test_patterns.py:135-153` 断言 `result["selector"]["status"] == "completed"` 与 `result["selected"]` 含 `SELECTED 2`；`completed == 3` 只数 3 个 proposer（selector 不进 `workers`）。故 bidding 模板必须是 `foreach(proposers) → subagent(selector) → aggregate`，或让兼容 adapter 从 selector 节点的 run envelope 合成 `selector` 字段。design.md D2 的 `aggregate: strategy(llm)` 与 D7 的「bidding → foreach + aggregate(selector)」（`design.md:76`）口径不一致，需在实现前统一；来源: grill-workflow-dsl-scheduler-2026-09-14
- **决策**: 新增的 workflow 工具（`DeclareWorkflow`/`StartWorkflow`/`GetWorkflow`/`CancelWorkflow`/`RunWorkflow`）必须同时加进两处：`agent/loop.py:374-385` 的工具注册列表，以及 `agent/subagent/manager.py:282-287` 的 `SPAWN_TOOL_NAMES`；并需同步 MODIFIED 既有 spec requirement。理由是 `RUNWorkflow` 等入口在语义上等价于 `RunPattern`（一次性声明并拉起整张图），而深度到限的子 agent 是靠**撤掉 `SPAWN_TOOL_NAMES` 里的 4 个工具**来失效的（`agent/subagent/manager.py:956-957`），`tests/agent/subagent/test_concurrency_queue.py:483-524` 逐条断言 `CreateSubagent`/`RunSubagent`/`RunPattern`/`ResumeSubagent` 不在深度到限子 agent 的工具集里。若新工具不进该名单，深度到限的子 agent 可以改用 `RunWorkflow` 绕开深度闸。对应的现行 spec 是 `openspec/specs/subagents/spec.md` 的「深度到限撤 spawn 工具」（枚举了 4 个工具名）——本 change 的 spec delta 未 MODIFIED 它，sync 时会留下矛盾口径，必须在本次 delta 里补一条 MODIFIED；来源: grill-workflow-dsl-scheduler-2026-09-14
- **决策**: D8 的 `root_run_id` 计数桶**当前没有任何载体**，需要新建字段或改用 `workflow_id` 作桶键；且主 loop（无 workflow 场景）的 `current_run_id()` 恒为 `None`，「每 orchestration 复位」对纯 CLI 会话不成立。理由是 `SubagentRunRecord` 只有 `parent_run_id`/`workflow_id`/`node_id`/`depth` 四个身份字段（`agent/subagent/manager.py:85-88`），无 `root_run_id`；contextvar 侧也只有 `_current_run_id`/`_workflow_id`/`_node_id`/`_spawn_depth` 四个（`agent/subagent/context.py:30-34`），无 root 桶。`set_current_run_id` 的唯一生产调用点是 `_execute_run_in_context`（`agent/subagent/manager.py:692`），即**主 agent loop 的 `current_run_id()` 是 None**——所以「root run 起算」在无 workflow 时退化为桶键 None，与 C1 现状（manager 生命周期计数，`agent/subagent/manager.py:344` + `:1191-1200` 且永不复位）等价，D8 声称要修的「web 长会话累计 200 后永久锁死」问题不会被修好；来源: grill-workflow-dsl-scheduler-2026-09-14

## Open Questions

- **Q1**: `DeclareWorkflow` 返回的 `workflow_id` 注册表存在哪、活多久？`GetWorkflow` 的可见性边界是什么？
  **场景**: Web 入口下每个浏览器 session 各建一个 `SubAgentManager`（`web/session.py:447`），CLI / benchmark 各一个（`agent/main.py:289`）。用户在 session A 里 `DeclareWorkflow` 拿到 `wf_3f9a`，在 session B 里 `GetWorkflow("wf_3f9a")`：
  - 选 **manager 作用域内存注册表**：B 返回 `unknown workflow_id`；进程重启后 A 也查不回来。实现最省，但 C5 `benchmark-workflow-replay` 要的「spec 可保存 + 哈希」需要另找落盘通道。
  - 选 **落盘 `.asterwynd/workflows/<workflow_id>.json`**：复用既有 checkpoint store 纪律（`agent/subagent/snapshot.py:33-45` 的 `SubagentSnapshotStore.for_workspace` 已经落在 `<workspace_root>/.asterwynd/subagents/`），spec 可跨进程读回、可直接喂 C5；代价是本 change 要顺带定 schema_version 兼容与脏读处理。
  请拍板：C2 只做内存注册表（落盘留给 C5），还是本次就把 spec 落盘？若落盘，`GetWorkflow` 是否要做跨 manager 读取（即注册表是 workspace 级而非 manager 级）？

- **Q2**: 调度器的**准入背压**策略：调度器是否只把「能立刻进 manager 队列」的节点派发出去，还是全量派发靠 `queue_full` 兜底？
  **场景**: 配 `max_active=5` / `max_queued_runs=20`。`foreach` 节点声明展开 30 项（集合来自上游产出），30 个 subagent 节点同时就绪。
  - 选 **全量派发**：前 5 个执行、第 6~25 个入队，第 26~30 个撞 `queue_full`。`_take_back_if_queue_full` 会**丢弃 run record、弹掉 session.runs、回滚 messages、把 session 置回 idle**（`agent/subagent/manager.py:695-734`）并返回 `{"status": "queue_full"}`。此时这 5 个节点是算 `node_failed`、还是排队重试、还是让整个 workflow 失败？注意 `all_required` 的语义是「所有 required 上游都终态才运行」（spec delta「DSL 汇合语义」），只要它们被标终态 workflow 就会继续跑出一个「5 项静默丢失」的 aggregate。
  - 选 **准入背压**：调度器只在「在途节点数 < max_active + max_queued_runs」时才派发新节点，其余留在自己的 ready 集合里等槽位。workflow 永不触发 `queue_full`，但 scheduler 要自己实现「槽位释放通知」（manager 只在 `_pump_queue`/`_on_run_task_done` 里泵队列，没有对外事件，`agent/subagent/manager.py:611-629`、`:663-676`）。
  请拍板选哪种，以及 `queue_full` 在 workflow 语境下是否允许出现（它会静默丢记录，`agent/subagent/manager.py:713-723`）。

- **Q3**: `best_effort` 的「截止时间」参数从哪来？失败记录怎么传给 aggregate？
  **场景**: 一个 `aggregate(join=best_effort)` 节点有 4 条 required 上游臂。
  - 「截止时间」的载体候选：(a) aggregate 节点字段 `deadline_s: 120`（从 aggregate 节点开始等算起）；(b) 每条入边的 `timeout_s`（逐臂不同）；(c) 全局配置项。design.md D4 只写「等截止时间」（`design.md:60`），G3 #174 也只写同一句话，没定载体。
  - 失败记录形态：3 臂 50 秒内完成、第 4 臂还在 `running` 时截止时间到。此时是 (i) 把第 4 臂 `CancelSubagentRun` 掉再聚合（会写 checkpoint + `status=cancelled`），还是 (ii) 不等它、直接按 3 条聚合、让第 4 臂继续在后台跑完（其 run 仍占 `max_active` 名额）？(ii) 下 aggregate 的 `workers[]` 里第 4 项写什么——`status: "timeout"` 还是干脆不出现？注意 `TERMINAL_RUN_STATUSES` 不含 `timeout`（`agent/subagent/manager.py:46-48`），若要新状态必须同步改这处集合与 `to_result_dict`。
  请给出 `deadline_s` 的归属与超时臂的处置语义。

- **Q4**: D5 的 reducer 具体是什么形态？「结果槽」在 DSL 里对应哪个字段？
  **场景**: 两个并行 `subagent` 节点 A、B 都汇入节点 C，且都要把结果写进 C 的输入。
  - 「槽」的候选：节点上的 `outputs: ["findings"]` 声明（槽名 = 节点输出字段名），还是边的 `channel: summary` 隐含的同一个隐式槽？design.md D2 的节点字段里**没有** `outputs`/`writes` 之类的字段（`design.md:48-52`），所以「多入边写同字段」目前无法在校验期判定——校验器拿不到「写哪个字段」这个信息。
  - reducer 的候选：命名枚举（`concat` / `merge_dict` / `sum` / `first_non_empty` / `last`）还是函数引用。注意本 change 的 Non-Goals 与 Risks 明确「不执行模型生成代码」（`design.md:91-93`），所以不可能是模型传 Python 函数，只能是受限枚举。
  请拍板：槽的声明位置（节点字段名）与 reducer 的枚举取值集合。这也直接决定校验测试「多入边写同槽无 reducer」怎么写。

- **Q5**: D6 的「步」（superstep）怎么数，以及它与 `max_nodes` / `max_runs` / `max_spawns` 四个闸的关系？
  **场景**: `foreach` 展开 5 项、每项内部是 1 个 subagent 节点，之后汇合。C1 的 `max_spawns=200` 按「`create_subagent` 计 1 + 每次 run 计 1」累计（`agent/subagent/manager.py:404`、`:579`、`:1191-1200`），一个 5 项 foreach 立刻消耗 10 次预算。
  - 「步」候选：(a) 一次调度循环（就绪一批 → 派发 → 等一批完成）算 1 superstep → 本例约 2~3 步；(b) 每个节点每次执行算 1 步 → 本例 5~6 步；(c) 每次状态转移算 1 步。默认 25 的限额下，(b)/(c) 会把一个正常的中等图判死。
  - 边界：`recursion_limit` 超限时**已经跑完的节点**怎么处理——已完成的 run 是否取消？还是只停止再派发新节点？
  - 闸门关系：G3 #174 第 8 条写「动态创建节点计入 workflow `max_nodes` / `max_runs`」，但 design.md D2 的 schema 里没有 `max_nodes`/`max_runs` 字段，`SubagentsConfig` 也没有这两项（`agent/config.py:246-276`）。请拍板这四个计数器的名字、默认值、配置落点（yaml `subagents.*` 还是 spec 节点字段）与相互关系。

- **Q6**: D8 计数桶的**键**与**复位时机**：无 workflow 的主 loop 算不算一个 orchestration？
  **场景 A（无 workflow）**: 用户在 Web 会话里逐轮调 `RunSubagent`，没有 workflow。`current_run_id()` 在主 loop 里恒为 `None`（`agent/subagent/manager.py:692` 是唯一 setter），`current_workflow_id()` 也是 `None`。若桶键取 `workflow_id`，所有主 loop spawn 落进同一个 `None` 桶，第 201 次 spawn 后该 Web 会话**永久**无法再 spawn——这正是 D8 要修的病（`docs/openspec-change-backlog.md:97` 记录的 C1 遗留项），没被修好。要修就必须给主 loop 也定一个 orchestration 边界：是「每个用户 turn 复位」还是「每个根 run 复位」（根 run 在主 loop 场景不存在）。
  **场景 B（有 workflow）**: 一个 workflow 里两个 `foreach` 各展开 40 项 → 160 次 spawn，落在同一个 workflow 桶。桶内 `max_spawns=200` 时第 161 次就拒。请确认是「一个 workflow run = 一个桶」（则两个 foreach 共享 200 上限），还是「一个 foreach 实例 = 一个子桶」（则上限被放大到 400）。
  **场景 C（嵌套 workflow）**: workflow A 的节点里子 agent 又 `DeclareWorkflow(B)` 并 `StartWorkflow`。B 的 spawn 计 A 的桶还是 B 自己的桶？这决定「A 是否会因为 B 的消耗而失败」。
  请拍板桶键、复位时机、嵌套归属三条。

- **Q7**: 新 workflow 工具的工具面元数据怎么定？
  **场景**: 给 `DeclareWorkflow`/`StartWorkflow`/`GetWorkflow`/`CancelWorkflow`/`RunWorkflow` 五个工具定 `read_only` / `parallelizable` / `permission`。
  - 现有约定：所有 subagent 控制工具都是 `read_only = True` + `SUBAGENT_CONTROL_PERMISSION`（`agent/subagent/... ` 见 `agent/tools/builtin/subagents.py:28-29`、`:74`、`:94`），`RunSubagent`/`GetSubagentRun` 标了 `parallelizable = True`（`agent/tools/builtin/subagents.py:73`、`:133`），`RunPattern` **没有**标（`tests/agent/subagent/test_concurrency_queue.py:653` 断言 `RunPatternTool.parallelizable is False`）。
  - 关键点：`loop.py` 的并行分组会把**连续**的 parallelizable 调用 `asyncio.gather` 起来（`agent/loop.py:1248-1263`）。若模型一轮发 5 个 `RunWorkflow(wait=true)` 且都标了 parallelizable，5 张图会同时调度——这与「一张图占用 `max_active` 全部门额」的调度假设叠加，可能让某个图永远等不到槽位。
  请拍板每个工具的 `parallelizable` 取值，以及 `StartWorkflow(wait=true)` 被 `asyncio.gather` 并发调用时的语义。

- **Q8**: `CancelWorkflow` 的递归取消语义与 `GraphRecursionError` 的模型可见形态？
  **场景 A**: workflow 有 12 个节点，其中 3 个 `running`、4 个 `queued`、5 个未派发。此刻 `CancelWorkflow(wf_3f9a)`。
  - `running` 的节点：走 `manager.cancel_subagent_run` 会 `task.cancel()` 并 `_write_checkpoint`（`agent/subagent/manager.py:760-791`、`:887-896`），写 checkpoint 到盘。
  - `queued` 的节点：按 C1 的 Q7 决议是**惰性取消**——标 `cancelled` 但仍占队列名额（`agent/subagent/manager.py:770-777`）。
  - 未派发节点：调度器自己标终态即可。
  请确认这套是期望语义，以及 `CancelWorkflow` 是否要等所有 in-flight 节点真正停下才返回（`asyncio.gather` 等待），还是立即返回一个「取消已提交」的 envelope。
  **场景 B**: 一个 `route` 节点构成的自环跑了 25 步触发上限。模型看到的是什么——工具返回 `[Error: GraphRecursionError: ...]` 文本（经 `RetryHook`，注意 `RETRYABLE_PATTERN` 不含此类词，会立即返回不重试，`agent/hooks/builtin/retry.py:19-26`），还是 `StartWorkflow(wait=true)` 的返回 envelope 里一个 `status: "graph_recursion_exceeded"`？还是 `accepts` 阶段抛 Python 异常打断整个工具轮？请拍板，并按 C1 Q1 的先例（envelope vs 异常）说明模型看到的字段。

- **Q9**: `run_pattern()` 新增的 `critical_path_s` / `peak_active` / `total_cost` 三个度量口径是什么？
  **场景**: 跑 `orchestrator-worker(workers=3)`。
  - `peak_active`：是「该 pattern 内并发执行的最大子 run 数」，还是「进程内 `max_active` 许可池的峰值占用」？后者会被**非本 pattern** 的 run 污染：Web 场景下一个 manager 服务多个并发 pattern，池子是全 manager 共享的（C1 Q2 决议明确「同一 manager 内所有 orchestration depth 共享一个 `max_active` 名额池」）。取哪个口径？
  - `critical_path_s`：从哪算起？`DeclareWorkflow` 到终态，还是 `StartWorkflow` 到终态？peer-review 的循环节点算不算路径上的重复访问？
  - `total_cost`：`SubAgentManager` 的 `cost_ledger` 是可选的（`agent/subagent/manager.py:301`），为 None 时（本地调试配置、benchmark fake agent）返回 `0` 还是 `None`？注意 `agent/config.py` 里没有任何 workflow 相关配置项，若需要一个 `subagents.workflow.*` 开关，`_parse_subagents_config` 是唯一的解析入口且必须逐字段显式改（`agent/config.py:1351-1384`）。

## User Confirmation

- **Q1**: 用户答复：workflow 注册表存 manager 内存（进程重启/跨 session 不可见），落盘（喂 C5 replay 的 spec 可保存+哈希）留给 C5；确认时间: 2026-09-14
- **Q2**: 用户答复：准入背压——调度器只在「在途节点数 < max_active+max_queued_runs」时派发新节点，其余留 ready 集合等槽位，workflow 永不撞 queue_full（避免静默丢 run record 的可观测性断裂）；确认时间: 2026-09-14
- **Q3**: 用户答复：aggregate 节点字段 `deadline_s`（从 aggregate 开始等算起）；超时臂取消（`CancelSubagentRun` + 写 checkpoint 供后续 resume），标 `status: cancelled`，不「放任后台跑完」（避免占 max_active 名额 + 结果无人消费的浪费）；需新增 `timeout`/复用 cancelled 状态到 TERMINAL_RUN_STATUSES；确认时间: 2026-09-14
- **Q4**: 用户答复：节点加 `outputs: ["<槽名>"]` 声明写哪些槽；reducer 用受限枚举（concat/merge_dict/first_non_empty/last，不执行模型生成代码）；校验器据此判定「多入边写同槽无 reducer → schema 错」；确认时间: 2026-09-14
- **Q5**: 用户答复：recursion_limit 按「superstep」（一次调度循环=就绪一批→派发→等一批完成）计，默认 25；三闸：recursion_limit=25（图级步数）/ max_nodes=200（节点数含 foreach 展开）/ max_runs=300（run 总数）；确认时间: 2026-09-14
- **Q6**: 用户答复：计数桶键=workflow_id；一个 workflow run=一个桶（两 foreach 共享 200 上限）；嵌套 workflow 各自独立桶（B 的 spawn 计 B 自己的桶，不因 A 消耗而失败）；无 workflow 的主 loop 沿用 C1 的 manager 生命周期保守语义（每 turn 复位归后续）；确认时间: 2026-09-14
- **Q7**: 用户答复：5 个新工具全不标 parallelizable（Declare/Get/Cancel 标 read_only，StartWorkflow/RunWorkflow 标 SUBAGENT_CONTROL_PERMISSION）；避免一轮多个 RunWorkflow(wait=true) 同时调度多张图抢 max_active；确认时间: 2026-09-14
- **Q8**: 用户答复：CancelWorkflow 立即返回「取消已提交」envelope（不 gather 等 in-flight 停下，checkpoint 保结果）；GraphRecursionError 走 StartWorkflow(wait=true)/GetWorkflow 返回 envelope 带 `status: "graph_recursion_exceeded"` + 诊断信息（跑了几步/当前节点/route 条件），非异常文本；确认时间: 2026-09-14
- **Q9**: 用户答复：peak_active=「该 pattern 内并发执行的最大子 run 数」（不被同 manager 其他 pattern 污染）；critical_path_s=StartWorkflow 到终态（peer-review 循环节点计入路径重复访问）；total_cost 当 cost_ledger 为 None 返回 0（保持数字类型一致）；spec_hash 改名 `workflow_spec_hash`（避免与 OpenSpec artifact hash 同名冲突）；确认时间: 2026-09-14

## 风险

- **严重: 深度闸可被新工具绕过（带 file:line）**: 深度到限的子 agent 靠撤 `SPAWN_TOOL_NAMES` 失效（`agent/subagent/manager.py:282-287`、`:956-957`），该名单只有 C1 的 4 个工具。本 change 新增的 `StartWorkflow`/`RunWorkflow` 是等价的 spawn 入口，若不入选，一个 depth=max_depth 的子 agent 可以直接 `RunWorkflow(spec)` 拉起整张图，深度护栏形同虚设，且 `_check_admission` 的 spawn 预算/深度检查（`:1162-1189`）也不会被调用（它只在 `create_subagent`/`run_subagent`/`resume_subagent` 入口）。必须同步改 `agent/loop.py:374-385` 的注册列表 + `SPAWN_TOOL_NAMES` + `openspec/specs/subagents/spec.md` 的「深度到限撤 spawn 工具」requirement。

- **严重: 「图级步数」与 C1 累计 spawn 预算在同一场景下互相误伤（带 file:line）**: 两者都是「防爆炸」闸，但量纲不同（`recursion_limit` 数步、`max_spawns` 数 spawn）。一个 5 项 foreach 就烧掉 10 次 spawn 预算（`create` 1 + `run` 1，`agent/subagent/manager.py:404`、`:579`），25 步的图上限却可能对应上百次 spawn。若两者默认值不做一致性校准，会出现「图还没跑完但 spawn 预算先耗尽」的失败，而失败信息是 `RuntimeError("subagent spawn budget exceeded ... (per orchestration)")`（`:1184-1189`）——模型无法从中判断是应该缩小图还是减少 foreach 项。design.md D6 与 D8 把两者分开描述，没有校准关系。

- **严重: `queue_full` 会静默丢弃节点 run（带 file:line）**: `_take_back_if_queue_full` 在丢弃时会把 `session.runs` 里刚 append 的 run **pop 掉**、回滚 messages、清 `active_run_id`（`agent/subagent/manager.py:713-723`），即「这个 spawn 从未发生」。若调度器把 `queue_full` 当成一次普通的节点失败来处理，节点状态机里就没有对应的 run record 可查——`GetWorkflow` 报 `node_failed` 但按 `subagent_id` 去查是空 session，可观测性断裂。D3 声称「复用 C1 的 max_active/max_queued_runs」（`design.md:56`）但没有描述这层映射，实现时极易踩。

- **中: pattern 模板「节点会话复用」的语义未定，直接撞既有测试（带 file:line）**: peer-review 现状是 producer/reviewer 会话跨轮复用（`agent/subagent/patterns.py:119-149`），编译成 `subagent + subagent + route + 有限循环` 后，`route` 回边是「重跑同一节点（复用 session）」还是「新建节点实例（新 session）」未定义。若选后者，`tests/agent/subagent/test_patterns.py:126-131` 的「每个 worker 都是真实 session run」会因为 session 数翻倍而改变语义（断言仍可能过，但 `workers` 数量变化会让 `completed == 2` 失败）。这会连带影响 `max_spawns` 的消耗量级（每轮新建 session = 每轮 +1 spawn）。

- **中: `run_pattern` 的 bus 生命周期与 workflow 的 bus 归属冲突（带 file:line）**: 现状 `run_pattern` 自建一个 `MessageBus`、`set_bus(bus)`、结束后 `reset_bus(token)`（`agent/subagent/patterns.py:227-235`），`tests/agent/subagent/test_patterns.py:181-188` 断言返回后 `current_bus() is None` 且结果里带 `bus.snapshot_payload()`。改成「编译成 WorkflowSpec 走调度器」后，bus 必须在**调度器派发节点时**装进入队上下文（否则节点内的 `PublishBusMessage` 拿不到 bus，`agent/tools/builtin/subagents.py:232-234` 会返回 `{"error": "no active message bus"}`），而 reset 必须在 workflow 终止/取消的 finally 里做。若调度器是 `asyncio.create_task` 派发，`reset_bus` 的 token 跨任务 reset 会抛 `ValueError`（contextvar token 只能在原 context 里 reset）——C1 已经因为同类问题在 `_execute_run_in_context` 里显式声明「No tokens are reset」（`agent/subagent/manager.py:684-690`）。bus 的 set/reset 落点需要与这条先例对齐。

- **中: `max_nodes`/`max_runs`/`recursion_limit` 没有配置落点（带 file:line）**: `SubagentsConfig` 是 `@dataclass(frozen=True)` 且 `_parse_subagents_config` 是逐字段 `mapping.get(...)` 构造（`agent/config.py:246-276`、`:1351-1384`），不是 `**mapping` 透传——只加 dataclass 默认值不会让 yaml 生效（C1 的 grill 已经吃过这条教训）。design.md 与 G3 #174 都提到这几个上限，但既没定它们的默认值，也没定它们是「配置项」还是「spec 节点字段」。任务 1.2「超 max_nodes 拒绝」的测试在配置落点确定前无法写。

- **中: 既有 `_spawn_count` 测试会在 D8 改造后语义漂移（带 file:line）**: `tests/agent/subagent/test_concurrency_queue.py:531-559` 直接依赖「create 与 run 各计 1、到达上限即抛 `RuntimeError(match="spawn budget")`」。D8 引入桶后，错误文案里的 `(per orchestration)` 与实际桶边界会不一致（现状文案在 `agent/subagent/manager.py:1186-1189`），且「桶随 workflow 复位」意味着同一个测试里的多次 spawn 必须落在同一桶——需要显式钉住桶键，否则测试偶发飘红。

- **低: `spec_hash` 与既有 `spec_hash` 命名冲突（带 file:line）**: 本 change 要在 `run_pattern()` 返回里新增 `spec_hash`，而仓库既有 `spec_hash` 是 review manifest 里对 `openspec/changes/<id>/specs/` 目录算的 artifact hash（`agent/workflow/review_manifest.py`、`scripts/check_openspec_artifacts.py`）。两者同名不同义，文档与工具输出里同时出现会造成混淆；建议在 design.md 里显式说明「WorkflowSpec 哈希」与「OpenSpec spec 目录哈希」是两个东西，或给前者换个名（如 `workflow_spec_hash`）。

- **低: `GetWorkflow` 的「bounded status」缺少边界定义（带 file:line）**: design.md D1 写 `GetWorkflow(id) → bounded status`（`design.md:31`），但没有定义 bound 的维度与默认值。可参照的既有先例是 `InspectSubagentTranscript`（`limit` 默认 5、`scope` 二选一，`agent/subagent/manager.py:793-833`）与 `to_result_dict` 的字段裁剪（`agent/subagent/manager.py:93-111`）。一个 200 节点的 foreach 图若逐节点返回完整 envelope，单次 `GetWorkflow` 就能把父 agent 上下文打爆——这与本 change「父 agent 永远 bounded envelope」的 C3 目标（`docs/openspec-change-backlog.md:98`）方向相反，建议在 C2 就定下节点级摘要字段。
