# Grill: workflow-graph-visualization 设计追问

## Reviewer

- run id: grill-workflow-graph-visualization-2026-09-15
- 时间: 2026-09-15
- 对象: `openspec/changes/workflow-graph-visualization/design.md` D1–D7
- 基线: C5 `benchmark-workflow-replay` 已合入（`agent/subagent/scheduler.py` 2249 行、`agent/subagent/manager.py` 1520 行、`agent/tools/builtin/subagents.py` 775 行、`web/server.py` 575 行、`web/session.py` 699 行、`web/static/{index.html,chat.js,style.css,debug.js}` 均已含 C1–C5 产物）

## Meta-Review（独立审阅员，2026-09-15）

本轮由**第二个零记忆审阅员**对上述追问记录做事后核验（自洽 / 正确 / 完整 / 与 design·tasks·spec 一致），逐条 Read 代码复核了 file:line 断言。本轮改动：

- 修正/补充 **决策 11、12**（`_mark_consumed` 有 4 个调用点；`_consumed_edges` 与 C5 指标的隔离条件）。
- 新增 **Q8–Q11**（ws 事件 schema/路由、图生命周期与 `spec_hash` 用途、快照字段边界、推送失败隔离），均为「该问没问」的设计点。
- 每条 codex 推荐下加 **审阅核实** 注记（哪些引用属实、哪几处需补口径）。
- 直接修掉 **design.md / tasks.md / spec delta / proposal.md 的纯文档 bug**：D4 触发点、D5 `>200` 不可达分支、D3 快照字段、风险节的「ws 队列有界」、tasks 2.1/1.2/1.3/4.1/6.1、spec 触发面与超限语义。依赖用户拍板的部分只标注「待确认 Q<n> 后回写」，未替用户拍板。

## Confirmed Decisions

以下 12 条是本审阅员**读代码后可自行收敛**的结论（不需要用户拍板），实现时必须按此写，否则会与既有代码/测试事实冲突。前 10 条为初轮追问产出，决策 11–12 为 meta-review 补充。

