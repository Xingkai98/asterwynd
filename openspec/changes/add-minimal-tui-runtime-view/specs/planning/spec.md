## ADDED Requirements

### Requirement: TUI 展示 planning state

TUI SHALL 使用结构化 planning state 展示当前计划和各步骤状态。

#### Scenario: planning state 更新

- **GIVEN** AgentLoop 发出 planning state 事件
- **WHEN** TUI 接收事件
- **THEN** TUI SHALL 更新计划面板或等价展示区域
