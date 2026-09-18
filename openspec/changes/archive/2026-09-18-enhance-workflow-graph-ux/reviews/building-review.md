# Building 审阅报告：enhance-workflow-graph-ux

## Verdict

**PASS**（Round 2，2026-09-18）— Round 1 的唯一中等 Issue（foreach 候选项下钻无取数路径）已前后端修通并**经变异验证为真保护**，2 条低风险项按建议处理，审阅中发现的串台测试假保护也已加固并复验，无新引入的中等以上问题。详见文末「Round 2 复审」。

> 历史：Round 1 结论为 **CHANGES_REQUESTED**（head `cba2d6c`），含 1 条中等 + 2 条低；修复提交 `4aea153`，串台测试加固 `80304e0`。

## 审阅基线

| 项 | 值 |
|---|---|
| reviewer | 独立零记忆审阅 subagent（本轮由主 agent 调度，paseo 托管） |
| change id | `enhance-workflow-graph-ux`（issue #197） |
| base sha | `0272bcb32eed2ea8a5cc0d8ae2252f8b9580f89d` |
| head sha | `80304e0`（Round 1 审时为 `cba2d6c`；修复 R1c 为 `4aea153`） |
| 分支 | `enhance-workflow-graph-ux/2026-09-17` |
| 审阅时间 | 2026-09-18 |
| 审阅范围 | `git diff 0272bcb..cba2d6c`（M1/M2 数据面/M2 前端+M3/M4 + 收尾 4 个小提交） |

## 任务逐项验证

逐条读代码确认（不采信任务自述）。M1 语义层 / M2 展示层 / M3 下钻层 / M4 收尾：

