## ADDED Requirements

### Requirement: Web UI 展示 planning state

Web UI SHALL 接收 `planning_state_updated` 事件，并在 Chat 或 Debug 视图中展示当前计划状态。

#### Scenario: 接收 planning 事件

- **GIVEN** WebSocket 已连接
- **WHEN** 服务端发送 planning state 事件
- **THEN** 前端 SHALL 更新计划展示
- **AND** 不影响普通聊天消息和工具事件展示
