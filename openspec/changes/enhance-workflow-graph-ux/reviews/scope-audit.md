# 范围与方案审阅（2026-09-17）

背景：gap-analysis 查出 27 条后，用户裁决「运行可见性全进 / 可诊断性全进 / 控制面只进 G18」，change 从「纯前端展示增强」膨胀为「前端 + scheduler 语义 + 运行期推送 + 诊断数据面 + 控制面路由」。用户要求「subagent 审阅 loop 把方案定一下」。

派两名独立只读审阅员，分别从 **范围切分与 change 边界（审阅员 A）** 与 **新决策技术正确性（审阅员 B）** 切入，各自逐条 Read 代码核验。

---

## 一、审阅员 A：范围切分

**结论：不该是一个 change，但理由不是代码行数，是「一个可交付单元只应有一个验收面」。** 现在有四个互不复用验收面（时间维增量推送 / 语义维状态口径 / 交互维下钻与路由 / 控制维写路径），**四套测试基建零复用**。3 轮 review-loop 封顶下，审阅者要同时判断「`skipped` 判据会不会破坏 `_ready_nodes` 门控」与「抽屉的 focus trap 是否正确」——不是一个审阅单元。

**推荐切法（按变更性质，不按 G 编号或前后端）**：
- 片 1（保留 `enhance-workflow-graph-ux`）：**观测面** = 纠错类 + 补数据出口类 + 原有 A–E + D2b
- 片 2（另立）：**调度语义细分** = G3 + G16
- 片 3（另立）：**控制面** = G18

**切 G3 的硬理由**：全仓 `"queued"` 只出现在读取侧判据（`scheduler.py:600/758/760/866/1772/2385`）而**无任何赋值**，是死代码、判据恒为假。给 `queued` 加赋值点会让这 6 处判据**同时激活**，其中 `:758` 参与 `_in_flight_nodes` 类收敛判断，而预算 drain 正是靠「在跑的 run 归零」落终态 → **爆炸半径比 G1 大**（G1 错了只是看不到进度，G3 错了图收不了尾）。且 `_dispatch` 在拿到 slot **之前**就置 `started`（`:1278`），真正的 `_acquire_slot()` 在 `_launch_run` 内部（`:1644-1723`），中间隔异步边界——「何时算 queued」需重新定义派发时序。

**切 G18 的理由**：片 1 其余全部条目的安全论证建立在「只读、不调 LLM、不写盘、不改执行状态」一句话上；掺进唯一写路径会破坏统一论证。且 G18 验收面（取消 vs 终态竞态、vs 预算 drain、vs 既有 `{"type":"cancel"}` 语义、重连补发口径）与片 1 零复用。补充事实：`web/session.py:1142-1143` 已有 `if msg_type in {"reset","cancel"}: fail_pending_interactions(...)` —— **前端今天发 `{"type":"cancel"}` 只会让待审批失败，run 照跑**，新增取消必须先与此划清边界。

**D2b 不可切的理由**（与 G3 的区别）：① 用户实测触发并已裁决；② 判据复用既有 `activations`，不引入新记账；③ 它是**终态**扩展（`_teardown` 时赋值，收敛之后），不参与运行中门控——而 `queued` 是**运行中态**扩展。且后端加 `skipped` 而前端不认会兜底成灰 + 原样输出英文（`workflow_graph.js:64-70`），**比现状更糟** → 后端状态与前端编码表必须同片。

**否掉的两个「不该切」论据**：(a)「共享快照 schema 所以不能切」只否掉按前后端切，否不掉按性质切（片 2 只改状态赋值、片 3 只发一条消息，都不碰 schema）；(b)「分开做会自相矛盾」对 G1 成立，但恰恰证明**切分维度必须是「用户可感知的完整场景」**——G1 的记账点修正不带 G2 的推帧等于没修（无迁移点则无帧），所以 G1+G2+G7+D5 计数行是不可切的一件事。

**审阅员 A 另指出 3 条文档级问题**：① design Goals 已改「8 档」但 spec delta 与 tasks 3.1 仍写「七档」，单测断言 7 还是 8 两份文档给出相反答案；② tasks.md 与 design.md 已脱节（tasks 仍是 30 项、0.1 还写「审视 D1–D7」）；③ 另立 change 的五类**没有 issue 号**，而仓库规则要求每个 OpenSpec 立项关联 issue，现为悬空。