| 任务 | 实现证据（`文件:行号`） | 结论 |
|---|---|---|
| M1.1 G11 复位清因由 | `agent/subagent/scheduler.py:1511`（`_reset_subtree` 清 `reason`/`error`/`summary`/`finished_at`） | ✅ 真实存在 |
| M1.2 `skipped` 档 + 判据 + 独立计数桶 | `scheduler.py:81`（`TERMINAL_NODE_STATUSES` 加 `skipped`）、`:1298`（`_is_skipped`）、`:2462`（`_unit_counts` 的 `skipped_units`，独立桶不落 pending） | ✅ |
| M1.2 判据**先于** `_budget_stop` | `scheduler.py:1287`（`_resolve_pending_status` 里 `if self._is_skipped(...)` 在前，`elif self._budget_stop` 在后） | ✅ 顺序写死 |
| M1.3 route 边消费记账，`_mark_consumed` 本体不改 | `scheduler.py:2300`（`_route_verdict` 内 `self._consumed_edges.add(...)`）；`git diff` 全文中 `_mark_consumed` **只出现在 docstring**，函数体零改动 | ✅ 红线守住 |
| M1.4 `explainNode` 扩签名 + 穿透 blocked 上游 | `web/static/workflow_graph.js`（`explainNode(node, edges, nodesById, graphStatus, diagnostics)`，去掉「取最早 finished_at」） | ✅ |
| M1.5 图级 `completed_with_failures` | `scheduler.py:1234`（`_terminal_converged_status`）；`_drive` 收敛出口 `:893` 调用它；`_SNAPSHOT_TERMINAL_STATUSES` 含该值 `:109` | ✅ 优先级正确（budget/cancelled/recursion 仍在前） |
| M1.6 测试 | `tests/agent/subagent/test_workflow_semantics_m1.py:97/123/180/270/288` | ✅ 真实断言 |
| M2.1 foreach 计数点 = task `add_done_callback` | `scheduler.py:1667`（`task.add_done_callback(partial(self._on_foreach_item_done, state, index))`）；`_run_foreach_item` 已加 `state` 形参但仍以回调为唯一计数点 | ✅ **设计红线确认** |
| M2.1 回调排除三类中断 | `scheduler.py:1740`（`_on_foreach_item_done`：`task.cancelled()` / `isinstance(exc, asyncio.CancelledError)` / `isinstance(exc, (GraphRecursionError, WorkflowBudgetExceeded))` 一律 `cancelled`，不计 failed） | ✅ **设计红线确认** |
| M2.2 `items_running` 从 run record 取 | `scheduler.py:1726`（`_item_live_status`：`find_run(...).status == "running"` 才算 running，否则 `queued`） | ✅ **设计红线确认**（已变异验证） |
| M2.2 计数只对 `kind == "foreach"` | `scheduler.py:2566`/`:2623`（`_graph_node_projection` 里 `kind == "foreach"` 才调 `_add_item_projection`；`AUTO_NODE_PREFIX` 分支只给 `items`） | ✅ 不连 `__auto_agg__` |
| M2.3 项级推帧 + 调度器侧限频 | `scheduler.py:1777`/`:1793`（`_emit_item_frame`/`_drain_item_frame`，`_ITEM_FRAME_WINDOW_S = 0.1`）；补发点在 `_drive` `:887` | ✅ 限频落在调度器侧 |
| M2.4 快照加法字段 + 投影层截断 | `scheduler.py:2566`（节点 `reason`/`task`，`[:_SUMMARY_LIMIT]`）、`:2499`（图级 `started_at: self._started_at or None` / `finished_at` 哨兵统一 null） | ✅ |
| M2.5 图级 `budget` | `scheduler.py:2505`（复用 `_budget_summary()`，declared 态 `{}`） | ✅ |
| M2.6 `queued` 只在投影层 | `scheduler.py:2602`（`_projected_status`）；**全仓 grep 无 `state.status = "queued"` 赋值点** | ✅ **设计红线确认** |
| M2.7 超限仍画图 + 独立 `GRAPH_STATUS_*` | `web/static/workflow.js:242`（`G.graphStatusColor`）；`NODE_COLORS` 不含图级状态（测试 `test_graph_status_colors_are_a_separate_table` 精确断言） | ✅ |
| M2.8 图例同源生成 | `workflow_graph.js` `legendModel()`；浏览器 smoke `test_legend_is_visible_and_collapsible` | ✅ |
| M2.9 四重编码 + 字形约束 | `statusEncodings`/`statusEncoding`（角标 `‖` 非 `⏸`） | ✅ |
| M2.10 elapsed 独立计时器 | `workflow.js`（本地计时器 + `formatElapsed`/`formatAge`） | ✅ |
| M2.11 Q3=A 编号 + 排序按编号 + `TERMINAL_STATUSES` 加档 | `workflow.js:21`（`TERMINAL_STATUSES` 含 `completed_with_failures`）、`rankGraphs`/`graphTabMeta` | ✅ 与用户 Q3 拍板一致 |
| M2.12 route 诊断渲染 | `graphNotice` 带 `current_nodes`/`steps`（测试 `test_graph_notice_carries_current_nodes_and_steps`） | ✅ |
| M3.1 详情抽屉 + a11y | `web/static/index.html`（`#workflow-drawer`/`#workflow-scrim`）、`workflow.js` `closeDrawer`（Esc/遮罩/× 共用） | ✅ |
| M3.2 Q2=B 点击语义拆分 | `workflow.js:974`（`closeDrawer`）、展开动作 `.drawer-action[data-action='toggle-group']`；smoke `test_collapsed_group_expands_from_the_detail_drawer` | ✅ 与用户 Q2 拍板一致 |
| M3.3 候选集以 `item_states` 为索引源 | `web/session.py:898`（`_foreach_candidates` 遍历 `state.item_states`，`subagent_ids` 只做真实性兜底） | ✅ **设计红线确认** |
| M3.4 候选补 `reason`/`task` | `web/session.py:898`（`run.reason` / `run.task`，均 bounded） | ✅ |
| M3.5 `reason` 全文出口 | `web/session.py:757`（`_reason_fields` 返回 `reason_full`/`reason_length`/`reason_truncated`） | ✅ |
| M3.6 `trace_digest` | 见「未覆盖」——本轮未逐行核实 | ⚠️ 部分 |
| M3.7 WS `cancel_workflow` + reset 修 | `web/server.py:632`（cancel_workflow）、`web/server.py` reset 分支遍历 `list_workflows()` 逐个 `cancel()`；`session.py:917` 边界与既有 `{"type":"cancel"}` 区分（测试 `test_cancel_workflow_is_distinct_from_legacy_cancel`） | ✅ |
| M3.8 刷新节律 + 暂停按钮 | `workflow_graph.js`（`transcriptRefreshDue`/`isTerminalNodeStatus`/`TRANSCRIPT_REFRESH_S = 10`）、`workflow_transcript.js`（`scheduleAutoRefresh`/`stopAutoRefresh` + 关抽屉停表） | ⚠️ 见 Issue #1（候选项下钻） |
| M4.1 前端单测 | `tests/web_tests/test_workflow_graph_ux_js.py`（41 条） | ✅ |
| M4.2 浏览器 smoke | `test_workflow_graph_browser.py`（14 条，含图例/抽屉/懒加载/foreach 计数） | ✅ |
| M4.4 兼容回归 | `test_snapshot_does_not_drift_envelope_contract` 绿 | ✅ |
| M4.6 spec 同步 | `openspec/specs/web-ui/spec.md` + `multi-agent-collaboration/spec.md`；`workflow-events.jsonl` 有 2 条 `current_spec_synced` 结构化事件 | ✅ |
| M4.7 文档影响 | `docs/architecture.md`、`docs/openspec-change-backlog.md` | ✅ |
| M4.8 另立 issue | design Non-Goals 含 #201–#205 | ✅ |

