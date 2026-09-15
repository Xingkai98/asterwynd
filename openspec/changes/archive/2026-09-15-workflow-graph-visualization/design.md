# Design: 多 Agent 运行态流程图可视化

## Context

C1–C5 已交付 subagent 编排的完整能力，但前端看不到 workflow 拓扑与实时状态。本 change 落地 codex 架构评审的 7 个决策（D1–D7），把运行态 workflow 图可视化到 Web UI（桌面/手机两端）。依赖 C2 的运行期图数据（`ExecutionPlan`）+ C5 的观测口径。

## Goals / Non-Goals

**Goals**

1. 模型触发 `StartWorkflow`/`RunWorkflow` 时，页面自动出现流程图界面。
2. 显示所有节点，每节点按状态高亮（七档）。
3. 显示整张图的流向，边按状态高亮（五档），route 控制边单列。
4. 桌面/手机两端适配（横向/纵向 DAG + 缩放平移）。
5. 断线重连后恢复当前图快照。

**Non-Goals**

- 不做「web 端编排画布」（拖拽设计拓扑）——G7 #178 已排除，本 change 是观测面非设计面。
- 不做力导向布局（DAG 上下游方向比自由聚类更重要）。
- 不做动画过渡（状态切换直接重绘）。
- 不做图历史回放（快照是当前态，历史归后续）。

## Decisions

### D1 — 渲染：轻量 SVG 自绘（零依赖）

前端纯 vanilla JS（`web/static/index.html:109-111` 只加载 chat.js/debug.js/markdown.js，无图库）。自绘 SVG 表达 4 种节点 + 边 channel/required/reducer 语义 + 实时高亮最可控，几十~200 节点够用。**确定性分层布局**（DAG 层级），不用力导向。

### D2 — 通道：复用 WebSocket

`/ws/{session_id}` 已是运行态事件通道（`agent/loop.py:948-970` → `web/session.py:672-677` 原样转发），前端有统一 `handleEvent`（`web/static/chat.js:414-570`）。新增 `workflow_started` / `workflow_snapshot` 事件，不引入第二套传输。**不放 debug 门禁**（debug 受 `debug_enabled()` 约束，流程图是用户态能力）。

### D3 — 数据面：独立 `workflow_graph_snapshot()`，不动父 Agent envelope

`_envelope`（scheduler.py:2115-2139）只序列化 nodes 不序列化 edges，`parent_envelope`（:2195-2217）还裁剪节点摘要并限 200 节点——这是 C1–C5 的父 Agent 契约，**不能塞 edges 污染它**。新增面向 Web UI 的专用快照，基于运行期 `ExecutionPlan`（`self._graph()`，scheduler.py:488-491）生成完整图：

```json
{
  "type": "workflow_snapshot",
  "data": {
    "workflow_id": "wf_xxx",
    "status": "running",
    "spec_hash": "...",
    "nodes": [{"id": "research", "kind": "subagent", "status": "started", "runs": 1, "summary": "...", "started_at": 0, "finished_at": null}],
    "edges": [{"from": "research", "to": "aggregate", "channel": "summary", "required": true, "reducer": "concat", "kind": "data", "status": "active"}]
  }
}
```

**快照字段选取（grill 决策 4；meta-review 修正）**：快照**不得**直接 `NodeState.to_dict()` 直出——`to_dict()` 缺 `started_at`/`finished_at`（`NodeState` 有这两个字段，`scheduler.py:152-153`，`to_dict` 未输出），且带 `subagent_ids`（foreach 展开每项一个 id，随图规模线性膨胀）与 `slots`（concat 后的巨型字符串）。`workflow_graph_snapshot()` 必须**显式挑字段**。上面的示例是示意形状，字段以「显式挑选 + bounded」为准，不以上面这份 JSON 的键集为完整契约。

**节点颜色七档**（与 scheduler 终态集合对齐，`budget_exceeded` 是独立终态不能并入 blocked）：