**另一个关键风险框架**：G1 的机制是「**design 的位置引用可验证，但时序/因果断言不可验证**」——design 写的 `scheduler.py:1485-1497` 位置**准确**，但没意识到它在 `await asyncio.gather` 之后。本 change 剩余的未实跑时序断言还有 5 条（G2 构造成本在 sink 之前、G3 派发时序、G9 运行中无 trace、G13 运行中 used 语义、G6 与 #190 冲突未裁决），**每条都是 G1 候选**。切分降低风险的正确机制不是「审阅更轻松」，而是**每片的时序断言能在 building 第一天被实跑证伪**。

## 二、审阅员 B：技术正确性

### 五个关键断言核实结果

| 断言 | 结论 |
|---|---|
| G12 前提「上游 failed 时下游会被派发」 | **成立**。`_data_deps_satisfied` 只要求上游 ∈ `TERMINAL_NODE_STATUSES`，而 `failed` 在其中（`:79-81`）→ D2 现有「沿入边找 failed 上游」规则对 blocked 节点**基本永远找不到目标** |
| G11「`_reset_subtree` 不清 reason」 | **成立**，负耗时也成立（`finished_at` 从未被清、`_run_node` finally 是 `if finished_at is None`）。**既有测试无依赖**，清理安全 |
| G3「25 vs 5」 | **成立**。但**不要改 25**——它等于 `max_active + max_queued_runs`，是「workflow 永不撞 queue_full」不变量的一半（`manager.py:925`） |
| G9「trace 终态后仍在内存、web 拿得到」 | **成立**。session 挂 `manager._sessions`，manager 经 `session.agent.subagent_manager` 可达（`loop.py:152`）。数据形状够用 |
| D2b `skipped` 判据 | `_has_control_incoming` **兜住了普通 pending 节点**，但**兜不住「控制它的 route 自己没跑过」** → 见下 |

### 必须改的 9 条（否则「按 design 实现完仍然不对」）

1. **D2b 判据补一条**：要求控制入边的源头 route **都 `completed`**。否则「route 从未跑」会被报成「条件没走这条」——**用户读到的是假话**，正是本 change 要消灭的那类错误。
2. **D2b 顺序写进 tasks**：`_teardown` 里 skipped 判定必须**先于** `_budget_stop` 分支，否则被 route 门控的根节点在预算停时会被写成 `budget_exceeded`。
3. **D3 记账落点改成 task `add_done_callback`**：`_run_foreach_item` **没有 `state` 形参**（签名 `(node, index, item)`），文档写的「返回处 +1」**落不了地**；`add_done_callback` 一处改动、天然覆盖异常路径。并**显式排除** `CancelledError`/`GraphRecursionError`/`WorkflowBudgetExceeded` 计成「失败」（否则把关取消谎报成失败）。
4. **D3 的 `items_running` 改口径**：从 run record 的 `status == "running"` 取，别用「已派发未终态」（含 20 个排队）；且计数**只对 `kind == "foreach"` 输出**，不要连上 `__auto_agg__`（auto 节点永不经过 `_execute_foreach`，会给它恒显「0/3 完成」）。
5. **G10 候选集不能反查 `_sessions`**：`create_subagent` 从**当前 contextvar** 取 workflow_id/node_id，而工具层从不 reset → **节点内部再 spawn 的子 agent 带同一 `(workflow_id, node_id)`**，会把 `single` 误判成 `candidates`。且候选顺序 ≠ item 序号（`create_subagent` 在 `_acquire_slot()` 之后，并发下顺序不定）。改以 `NodeState.subagent_ids` 为权威，`index`/`task`/`reason` 从 run record 取。
6. **G12 的 `explainNode` 必须扩签名**：现签名 `(node, edges, nodesById)` **看不到图级 status/diagnostics**，「优先引用图级停止原因」在现签名下**无法实现**。且扫描要**穿过 blocked 上游**（blocked 的上游常常也是 blocked），去掉没有依据的「取 `finished_at` 最早」。
7. **补 tasks**：`test_node_colors_cover_seven_tiers`（`test_workflow_graph_js.py:73-80`）是**精确相等**断言，加第 8 档**必红**——design/tasks 全文没点名这个测试。
8. **spec delta 的 Scenario 要改**（`specs/web-ui/spec.md:82-84`）：钉的 GIVEN（节点未选中 + 数据上游 failed/cancelled/blocked）**在真实调度器里几乎不可达**（由核实 1，failed/cancelled 都是终态 → 节点会被派发），得叠第二个未满足依赖才成立，否则**这条 spec 无法验收**。
9. **G11 清理清单补 `summary` 与 `items`/`item_states`**：重跑期间旧 summary 会一直当「产出」显示到新 run 写入。