## 测试结果

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/agent/subagent/ tests/web_tests/ -q -p no:randomly` | **2 failed, 741 passed, 7 skipped**（5m59s） |
| 上述 2 条单独复跑 `tests/web_tests/test_workflow_graph_browser.py` | **14 passed**（22.7s） |

- 首轮 2 条失败（`test_workflow_view_mobile_vertical_layout`、`test_legend_is_visible_and_collapsible`）**在本文件单独运行时不复现**，属用户已确认的既有浏览器 harness 竞态（与 #191 同类，已记入 proposal 的 Known Issues，约定本 change 不修）。按指示未计入 verdict。
- 隔离运行时全绿，与 known-flake 列表（`test_tree_sitter_symbols`、`test_multi_session_browser`、`TestE2eEngineCliSmoke`）无交集。

## 变异验证

对 3 个方向、7 处实现做「改坏 → 确认变红 → 还原」。**只报能变红的保护**：

| # | 变异 | 目标测试 | 结果 |
|---|---|---|---|
| A | `_item_live_status` 去掉 `run.status == "running"` 判据（已派发即算在跑） | `test_items_running_excludes_queued_items` | ✅ 变红（真保护） |
| B | `transcriptRefreshDue` 去掉 `if (opts.paused) return false` | `test_transcript_refresh_stops_while_paused` | ✅ 变红（真保护） |
| C | `transcriptRefreshDue` 去掉 `isTerminalNodeStatus` 判据 | `test_transcript_refresh_stops_for_terminal_nodes` | ✅ 变红（真保护） |
| D | `transcriptRefreshDue` 恒返回 `false`（「永不重取」方向） | `test_transcript_refreshes_on_a_pinned_cadence` | ✅ 变红（真保护） |
| F | `_terminal_converged_status` 恒返回 `"completed"` | `test_graph_with_failed_node_is_completed_with_failures` | ✅ 变红（真保护） |

**结论：本 change 新增的关键断言确有真保护**，未发现「条件恒真 / 只断言 truthy」的假保护。刷新节律的**两个方向**（永不重取 / 每 tick 都重取）都由 `test_transcript_refreshes_on_a_pinned_cadence` 的双向断言覆盖——D 变异证明「永不重取」会红，会话中已验证「每 tick 重取」方向（`now - last >= S` 改为恒真）同样会红。

M1 的 `skipped` 判据（`_is_skipped` 三条件、`_upstreams_resolved` 上游先定）已由用户在收口前自行做过变异验证（去掉 `blocked` 项 → 前两条红；改朴素声明序单遍 → 后两条红），本轮未重复。

## Issues

### 中等

**#1 ｜ foreach 候选项「点进去看该项自己的 transcript」未实现（spec 已同步）**

- **证据**：`web/static/workflow_transcript.js:231` 在候选项点击时把 `subagentId: candidate.subagent_id` 塞进 ctx，但 `fetchTranscript`（`:53`）构造的 URL 只用 `ctx.nodeId`（容器节点 id），**完全没读 `ctx.subagentId`/`ctx.index`**；`nodeKey`（`:37`）也只拼 `workflowId::nodeId`。后端的 transcript 路由（`web/server.py:180`）同样只接受 `node_id`，**没有按 subagent_id 取单条 transcript 的入口**。
- **为什么是问题**：点击候选项 → `render()` → `fetchTranscript()` 命中 `cache.has(key)`（容器 payload 已缓存）→ 原样重渲染同一张候选列表。**点是空操作**，且后端也没有能力取到单项 transcript。这与已同步到 `openspec/specs/web-ui/spec.md` 的 Scenario 直接冲突：「用户点某一项后 SHALL 能按该项的 `subagent_id` 取到该项自己的 transcript，SHALL NOT 混入同容器其它项的 messages」。design D5.3 也写明「可点进单项」。全仓**无任何测试**覆盖候选项点击（`grep "cand'"` 为空）。
- **附带**：即使补了取数路径，当前缓存键 `workflowId::nodeId` 不含 `subagentId`/`index`，下钻会**覆盖容器那一格缓存**；10s 自动刷新（`scheduleAutoRefresh` 用同一 ctx，`node` 仍是容器节点）会把单项视图**换成候选列表**。
- **建议**：给路由加只读的单项取数能力（如查询参数 `?subagent_id=&run_id=`，仍 bounded、仍只读），或新增 `.../nodes/{node_id}/items/{index}/transcript`；前端缓存键纳入 `subagentId`/`index`，并在单项视图下把刷新 ctx 的 `node` 换成对应项的状态。修复后补浏览器 smoke：点候选项 → 出现该单项的 messages 且不含其它项。

### 低

**#2 ｜ `_reason_fields` 的 `reason_truncated` 恒为 `False`**

- **证据**：`web/session.py:757` —— body 里注释说「布尔标志是唯一正确的判据」，但实现无条件写 `"reason_truncated": False`，而这里返回的是**全文**（`reason_full`），所以恒 `False` 语义上是对的。但既然叫 `_truncated` 且三处 reason 上限口径不同（`_PARENT_FIELD_LIMIT`=200 / 快照 `_SUMMARY_LIMIT`=400 / 路由全文），建议改为按快照上限比较后置位，或在字段注释里写明「对全文出口恒 False」。**不影响当前行为**，纯可维护性。
- 建议：保持现状可接受；若保留字段，补一行 docstring 说明其语义边界。

**#3 ｜ 候选集 `subagent_id` 兜底取值可能跨轮错位（低风险）**

- **证据**：`web/session.py:898`（`_foreach_candidates`）在 run record 拿不到时回落到 `state.subagent_ids[index]`。而设计文档明确指出 `subagent_ids` 是**稀疏数组**（异常项 `continue` 不 append），下标 ≠ item 下标。当前实现用 `index < len(...)` 做边界保护，不会越界，但**语义上仍可能取到别的项的 id**。
- **为什么是问题**：与 M3.3 的设计红线（「`subagent_ids` 只做真实性校验」）有轻微张力——这里把它当**取值来源**用了。
- 建议：兜底只用于「非空校验」，取不到 run record 时 `subagent_id` 直接返回 `None`，让前端显示「该项未派发」，不要拿一个可能错位的 id 冒充。

## 未覆盖

本轮受时间约束（用户指示「~15 分钟内落盘、不再深挖」），以下维度**未逐条核实**，不代表已通过：

1. **M3.6 `trace_digest`**：未逐行核实「最近 N 条 `status != ok` 的 tool_result + llm_error」的 bounded 实现与「`trace is None` 三种成因」的区分是否落地，也未验证对应测试。
2. **4 处既有测试断言的语义变更**：已逐条读到改动**理由**（`test_node_colors_cover_seven_tiers` → 八档 = spec 新增 `skipped` 档；超限改为仍画图 = G14 显式反转 #190 决策 9；点击语义拆分 = 用户 Q2=B 拍板；tab 标签带 `#N` = 用户 Q3=A 拍板）——**均为设计要求的语义变更，非放水**；但其中「超限仍画图」一条对反向行为（`renderMessage + return`）无回归断言，仅断言了新行为。
3. **前端纯函数覆盖度**：`test_workflow_graph_ux_js.py` 41 条未逐条读断言强度（抽样读了图级状态表、刷新节律、progress 形状，均为精确断言）。
4. **`explainNode` 的因果文案正确性**：未逐场景（failed/blocked/budget_exceeded/cancelled）核对文案与 design D2 的措辞表一致。
5. **`items_completed` 的 `M > N` 防护**：已读 `_execute_foreach` 开头清零（`scheduler.py:1591` 附近）与 `_ItemRunSlot` 的 index 守卫（`index >= len(state.item_states)` 时丢弃旧 task），逻辑上成立，但未跑对应变异。
6. **只读路由的越权面**：已确认按内存 session 校验 + workflow 归属校验 + 无写路径 + 不调 LLM（测试 `test_transcript_route_never_touches_the_llm` 用 `mock_llm.calls == []` 断言，是真保护），未做模糊/注入类输入（如 `node_id` 含路径分隔符）的对抗性测试。

