# Tasks: Workflow 流程图可视化体验增强

## 0. 设计追问（实现前门禁）

- [ ] 0.1 跑 `batch-grill-me`（或等价独立零记忆 subagent 设计追问）审视 design.md D1–D7，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）。

## 0b. 后端语义适配（D2b，用户裁决纳入）

- [ ] 0b.1 `TERMINAL_NODE_STATUSES` 加 `skipped`；`_teardown` 的 `pending` 分支加判据：节点只被 route 控制边门控且 `activations <= 0` → `skipped`；同时满足「被上游连累」→ 优先 `blocked`。预算路径下同样适用（route 没选它跟预算无关）。
- [ ] 0b.2 `_unit_counts` 加独立 `skipped_units` 桶（**不得落进 `pending_units`**）；回归「图终态时 pending_units 为 0」。
- [ ] 0b.3 `_route_verdict` 读上游产出处**旁加** per-edge 记账（`_consumed_edges.add((edge.source, edge.target))`，`_mark_consumed` 本体不改）；回归 C5 `useful_runs`/`redundancy` 逐位不变。
- [ ] 0b.4 回归测试：route 未选中分支记 `skipped`（用 `_route_spec()` 实跑，断言 `no` 节点 status 为 `skipped` 且 `a→gate` 边为 `passed`）；「被上游连累」优先于「未选中」的对照用例。
- [ ] 0b.5 契约影响：确认 `NodeState.to_dict()` 直出 status 无需改码，但 `_envelope` 消费方（benchmark 报告 / `GetWorkflow`）容忍新值；docstring/spec 说明。

## 1. 数据面：快照加法字段（前端增强优先，后端只补图上看不到的）

- [ ] 1.1 `agent/subagent/scheduler.py::_graph_node_projection` 补 `reason`（**必须在投影层截断到 `_SUMMARY_LIMIT`**，与 `summary` 同口径；`state.reason` 本体不改——它是 `_envelope` 字段；截断额度见 grill Q4）。
- [ ] 1.2 `workflow_graph_snapshot()` 图级补 `started_at`/`finished_at`——**哨兵统一成 `null`**：`started_at: (self._started_at or None)`（`declared` 态是 `0.0` 哨兵）、`finished_at: self._finished_at`（运行中 `None`）；**不要**复用 `_envelope` 的 `or time.time()` 口径。
- [ ] 1.3 `NodeState` 新增 `items_completed`/`items_failed`，在 `_run_foreach_item` 的 gather 结果循环里**旁加**自增（失败口径与既有 `failures` 对齐：异常 envelope 与 `status != "completed"` 都算失败）；**同时在 `_execute_foreach` 开头随 `items`/`subagent_ids`/`run_ids` 一起清零**（否则 route 回边重跑累加出 `M > N`）；`CancelledError` 提前 return 时计数停在部分值（前端容忍 `M < N`）。`_graph_node_projection` 只对 foreach / `__auto_agg__` 节点输出。
- [ ] 1.4 更新 `tests/agent/subagent/test_workflow_graph_snapshot.py`：节点白名单 `SNAPSHOT_NODE_KEYS`（模块级 frozenset，`:34-36`）+ **图级内联白名单字面量**（`:173-176`），**保留**排除断言（`subagent_ids`/`slots`/`raw`/`error`/`bus`/`attribution`）与「`_envelope`/`parent_envelope` 逐字节不变」回归。

## 2. 后端：只读 transcript 路由

- [ ] 2.1 `web/session.py` 新增「按 `(workflow_id, node_id)` **收集候选集**」的解析（遍历 `_sessions` 匹配 `SubagentSessionRecord.workflow_id`/`node_id`；键在 foreach 容器上一对多），复用 `SubAgentManager.inspect_transcript()`。**注意**：必须显式传 `scope="recent_messages"` + `limit`（`summary` 分支无 `messages` 键）；`inspect_transcript` **不按 run_id 过滤、不截断单条内容**，单条截断要在路由层自己做；`KeyError`（`_require_session`）要转结构化响应。
- [ ] 2.2 `web/server.py` 新增只读路由 `GET /api/sessions/{session_id}/workflows/{workflow_id}/nodes/{node_id}/transcript`（bounded：条数上限 200 + **路由层**单条长度上限 + `include_tool_results` 默认 false；**不调 LLM、不写盘、不改执行状态**）。session 校验用 `session_manager.get_session()`（内存口径，冷会话 404，与 `/timeline` 同）。
- [ ] 2.3 边界语义（候选集规则）：0 条候选 → 未派发（`subagent_id: null` + 说明）；1 条 → 直接给该条 transcript（含 N=1 的 foreach）；N>1 条 → 结构化「容器，附 N 个候选（`subagent_id`/`status`/`summary`）」（形态见 grill Q1）；未知 node/session → 404。
- [ ] 2.4 测试：正常 / foreach 容器 / 未派发节点 / 未知 node 404 / 未知 session 404 / bounded。

## 3. 前端纯函数层（`workflow_graph.js`，node + vm 单测）

