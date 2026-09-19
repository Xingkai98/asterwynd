# Building Review: workflow-graph-visualization

- reviewer run id: `review-workflow-graph-visualization-20260915-r3`
- 审阅员: 独立零记忆 subagent（review-loop，issue #90）
- base sha: `cb9902c`（与 master 的 merge-base）
- head sha: `d206adf`
- 轮次: 3（R1 → R2 → R3 各含修复与回归测试）
- verdict: **PASS**

## 结论

数据面（`workflow_graph_snapshot` 字段挑选 / 节点七档 / 边五档 / route 控制边 /
per-edge 记账不改 C5 口径）、事件链（manager sink → session forwarder → ws、
重连补发、时间窗合并、Q11 隔离）与 spec delta 对齐**全部通过**，18 项 tasks 真完成、
无假勾选、无冗余实现。

三轮审阅共发现 **4 处缺陷**（3 处前端渲染层 + 1 处后端 C5 契约回归），全部已修复并
补回归测试。前 3 处是「功能写了但实际不生效/画错」类问题——单测与后端测试都覆盖不到，
只有真浏览器点击与跨模块契约核验才暴露。

| 轮次 | 缺陷 | 位置 | 严重度 |
|---|---|---|---|
| R1 | 点击折叠组无法展开（D5 是死功能） | `web/static/workflow.js` | 高（spec 明文要求） |
| R1 | 折叠组聚合状态落在状态词表外 + 显示自己的状态 | `web/static/workflow_graph.js` | 中 |
| R1 | 死导出 `isCollapsibleContainer`/`declarationRejectedNotice` | `web/static/workflow_graph.js` | 低 |
| R3 | `cancel()` 把「只声明未启动」的图变成已运行（破坏 C5 契约） | `agent/subagent/scheduler.py` | 高 |

## 逐条任务验证

全部 18 项，逐项 Read 实现 + 跑对应测试核验，**无假勾选**。

### 0. 设计追问

- [x] **0.1** ✅ `reviews/grill-design.md` 存在，12 条 Confirmed Decisions + Q1–Q11
  全部有 `## User Confirmation` 记录（无占位文本）。checker 的
  `_unconfirmed_open_questions` 校验通过。

### 1. 数据面：workflow 图快照

- [x] **1.1** ✅ `workflow_graph_snapshot()` 在 `scheduler.py:2199-2249`。含完整
  nodes + edges + 每节点/每边 status；基于 `self._plan`（运行期 `ExecutionPlan`，
  含自动插层）。**`_envelope`/`parent_envelope` 与 base 逐字节相同**（见下方专项核验）。
  证据：`tests/agent/subagent/test_workflow_graph_snapshot.py:123-139`。
- [x] **1.2** ✅ 节点七档 = `TERMINAL_NODE_STATUSES` + `started`/`pending`，与
  grill 决策 5 逐条一致（`scheduler.py:105-112` 的 `_SNAPSHOT_TERMINAL_STATUSES`）。
  边五档在 `_edge_status`（`scheduler.py:2274-2305`），优先级链与决策 7 一致。
  route 控制边 `kind: "control"`（`:2231`），只高亮 `targets` 选中出口
  （`:2290-2292`），容忍 `targets` 被 `_reset_subtree` 清空的瞬时态
  （测试 `:286-294`）。`passed` 的 per-edge 记账在**三个消费循环**的
  `_mark_consumed` **旁**新增（`:1876`/`:1916`/`:1941`），`_mark_consumed` 本体
  （`:693-702`）一行未改 → `_consumed_run_ids` 基数逐位不变，
  测试 `:372-380` 断言 `useful_runs == 2` 且 `_consumed_run_ids` 基数 2。