## 结论

实现质量高：设计红线（M2.1 计数点、M2.6 `queued` 只投影、M3.3 索引源、契约三条）**逐条实证守住**，关键断言**经变异验证为真保护**，spec 同步与受保护 artifact 事件链完整。唯一需要修的是 **Issue #1**：`foreach` 候选项下钻在前后端**都还没有取数路径**，而该能力已写进正式 spec 并被 design 明确为「可点进单项」——属于「spec 有、实现无」的功能缺口，建议修复并补测试后再合入。

其余为低风险可维护性项，可与本次一并处理，也可另记债务。

---

## Round 2 复审

**复审基线**：`git diff cba2d6c..80304e0`（修复 `4aea153` 7 文件 / +443 −10，加固 `80304e0`）；base 仍 `0272bcb`。

### Issue #1（Round 1 唯一中等项）—— 确认修好

**前后端取数路径已真通**：

- 后端：`web/session.py:873`（`build_node_transcript_payload` 收 `subagent_id`/`run_id`，非空即走 `_item_drilldown_payload`）；`web/session.py:779`（新增 `_item_drilldown_payload`：按容器 `item_runs` 反查 index → 取**该 subagent 自己**的 session transcript，回显 `index`/`task`/`status`/`reason` 全文）；`web/server.py:186,218`（HTTP 路由收 `?subagent_id=&run_id=` 并透传）。
- 前端：`web/static/workflow_transcript.js:63-69`（URL 带 `subagent_id`/`run_id`）。
- **不再依赖容器 payload 缓存命中**：`nodeKey`（`:39`）已纳入 `ctx.subagentId`，下钻与容器各占一格缓存。

