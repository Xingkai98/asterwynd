# Grill: enhance-workflow-graph-ux 设计追问

## Reviewer

- run id: grill-enhance-workflow-graph-ux-2026-09-17
- 时间: 2026-09-17
- 对象: `openspec/changes/enhance-workflow-graph-ux/design.md` D1–D7（proposal.md / tasks.md / specs/web-ui/spec.md delta 一并核验）
- 基线: 分支 `enhance-workflow-graph-ux/2026-09-17`，base `master` @ `8a52ac3`（立项 commit）。本审阅员逐条 Read 核验的代码行数：`agent/subagent/scheduler.py` 2453 行、`agent/subagent/manager.py` 1528 行、`agent/subagent/aggregation.py`、`agent/subagent/workflow.py`、`web/server.py` 644 行、`web/session.py` 1260 行、`web/static/workflow.js` 576 行、`web/static/workflow_graph.js` 575 行、`web/static/index.html` 128 行、`web/static/style.css` 1492 行、`tests/agent/subagent/test_workflow_graph_snapshot.py` 411 行、`tests/agent/subagent/test_workflow_graph_events.py` 319 行、`tests/web_tests/test_workflow_graph_js.py` 416 行、`tests/web_tests/test_workflow_graph_browser.py` 435 行、`tests/web_tests/test_workflow_graph_server.py` 227 行、`openspec/specs/web-ui/spec.md` 714 行。
- 方法: 独立零记忆审阅。所有事实断言以本次 Read 到的源码为准，未采信 design.md 的 file:line 数字；下文凡与 design 原文不符处均给出正确 file:line。业界调研段落（Airflow/Argo/Temporal/GitHub Actions 等外部结论）无法在本地核验，本轮不评判其真实性，只核验其对本仓库事实的描述是否成立。

## Confirmed Decisions

以下 12 条是本审阅员读代码后可自行收敛的结论，不需要用户拍板；实现时必须按此写，否则会与既有代码/测试事实冲突。