- [x] **1.3** ✅ 显式挑字段：`_graph_node_projection`（`:2251-2272`）不复用
  `NodeState.to_dict()`，排除 `subagent_ids`/`slots`/`raw`/`error`/`verdict`；
  `summary` 截断到 `_SUMMARY_LIMIT=400`；edges 只含 7 个结构字段。
  白名单断言 `SNAPSHOT_NODE_KEYS`/`SNAPSHOT_EDGE_KEYS` 严格（`set(edge) ==` 全等，
  `set(node) <=` 子集 + 显式排除 `subagent_ids`/`slots`/`raw`/`error`/`verdict`）。
  规模测试 `:301-322` 断言 12 项 foreach 展开后快照 < 12000 字符。

### 2. 事件通道：workflow 事件进 WebSocket

- [x] **2.1** ✅ 触发点在 `scheduler.run()` 的 `_record_event("workflow_started")` hook
  之后（`scheduler.py:647-653`），**工具层零改动**（grill 决策 1）。
  `DeclareWorkflow` 只 `register_workflow` 不调 `run()` → 零事件
  （测试 `test_declare_only_scheduler_emits_nothing`）。
- [x] **2.2** ✅ **（R1 修正）** tasks 原文写「经 `AgentLoop.on_event` → session queue
  → ws」，与 grill 决策 1/2/3 推翻的实现不符，**已回写 tasks.md** 为实际链路
  （manager sink → session forwarder → ws）。实现核验：`_emit_graph_snapshot`
  在 `_dispatch`（`:1271`）、`_run_node` 终态（`:1319`）、`run()` 启动/收尾
  （`:652`/`:687`）、`_mark_budget_stop`（`:945`）、`_mark_graph_recursion_exceeded`
  （`:721`）、`cancel()`（`:614`）六处迁移点触发。
- [x] **2.3** ✅ `build_workflow_resume_payloads`（`web/session.py:409-...`）按
  `started` property 过滤 declared，补发「running + 最近 5 张终态」；
  `bind_workflow_graph_channel`（`web/server.py:35-58`）**先补发再 rebind**
  （顺序正确，避免补发期间新帧被旧帧覆盖）。

### 3. 前端：Workflow 视图 + SVG 渲染

- [x] **3.1** ✅ `#workflow-tab`/`#workflow-view` 在 `index.html:19-20`/`:97-105`，
  **不在 debug 门禁内**（`#debug-tab` 仍 `style="display:none"`，workflow tab 用
  `hidden` 属性、由 `showTab()` 在首事件时放行）。`chat.js:261-265`
  `switchToWorkflowView` 由 `workflow_started` 触发自动跳转。
- [x] **3.2** ✅ 零依赖 SVG 自绘（`workflow.js` 无外部库 import）；
  分层布局在 `workflow_graph.js:110-281`；七档颜色 `:18-26`；五档边状态 `:40-47`；
  channel 线型 `:50-55`。**（R1 修复）** 折叠组聚合状态词表见 issue 2。
- [x] **3.3** ✅ route 控制边按 `kind === 'control'` 单独走空心箭头 + 实线
  （`workflow.js:353`/`:364-366`），未选分支由后端给 `inactive`。

### 4. 规模分级

- [x] **4.1** ✅ `<50` 全展开（`collapseGraph` 阈值 50，`workflow_graph.js:360`）；
  `50–200` 折叠 foreach + `__auto_agg__` 前缀（`isAutoNode`）；
  `>200` **不按 `nodes.length` 判断**——`graphNotice` 只看
  `status === 'graph_recursion_exceeded'`（`:521-537`），且超限时**不画图**
  （`workflow.js:226-230` 直接 return）。声明期被拒无 scheduler 无图（Q6 确认不补事件）。
  **（R1 修复）** 点击展开/收起见 issue 1。

### 5. 跨端适配

- [x] **5.1** ✅ `graphOrientation(>720 → horizontal)`（`:304-306`），复用既有
  720/380 断点（`style.css:1481-1484` 只有一个 `max-width: 720px` 覆盖块，未新增
  断点）；safe-area 复用 `env(safe-area-inset-bottom)`（`style.css:1392-1393`）。
  真浏览器验证：`test_workflow_view_desktop_horizontal_layout` /
  `test_workflow_view_mobile_vertical_layout`。