- **决策**：**决策 1** — `workflow_started` 的正确触发点是 `scheduler.run()` 里已有的 `_record_event("workflow_started", status="running")`，不是 `StartWorkflowTool.execute`/`RunWorkflowTool.execute`。 design D4 让工具层发事件，但工具类只持有 `SubAgentManager`（构造点 `agent/loop.py:394-401` 传的全是 `self.subagent_manager`），拿不到 session 的事件 sink；而 `run()` 在真正开跑时已经写了这条事件（`agent/subagent/scheduler.py:581`），且 `DeclareWorkflow` 只 `register_workflow` 不调 `run()`（`agent/tools/builtin/subagents.py:475-499`），所以「Declare 不发、Start/Run 才发」这个 spec 要求由 hook 点天然满足，工具层一行都不用改。注意副作用：`run_pattern()` 也直接调 `scheduler.run()`（`agent/subagent/patterns.py:434`），hook 在 `run()` 上意味着 pattern 也会发 `workflow_started`（见 Q3）。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 2** — scheduler 到 `on_event` 之间今天没有任何现成通路，必须新建 manager 级 sink；`AgentLoop._active_on_event` 不能复用。 `_record_event` 只做两件事——追加到 `_latest_events` ring buffer 和写 `WorkflowStore` 事件日志（`agent/subagent/scheduler.py:500-528`），不碰 `on_event`。`SubAgentManager.__init__` 的字段清单里没有任何事件回调（`agent/subagent/manager.py:337-410`）。`AgentLoop._active_on_event` 在 `run()` 里 set、在 `finally` 里恢复成前值（`agent/loop.py:545-548`、`:572`），而子 agent 的 loop 由 manager 构造时 不传 on_event（`agent/subagent/manager.py:1082-1088` 的 `loop.run(...)` 只给 trace_recorder/session_id/run_id），即子 loop 的 `_active_on_event` 恒为 `None`。结论：snapshot 的投递需要一个新的、由 web 层注入 manager 的 sink，且必须能在没有活跃 `run()` 的情况下工作。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 3** — web 层现有的事件队列是 per-run 局部变量，run 一结束 drain 循环就退出——`wait=false` 的 workflow 快照会全部丢在队列里。 `_run_session_locked` 里 `queue: asyncio.Queue = asyncio.Queue()` 是函数局部（`web/session.py:547`），消费者是同一函数内的 `while True: event = await queue.get()`（`web/session.py:672-677`），`run_agent()` 的 `finally` 会 `queue.put(None)` 收尾（`web/session.py:608-612`）。所以 `StartWorkflow(wait=false)`（`agent/tools/builtin/subagents.py:536-541` 用 `asyncio.ensure_future` 起后台任务）在父 run 返回后仍在跑，此时往这个 queue 里 put 没人消费。另外同一 session 的并发保护是 `run_lock`（`web/session.py:524-536`），它只圈住一次 `run_session`，不圈后台 workflow。实现上必须把「事件出口」从 per-run queue 提升为 session 级、跨 run 存活的 sender（具体形态见 Q1）。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 4** — 新快照不能复用 `NodeState.to_dict()`——它缺 `started_at`/`finished_at`，且带两个会随图规模线性膨胀的字段。 `to_dict()` 输出的键是 `id/kind/status/runs/subagent_id/summary/reason`（+ 条件性的 `subagent_ids`/`items`/`slots`/`verdict`/`raw`/`targets`/`error`）（`agent/subagent/scheduler.py:165-191`），没有 `started_at`/`finished_at`，而 design.md:45 的 snapshot 示例里这两个字段是有的（`NodeState` 本身有这两个字段，`:152-153`）。更麻烦的是 `subagent_ids` 对 foreach 容器节点是每个展开项一个 id（`scheduler.py:1379` 初始化、`:1406` 逐个 append），20 项展开就是 20 个 id；`slots` 则是 concat 后的巨型字符串（`to_dict` 里只裁到 `_SUMMARY_LIMIT=400`，但仍按槽数累加）。结论：`workflow_graph_snapshot()` 必须显式挑选字段，不能 `to_dict()` 直出，否则「快照 bounded」（design.md:107）这条风险对策就是空话。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 5** — 节点七档与代码实际会写入的 `state.status` 集合完全一致，无需新增状态；`queued` 对节点是只读不写的死分支。 全部赋值点：`cancelled`（`agent/subagent/scheduler.py:540,679,787,868,1207,1401,1659,1689`）、`blocked`（`:686,896`）、`budget_exceeded`（`:893`）、`started`（`:1176`）、`failed`（`:1212,1223,1414,1662`）、`pending`（`:1266` 的 `_reset_subtree`）、`completed`（`:1327,1356,1417,1420,1657`）。`"queued"` 在调度器里只出现在读取侧（`:536,676,678,784,786,867,1505,1685,2181`），没有任何一处把 `state.status` 写成它（`NodeState.status` 默认是 `"pending"`，`:141`）。所以 design.md:53-61 的七档表可以直接落地，不必为 `queued` 预留颜色。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 6** — route 控制边「选中出口」的信号已经存在，就是 `NodeState.targets`，不需要新记账；但要注意 `_reset_subtree` 会先清空它。 字段定义在 `agent/subagent/scheduler.py:161`，唯一写入点是 `_execute_route` 的两条分支（命中 case：`:1345` `state.targets = [case.to]`；走 default：`:1348` `state.targets = [node.default] if node.default else []`）。`to_dict()` 也只在 `kind == "route"` 时输出 `targets`（`:185-188`），口径已经是「route 专有」。控制边的推导规则因此可以直接写死：route 节点 `status == "completed"` 且 `edge.target ∈ state.targets` → 选中；其余出边 → `inactive`。但 `_reset_subtree` 在数据上游重跑时会清空 `state.targets` 与 `state.verdict`（`:1270`），`_execute_route` 里也因此会先把下游从终态复位（`:1359-1365`）——前端必须容忍「route 已 completed 但 `targets` 为空」这个瞬时态（渲染成全部 inactive，不要崩）。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 7** — 边状态五档里，`passed` 是唯一必须新增记账的一档；`inactive`/`ready`/`active`/`blocked` 都能从既有信号推出。 现有消费记账是 run 级的：`self._consumed_run_ids: set[str]`（`agent/subagent/scheduler.py:384`）由 `_mark_consumed`（`:625-634`）写入，颗粒度是 `state.run_id`/`state.run_ids`，按节点不按边——同一节点的两条出边无法区分谁消费了它。四处打标调用点里有**三处**恰好都在「遍历数据入边」的循环体内，`edge` 变量在作用域里：`_collect_slots` 的 `for edge in self._graph().data_incoming(...)` 循环（`:1782-1802`，打标在 `:1795`）、`_node_task_text`（`:1814-1838`，打标在 `:1834`）、`_aggregate_task_text`（`:1840-1869`，打标在 `:1858`）（**第四处 `_write_root_result` `:2235` 不在边循环里、无边可标，见决策 11**）。所以只要在这三处顺手把 `(edge.source, edge.target)` 记进一个新的 `_consumed_edges` 集合，`passed` 就是一次查表。其余四档的口径建议：`blocked` = 目标节点 ∈ {blocked, budget_exceeded} 或源 ∈ {failed, cancelled}；`ready` = 源 completed 且目标仍 pending；`active` = 源或目标 ∈ {started}；`inactive` = 兜底。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 8** — foreach 的展开项不在 ExecutionPlan 的 nodes 里，快照的 `nodes` 只会有一个 foreach 容器节点 + 若干自动插入的 aggregate 节点；前端折叠组必须自己按 `kind`/前缀识别。 `_expand_plan` 只把新增的 auto aggregate 节点塞进 `self._plan` 与 `self._states`（`agent/subagent/scheduler.py:1485-1490`），展开项本身只体现在 `state.items`（项数，`:1376`）、`state.subagent_ids`（`:1379,1406`）、`state.run_ids`（`:1407`）上，从来不是 `NodeState`。自动节点的识别前缀是 `AUTO_NODE_PREFIX = "__auto_agg__"`（`agent/subagent/aggregation.py:40`），且 `ExecutionPlan.inserted_nodes` 已经现成可用（`_envelope` 就在用它，`agent/subagent/scheduler.py:2190`）。结论：design D5 说的「折叠组显示 `N items`/完成数/失败数」数据完全在既有字段里（`items` + 容器节点自己的 `status`），不需要新协议字段；折叠组判据是「`kind == "foreach"`」+「id 以 `__auto_agg__` 开头」两类。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 9** — design D5 的「`>200` 前端显示超限状态」这条分支在正常链路上不可达——超限时图根本不存在，前端会看到的是 `graph_recursion_exceeded` 状态的快照。 `max_nodes` 是双闸：声明期 `len(nodes) > limits["max_nodes"]` 直接抛 `WorkflowValidationError`（`agent/subagent/workflow.py:369-371`），运行期 `_check_declared_limits` 对自动插层后的 `len(self._plan.nodes)` 复检（`agent/subagent/scheduler.py:655-666`）、`_expand_plan` 对新增 auto 节点复检（`:1474-1488`）、`_check_foreach_budget` 对展开项复检（定义 `:1509-1553`）。三者都抛 `GraphRecursionError`，被 `_mark_graph_recursion_exceeded` 收敛成 `self._status = "graph_recursion_exceeded"`（`:636-645`）。也就是说：要么图存在且 ≤ 200 节点，要么整图被拒。前端要处理的是「`data.status == "graph_recursion_exceeded"` + `data.diagnostics`」这个渲染分支（结构见 `_envelope` 的 `diagnostics` 键，`:2183`），而不是「snapshot.nodes.length > 200」。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 10** — `_expanded_nodes` 是「计费高水位」，不能拿它当「当前图规模」做折叠判据。`_prune_states` 的 docstring 明写「已计费的 `_expanded_nodes` 不退还——预算是保守的高水位口径」（`agent/subagent/scheduler.py:1492-1507`），`_check_foreach_budget` 也是只收增量（`:1509-1553`）。route 回边重跑导致展开项数收缩（`_expand_plan` 的 stale 分支，`:1460-1468`）之后，`_expanded_nodes` 仍停在历史高点。当前图规模的权威来源是 `len(self._graph().nodes)`——`_envelope` 自己就是按 `plan.nodes` 逐个取 state 的（`:2117-2119`），`_check_declared_limits` 也是用它判超限（`:655`）。快照的 `nodes` 长度天然就是这个值，前端不需要额外字段。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 11（审阅员补充）** — `_mark_consumed` 今天有 **4** 个调用点，不是 3 个；`_write_root_result` 也打标，因此 per-edge 记账点必须写清是否覆盖它。前三个在数据入边循环体内（`_collect_slots` `:1795`、`_node_task_text` `:1834`、`_aggregate_task_text` `:1858`，三处 `edge` 都在作用域里，可顺手记 `(edge.source, edge.target)`）；**第四个**在 `_write_root_result`（`:2235`）——那里遍历的是 `plan.terminal` 的节点、**没有 `edge` 变量**，语义是「终态产出进了根结果也算一次消费」，**不对应任何一条边**。所以 Q5 若拍「加 per-edge 记账」，只能在 3 个边循环里加第 4 步（第 4 个调用点保持只写 `_consumed_run_ids` 不动）；根结果消费**天然没有边可标**，`passed` 边状态里不含「被根结果消费」这一支。这条不澄清，实现者很容易在 `:2235` 处硬凑一条边。来源: grill-workflow-graph-visualization-2026-09-15