- **决策**：D3 关于「`reason` 是既有字段但今天没进快照」属实，且截断是**硬要求**——`state.reason` 确实可能取到完整异常文本。 `NodeState.reason` 定义在 `agent/subagent/scheduler.py:163`；`_graph_node_projection`（`:2261-2279`）输出的键是 `id/kind/status/runs/summary/started_at/finished_at`（+ `route` 的 `targets`、foreach/`__auto_agg__` 的 `items`），**没有 `reason`**，design 的断言准确。取值链有两条且都不 bounded：`_run_node` 的 `except Exception` 分支写 `state.error = f"{type(exc).__name__}: {exc}"` 后 `state.reason = state.reason or state.error`（`:1307-1310`，GraphRecursionError 分支同理 `:1294-1299`）；另一条是 `state.reason = envelope.get("reason")`（`:1376`、`:1399`），而 envelope 的 `reason` 来自 `run.reason`，`manager.py:1215` 写的是 `run.reason = result.error` —— LLM/工具链路的原始错误串。所以「按 `_SUMMARY_LIMIT`（`:91`，=400）截断」这条对策必须落进实现，且要在 projection 里做（`state.reason` 本体不能改，它是 `_envelope` 的字段）。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D3 关于图级 `self._started_at`/`self._finished_at`「已有」属实，但两者的**哨兵语义不同**，直接进 payload 会让前端拿到 `0.0` 与 `None` 两种「没有时间」的表示。 定义在 `agent/subagent/scheduler.py:419-420`：`self._started_at = 0.0`（构造期哨兵，`:640` 才在 `run()` 里赋 `time.time()`）、`self._finished_at: float | None = None`（`:687` 的 `finally` 才赋值）。`declared` 态（只 `DeclareWorkflow` 未 `run()`）的调度器确实能取快照——`test_snapshot_available_after_declare_without_run`（`tests/agent/subagent/test_workflow_graph_snapshot.py:341-351`）就断言 `status == "declared"`，此时 `started_at == 0.0`。同一份数据在 `_envelope` 里已有两种口径：顶层直接给 `"started_at": self._started_at`、`"finished_at": finished_at`，而 `finished_at` 是局部变量 `self._finished_at or time.time()`（`scheduler.py:2336`、`:2382-2383`）。结论：快照必须显式选一种——推荐 `started_at: (self._started_at or None)`、`finished_at: self._finished_at`（运行中为 `None`），把「没有值」统一成 `null`，绝不能让前端把 `0.0` 当 epoch 0 渲染成「56 年前」或把 `0.0` 当「已跑时间」算出天文数字。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D3 的 foreach 记账点定位正确（`scheduler.py:1482-1507`），但**必须同时在 `_execute_foreach` 开头把这组计数归零**，否则 route 回边重跑会累加出 `M > N`。 `_execute_foreach` 在派发前重置的是 `state.items = len(items)`、`state.subagent_id = None`、`state.run_ids = []`、`state.subagent_ids = []`（`:1462-1466`），当时没有计数器所以无事；新增 `items_completed`/`items_failed` 后若不在此处一并清零，`_execute_route` 命中回边激活同一个 foreach 容器（`:1446-1452` 把下游从终态 `_reset_subtree` 后重跑）就会在上一次的结果上继续 `+=`。另有两处必须写进实现的细节：(a) gather 结果循环里 `asyncio.CancelledError` 分支是**提前 return**（`:1487-1489`），此时计数停在部分值——与既有 `state.status = "cancelled"` 一致，前端要容忍 `M < N`；(b) 计数的「失败」口径应与既有 `failures` 对齐（`:1486-1497`：异常 envelope 与 `status != "completed"` 都算失败），否则 `M/N` 与 `state.reason` 的 `f"{failures}/{len(items)} foreach items did not complete"`（`:1505`）会自相矛盾。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D3 要求的白名单同步只影响**一个测试文件**，但图级白名单不是模块常量而是内联字面量——任务 1.4 的措辞要落到具体行。 `SNAPSHOT_NODE_KEYS` 是模块级 `frozenset`（`tests/agent/subagent/test_workflow_graph_snapshot.py:34-36`，当前值 `{id, kind, status, runs, summary, started_at, finished_at, targets, items}`），用 `<=` 断言（`:150`）；节点排除断言在同一函数里（`:151-155`，含 `verdict`）。图级白名单是**内联 set 字面量**（`:173-176`：`workflow_id/spec_hash/goal/status/nodes/edges/total/completed/failed/diagnostics/timestamp`），加两个时间戳必须改这里，没有常量可改。边白名单用 `==`（`:159`），本 change 不动边字段所以不受影响。全仓 grep 确认没有第二个测试断言快照的键集（`test_workflow_graph_events.py` 只断言 `node["status"]`/`diagnostics["reason"]`，`test_workflow_graph_server.py` 只断言事件到达）。`test_snapshot_does_not_drift_envelope_contract`（`:358-368`）断言的是 `_envelope`/`parent_envelope` 的键，本 change 不动这两者，会继续绿。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D4 说「点击语义变更须同步更新既有 `test_workflow_graph_js.py` 里依赖点击语义的用例」是**指错了文件**——该文件是纯函数单测（node+vm 跑 `workflow_graph.js`），全文件没有任何 click/toggle 用例；真正会红的是**浏览器 smoke**。 依赖点击语义的既有断言在 `tests/web_tests/test_workflow_graph_browser.py:343-369`（`test_collapsed_group_click_expands_members`：两次 `page.click(".workflow-node[data-node-id='fan']")`，先断言成员出现、再断言收回），这正是 tasks 4.3 要改的用例。渲染侧的实现点是 `web/static/workflow.js:423`（`group.addEventListener('click', () => toggleGroup(tab, entry, node))`）与 `:434-443`（`toggleGroup`，非 `groupLeader` 直接 return）；配套的 CSS 是 `web/static/style.css:1482` 的 `.workflow-node.group-leader { cursor: pointer; }`——拆分后普通节点也要可点，cursor 口径要一起改。`test_workflow_graph_js.py` 里与折叠相关的是 `collapseGraph`/`groupLeader` **数据**断言（`:322-354`），它们断言的是「展开态仍带 `groupLeader`」，与点击事件无关，本 change 不需要动。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D7 说并行边偏移「改动局限在 `edgePath()` 一个函数内」**不成立**——`edgePath(from, to, orientation)` 拿不到 multiplicity 与序号，必须在 `layoutGraph` 里加一次预扫。 `edgePath` 定义在 `web/static/workflow_graph.js:285-300`，签名只收两个节点盒（`from`/`to`）与方向；调用点是 `layoutGraph` 的 `layoutEdges`（`:248-266`，`item.path = edgePath(from, to, orientation)`），这是唯一能同时看到同一对 `(from,to)` 全部边的地方。所以 `offset = (k - (n-1)/2) * DELTA` 需要：(a) 在 `layoutEdges` 里先按 `from->to` 分组统计 `n` 与每个 `k`；(b) 把 `{index, total}`（或已算好的 `offset`）传进 `edgePath`。`edgePath` 是对外导出的 API（`:563`），加可选参数保持向后兼容即可。另外分组键建议用 **`(from,to)` 而不是 `(from,to,kind)`**：route 节点的出边全部被 `is_control_edge` 判为控制边（`agent/subagent/aggregation.py:208-209`：`edge.source in self._control_sources`；`agent/subagent/workflow.py:243-245`：源是 route 即控制边），而 `data_outgoing` 明确排除控制边，因此同一对端点上控制边与数据边不会共存，两种键在本仓库等价——选 `(from,to)` 更简单且不会因为未来新增 kind 而漏铺。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D4 的「`node 重跑多次` → 按 `run_id` 取最新 run（与 `inspect_transcript` 默认口径一致）」**不实**：`inspect_transcript` 的 messages 分支完全不按 `run_id` 过滤，默认 `limit=5`，且没有单条内容截断。 签名与实现在 `agent/subagent/manager.py:1009-1049`：`inspect_transcript(*, subagent_id, scope="summary", run_id=None, limit=5, include_tool_results=False)`；`inspect_transcript` 的返回值里 `run_id` 只是**回显**参数，messages 分支取的是 `messages = session.messages` → `tail = messages[-limit:]`（`:1035-1038`），即**整段 session 消息**（同一 subagent 被重跑时历次 run 的消息都在 `session.messages` 里累积）的尾部，不是「最新 run 的消息」；参数初值也在 `InspectSubagentTranscriptTool.execute`（`agent/tools/builtin/subagents.py:207-215`）里证实（`limit` 默认 5、`include_tool_results` 默认 False）。`extract_text(msg.content)`（`:1044`）逐条返回，也没有单条长度上限。三条落地结论：(a) 路由必须显式传 `scope="recent_messages"` 与 `limit=200`（`scope="summary"` 返回体根本**没有 `messages` 键**，只有 `summary`）；(b) 「单条内容截断」是**路由自己**要加的能力，`inspect_transcript` 不提供；(c) `truncated` 的语义是 `len(messages) > limit`（已剔除 tool 角色后），前端文案别写成「内容被截断」。未知 `subagent_id` 会抛 `KeyError`（`_require_session`，`:1433-1437`），路由要捕获后转结构化响应。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D4 的「按 `(workflow_id, node_id)` 找对应 subagent」在 foreach 容器上**不是一对多里的「找不到」，而是一对多里的「找到 N 个」**——每个展开项都有自己的 session，且 `node_id` 都等于容器 id。 `_execute_foreach` 先把容器状态清空（`state.subagent_id = None`、`state.subagent_ids = []`，`scheduler.py:1464-1466`），再对每一项 `asyncio.create_task(self._run_foreach_item(node, index, item))`（`:1476-1479`）；`_run_foreach_item` 调 `_launch_run(node=node, ...)`（`:1509-1523`），而 `_launch_run` 里 `set_node_id(node.id)`（`:1669`）用的正是**容器节点**，`manager.create_subagent` 因此把 `node_id=<foreach 容器 id>` 写进 `SubagentSessionRecord`（`manager.py:467-478`，字段定义 `:168-169`）。所以 manager 的 `_sessions`（`:360`）里会有 N 条 `(workflow_id, node_id)` 相同的记录。这直接决定路由的解析规则必须写成「按 `(workflow_id, node_id)` 收集候选集」而不是「取第一条」：候选 0 条 → 未派发（`subagent_id: null`）；候选 1 条（普通节点，或恰好 1 项的 foreach）→ 直接给该条 transcript；候选 N>1 条 → 返回结构化「容器，附 N 个候选（subagent_id/status/summary 摘要）」。design 现在写的「foreach 容器 → 一律无单一 transcript」会把 N=1 的容器也拒掉，且丢掉了 D5 想展示的项列表数据。普通节点重跑复用 `subagent_id`（`_launch_run` 里 `reuse_state.subagent_id` 非空则复用，`:1673-1682`），所以不会因重跑产生第二条候选——这一点 design 的担心是不必要的。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D4 的「需真实存在的 `session_id`」在本仓库的含义是「**在内存里**存在」，冷会话/重启后恢复的会话一律 404——与既有 `/api/sessions/{id}/timeline` 同口径，路由与前端文案都必须按这个口径写。 既有路由的校验方式是 `session = session_manager.get_session(session_id)`，取不到直接 `404 {"error": "session not found"}`（`web/server.py:160-175`）；`SessionManager.get_session` 只查内存字典 `self._sessions`（`web/session.py:1013-1014`，字典在 `:780` 定义，只在 `_create_session` 里写入 `:1009`）。也就是说 `/api/sessions`（hub 列表，`web/server.py:205-217`）能列出的磁盘会话，其 transcript 路由会 404。这不是缺陷，但必须写进 spec/测试（tasks 2.4 的「未知 session 404」用例要覆盖「进程重启后同名 session」这个最容易误判为 bug 的场景），且前端「对话」tab 要对 404 优雅降级为「该会话未在本进程加载」。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D2/Context 的「今天节点摘要单靠 `<svg:title>`，移动端看不到」在**代码事实层面成立**，且比 design 说的更严重：非折叠组长节点的点击是全然的 no-op。 唯一的摘要出口是 `web/static/workflow.js:418-421`（`svgEl('title')`，内容是 `id [kind] label` + `truncate(summary, 200)`），没有任何其它摘要元素或 tooltip；点击绑定在 `:423`，而 `toggleGroup` 对非 `groupLeader` 直接 return（`:435`），所以普通节点**点了没有任何反应**——这正是 proposal「非折叠组节点点击完全无效」的依据，核实无误。截断函数 `truncate` 在 `:561-564`（半角省略号）。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：D7 的根因归因**成立但只覆盖了一半**：`collapseGraph` 的去重**只在折叠态发生**（节点数 ≥ threshold），未折叠时边是原样透传的，所以「11 edges 只画 6 条线」在 <50 节点的小图上只能由几何重合解释。 `collapseGraph` 在 `allNodes.length < threshold` 时直接 `return {nodes: allNodes.slice(), edges: allEdges.slice(), collapsed: false}`（`web/static/workflow_graph.js:404-406`），**不做去重**；只有走到折叠分支才用 `` `${from}->${to}:${edge.kind}` `` 做 `seenPairs` 去重（`:507-516`）。而 summary 报的确实是原始边数：`renderSummary` 取的是 `(snapshot.edges || []).length`（`web/static/workflow.js:262-265`），不是 `collapsed.edges.length`。`edgePath` 无任何偏移（`:285-300`）这一条准确。结论：两条根因（口径不一致 + 几何重合）都要写进 spec 的「可解释口径」措辞，但实现者不能假设「去重一定发生」——小图场景下 `collapsed.edges.length === snapshot.edges.length`，此时 `N paths (原始 M edges)` 里两个数字相等，文案不能写死「含并行边/折叠合并」。来源: grill-enhance-workflow-graph-ux-2026-09-17