- [ ] 3.1 `legendModel()`：从 `NODE_COLORS`/`EDGE_STYLES`/`KIND_GLYPHS`/`NODE_LABELS` **同源生成**图例内容（节点类型 + 7 档状态 + 5 档边状态 + channel 线型），每条目带人话解释；单测断言 7 档状态全覆盖。
- [ ] 3.2 `explainNode(node, edges, nodesById)`：failed / blocked（有失败上游 / 无失败上游）/ budget_exceeded / cancelled 的因果句；**回归「12 文件 foreach 超预算」场景**（3 failed + 2 blocked + 1 budget_exceeded）。
- [ ] 3.3 异常态编码表（八档）：状态 → 形状/角标（`failed` ✕ / `blocked` ⊘ 虚边框 / `budget_exceeded` ‖ 双边框 / `cancelled` ⊝ / **`skipped` — 冷灰蓝+虚边框**）；**角标字形只用默认字体普遍覆盖的字符**（`⏸` U+23F8 实测渲染成豆腐块，已改 `‖`）。
- [ ] 3.4 并行边等距偏移：在 `layoutGraph` 的 `layoutEdges` 里**先按 `(from,to)` 分组**（`edgePath` 拿不到 multiplicity），把 `{index,total}`/`offset` 作为**可选参数**传进 `edgePath`（保持导出 API 兼容）；`offset = (k - (n-1)/2) * DELTA`，横向偏 y / 纵向偏 x；n 超上限退化为聚合标注。单测「3 条边路径互不相同且有限」。
- [ ] 3.5 边统计口径：报**实际绘制路径数**（`collapsed.edges.length`）+ 原始边数（`snapshot.edges.length`）；**两数相等时不加解释后缀**（<50 节点未折叠时边原样透传，去重不发生），不等时才给可解释口径。
- [ ] 3.6 tab 元信息格式化：`#序号 · 相对时间 · 耗时 · M/N`，运行中/终态两分支 + 运行中排最前。
- [ ] 3.7 foreach 计数与迷你堆叠条的数据模型（`M/N 完成`、`· 失败 K`、N 大时退化）。

## 4. 前端渲染层（`workflow.js` + `index.html` + `style.css`）

- [ ] 4.1 图例条 `#workflow-legend`（桌面默认展开 / 手机默认折叠为 `图例 ▾`，同一 DOM 切 class）；`index.html` + `style.css`。
- [ ] 4.2 节点渲染升级：异常态角标 + 虚/双边框 + 加粗状态词 + `why` 小字（仅异常态占位）。
- [ ] 4.3 **点击语义拆分**：点节点 = 开详情面板；折叠组展开/收起挪到独立小控件（形态见 grill Q2）。**同步更新浏览器 smoke** `tests/web_tests/test_workflow_graph_browser.py:343-369`（`test_collapsed_group_click_expands_members`，现靠点节点展开）+ `web/static/style.css:1482` 的 cursor 口径（普通节点也要可点）。**注意**：`tests/web_tests/test_workflow_graph_js.py` 是纯函数单测，无 click 用例，不需要改。
- [ ] 4.4 详情抽屉（桌面右侧 / 手机底部，同一 DOM 切 class）+ 分 Tab（任务 / 产出 / 对话）+ `role="dialog"`/`aria-modal`/focus trap/Esc/遮罩关闭；抽屉开合**不改 viewBox**。
- [ ] 4.5 「对话」tab transcript 懒加载 + **仅 UI 虚拟化**（50 行聚簇、按簇增删 DOM、单条截断）；实时刷新时 transcript 不重排（暂停按钮）。
- [ ] 4.6 多图 tab 渲染升级：`#序号 · 相对时间 · 耗时 · M/N` + 最差状态色点 + `title` 补全 goal；运行中排最前。
- [ ] 4.7 foreach 容器计数行 + 迷你堆叠条渲染（常显，不再只在折叠时显示）。
- [ ] 4.8 `<svg:title>` 在移动端失效的修复：节点/边信息并入详情面板 + 自绘 tooltip（不再单靠 `<svg:title>`）。

## 5. 跨端与配色

- [ ] 5.1 图例条 / 抽屉 / 计数行在 720 断点两侧行为验证（桌面横向、手机纵向）。
- [ ] 5.2 节点配色拉开**明度**差（`blocked`/`budget_exceeded`/`pending` 转灰度可辨），Chrome DevTools deuteranopia 模拟目视验证并记录到 building review。

## 6. 测试与收尾

- [ ] 6.1 前端 node+vm 单测覆盖 tasks 3.1–3.7；浏览器 smoke（Playwright）覆盖图例可见可折叠、点节点开抽屉、切「对话」tab 触发请求、折叠组独立控件展开。
- [ ] 6.2 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过（本 change 触及 observability/快照链）。
- [ ] 6.3 兼容回归：既有无 workflow 会话前端不崩；`test_workflow_graph_js.py` 既有用例（含点击语义）继续绿；`_envelope`/`parent_envelope` 结构不变。
- [ ] 6.4 `uv run pytest -q` 全绿；OpenSpec validate + project artifact checker 通过。
- [ ] 6.5 同步 current spec：把 spec delta（含快照加法字段的 MODIFIED Requirement）合入 `openspec/specs/web-ui/spec.md`。
- [ ] 6.6 文档影响检查：`docs/openspec-change-backlog.md`、`docs/architecture.md`（若有图视图描述）、`docs/development-guide.md`（若新增路由需记）。
