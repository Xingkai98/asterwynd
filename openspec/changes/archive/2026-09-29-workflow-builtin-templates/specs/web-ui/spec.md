# web-ui spec delta: Workflow 视图触发工具列表随 RunPattern 退役而收敛

## MODIFIED Requirements

### Requirement: workflow 运行态流程图视图

Web UI SHALL 在模型触发多 Agent 流程（`StartWorkflow`/`RunWorkflow` 驱动的 workflow execution）时自动显示一个 Workflow 视图，SHALL 显示 workflow 的所有节点与边。该视图 SHALL 是用户态能力，SHALL NOT 受 debug 模式门禁约束。

#### Scenario: workflow 启动自动显示图

- **GIVEN** 模型调用 `StartWorkflow` 启动一个 workflow
- **WHEN** `workflow_started` 事件到达前端
- **THEN** Web UI SHALL 自动打开 Workflow 视图
- **AND** SHALL 显示该 workflow 的节点与边

#### Scenario: 模板入口驱动的图同样显示

- **GIVEN** 模型调用 `RunWorkflow(template=…)` 驱动一张内置模板图
- **WHEN** `workflow_started` 事件到达前端
- **THEN** Web UI SHALL 自动打开 Workflow 视图并显示该图
- **AND** `RunPattern` SHALL NOT 再作为触发来源出现（该工具已退役）
