# Proposal: 多 Agent 运行态流程图可视化（workflow-graph-visualization）

关联跟踪 issue：[#189](https://github.com/Xingkai98/asterwynd/issues/189)。依赖 C2（Workflow DSL 调度器，spec 可哈希 + 运行期图数据）+ C5（workflow 报告字段/观测面）。

## Change Type

- primary: feature
- secondary:
  - web-ui
  - observability
  - subagent

## Why

C1–C5「subagent 编排自由度」系列已合入，模型现在能自由声明几十~上百个 subagent 的协作拓扑（Workflow DSL，4 种节点 subagent/aggregate/route/foreach + 边）。但**前端完全看不到这张图**——用户无法观察多 Agent 的运营流程：哪些节点在跑、哪些完成、哪些排队、流向走到了哪。

这是一个真实的能力缺口（不是锦上添花）：后端有完整的运行期图数据（`ExecutionPlan` 的 nodes/edges + `NodeState` 的 status），但 `_envelope` 只序列化了 nodes 没序列化 edges，且 WebSocket 事件类型里没有任何 workflow 事件——前端既拿不到图结构、也拿不到实时状态。

本 change 落地 codex 架构评审的 7 个决策（D1–D7）：当模型触发 `StartWorkflow`/`RunWorkflow` 时，页面自动多出一个流程图界面，显示所有节点 + 每节点状态高亮（七档）+ 流向高亮（数据边 + route 控制边），桌面/手机两端适配。

## What Changes

- **数据面**：scheduler 新增独立 `workflow_graph_snapshot()` 方法（完整 nodes + edges + 每节点 status + 每边 status），**不动**现有 `_envelope`/`parent_envelope` 的父 Agent 数据契约。
- **事件通道**：WebSocket 新增 `workflow_started` / `workflow_snapshot` 事件；scheduler 在节点状态迁移处经 `on_event` 链路推快照。
- **触发**：**（meta-review 修正）** `workflow_started` 的触发点是 `scheduler.run()` 启动 hook（`agent/subagent/scheduler.py:581` 已有的 `_record_event("workflow_started")` 处新增 sink 调用），**不是**工具层——`StartWorkflowTool`/`RunWorkflowTool` 只持有 `SubAgentManager`，拿不到 session 事件 sink；`DeclareWorkflow` 只注册不调 `run()`，天然不触发。
- **前端**：Chat 旁新增用户态 Workflow 视图（不放 debug 门禁内），零依赖 SVG 自绘，DAG 分层布局。
- **节点高亮**：pending 灰 / started 蓝 / completed 绿 / failed 红 / cancelled 深灰 / blocked 黄 / budget_exceeded 橙（与 scheduler 终态集合对齐）。
- **边高亮**：边状态五档（inactive/ready/active/passed/blocked）；route 控制边单列（只高亮 `targets` 中实际选中的出口）；channel 用线型区分（summary/result_ref 实线、artifact 虚线、bus 点线）。
- **规模**：<50 全展开，50–200 折叠 foreach/自动插层（折叠是视觉投影不改状态语义）；**（meta-review 修正）** `max_nodes` 超限分两条路径——声明期抛 `WorkflowValidationError`（无 scheduler、无图），运行期收敛为 `graph_recursion_exceeded` + `diagnostics`，前端不靠 `nodes.length` 判断。
- **跨端**：桌面横向 DAG（左→右）+ 手机纵向 DAG（上→下），pinch 缩放 + pan 平移，复用 720/380 断点 + safe-area。

## Capabilities

### New Capabilities

无新能力域；在既有 `web-ui` + `observability` 能力域上深化。

### Modified Capabilities

- `web-ui`: 从「Sessions/Chat/Debug 三 tab」演进为「新增 Workflow 运行态流程图视图」。
- `observability`: 从「Session Timeline / trace」演进为「workflow 图级运行态可视化（节点/边状态快照）」。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 架构级改造（WS 事件协议 + scheduler 观测接口 + 前端视图三层联动），走 grill 的非平凡 change，命中 `full` 判据。
- research questions:
  1. 业界 coding agent 的多 Agent 运行态可视化怎么展示（Claude Code / Codex / LangGraph Studio / LangSmith）？
  2. 节点/边状态高亮的语义怎么定（区分数据流 vs 控制流）？
  3. 跨端（桌面/手机）的 DAG 布局怎么做？
- findings: 见 codex 架构评审（agent `e75b86f3`）核实结论——
  - **数据源**：运行期权威图是 `ExecutionPlan`（含自动插层 + foreach 展开），不是原始 spec（`agent/subagent/scheduler.py:559-564`）；`WorkflowSpec.to_dict()` 已能序列化 nodes+edges（`agent/subagent/workflow.py:270-285`）。
  - **事件链路**：`AgentLoop.on_event` → session queue → WebSocket 原样转发（`agent/loop.py:948-970`、`web/session.py:672-677`），新增 workflow 事件不需第二套传输。
  - **触发点**：`StartWorkflowTool`/`RunWorkflowTool` 在 `wait=false` 时直接创建后台 scheduler 任务（`agent/tools/builtin/subagents.py:530-542`/`:755-772`），`DeclareWorkflow` 只注册不启动（`:475-499`）。**（meta-review 修正）** 但**事件触发点在 `scheduler.run()` 的 `_record_event("workflow_started")` hook（`scheduler.py:581`），不在工具层**：工具只持有 `SubAgentManager`（`loop.py:394-401`），拿不到 session 事件 sink；`run()` 是唯一同时知道「图真的开跑了」和持有调度器状态的入口。
  - **route 控制边**：不传数据、不参与 reducer（`agent/subagent/workflow.py:243-260`），须单列表达。
- design impact: 见 design.md D1–D7。

## Impact Analysis

- **能力域**: `web-ui`（流程图视图）+ `observability`（workflow 图级观测）。
- **代码**: 改 `agent/subagent/scheduler.py`（新增 `workflow_graph_snapshot()` + 节点迁移处发快照）、`agent/tools/builtin/subagents.py`（Start/RunWorkflow 启动点发事件）、`agent/loop.py`/`web/session.py`（workflow 事件进 ws 链路）、`web/server.py`（ws 事件类型 + 重连恢复查询）、`web/static/`（新增 workflow view + SVG 渲染 + 跨端布局）。
- **测试**: 新增 snapshot schema 测试、节点/边状态映射测试、启动事件测试、重连恢复测试、前端事件分发测试、跨端布局测试。
- **文档**: `docs/openspec-change-backlog.md`（登记 change）、issue #189。
- **流程（process）**: 独立 change，走 OpenSpec 全套；spec delta 落 `openspec/specs/web-ui/`。
