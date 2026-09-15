# Tasks: 多 Agent 运行态流程图可视化

## 0. 设计追问（实现前门禁）

- [x] 0.1 跑 `batch-grill-me`（或等价设计追问）审视 design.md D1–D7，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）。

## 1. 数据面：workflow 图快照

- [x] 1.1 `agent/subagent/scheduler.py` 新增 `workflow_graph_snapshot()`：完整 nodes + edges + 每节点 status + 每边 status（基于 `ExecutionPlan` 运行期图；**不动** `_envelope`/`parent_envelope` 父 Agent 契约）。
- [x] 1.2 节点七档状态 + 边五档状态推导（route 控制边单列，只高亮 `targets` 选中出口；`passed` 档若拍板新增，在三个消费循环里 `_mark_consumed` **旁**加 per-edge 记账，不改 `_mark_consumed` 本体）。
- [x] 1.3 快照 bounded（**显式挑字段**，不复用 `NodeState.to_dict()`：排除 `subagent_ids`/`slots`/`raw`；edges 只含结构字段），对齐 200 节点口径。

## 2. 事件通道：workflow 事件进 WebSocket

- [x] 2.1 **（meta-review 修正）** `workflow_started` 的触发点是 `scheduler.run()` 里已有的 `_record_event("workflow_started")`（`agent/subagent/scheduler.py:581`）——在该 hook 处新增一次 sink 调用，**不改工具层**（工具拿不到 sink，见 grill 决策 1/2）；`DeclareWorkflow` 只 `register_workflow` 不调 `run()`，天然不发。
- [x] 2.2 scheduler 节点迁移处（`_dispatch`/`_run_node`/route/取消/预算停止）发 `workflow_snapshot`，经 `AgentLoop.on_event` → session queue → ws 链路。
- [x] 2.3 ws 重连后从 manager 注册表补发当前快照。

## 3. 前端：Workflow 视图 + SVG 渲染

- [x] 3.1 Chat 旁新增用户态 Workflow 视图（不放 debug 门禁），监听 `workflow_started` 自动打开。
- [x] 3.2 零依赖 SVG 自绘：DAG 分层布局 + 节点七档颜色 + 边五档状态 + channel 线型。
- [x] 3.3 route 控制边单列渲染（选中出口高亮，未选分支 inactive）。

## 4. 规模分级

- [x] 4.1 `<50` 全展开；`50–200` 折叠 foreach/自动插层（折叠组按 `kind == "foreach"` + `__auto_agg__` 前缀识别，聚合状态，点击展开局部）；`>200` **（meta-review 修正）** 不存在「拿到 >200 节点的图」这条路——声明期超限抛 `WorkflowValidationError`（无 scheduler 无图），运行期超限收敛为 `status == "graph_recursion_exceeded"` + `diagnostics`，前端按该状态渲染告警而非按 `nodes.length` 判断。

## 5. 跨端适配

- [x] 5.1 桌面横向 DAG（左→右）+ 手机/平板纵向 DAG（上→下），复用 720/380 断点 + safe-area。
- [x] 5.2 pinch 缩放 + pan 平移（pointer events + SVG viewBox transform）。

## 6. 测试与收尾

- [x] 6.1 新增 snapshot schema、节点/边状态映射、启动事件、重连恢复、前端事件分发、折叠组、跨端布局测试；**（meta-review 补充）** 加一条「快照推送失败不影响 workflow 状态」的隔离测试（grill Q11）。
- [x] 6.2 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过（**（meta-review 补充）** 本 change 触及 `agent/tools/`、`agent/subagent/scheduler.py` 与 `benchmarks/` 观测链，命中 artifact checker 的 benchmark smoke 门禁）。
- [x] 6.3 兼容回归：`_envelope`/`parent_envelope` 结构不变（C1–C5 契约）；既有无 workflow 会话前端不崩。
- [x] 6.4 `uv run pytest -q` 全绿；OpenSpec validate + artifact checker 通过。
- [x] 6.5 同步 current spec：把 spec delta 合入 `openspec/specs/web-ui/spec.md`。