- **决策**：**决策 12（审阅员补充）** — `_consumed_run_ids` 与 `_consumed_edges` 天然隔离——只要不改 `_mark_consumed` 本体，C5 冗余度指标零漂移。`_mark_consumed(state)`（`:625-634`）只读 `state.run_id`/`state.run_ids` 写进 `_consumed_run_ids`；`useful_runs`（`:2167`）与 `redundancy`（`:2052`，分子 `len(self._consumed_run_ids)`）只依赖该集合。把 `_consumed_edges.add((edge.source, edge.target))` 加在**调用点旁**（而不是塞进 `_mark_consumed` 内部）时，`_consumed_run_ids` 的基数**逐位不变**，C5 的 `useful_runs`/`redundancy` 断言不受影响。**唯一会漂移的写法**是改 `_mark_consumed` 的签名/内部（例如让它在没有 run_id 时也记边），实现时必须避免——这也是 Q5 场景里「旁新增」三个字的确切含义。来源: grill-workflow-graph-visualization-2026-09-15

### 附：design.md 的 file:line 断言核对（不同于 C5，本 change 的引用**基本准确**）

逐条按当前代码核对：`web/static/index.html:109-111` 确实是三个 `<script>`（markdown.js / chat.js / debug.js，无图库）✓；`agent/loop.py:948-970` 确实是 `on_event` 分发块 ✓；`web/session.py:672-677` 确实是 `ws_send` drain 循环 ✓；`web/static/chat.js:414-574` 是 `handleEvent`（design 写 414-570，尾差 4 行）✓；`_envelope` 定义在 `scheduler.py:2115`（函数体 2115-2193，design 写 2115-2139 是其中的 nodes 段）✓；`parent_envelope` `:2195-2217` ✓；`self._graph()` `:488-491` ✓；route 控制边 `workflow.py:243-260`（`is_control_edge` + `data_incoming` + `data_outgoing`）✓；`DeclareWorkflow` `subagents.py:475-499` ✓；`StartWorkflowTool.execute` `:530-542` ✓；`RunWorkflowTool.execute` `:755-772`（实际到 774）✓；`_dispatch` `:1128-1193` ✓；`_run_node` `:1196-1240` ✓；`workflow.py:34-37` 三闸默认值 ✓。唯一需要改口径的是 `parent_envelope` 的引用位置说明（design 写 `:2195-2217` 正确）与 manager 注册表：`self._workflows` 字段在 `manager.py:408`，`register_workflow`/`get_workflow`/`list_workflows` 在 `:558-565`（design 写 406-413 / 556-565，两段都正确）。**实现时仍以 Read 到的当前行为为准，不要凭 design 的数字直接跳转。** 来源: grill-workflow-graph-visualization-2026-09-15

## Open Questions

> Q1–Q7 为初轮追问产出；Q8–Q11 为 meta-review（2026-09-15）补充。**全部 11 条都必须在停轮确认里逐条给用户答复并回填 `## User Confirmation`**，缺一条不得进入实现。

- **Q1: 事件 sink 挂在哪、生命周期多长？** 这是本 change 最硬的一个决定，直接决定 Q2/Q4 的实现形态。
  **场景**: 用户在手机上打开一个 session，模型调用 `StartWorkflow(workflow_id, wait=false)` 起了一张 6 节点图。工具立刻返回 `{"status": "running", "nodes": []}`（`agent/tools/builtin/subagents.py:538-541`），父 agent 继续本轮迭代、再迭代两轮后 `AgentLoop.run()` 整体返回 → `_active_on_event` 在 finally 里被恢复成 `None`（`agent/loop.py:572`），`web/session.py` 的 `_run_session_locked` 也走完了它的 `while True: await queue.get()`（`:672-677`）。此刻 workflow 还在跑第 4 个节点，scheduler 想推快照。三种落法：
  - **A（manager 级 sink + session 级 forwarder）**：`web/session.py` 在 `_create_session` 时给该 session 的 `SubAgentManager` 装一个 sender，该 sender 持有 session 而非某次 run 的 queue，ws 重连时把 `ws_send` 重新绑定到这个 forwarder 上。改动面最小（manager 与 session 本来就 1:1，见 `web/session.py:447-453` 的 `SubAgentManager(...)` 构造），但要在 `AgentSession` 上加生命周期管理（`remove_session` 时要摘掉）。
  - **B（进程级 hub + session_id 路由）**：manager 之上再放一个进程级 registry，snapshot 带 `session_id`，多个 ws 各自订阅。跨 session 天然隔离靠 id，但要为 session 生命周期、并发 run、多个 ws 同 session 各写一套订阅管理。
  - **C（只推给「发起 workflow 的那次 run」）**：snapshot 沿用现有 per-run queue，run 结束后事件丢弃、靠「下次 run 时补发完整快照」兜底。最省事，但 `wait=false` 的后台图在父 run 结束后**完全不实时**——用户会看到一张停在启动瞬间的图，直到模型下一轮再调用 `GetWorkflow` 触发一次 run。
  **第四种落法（审阅员补充）**：**复用现有 `web/session.py` 的 session 恢复机制**——manager 挂在 `AgentSession` 上，session 本身在 `resume_session_async` 里 `existing = self._sessions.get(session_id); if existing is not None: return existing`（`web/session.py:351-353`）。也就是说 **ws 重连时若 session 仍在内存，拿到的是同一个 `AgentSession` 对象**（同一个 manager、同一张图）。这条路对「重连补发」几乎零成本：不需要在 `AgentSession` 上加注销逻辑，只需在 `resume_session_async` 返回后把新的 `ws_send` 绑到 forwarder。**但**它与 A 并不冲突——A 的「session 级 forwarder」正好可以架在这条既有恢复路径上，只是 A 文字里写的「`remove_session` 时要摘掉」要改成「**`reset` 消息**（`web/server.py:531-543` 会 `remove_session` + 新建）时摘掉，冷会话 DELETE 时顺带清」。请把这条作为 A 的实现细节一并确认。

  **附带必须一并拍板的两点**：(a) 同一 session 在后台 workflow 运行期间，用户再发一条消息触发新 run，是否允许并发（现在 `run_lock` 只锁 run，不锁后台 workflow，技术上允许）；(b) workflow 事件是否也需要一个「回放/历史」入口，还是纯实时。
  请拍板 sink 落点（A/B/C）与后台 workflow 期间的同 session 并发策略。