- [x] **5.2** ✅ pointer events + viewBox transform（`workflow.js:451-538`）。
  **（R1/R2 修复）** capture 时机见 issue 1。

### 6. 测试与收尾

- [x] **6.1** ✅ 6 个测试文件覆盖：快照 schema/事件发射/forwarder+重连/服务器链路/
  纯函数 JS/browser smoke。Q11 隔离测试有三层
  （scheduler 层 `test_sink_exception_does_not_break_workflow`、
  forwarder 层 `test_forwarder_swallows_send_errors`、
  端到端 `test_forwarder_does_not_raise_to_scheduler`）。
- [x] **6.2** ✅ benchmark smoke 通过（`--agent fake`：72 tasks / 5 passed /
  38 unsupported / 29 failed，与 fake agent 能力相符，非回归）。
- [x] **6.3** ✅ 兼容回归：`_envelope`/`parent_envelope` 逐字节未变；
  `test_snapshot_does_not_drift_envelope_contract`；
  浏览器 `test_session_without_workflow_is_unaffected`。
- [x] **6.4** ✅ `uv run pytest -q` **2696 passed / 8 skipped**；
  `openspec validate --all --strict` 30 passed / 0 failed；
  artifact checker 除「缺 building-review」外**无其他错误**（本次补上后应通过）。
- [x] **6.5** ✅ spec delta 5 个 ADDED Requirement 已合入
  `openspec/specs/web-ui/spec.md:475-544`，delta 与合入结果逐条比对一致
  （相对 delta 有三处经 Q5/Q10/Q11 确认的口径补强）。

## Issues

### Issue 1（R1 已修复，高）— 点击折叠组无法展开，D5「点击展开局部」是死功能

**现象**：`50–200` 节点图上，点击折叠组长既不展开也不收起，成员永远放不出来。

**根因**（两处叠加，缺一不可）：

1. `web/static/workflow.js:232` 把 `expandedGroups` 传给了 `layoutGraph`——
   而 `layoutGraph`（`workflow_graph.js:185-281`）**根本不消费该选项**；
   真正消费它的 `collapseGraph` 没收到 → 展开状态对折叠决策不可见。
2. `web/static/workflow.js:458` 在 `pointerdown` 立刻 `host.setPointerCapture()`。
   pointer capture 会把随后的 `click` 一并重定向到 host，节点 `<g>` 上的
   click 处理器**永远收不到**。实测：合成 `dispatchEvent(new MouseEvent('click'))`
   能触发（合成事件不走 capture 路径），真实鼠标点击不能——所以只看合成事件的
   测试会漏掉这个 bug。

**修复**（`web/static/workflow.js`）：

- 把 `expandedGroups` 改传给 `collapseGraph`，`layoutGraph` 只收 `orientation`。
- capture 推迟到指针位移超过 `TAP_SLOP`（4px）、确定是拖动而非点击时。
- 引入 `groupLeader` 标记（`workflow_graph.js` 的 `collapseGraph` 输出 + 
  `layoutGraph` 透传），渲染层按它判可点击——若按 `collapsed` 判，展开后标志消失，
  折叠组会变成**单向**操作（能展开、不能收起）。

**回归测试**：
- `test_collapsed_group_click_expands_members`（真鼠标点击，展开 + 收起双向）
- `test_group_leader_flag_survives_expansion`
- `test_layout_projection_carries_group_leader`

### Issue 2（R1 已修复，中）— 折叠组聚合状态落在节点状态词表外，且显示组长自己的状态

**问题 A**：`groupStatus` 返回 D5 口语里的 `"running"`，但 `NODE_COLORS`
（`workflow_graph.js:18-26`）的键是 `"started"` → `nodeColor("running")` 落到兜底灰
（`:64-66`），折叠组长画成灰色而非蓝色。测试只断言了字符串相等，没断言可渲染。

