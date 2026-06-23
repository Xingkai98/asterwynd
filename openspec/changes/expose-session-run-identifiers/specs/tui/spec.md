## ADDED Requirements

### Requirement: 未来 TUI 展示 session id 和 run id

未来 TUI SHALL 展示当前交互式 session id 和最近一次 Agent 运行的 run id。

#### Scenario: TUI 启动 session

- **GIVEN** 用户打开 TUI
- **WHEN** 创建或恢复运行
- **THEN** TUI SHALL 展示可用于日志关联的 session id
- **AND** 当 Agent 运行开始时，TUI SHALL 展示 run id