- **Q2: 一个 session 里存在多张 workflow 图时，前端显示哪张？断线重连补发哪些？**
  **场景**: 模型先 `StartWorkflow(wf_aaa, wait=false)` 起了一张 4 节点「调研」图；10 秒后又 `RunWorkflow(spec_b, wait=false)` 起了一张 9 节点「实现」图（两次调用都在同一次父 run 里，`agent/tools/builtin/subagents.py:536-541` / `:762-772`）。两张图此时都在跑，manager 注册表里同时有 `wf_aaa`（running）和 `wf_bbb`（running）（`agent/subagent/manager.py:558-559` 的 `_workflows` 是 dict，key 是 workflow_id）。用户此时拔网线重连，服务端从注册表补发快照。
  - **只显示最新一张**：`wf_aaa` 从视图里消失，用户看不到它还在跑，也看不到它什么时候完成。
  - **多图 tab / 图选择器**：前端要维护 `workflow_id → 图状态` 的 map，snapshot 事件必须带 workflow_id 路由；`workflow_started` 只负责「开一张新图 / 切到它」。
  - **只补发 running 的**：已终态的图（`_status != "declared"` 之后都会留在注册表里，`register_workflow` 从不删除，`:558-559`）重连后看不到——但用户很可能正是想看「刚才那张图跑完没有」。注意注册表里还有 `declared` 态的图（`DeclareWorkflow` 也会注册，`:475-484`），它们**不该**出现在补发列表里（`started` property 就是为过滤它而存在的，`scheduler.py:419-426`）。
  请拍板多图的 UI 形态（单图最新 / 多图切换）与重连补发的过滤规则（只 running / running + 最近 N 张终态 / 全部 non-declared）。

- **Q3: hook 在 `scheduler.run()` 上意味着 `RunPattern` 也会触发流程图——这符合预期吗？**
  **场景**: 模型调用 `RunPattern(pattern="peer-review", task="...")`（`agent/loop.py:390` 注册、`agent/subagent/patterns.py:409-440` 实现）。该函数内部 `WorkflowScheduler(manager, bus=bus)` + `manager.register_workflow` + `await scheduler.run(spec)`（`patterns.py:432-434`），所以按决策 1 的 hook 点，它会照常发 `workflow_started`。**与 Q2 多图 tab 的接口（审阅员核实）**：pattern 有自己独立的 `workflow_id`——`run_pattern()` 每条调用新建一个 `WorkflowScheduler`（默认 id），并把 `envelope["workflow_id"]` / `envelope["spec_hash"]` 透传进返回结构（`_legacy_result`，`patterns.py:381-382`）。**但 `RunPatternTool` 不经过 `parse_spec_for_manager`**（全仓只有两处调用：`subagents.py:477` 的 `DeclareWorkflowTool` 与 `:757` 的 `RunWorkflowTool`），所以它**没有「声明 → 启动」两段式**：一次 `RunPattern` 调用直接建图、直接 `run()`，`workflow_started` 和首个快照几乎同时到达。（`RunPattern` 确实在 `SPAWN_TOOL_NAMES` 里，`manager.py:326-333`——它是 spawn 入口、深度撤工具对象，但这与图事件无关。）因此 Q2 若选「多图 tab」，RunPattern 的图**必须**有自己的 tab（靠 `workflow_id` 区分），不会和 `StartWorkflow` 的图混淆；它只是「生命周期更短」。**若 Q3 选「排除」（加 `emit_graph_events` 开关），Q2 的多图 tab 就只剩 Start/RunWorkflow 两类图**——两条结论互相约束，拍板时要一起看。
  - **纳入**：四种 pattern 本来就已经降级为 DSL 模板（C2 完成的改造），图是真图，展示它信息量不小；代价是 spec delta 的措辞「模型触发多 Agent 流程（`StartWorkflow`/`RunWorkflow`）」与实际触发面不符，要改 spec。
  - **排除**：需要在 scheduler 上加一个 `emit_graph_events: bool` 之类的开关，由 `run_pattern` 显式关掉；代价是多一个状态位，且 `benchmarks/agent_runner.py:517/562` 那条路径是否也算要一起定（那条路径没有 ws，但 hook 关不关会影响测试断言）。
  - **第三种**：不按工具分，按「有没有 sink」分——没有 sink 就静默丢弃，pattern 在 web 里跑照样出图、在 benchmark 里跑天然无声。这最省事，但等于把「哪些流程该可视化」的决定交给部署形态。
  请拍板 `RunPattern` 是否触发流程图（以及 spec delta 措辞要不要跟着改）。

