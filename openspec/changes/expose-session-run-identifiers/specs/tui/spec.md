## ADDED Requirements

### Requirement: 未来 TUI 展示 correlation id

未来 TUI SHALL 展示当前 session 或 run 的 correlation id。

#### Scenario: TUI 启动 session

- **GIVEN** 用户打开 TUI
- **WHEN** 创建或恢复运行
- **THEN** TUI SHALL 展示可用于日志关联的 id