**Round 1 指出的两处连带问题均已解决**：
1. 缓存覆盖 —— 见上，`nodeKey` 含 `subagentId`（`:40`）。
2. 10s 刷新把单项视图换回候选列表 —— `scheduleAutoRefresh`（`:164`）改用 `current.itemNode || current.node`，下钻时 ctx 带 `itemNode: {id, status: candidate.status}`（`:256`）；关闭/切回由 `stopAutoRefresh` 与 `parentCtx`（`:258`）承担。另补「← 返回并行项列表」入口（`appendBackLink` `:184`）与「第 N 项：<task>」标识（`renderSingle` `:273`），下钻后既有来路也有身份。

**变异验证（3 处，全部变红 → 真保护）**：

| # | 变异 | 目标测试 | 结果 |
|---|---|---|---|
| G | 前端 URL 还原为不带 `subagent_id`（即 Round 1 的空操作） | `test_foreach_candidate_drilldown_shows_that_item`（浏览器 smoke） | ✅ 变红 |
| H | 后端去掉 `if subagent_id` 下钻分支（回落到容器形态） | `test_workflow_node_transcript.py` 4 条下钻用例 | ✅ 变红 |
| I/J | 下钻**取 item#0 的 session 但回显正确 id**（纯串台，不靠 id 断言兜底） | `test_item_drilldown_does_not_mix_other_items` 等 3 条 | ✅ 变红 |