- **Q4: 快照推送频率——每次节点迁移都发完整快照，会不会把 ws 打满？**
  **场景**: 一张 50 节点图 + 一个 `max_items=20` 的 foreach 节点。`_dispatch` 每次置 started 发一次（`scheduler.py:1176`）、`_run_node` 每次终态发一次（`:1239` 的 `_on_node_finished` 附近）、route 命中一次、取消一次、预算停止一次——按 design D4 的口径这些都是「发完整快照」。一次 run 粗算 50×2 + 20×2 + 若干 ≈ 150 次推送；每次快照 50 节点 ×（id+kind+status+runs+summary 裁剪到 400 字符）≈ 15–25 KB，150 次就是 3–4 MB 的 ws 出流量，而且手机端要重排 150 次 SVG。design.md:105 写的兜底是「ws 队列有界，丢事件用重连补发完整快照」——但 `web/session.py:547` 的 `asyncio.Queue()` **是无界的**（没有 maxsize），所以真实风险不是丢事件，而是**事件堆积 + 无节流的重绘**。
  - **每次迁移都发**：语义最直白、实现最简单（迁移点就地调用），但上面的量级会实打实地压手机端。
  - **合并节流（例如 ≥100ms 合并成一次，终态必发）**：需要在 session 级 sender 里加一个带时间窗的合并缓冲，或者让 scheduler 侧只在「一批节点迁移结束」时发（`_drive` 的一次 superstep 末尾，`:731-735` 处 `dispatched` 统计之后）。
  - **只在 superstep 边界 + 终态发**：推送次数从 ~150 降到 ~（steps + 2），但 `steps` 受 `recursion_limit=25` 限制（`workflow.py:35`），一张快图可能只推 3–4 次——实时感会明显变差（一个跑 2 秒的节点可能整段都不刷新）。
  请拍板推送策略（每次迁移 / 时间窗合并 / superstep 边界），以及是否接受为此在 session 级 sender 里引入缓冲状态。

- **Q5: 边状态五档里的 `passed`（数据被下游消费）要不要为了它新增 per-edge 记账？**
  **场景**: 一张 `a → join`、`b → join` 的图，`join` 是 aggregate。`a` 完成、`b` 完成，`_collect_slots` 遍历 `join` 的两条数据入边时对上游逐个 `_mark_consumed`（`agent/subagent/scheduler.py:1782-1802`）。今天这个打标记的是 `upstream.run_id`（`:625-634`），无法回答「是 `a→join` 这条边被消费了，还是 `b→join`」。要区分有两种做法：在三个打标循环里顺手记 `(edge.source, edge.target)`（改动 3 行，见决策 7）；或者把 `passed` 降级为「源 completed 且目标开始跑」这类结构性近似。
  - **加记账**：五档语义完整，实现代价小但**污染了 C5 的消费口径代码路径**——`_mark_consumed` 那三处是 C5 D4/Q2「冗余度 = 有用产出 / spawn 总数」的唯一数据源，加东西进去要确认不改变 `_consumed_run_ids` 的基数（否则 `useful_runs`/`redundancy` 两个 C5 指标会漂移，`scheduler.py:2167-2168`）。
  - **四档（去掉 `passed`）**：`active` 直接覆盖「上游产出被下游拉走」的语义，前端少一个状态；代价是 design.md:63 与 spec delta 的「五档」措辞要一起改（`openspec/changes/workflow-graph-visualization/specs/web-ui/spec.md:29`）。
  请拍板 `passed` 是新增 per-edge 记账还是降级为四档（若新增，请确认允许改动 C5 的 `_mark_consumed` 调用点）。

- **Q6: 超限（`graph_recursion_exceeded`）时前端到底显示什么？**
  **场景**: 模型声明了一张 210 节点的 spec（超过默认 `max_nodes=200`）。`parse_workflow_spec` 在声明期就抛 `WorkflowValidationError`（`agent/subagent/workflow.py:369-371`），工具返回 `_invalid_spec(exc)` 错误 JSON——**此刻连 `WorkflowScheduler` 都没创建，没有任何 scheduler 对象可发快照**。另一个场景：声明 180 节点但 `max_fan_in` 自动插层后变成 205 节点，`_check_declared_limits` 在 `run()` 里抛 `GraphRecursionError`（`scheduler.py:655-666`），被收敛成 `_status="graph_recursion_exceeded"`，`_envelope` 里有 `diagnostics`（`:2183`）但这张图的 `nodes` 是**完整的 205 个**（`plan.nodes` 已构建完，`:2120`）。
  - **全图渲染 + 顶部告警条**：205 节点照样画，用户看得到「哪层插爆了」。前端要能处理 >200。
  - **只渲染 `diagnostics`**：`data.nodes` 非空但前端不画图，只显示「图超限（205 > 200）」+ 原因。**前端要显式忽略 nodes，不能靠长度判断**（决策 9）。
  - **声明期失败（210 节点，无 scheduler）**：这条路径根本没有 workflow 事件流，前端只能从 `tool_result` 里看到错误文本。要不要为它单独做点什么（例如 `workflow_started` 的失败变体），还是接受「这种情况就是没有图」？
  请拍板超限场景的前端行为（全图+告警 / 只报错不画图），以及是否为「声明期就被拒」的场景补一条事件。

- **Q7: 前端渲染的验收方式——CI 里浏览器测试恒 skip，怎么算「跨端布局做完了」？**
  **场景**: 任务 5.1/5.2（横/纵 DAG、pinch + pan）写完后要验收。现有基建事实：`playwright` 在 dev extra 里（`pyproject.toml:48-54`），但 CI 的 `validate` job 只有 `uv sync --extra dev --locked` + `uv run pytest -q`，**没有 `playwright install` 步骤**（`.github/workflows/ci.yml` 的 validate job），而 `tests/web_tests/test_browser.py:22` 的 `importorskip` 只检查 Python 包（装了）、`page` fixture 在 `p.chromium.launch` 失败时 `pytest.skip`（`:125-129`）——所以浏览器测试在 CI 里**永远 skip**。
  - **照 `markdown.js` 先例做 node 单测**：`tests/web_tests/test_server.py:614-633` 已经用 `subprocess.run(["node", "-e", ...])` + `vm.createContext` 在无浏览器环境跑前端 JS。把分层布局算法、状态→颜色/线型的映射、折叠组归类做成纯函数放独立模块，就能在 CI 里真跑。CI 有 `setup-node@v4`（node 22），这条路可行。
  - **只做后端测试 + 手工验收**：snapshot schema / 事件 / 重连全部可测（照 `tests/web_tests/test_session.py` 的 `run_session(..., ws_send=collect)` 先例），前端只留手工检查清单。
  - **把 `playwright install chromium` 加进 CI**：浏览器测试真跑、pinch/pan 也能模拟（`page.touchscreen`）。代价是 CI 时长与 flakiness。
  请拍板前端验收路径（node 单测覆盖 + 手工 / 纯手工 / CI 装 chromium），以及「分层布局算法」是否必须与 DOM 解耦到可单测的程度。