**问题 B**：`collapseGraph` 折叠时写 `status: node.status`——组长的**自己**状态，
不是 D5 要求的**整组**聚合状态（`workflow_graph.js:489-494`）。

**修复**：`groupStatus` 返回 `"started"`；折叠时 `status: group.status`；
去掉从不被读取的冗余 `groupStatus` 键。

**回归测试**：`test_collapsed_group_shows_aggregated_status`（浏览器，断言组长
`data-status == "failed"` 且描边 `#f87171`）、`test_collapsed_leader_carries_group_status`
（含「聚合结果必须落在 `nodeColors()` 键集内」断言）、`test_collapse_group_aggregates_status`
（扩展为遍历多种组合断言词表内）。

### Issue 3（R3 已修复，高）— `cancel()` 把「只声明未启动」的图变成已运行，破坏 C5 契约

**位置**：`agent/subagent/scheduler.py:606`（本 change 新增行）。

**根因**：本 change 给 `cancel()` 加了 `self._status = "cancelled"`。而 `started`
property 就是 `self._status != "declared"`（`:445-449`），且 C5 的
`benchmarks/workflow_replay.py:61-71` `_started()` 与
`benchmarks/agent_runner.py:704-716` `_first_started_scheduler()` 都拿它当
「这张图是否真跑过」的判据。

**后果**（实测复现）：模型只 `DeclareWorkflow` 一张图（`subagents.py:475-499`，
`register_workflow` 不调 `run()`），随后 `CancelWorkflow` 取消它。父 run 结束时
C5 的 `collect_workflow_records` 会凭空多采一条 record——
`collection_status` 从 `no_workflow` 变成 `ok`，record 的 `observed` 指标全是
空跑产物，污染 benchmark report 与 `dynamic-replay`。

`declared → cancelled` 这条路径在**本 change 之前**是安全的（`cancel()` 不碰
`_status`），是本 change 引入的回归。

**修复**：仅当 `_status != "declared"` 时才落 `cancelled` 并推快照。
`StartWorkflow` 复用 `DeclareWorkflow` 注册的同一个 scheduler（`subagents.py:530-542`），
真跑过的图不受影响；从未开跑的图本来也没有快照可发。

**回归测试**：
- `test_cancel_on_declared_only_scheduler_keeps_declared`（scheduler 层：断言
  `started is False` + 零事件）
- `test_cancelled_declared_workflow_is_not_collected`（**C5 采集层**，锁住真实后果）
- 同步修正两条既有测试的前提（它们直接调 `cancel()` 而未先置 `running`）。

### Issue 4（R1 已修复，低）— 死代码

`web/static/workflow_graph.js` 导出 `isCollapsibleContainer` 与
`declarationRejectedNotice`，全仓零引用。后者对应 Q6 已明确**不做**的
「声明期被拒补 workflow 事件」路径，留着会误导实现者以为该路径存在。已删除。

## 专项核验（building agent 自报项）