| status | 颜色 | 语义 |
|---|---|---|
| pending | #94a3b8 灰 | 未满足依赖/未派发 |
| started | #60a5fa 蓝 | 正在运行 |
| completed | #4ade80 绿 | 成功完成 |
| failed | #f87171 红 | 执行失败 |
| cancelled | #64748b 深灰 | 被取消 |
| blocked | #facc15 黄 | 上游/流程条件无法继续 |
| budget_exceeded | #fb923c 橙 | 被预算闸门阻止 |

**边状态五档**：`inactive`（无可传播结果）/ `ready`（上游完成）/ `active`（源或目标在跑）/ `passed`（数据被下游消费）/ `blocked`（目标因上游失败/取消/预算/控制无法继续）。

**route 控制边单列**：route 出边不传数据不参与 reducer（workflow.py:243-260），标 `kind: "control"`，只高亮 `targets` 中实际选中的出口，未选分支保持 inactive。channel 只决定线型：summary/result_ref 实线、artifact 虚线、bus 点线。

### D4 — 触发：scheduler 启动 hook + 节点迁移处（meta-review 修正）

> **修正说明**：本节原写「触发点是 `StartWorkflowTool`/`RunWorkflowTool` 的启动点」，与代码事实冲突——工具类只持有 `SubAgentManager`（构造点 `agent/loop.py:394-401`），拿不到 session 的事件 sink，工具层一行都发不出事件。正确触发点是 `scheduler.run()` 里**已有的** `_record_event("workflow_started", status="running")`（`agent/subagent/scheduler.py:581`）。详见 `reviews/grill-design.md` 决策 1/2。

`DeclareWorkflow` 只注册不启动（subagents.py:475-499），不能当触发点；`run()` 的启动 hook 天然满足「Declare 不发、Start/Run 才发」（`DeclareWorkflow` 只 `register_workflow` 不调 `run()`），工具层无需改动。副作用：`run_pattern()` 也直接调 `scheduler.run()`（patterns.py:434）→ pattern 也会触发图（见 grill Q3）。

工具层拿不到 sink，所以必须在 scheduler 启动时由 web 层注入一个 **manager 级 sink**（形态见 grill Q1）。节点更新不能靠解析 `tool_result`（`wait=true` 要等整图结束才返回）。低延迟 hook 是 scheduler 的 `_dispatch`（节点置 started，:1128-1193）、`_run_node` 终态（:1196-1240）、route 选择、取消、预算停止——这些点发 `workflow_snapshot`。优先发完整快照（可重放），不发局部 patch。

**数据流**：`scheduler.run()` 启动 hook → manager 级 sink → session 级 sender → WebSocket → 前端自动开 Workflow 视图；scheduler 迁移 → `workflow_snapshot` → 同链路。

**重连恢复**：ws 重连后，服务端从 manager 的 workflow 注册表（`get_workflow`/`list_workflows`，manager.py:406-413/556-565）查当前已启动 workflow，补发当前快照。注意注册表**从不删除**条目且含 `declared` 态图，补发必须按 `started` property 过滤（`scheduler.py:419-426`）。

### D5 — 规模：200 节点上限，分级折叠

对齐后端 `max_nodes=200`（workflow.py:34-37）。运行期权威图是 `ExecutionPlan`（含自动插层 + foreach 展开）。

- `<50`：默认全展开。
- `50–200`：仍渲染完整图，但默认折叠 foreach 展开项、自动插入聚合层、重复结构；折叠组显示 `N items`/完成数/失败数，点击展开局部。
- `>200`：**（meta-review 修正）**`max_nodes` 是双闸——声明期 `len(nodes) > max_nodes` 直接抛 `WorkflowValidationError`（`workflow.py:369-371`，此时连 scheduler 都没创建、无图可发）；运行期自动插层后复检抛 `GraphRecursionError` 并被收敛成 `status = "graph_recursion_exceeded"`（`scheduler.py:636-645`、`655-666`）。因此**不存在「前端拿到一张 >200 节点的图再显示超限」这条路**：要么图存在且 ≤ 200 节点，要么整图被拒。前端要处理的是「`data.status == "graph_recursion_exceeded"` + `data.diagnostics`」的渲染分支，不是靠 `nodes.length > 200` 判断。折叠组的展开项也**不是** `NodeState`（只体现在容器节点的 `items`/`subagent_ids` 上），折叠组按 `kind == "foreach"` 与 `__auto_agg__` 前缀识别（`aggregation.py:40`）。