- **决策**：spec delta 与**既有 spec 会直接冲突**——`openspec/specs/web-ui/spec.md:543` 的「workflow 图跨端适配」明文写着「50–200 节点 SHALL 折叠 foreach/自动插层（折叠组聚合状态、**点击展开局部**）」，而本 change 的 ADDED Requirement「workflow 节点详情面板」要求「打开面板的点击 SHALL NOT 与折叠组展开/收起复用同一手势；折叠组展开 SHALL 由独立控件承担」。归档后两条 Requirement 会在同一份 spec 里并存且互相否定。 delta 目前只有 **1 个 MODIFIED Requirement（workflow 图快照）** + 4 个 ADDED，**没有**改「workflow 图跨端适配」。这是必须在实现前补的：要么把「workflow 图跨端适配」也写进 `## MODIFIED Requirements` 并改写「点击展开局部」为「点击开详情 + 独立控件展开」，要么在新 Requirement 里显式声明它 supersede 该措辞（OpenSpec 的规范做法是前者）。另外「快照显式挑字段」那条**不冲突**：delta 的 MODIFIED 段落把原句（`subagent_ids`/`slots`/`raw` 排除 + 边只含结构字段）**逐字保留**后追加加法字段段，与既有 spec `:497` 一致，无需额外处理。来源: grill-enhance-workflow-graph-ux-2026-09-17