- **Q8（审阅员补充）: `workflow_started` / `workflow_snapshot` 的 ws payload 长什么样，前端 `handleEvent` 怎么路由？**
  **场景**: 前端 `handleEvent(event)`（`web/static/chat.js:414`）今天是一个 `switch (event.type)`，`case` 分支吃的是 **`event.data`**，而**顶层 `session_id` 是服务端加在外层的、不在 `data` 里**（`web/server.py:286-291` 的 `session_created` 就是 `{"type": ..., "session_id": ..., "mode": ...}` 的扁平形状）。现有 tool 事件走的是 `{"type": "...", "data": {...}}` 两层（`web/session.py:550` 的 `on_event` 包了 `{"type": ..., "data": ...}`）。新增两个 workflow 事件若不把形状和归属定死，前端拿不到 `workflow_id` 就没法做 Q2 的多图 map。
  - **推荐（审阅员）**：沿用现有两层形状 `{"type": "workflow_started"|"workflow_snapshot", "data": {...}}`，`data` 里带 `workflow_id` / `session_id` / `timestamp`（`workflow_snapshot` 的 `data` 即 design D3 那份 + 这三个归属字段；`workflow_started` 的 `data` 是 `{workflow_id, session_id, spec_hash, goal, status: "running", timestamp}`）。前端 `handleEvent` 按 `event.data.workflow_id` 路由到 `workflow_id → 图状态` 的 map。
  - **替代**：顶层扁平（照 `session_created` 先例）——但会和既有 tool 事件形状分叉，前端要写两种解包，不推荐。
  请拍板事件形状（两层 `data` 内归属 / 顶层扁平）与 `timestamp` 用 wall-clock 还是 `time.time()`（后者与 `scheduler.py` 的 `started_at`/`finished_at` 同源，便于对齐）。

- **Q9（审阅员补充）: 图的生命周期（终态后视图自动关还是保留）+ 多图 tab 何时清理 + `spec_hash` 拿来干什么？**
  **场景**: 一张 6 节点图跑完（最常见的是 10–30 秒的小图）。用户去看了眼别的，回来时图还在——**是好事**（能看到「刚跑完的那张」）；但如果一个长会话里跑了 20 次 pattern（Q3 选「纳入」时尤其常见），多图 tab 会堆 20 个 tab，每个都留着 50 个节点的 SVG。另一方面 design D3 的快照里带了 `spec_hash`，但**本 change 不做 benchmark replay**（Non-Goals 明确「不做图历史回放」），所以 `spec_hash` 到底是给用户看的、还是前端拿它对齐/去重 record 的，design 没说。
  - **推荐（审阅员）**：(a) 终态图**保留在图选择器里**但不自动切走——用户正在看的那张跑完了就停在那，标个终态徽标；**只有「用户手动关闭」或「session 被 reset/删除」才移除**。(b) 多图 tab 设一个**上限**（例如只保留最近 5 张终态 + 全部 running，与 Q2 推荐的补发规则同口径），超出按「最早终态先淘汰」。(c) `spec_hash` **只做展示与同图识别**（同一 `workflow_id` 的哈希不会变），**不做校验**——本 change 无 replay，对不上也没有兜底动作；若将来接 replay，它才是锚点。
  请拍板终态图保留策略（保留 / 自动关）、tab 上限与淘汰规则、`spec_hash` 的用途定位。

- **Q10（审阅员补充）: `workflow_snapshot` 的字段边界怎么划——要不要复用 `_envelope` 的现成键？**
  **场景**: 最省事的实现是「`workflow_graph_snapshot()` = `_envelope(status) + edges`」。但 `_envelope`（`scheduler.py:2115-2193`）里塞了一批**父 Agent 口径**的重字段：`bus`（`bus.snapshot_payload()`，`:2192`）、`attribution` + `attribution_ref`（`:2151-2152`）、`latest_events`（`:2148`）、`inserted_nodes`（`:2190`）、三份 hash（`:2187-2189`）、`diagnostics`（`:2183`）。每迁移一次就带一份 `bus` 快照推给前端，正是 design.md:107「快照数据量打爆 ws」这条风险的对立面。
  - **推荐（审阅员）**：快照**只**含 `workflow_id` / `session_id` / `spec_hash` / `status` / `nodes` / `edges` / `diagnostics`（超限时）/ `timestamp`，**显式挑字段、不整包复用 `_envelope`**。`nodes` 按决策 4 挑字段（`id/kind/status/runs/summary` + route 的 `targets`，**排除** `subagent_ids`/`slots`/`raw`/`error` 原文），`edges` 只含 `from/to/channel/required/reducer/kind/status`。终态快照可额外带 `total/completed/failed` 三个计数（供视图头展示），仍不带 `bus`/`attribution`/`latest_events`。
  请拍板快照字段集（是否包含 `diagnostics`、终态计数、是否给 route 节点带 `verdict`）。

- **Q11（审阅员补充）: 快照推送失败（ws 已断）会不会把后台 workflow 打断？**
  **场景**: `StartWorkflow(wait=false)` 走 `asyncio.ensure_future` 起后台 task（`subagents.py:537`）。按 Q1 推荐 A，快照从 scheduler 的迁移点经 session 级 forwarder `await ws_send(...)` 推给前端。用户此时**关掉页面**（ws 断开）——`ws_send` 绑的还是那条已关闭的连接，`await` 大概率抛 `WebSocketDisconnect`/`RuntimeError`。这个异常发生在**节点任务的调用栈里**（`_dispatch`/`_run_node` 都在 `_run_node` 的 task 中），会被 `_run_node` 的 `except Exception`（`:1222-1225`）吞成「节点 failed」——**用户的图因为关了个页面而失败**。这是本 change 最隐蔽的耦合：**可观测性通道反向影响执行**。
  - **推荐（审阅员）**：sink 调用必须**完全隔离**——session 级 sender 内部 catch 所有发送异常并静默丢弃（`logger.debug` 即可），对 scheduler 侧保证「调用 sink 永不抛」；scheduler 侧在 hook 点调用 sink 时也包一层 `try/except Exception: pass`（与既有 `_record_event` 里 `except Exception: pass` 写事件日志的口径一致，`:527-528`）。**并且**要把「快照推送失败不影响 workflow 状态」写成一条测试。
  请拍板隔离策略（sink 内部吞 vs scheduler 侧吞 vs 两侧都吞），以及是否接受「ws 断开期间快照静默丢失、靠重连补发兜底」。