折叠是**视觉投影**，不改快照节点身份和状态。折叠组聚合状态：组内任一 failed→failed，否则任一 started→running，否则任一 pending/blocked/budget_exceeded→受阻，全 completed→completed。

### D6 — 推进：OpenSpec 全套

新能力面（WS 协议 + scheduler 观测接口 + 前端视图三层联动），走 propose→grill→独立 worktree→TDD→review-loop→archive。

### D7 — 跨端：桌面横向 DAG + 手机纵向 DAG

- **桌面**（>720px）：横向 DAG（左→右）。
- **手机/平板**（≤720px）：纵向 DAG（根在上→叶在下），同一份分层数据只换坐标轴方向；自动 fit 到屏宽。
- **手势**：首版只做 pinch 缩放 + pan 平移（pointer events + SVG viewBox transform），不做 swipe。
- **断点**：复用现有 720（主断点）+ 380（窄屏微调），不加新断点。
- **safe-area**：复用 `env(safe-area-inset-bottom)` 给图底部留安全区。

## Pre-Implementation Review

> 本 change 为架构级改造（WS 事件协议 + scheduler 观测接口 + 前端视图），实现前需按 AGENTS.md 走 `batch-grill-me`（或等价独立 subagent 设计追问）审视本 design.md 的 D1–D7，逐项确认实现细节、依赖、风险与测试策略，产出结构化决策记录到 `reviews/grill-design.md`，并经停轮确认（grill-confirmation-gate）。本节为占位声明，实际 review 记录以 `reviews/grill-design.md` 为准。

## Risks / Trade-offs

- **风险**:事件丢失导致前端图状态陈旧 → 快照完整可重放 + 重连恢复；**（meta-review 修正）**`web/session.py:547` 的 `asyncio.Queue()` **无 maxsize**，是**无界队列**——真实风险不是「队列有界丢事件」，而是**事件堆积 + 无节流重绘**（一张 50 节点图约 150 次推送、3–4 MB 出流量），靠 session 级 sender 的时间窗合并（grill Q4）兜底，靠重连补发完整快照修复陈旧态。
- **风险**:上百节点 SVG 重绘性能 → 分级折叠 + 局部重绘；首版不做动画过渡。
- **风险**:快照数据量打爆 ws → 快照 bounded（节点 summary 截断、edges 只含结构字段），对齐 parent_envelope 的 200 节点口径。
- **Trade-off**:自绘 SVG 要自己实现布局/避让/缩放 → 换可控性与零依赖。
- **Trade-off**:route 控制边单列让语义更准确 → 增加边状态推导逻辑。

## Testing Strategy

- snapshot schema：nodes/edges 结构 + 节点七档状态 + 边五档状态 + route 控制边 kind。
- 节点/边状态映射：每种 status → 颜色/线型正确。
- 启动事件：`scheduler.run()` 启动 hook 发 workflow_started，`DeclareWorkflow`（只注册不调 `run()`）不发。
- 重连恢复：ws 重连后补发当前快照（按 `started` property 过滤掉仅 Declare 的图）。
- 故障隔离：快照推送失败（ws 已断）**不得**影响 workflow 执行状态（grill Q11）。
- 兼容回归：`workflow_graph_snapshot()` 的字段挑选不改变 `_consumed_run_ids` 基数（grill 决策 12）。
- 前端：事件分发 + SVG 渲染 + 折叠组 + 跨端布局（横向/纵向 DAG）。
- 规模：<50 / 50-200 / >200 三档行为。
- 全量 pytest 绿 + OpenSpec validate + artifact checker。