## Open Questions

> **本节已按 2026-09-17 重评估更新，Q1–Q4 全部收敛（用户 2026-09-18 拍板）**：原 4 条中，**Q1 与 Q4 已被后续设计唯一确定、不需要用户拍板**（见下节「重评估」的完整论证）；**Q2 与 Q3 经改写后由用户拍板**（见文末 `## User Confirmation`）。四条均已有唯一答案，**不再有未决问题**。

- **Q2: 折叠组的「展开/收起」入口放在哪？**（改写自原 Q2。原三选项均假设「控件画在节点上」，审阅员证明该前提在手机上不成立。）
  **场景**: 手机（≤720px、纵向 DAG）上一张 60 节点的图，`fan` 容器折叠着 3 个 auto 层节点，用户有两个意图——(a) 展开 `fan` 看看里面有哪些成员，(b) 点 `fan` 看它的详情/产出。**原前提为何不成立**：节点盒是 168×58 **SVG 用户单位**（`workflow_graph.js:96-97`），手机 380px 视口下 `fitToWidth` 缩放后节点实显仅约 **36px 高**（3 节点层）/ **27px**（4 节点层）——「≥44px 按钮」在 SVG 坐标里是**假的**（实显约 27/21px，比节点本身还大）；且 `TAP_SLOP = 4`（`workflow.js:449`）判定点击/拖动，手指漂移超 4px 后 host `setPointerCapture`（`:490-497`）会吃掉 click，手机上最常见的操作必然踩坑。
  **选项 A（节点内 HTML 覆盖层小控件）**：控件脱离 SVG 变换、按节点屏幕坐标定位随 pinch/pan 重算，才能真正达到 44px；点按钮 = 展开、点节点其余 = 开详情；必须 `pointerdown` 级 `stopPropagation`（只靠 click 的 `stopPropagation` 不够）。**选项 B（展开收进详情抽屉）**：点节点一律开详情，抽屉里给 `groupLeader` 一个「展开成员」动作——零触控目标问题、零手势冲突、实现最省，代价是手机端抽屉占 70vh、展开后要先关抽屉才看得到结果。
  **推荐**: 选项 A。