| 关注点 | 结论 |
|---|---|
| **tasks 2.2 描述偏差** | 确认偏差属实。已**回写 tasks.md**（不只记录）：原文链路与 grill 决策 1/2/3 冲突，留着会让后续读者按错误链路理解。 |
| **`_consumed_edges` 不清理** | **安全，已补测试**。`run()` 开头（`scheduler.py:641-642`）与 `_consumed_run_ids` **成对重置**，cancel 后重跑的残留不会带进下一张图。新增 `test_consumed_edges_share_run_scope_lifecycle` 锁定。 |
| **building 阶段已写 `workflow-events.jsonl`（1 行）** | **格式规范，无「假通过」风险**。该行是 `current_spec_synced` + `artifact_path: openspec/specs/web-ui/spec.md`，字段集（`schema`/`seq`/`event_type`/`change_id`/`artifact_path`/`reason`/`approved_by`）与 C3/C4/C5 归档件逐字段同构，`approved_by: "human"` 与全仓 15 条既有 `current_spec_synced` 一致。**不会掩盖 closing 该补的事件**：checker 的 `_event_covers_artifact_path` 是「路径精确/前缀匹配」，只覆盖 `openspec/specs/web-ui/spec.md` 一条；closing 阶段仍需为 `docs/openspec-change-backlog.md`（`backlog_updated`）和归档目录（`change_archived`）各补一条——这两条本次 diff **未**覆盖，checker 会如实报缺。时序上确实早于惯例（C3–C5 都在 closing 提交里写），但不构成门禁规避。 |
| **`test_multi_tab_slash_suggestion_isolation` 偶发超时** | **与本 change 无关，既有 flake**。在 **base commit `61ad62c`**（本 change 之前）用同一 venv 跑 5 次复现 1 次失败（3.6s 通过 / 34s 超时），失败模式与本 change 分支一致。该测试走 `hub-session-open` → 新建 tab → slash 建议，不经过任何 workflow 代码路径。建议另立债务 issue，不在本 change 处理。 |
| **快照字段白名单严格性** | ✅ 严格。`_envelope`/`parent_envelope` 与 base **逐字节相同**（脚本比对确认 IDENTICAL，本 change 一行未改）；快照键集用 `set(edge) == SNAPSHOT_EDGE_KEYS`（全等）与 `set(node) <= SNAPSHOT_NODE_KEYS`（子集 + 5 个显式 `not in` 排除）+ 顶层 `set(snapshot) <= {...}`。 |

## 安全性

- 快照无路径逃逸：`workflow_graph_snapshot()` 只读内存态（`_plan`/`_states`），
  不落盘、不拼路径；`result_ref` 相关逻辑本 change 未触碰。
- 无模型代码执行：route 判定与折叠归类都是纯数据映射，`workflow_graph.js` 无
  `eval`/`Function`/`innerHTML`（DOM 文本一律走 `textContent`）。
- **事件推送失败隔离（Q11）三层齐备**：scheduler 侧 `_emit_graph_event` 包
  `try/except Exception: pass`（`scheduler.py:553-570`，注释明写「调用 sink 永不抛」
  并指出漏出会被 `_run_node` 的 `except Exception` 吞成节点 failed）；forwarder 侧
  `__call__`/`_send_now`/`_swallow` 三处吞；重连补发 `web/server.py:52-56` 也吞。
  端到端测试验证 ws 断开时 workflow 仍 `completed`。

## 冗余度 / 可维护性

- 无重复实现：`workflow_graph.js`（纯函数，可 node 单测）与 `workflow.js`
  （DOM 渲染）分层清晰，纯函数层零 DOM 依赖（`vm.createContext({window: {}})` 可跑），
  符合 spec「分层布局、状态映射与折叠归类 SHALL 与 DOM 解耦」。
- 删除了 2 个死导出（Issue 4）；其余导出均被测试或渲染层消费。
- 注释密度与既有代码一致，关键约束（Q11 隔离、决策 11「旁新增」、
  capture 时机）都有「为什么」而非「做什么」的说明。

## CI 完整性

- `.github/workflows/ci.yml:44-46` 新增 `uv run playwright install --with-deps chromium`，
  位置在 `Install dependencies` 之后、`Run tests` 之前，顺序正确。
  本地装 chromium 后 `test_workflow_graph_browser.py` 10 条**真跑**（非 skip），
  证明该步骤有效。`--with-deps` 在 ubuntu-latest 上正确（会装系统依赖）。
- `validate`/`benchmark-gate` 两个 required check 保持不动；`pytest -q` 全绿。

## 验证命令与结果（最终）

```
$ uv run pytest -q
2696 passed, 8 skipped, 19 warnings in 191.56s

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)

$ PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py --base-ref master
（补上本报告与 manifest 后 → 通过；此前仅报 building-review.md missing）

$ uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-final
Tasks: 72 | passed: 5 | warnings: 0 | unsupported: 38 | failed: 29
```

## 封印

3 轮封顶内收敛，最终 verdict = **PASS**。
