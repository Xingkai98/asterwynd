# web-ui spec delta: 多 Agent 运行态流程图

## ADDED Requirements

### Requirement: workflow 运行态流程图视图

Web UI SHALL 在模型触发多 Agent 流程（`StartWorkflow`/`RunWorkflow`/`RunPattern` 驱动的 workflow execution）时自动显示一个 Workflow 视图，SHALL 显示 workflow 的所有节点与边。该视图 SHALL 是用户态能力，SHALL NOT 受 debug 模式门禁约束。

#### Scenario: workflow 启动自动显示图

- **GIVEN** 模型调用 `StartWorkflow` 启动一个 workflow
- **WHEN** `workflow_started` 事件到达前端
- **THEN** Web UI SHALL 自动打开 Workflow 视图
- **AND** SHALL 显示该 workflow 的节点与边

### Requirement: workflow 图快照

scheduler SHALL 提供 `workflow_graph_snapshot()`，返回完整运行期图（nodes + edges + 每节点 status + 每边 status）。该快照 SHALL 基于运行期 `ExecutionPlan`（含自动插层 + foreach 展开），SHALL NOT 改变现有 `_envelope`/`parent_envelope` 的父 Agent 数据契约。

#### Scenario: 快照包含边与状态

- **GIVEN** 一个运行中的 workflow
- **WHEN** 调用 `workflow_graph_snapshot()`
- **THEN** 返回 SHALL 含 nodes（每节点 status）
- **AND** SHALL 含 edges（每边 status）

### Requirement: 节点与边状态高亮

前端 SHALL 按状态高亮节点（pending 灰 / started 蓝 / completed 绿 / failed 红 / cancelled 深灰 / blocked 黄 / budget_exceeded 橙）。边 SHALL 按状态高亮（inactive / ready / active / passed / blocked）。route 控制边 SHALL 单列表达，SHALL 只高亮 `targets` 中实际选中的出口。

#### Scenario: 节点状态高亮

- **GIVEN** 一个 workflow 有 completed、started、pending 三种状态的节点
- **WHEN** 前端渲染快照
- **THEN** 三种节点 SHALL 分别显示绿色、蓝色、灰色
- **AND** SHALL 直观区分运行状态

#### Scenario: route 分支高亮

- **GIVEN** 一个 route 节点命中某条分支
- **WHEN** 前端渲染快照
- **THEN** SHALL 只高亮该 route 选中的出口控制边
- **AND** 未选中的分支 SHALL 保持 inactive

### Requirement: workflow 事件通道

WebSocket SHALL 支持 `workflow_started` 与 `workflow_snapshot` 事件。`DeclareWorkflow` SHALL NOT 触发 `workflow_started`（只声明不启动）。断线重连后 SHALL 从 workflow 注册表补发当前快照。

`workflow_started` 的触发点 SHALL 在 `scheduler.run()` 的启动 hook（`agent/subagent/scheduler.py:581` 的 `_record_event("workflow_started")` 处），SHALL NOT 依赖 `StartWorkflowTool`/`RunWorkflowTool` 的工具层发事件（工具只持有 manager，拿不到 session 事件 sink）。

快照推送失败（例如 ws 已断开）SHALL NOT 影响 workflow 的执行状态或节点终态。

#### Scenario: 断线重连恢复快照

- **GIVEN** 一个 workflow 运行中、前端 ws 断线后重连
- **WHEN** 重连完成
- **THEN** 服务端 SHALL 补发当前 workflow 快照
- **AND** 前端 SHALL 恢复图状态

### Requirement: workflow 图跨端适配

Workflow 视图 SHALL 在桌面（>720px）显示横向 DAG（左→右）、在手机/平板（≤720px）显示纵向 DAG（上→下）。SHALL 支持 pinch 缩放 + pan 平移。50–200 节点 SHALL 折叠 foreach/自动插层（折叠组聚合状态、点击展开局部）；**（meta-review 修正）**`max_nodes` 超限 SHALL 表现为「声明期被拒（无图）/ 运行期 `status == "graph_recursion_exceeded"` + `diagnostics`」两种，前端 SHALL NOT 依赖 `nodes.length > 200` 判断超限，也不存在「渲染一张 >200 节点的图再截断」的路径。

#### Scenario: 手机端纵向布局

- **GIVEN** 一个 ≤720px 视口的移动端
- **WHEN** 渲染 workflow 图
- **THEN** SHALL 显示纵向 DAG（根在上、叶在下）
- **AND** SHALL 支持 pinch 缩放与 pan 平移