- **Q3: tab 的编号与排序——`#N` 按什么算，运行中是否仍排最前？**（改写自原 Q3。原选项缺「排序」这一维。）
  **场景**: wf1 起后跑 10 分钟，wf2/wf3 随后起并很快结束。按「出现序编号 + 运行中排最前」，tab 条从左到右读作 **`#1 #3 #2``**（`design.md:363` 写「出现顺序」、`:368` 又写「运行中排最前」，二者必然冲突）。**第二个反例**：`_workflows` **永不注销**（`manager.py:408/567`），WS 重连补发（`web/session.py:695-723`）会把前端**早已淘汰**的图塞回来并分配新 `nextSeq` → 同一张图重连前 `#2`、重连后 `#9`，「第几次 run」**答错**。
  **选项 A（按 `started_at` 排序编号 + 排序也按编号）**：编号与位置一致、跨整页刷新稳定、与用户嘴里的「第几次 run」同义；运行中用徽标区分（不靠排序表达）；代价是淘汰后编号前移。**选项 B（到达序单调计数器 + 保持「运行中排最前」）**：淘汰不重编号，但 tab 序列非单调，且 WS 重连补发会让被淘汰过的图拿到新编号。
  **推荐**: 选项 A。


## 重评估（2026-09-17）：Q1–Q4 在设计大幅演进后是否仍合理

用户提出：「起 subagent grill 主要是我在想这个比较久了，现在已经改了这么多设计，这几个是否还合理」。派**两名独立零记忆审阅员**（A/B）重新评估 Q1–Q4 的前提是否仍成立。**两名审阅员在 Q1/Q4 上一致，在 Q2/Q3 上分歧**——分歧本身是本次重评估的主要产出。

### 一致的结论：Q1、Q4 已 moot，不需再问

- **Q1（foreach 容器 transcript）**：原二选一（候选清单 vs 一律无入口）已被「界面效果 §0」+ D4 三态 union + G10 唯一确定；方案 B 被 G10 的立项理由否掉（失败项 `summary` 为空 → 不给候选就是「3 个红点、点开每行空白」，正是 issue 原始场景）。
  **但审阅员 B 找出 design 内部矛盾**：`subagent_ids` 是**稀疏数组**（异常 envelope 走 `continue` 跳过 append，`scheduler.py:1487-1492`），**不能当索引源**——12 项被取消时点开只有 8 行候选，而「还有哪 4 个没跑」恰是用户最想知道的。已修正为「索引源 = `item_states`（index 空间），`subagent_ids` 只做真实性校验」。