### 更省的替代（显著降风险）

- **G3 改用投影层实现**：在 `_graph_node_projection` 里，若 `state.status == "started"` 且 `manager.find_run(...).status == "queued"` 就投影成 `"queued"`——**一处函数、不动状态机、不多推一帧**；`_edge_status` 读 state 而非投影，边配色不受影响。**远优于「让 `_dispatch` 标 queued」**。
- **G14 用独立 `GRAPH_STATUS_COLORS`/`GRAPH_STATUS_LABELS`** 而非塞进 `NODE_COLORS`——后者有精确相等契约测试与 `groupStatus` 落表断言，塞图级状态会污染它。
- **G18 走 WS 而非新 HTTP 路由**：WS handler 手里有 `session`，`session.agent.subagent_manager.get_workflow(wf_id)` 直接拿 scheduler；`cancel()` 内部 `ensure_future` 需要 running loop，WS 天然满足；HTTP 还要重做内存口径 session 校验。
- **G9 并入因由区**：不新开 tab，把「最近 N 条 `status != ok` 的 `tool_result` + `llm_error`」附在失败节点的因由区（与 G10 的 reason 同处），其余懒加载。

### 审阅员 B 另指出

- **G2 的构造成本**：`_emit_graph_snapshot` 先**全量重建**快照（`:2226-2242` 遍历全部节点与边）再交 sink，**scheduler 侧没有任何节流**；0.1s 窗只合并**发送**、不合并**构建**。200 项 foreach = 200 次 O(nodes+edges) 构造，全在事件循环上。design 写「不放大流量」只对 WS 成立，对 CPU 不成立。
- **G9 的 `trace is None` 有三种成因**必须区分（queue_full 根本没有 / 排队取消是空 steps 不是 None / `_mark_budget_exceeded` 在 trace is None 时写 None），前端把 None 与 `steps == []` 都显示成「无证据」会漏报。
- **G13 边界**：`declared` 态 `self._budget is None` → `_budget_summary()` 返回 `{}`，前端必须容忍空 dict。
- **G18 副作用**：`cancel()` 返回 `{"status": "cancelling"}` **不是终态**；且取消是「立即标终态 + 异步 cancel 底层 run」，若 run 恰在取消前完成，`_apply_run_status` 可能把节点从 cancelled 改回 completed（既有行为，按钮要容忍状态闪动）。
- **D2b 的 `_route_verdict` per-edge 记账确认安全**：`_consumed_edges` 只在 `_edge_status` 被读，与 `_consumed_run_ids` 是两个集合，**C5 零漂移**，可照做。

---

## 三、综合方案（主 session 建议）

两位审阅员独立收敛到同一判断：**G3 该用投影层省法（审阅员 B）或切出去（审阅员 A）——两条路都指向「不要动状态机」**；**G18 成本最低、价值最高，但验收面独立**。

**推荐：本 change 保持「观测面」定位，范围不切，但按审阅员 A 的「最低限度缓解」执行**——

1. **G3 采纳审阅员 B 的投影层省法**（不动状态机，风险从「图收不了尾」降到「投影多一个分支」），留在本 change。
2. **G16 留本 change**（展示层按 reason 前缀细分，纯前端）。
3. **G18 留本 change 但在 tasks 里标为独立验收组**（用户明确要；后端已就绪，成本最低），并补 reset 先 cancel 的修正。
4. **tasks 分 3 个里程碑，每个以实跑收口**（M1 语义层 / M2 展示层 / M3 下钻层，M2 与 M3 可并行但都等 M1）——这正是发现 G1 的方式，也是审阅员 A 认可的缓解。
5. **Risks 记录**：单次 review-loop 的 3 轮封顶大概率不够；G3 类风险若在 building 后期暴露，回滚要整片回滚。
6. **修完审阅员 B 的 9 条「必须改」**再进入实现。
7. 另立 change 的五类**补开 GitHub issue**（当前悬空）。

若用户接受审阅员 A 的完整切分（G18 另立片 3），则本 change 收窄为纯观测面，G18 在片 1 合入后立刻立项——代价是用户多等一个 change 周期，收益是审阅单元更干净。