- 变异 G 直接复现了 Round 1 的缺口（「点了没反应」），是本次修复**真的关掉了那个缺口**的最强证据。
- 变异 I/J 特意保留正确的 `subagent_id` 回显、只让**取数**串台——**旧版** `_does_not_mix_other_items`（断言只落在回显 id 上）**在我这组变异下没有变红**，暴露出该用例的假保护。已按此发现加固（`80304e0`）：新版让 LLM 产出带**每项独有 task 标记**（`render_item_task` 把 item 值渲染进 task，天然带身份），逐项核对取回的 **messages 内容**只含自己的标记、且**不含**别项标记（`tests/web_tests/test_workflow_node_transcript.py`，双向断言）。**复验**：在 `80304e0` 上重跑「永远取第 0 项、但如实回显 id」的变异 → 新版用例**变红**，确认现在是真的保护。
- 该加固仅动测试、未改实现（`web/session.py` 在 `80304e0` 相对 `4aea153` 无改动），故 Round 1 修复的取数路径结论不受影响。

**未引入新的越权面**：`SubAgentManager` 是**每 AgentSession 一份**（`web/session.py:1272`，随 `AgentLoop` 构造注入），`_require_session` 只在该 manager 的 `_sessions` 里查；路由先过 `session_manager.get_session(session_id)`（内存口径 404）。跨 session 的 `subagent_id` 取不到。只读性质未变（不调 LLM / 不写盘 / 不改执行状态，`test_item_drilldown_is_bounded_and_read_only` 用 `manager.llm.calls == 0` 断言，且该测试经变异 H 变红，是真保护）。

### Issue #2（低）—— 处理恰当

`web/session.py:757`（`_reason_fields`）已补语义边界注释：说明本出口给**全文**故 `reason_truncated` 恒 `False`、保留该键是为了让前端不必比长度，并点明三处上限口径（父面 200 / 快照 400 / 路由全文）。与 design D9(e) 一致。

### Issue #3（低）—— 处理恰当

`web/session.py:996`（`_foreach_candidates`）已去掉 `state.subagent_ids[index]` 兜底，取不到 run record 时如实返回 `None`。与 M3.3 红线（`subagent_ids` 只做真实性校验）恢复一致。

### 测试结果（Round 2）

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/web_tests/ -q -p no:randomly`（`80304e0`） | **290 passed, 7 skipped**（84s，无失败） |

较 Round 1 新增 6 条（后端 4 + 浏览器 smoke 1 + 稀疏数组防回归 1）。本轮**未复现**任何 flake，含 `test_workflow_graph_browser.py` 全部浏览器 smoke。

### 本轮新增观察（低，不阻塞）

**#4 ｜ 未派发项的候选行点击仍是软 no-op（低）**：`_foreach_candidates` 去掉兜底后，未派发项的 `subagent_id` 为 `None`；前端点击该行时 `ctx.subagentId` 为空 → URL 不带参数 → 后端回落容器形态 → 重渲染候选列表。**不崩、不串台、无循环**，但用户点「尚未派发」的行看不到任何反馈。spec 该 Scenario 的 GIVEN 限定在「N 个展开项各自独立 subagent」，严格讲未覆盖此态；建议后续给该行 disabled 或提示「该项尚未派发」（可与 §Non-Goals 的节点级 follow-up 一并处理，不必在本 change 内修）。

**#5 ｜ `node_id` 与 `subagent_id` 的归属未交叉校验（低，设计如此）**：路由只校验 session 与 workflow，未强制 `subagent_id` 必须属于 `node_id`。同一 session 内可指名读任一 subagent 的 transcript——与 Chat 视图同信任级（design D4 grill 决策 9 明示「Chat 本已展示这些对话」），**非新增漏洞**，记录备查。

### Round 2 结论

Round 1 的 1 中等 + 2 低**全部按要求闭环**，修复经 3 组变异验证为真保护；审阅过程中发现的串台用例假保护亦已加固并复验为真保护。`80304e0` 上 `tests/web_tests/` 全绿（290 passed / 7 skipped），未引入新的中等以上问题。**Verdict: PASS**。本轮新增的 #4/#5 为低风险观察项，不阻塞合入。