- **Q4（reason 截断额度）**：前提被 G17 证伪——「全文去 transcript 看」不成立（scheduler 侧 reason 从不出现在任何 subagent transcript 里），G17 已强制要求路由返回全文。剩下只是数值，而**截断值对用户不可见**（快照 reason 只用于节点 `why` 小字与详情状态区，都不渲染 2KB；全文阅读走详情面板从路由取）。落为设计裁决：快照 400（`_SUMMARY_LIMIT`）+ `reason_truncated` 布尔；路由 `single`/`candidates`/`none` 返回 `reason_full`/`reason_length`。
  **审阅员 B 补两处**：(a) **前端比长度判截断是错的**——恰好 400 字符的 reason 会被误判「已截断」，布尔标志是唯一正确做法；(b) `none` union 也须给全文（`blocked`/`budget_exceeded` 恰是最常点的节点，而它们的 reason 属于 `none` 态）。

### 分歧：Q2、Q3 仍需用户拍板，且**推荐答案都有会出错的反例**

两名审阅员对 Q2/Q3 是否需用户拍板判断相反（A 说不需要、B 说需要），**B 给了可复现的反例，故采信 B**：

- **Q2（展开控件）**：审阅员 B 构造出反例——节点盒 168×58 SVG 单位，手机 380px 视口下 `fitToWidth` 缩放后节点实显仅约 36px（3 节点层）/ 27px（4 节点层），**「≥44px 按钮」在 SVG 坐标里是假的**（实显约 27/21px，比节点本身还大）；且 `TAP_SLOP=4` 会让手指漂移超过 4px 后 `setPointerCapture` 吃掉 click（`:490-497`）→ 手机上最常见的操作必然踩坑。**问题前提「控件必须画在节点上」本身要重新审视**。
- **Q3（tab 序号）**：审阅员 B 构造出反例——`_workflows` 永不注销，重连补发会把前端**早已淘汰**的图塞回来并分配新 `nextSeq`，同一张图重连前 `#2`、重连后 `#9`，「第几次 run」答错；且「按时间编号 + 运行中排最前」的组合必然产生非单调序列（长跑 wf1 + 快结 wf2/wf3 → tab 读作 `#1 #3 #2`），而 Q3 的三个选项里没有「排序」这一维。

**这两条已改写为 Q2′/Q3′ 抛给用户（见 `## User Confirmation`）。**

### 审阅员找出的其他缺口（非用户决策，已直接修正）

1. `TERMINAL_STATUSES` **双副本**（`scheduler.py:104-109` + `workflow.js:16`）必须同步加 `completed_with_failures`，否则那张图被当成 running → 永不淘汰、永久排最前。
2. 候选集字段三处对不上（spec scenario / design schema / G10），统一为含 `index`/`task`/`reason` 的版本。
3. D5.3 项列表的 tab 归置与 §3 形态图矛盾（「任务」tab vs 「对话」tab）——定为「对话」tab，否则破掉懒加载契约。
4. spec delta 缺 G17 的 Requirement（tasks 有、spec 没有 → 做完守不住）。
5. G19（定位异常节点）/ G21（复制）在 design 里一个字都没有——已补进 Non-Goals 显式记录。

## User Confirmation

- **Q2**: 用户答复：**选 B——把「展开/收起折叠组」收进详情抽屉**（点节点一律开详情，抽屉里给 `groupLeader` 一个「展开成员」动作）。理由：该控件只服务 ≥50 节点的大图，日常小图（如 12 文件体检）根本看不到它；为大图专属的小控件去实现「脱离 SVG 缩放的 HTML 覆盖层 + pointerdown 级阻断」性价比不高，B 零触控目标问题、零手势冲突。代价（手机抽屉占 70vh、展开后需先关抽屉）用户接受。；确认时间: 2026-09-18
- **Q3**: 用户答复：**选 A——按 `started_at` 编号，且排序也按编号**（运行中用徽标区分，不靠排序表达）。理由：用户认的是「第几次 run / 何时起 / 结果差异」，空间顺序与编号一致比「运行中排最前」更重要；运行中完全可用徽标表达，不必占位置。接受的代价：淘汰后编号前移（原 `#2` 变 `#1`）。；确认时间: 2026-09-18