## Codex Recommendations（codex 独立评审，2026-09-15）

以下 7 条是 codex 独立评审（agent `0408724f`）对 Q1–Q7 的**推荐答案**。主 agent 已把它们作为「codex 推荐」标注进停轮确认，最终以用户在 `## User Confirmation` 的逐条答复为准。

- **Q1 推荐（选 A）**：manager 级 sink + session 级 forwarder；允许后台 workflow 期间启动新前台 run（`run_lock` 只锁前台 AgentLoop），但禁止两个前台 run 并发；不做历史回放，只保留当前快照重连恢复。
  **审阅核实**：与决策 1/2/3 一致，无冲突。引用属实——`run_lock` 是 `AgentSession` 上的字段（`web/session.py:241`），只圈 `run_session`（`:524-536`）；manager 与 session 1:1（`:447-453`）。**两处实现细节要一并接受**：(a) 「不允许两个前台 run 并发」是**现状**（`run_lock.locked()` 直接拒绝，`:524-529`），不是新增约束，无需改代码；(b) 「`remove_session` 时要摘掉」应改为「**`reset` 消息路径**摘掉」（`web/server.py:531-543`），冷会话 DELETE（`:164-182`）顺带清——重连本身走 `resume_session_async` 命中内存 session 直接复用（`web/session.py:351-353`），不经过 `remove_session`。**且必须叠加 Q11 的发送隔离**，否则 A 的 forwarder 会在 ws 断开时把节点任务打挂。
- **Q2 推荐（多图 tab）**：多图 tab/图选择器（`workflow_id → 图状态` map，snapshot 事件带 workflow_id 路由）；重连补发全部 non-declared，但限制「当前 running + 最近 5 张终态」；不显示仅 Declare 未启动的图。
  **审阅核实**：引用属实——`_workflows` 是 `workflow_id → scheduler` 的 dict（`manager.py:408`、`:558-559`），`register_workflow` **从不删除**（无 `unregister_workflow`，全仓 grep 无命中），`started` property 就是为过滤 `declared` 而存在（`scheduler.py:419-426`）。**但「最近 5 张终态」在本 change 里无法按时间排序**：注册表的 value 是不透明的 `object`（`:408` 类型就是 `dict[str, object]`），`started_at` 虽在 `_envelope` 里（`:2178`）但不在注册表投影上；要么按 dict 插入序（Python 保序，取**最后 5 个**）近似，要么在注册表上加一条带时间的投影。请用户在 Q9（tab 上限与淘汰规则）里一并确认口径。**与 Q3 的耦合**：若 Q3 选「纳入 RunPattern」，pattern 图也有独立 `workflow_id`（`patterns.py:381-382`），会进同一个 tab 集合。
- **Q3 推荐（纳入 RunPattern）**：`RunPattern` 也触发流程图（它内部直接 `scheduler.run(spec)`，pattern 是真图）；spec delta 触发措辞改为「`StartWorkflow`/`RunWorkflow`/`RunPattern` 驱动的 workflow execution」。
  **审阅核实**：引用属实——`patterns.py:432-434` 确为 `WorkflowScheduler(manager, bus=bus)` + `register_workflow` + `await scheduler.run(spec)`（行号精确）。**代价核实**：pattern 不经过 `parse_spec_for_manager`（只有 Declare/RunWorkflow 调用它），无「声明」段，`workflow_started` 与首快照同帧到达；`benchmarks/agent_runner.py:520/564` 也直接调 `scheduler.run(spec)`（**benchmark 路径没有 manager 级 sink**，按「有没有 sink」的第三种口径天然静默；但若选了「加 `emit_graph_events` 开关」的排除口径，这两条 benchmark 调用点也要显式赋值，否则默认值会把它们卷进来——**这正是推荐里没写清的一处**）。spec delta 措辞改动涉及 `specs/web-ui/spec.md:7`（「模型触发多 Agent 流程」）与 `:11`（GIVEN 只提 `StartWorkflow`），已按「待确认 Q3」标注，等用户拍板后回写。
- **Q4 推荐（时间窗合并）**：≥100ms 时间窗合并，按 workflow 保留最新快照，终态立即发送；session 级 sender 引入缓冲状态（定时 flush + 按 workflow 去重 + 销毁清理）。
  **审阅核实**：与决策 3 的「session 级 sender」是**同一个对象**（就是 Q1 推荐 A 里那个 forwarder，加一层时间窗缓冲），不冲突；与 Q1 的「不做历史回放」也一致——「按 workflow 保留最新快照」是 sender **内部**的合并缓冲（内存里只留每个 workflow 的**最新**一份待发快照，旧的在合并时被覆盖丢弃），**不是**可回放历史。**一处 design.md 措辞需要纠正**（见 design.md 风险节修正）：`web/session.py:547` 的 `asyncio.Queue()` **没有 maxsize**，是**无界队列**，「ws 队列有界」这句是错的；Q4 场景里已点出「真实风险不是丢事件，而是事件堆积 + 无节流的重绘」，推荐的时间窗合并正是对策，二者自洽。
- **Q5 推荐（加 per-edge 记账）**：保留五档边状态，`passed` 加 `(edge.source, edge.target)` 集合（在三个消费循环里 `_mark_consumed` 旁新增），**不改变** `_consumed_run_ids` 基数（避免 C5 冗余度指标漂移）。
  **审阅核实**：与 C5 指标不冲突，隔离方案成立（见决策 12）——**前提是「旁新增」按字面执行**：只加在 3 个边循环的调用点旁，`_mark_consumed` 本体（`scheduler.py:625-634`）一行不改，`_consumed_run_ids` 基数逐位不变，`useful_runs`（`:2167`）与 `redundancy`（`:2052`）不受影响。**推荐里「三个消费循环」的措辞需补一句**：`_mark_consumed` 还有**第四个**调用点 `_write_root_result`（`:2235`），那里**没有 `edge` 变量、也不对应任何边**，per-edge 记账**不覆盖**它（见决策 11）。三个边循环的行号（`:1795`/`:1834`/`:1858`）已逐一核实属实。
- **Q6 推荐（只报错不画图）**：`graph_recursion_exceeded` 只显示 diagnostics + 告警条、不渲染图；声明期 max_nodes 被拒不补 workflow 事件（继续由 tool_result 返回错误），前端把 tool error 与 workflow error 分成两条路径。
  **审阅核实**：与决策 2/9 自洽，且**「不补事件」在 manager 级 sink 下仍然成立**——sink 挂在 workflow 的 scheduler / manager 上，而声明期被拒时 `WorkflowScheduler` **根本没被创建**（`DeclareWorkflowTool.execute` 在 `parse_spec_for_manager` 抛错时就 `return _invalid_spec(exc)`，`subagents.py:477-479`；`RunWorkflowTool` 同构，`:756-759`），scheduler 侧 hook 点（决策 1）自然无从触发。**不存在「别的入口绕过」**：全仓**生产代码**里 `scheduler.run(spec)` 的调用点只有 6 处（`agent/tools/builtin/subagents.py:559` 的 `_drive_scheduler`、`:763`、`:774`，`agent/subagent/patterns.py:434`，`benchmarks/agent_runner.py:520`、`:564`；其余全是测试），全部在 scheduler **已成功构造之后**；声明期失败路径一条都不经过它们。**唯一例外**是「声明 180 节点但自动插层后 205」这条——scheduler 存在且在 `run()` 里抛 `GraphRecursionError`（`:655-666`），会被 `_mark_graph_recursion_exceeded` 收敛成 `graph_recursion_exceeded`（`:636-645`），**此时有快照可发**（`_envelope` 里 `nodes` 是完整 205 个，`:2180-2183`），前端走「只渲染 diagnostics」分支。两种超限路径前端表现不同，Q10 已把 `diagnostics` 是否进快照单列。
- **Q7 推荐（CI 装 Chromium + node 单测）**：CI 加 `playwright install chromium` 跑关键 smoke（响应式断点 + 手势）；分层布局/状态映射/折叠归类抽成与 DOM 解耦的纯函数用 node 单测覆盖（复用 `tests/web_tests/test_server.py:614-635` 的 vm 先例）。
  **审阅核实**：引用属实——`playwright>=1.40.0` 在 dev extra（`pyproject.toml:49`）；CI `validate` job 只有 setup-python（3.11）/setup-node（22）/uv sync/`uv run pytest -q`，**无 `playwright install`**（`.github/workflows/ci.yml:22-42`；推荐原文写「`:38-42`」，实为 install 步骤在 `:38-39`、pytest 在 `:41-42`，范围基本准确）；`tests/web_tests/test_browser.py:22` 的 `importorskip("playwright")` 只查包、`:127-129` 的 `p.chromium.launch` 失败才 `pytest.skip`，所以 CI 里浏览器测试**恒 skip**——两条断言都属实。node 单测先例行号精确（`tests/web_tests/test_server.py:614-635` 的 `_render_markdown` 用 `subprocess.run(["node", "-e", ...])` + `vm.createContext`）。**补充一条事实**：CI 里 node 22 已就位（`:27-30`），走 node 单测路线**不需要新增 CI 步骤**，只有「装 Chromium 跑 smoke」才需要加 `playwright install chromium`——两种验收路径的成本差比推荐里写得更分明。

## User Confirmation

- **Q1**: 用户答复：按 codex 推荐 A——manager 级 sink + session 级 forwarder（sender 持有 session 而非单次 run 的 queue）；允许后台 workflow 期间起新前台 run，但禁止两个前台 run 并发；不做历史回放，只当前快照重连恢复；确认时间: 2026-09-15
- **Q2**: 用户答复：按 codex 推荐——多图 tab/图选择器（workflow_id→图状态 map，snapshot 事件带 workflow_id 路由）；重连补发「当前 running + 最近 5 张终态」，不显示仅 Declare 未启动的图；确认时间: 2026-09-15
- **Q3**: 用户答复：按 codex 推荐——RunPattern 也触发流程图（内部直接 scheduler.run(spec)）；spec delta 触发措辞改为「StartWorkflow/RunWorkflow/RunPattern 驱动的 workflow execution」；确认时间: 2026-09-15
- **Q4**: 用户答复：按 codex 推荐——≥100ms 时间窗合并，按 workflow 保留最新快照，终态立即发送；session 级 sender 引入缓冲（定时 flush + 按 workflow 去重 + 销毁清理）；确认时间: 2026-09-15
- **Q5**: 用户答复：按 codex 推荐——保留五档边状态，`passed` 加 per-edge 记账（在消费循环里 `_mark_consumed` 旁新增 `(edge.source, edge.target)` 集合，不改 `_mark_consumed` 本体，保证 C5 冗余度指标零漂移）；确认时间: 2026-09-15
- **Q6**: 用户答复：按 codex 推荐——`graph_recursion_exceeded` 只显示 diagnostics + 告警条、不渲染图；声明期 max_nodes 被拒不补 workflow 事件（继续 tool_result 返回错误），前端把 tool error 与 workflow error 分两条路径；确认时间: 2026-09-15
- **Q7**: 用户答复：按 codex 推荐——CI 加 playwright install chromium 跑关键 smoke；分层布局/状态映射/折叠归类抽成与 DOM 解耦的纯函数用 node 单测覆盖（复用 test_server.py vm 先例）；确认时间: 2026-09-15
- **Q8**: 用户答复：按审阅员推荐——ws 事件 `data` 带 workflow_id/session_id/timestamp，前端按 workflow_id 路由到多图 map；确认时间: 2026-09-15
- **Q9**: 用户答复：按审阅员推荐——终态图保留策略 + 多图 tab 上限淘汰规则按「最近 5 张终态 + 当前 running」；spec_hash 只做展示不做校验（本 change 无 replay）；确认时间: 2026-09-15
- **Q10**: 用户答复：按审阅员推荐——快照不复用 `_envelope`（排除 bus/attribution/latest_events 等父 Agent 重字段），用独立 `workflow_graph_snapshot()` 显式挑字段；确认时间: 2026-09-15
- **Q11**: 用户答复：按审阅员推荐——sink 调用永不抛（ws 已断时 push 异常不得经 `_run_node` except 吞成节点 failed），快照推送失败不影响 workflow 执行状态；确认时间: 2026-09-15
