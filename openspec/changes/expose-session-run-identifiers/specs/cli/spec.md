## ADDED Requirements

### Requirement: CLI 展示 run id

CLI SHALL 在运行开始时展示本次 run id 或等价 correlation id。

#### Scenario: CLI 启动 agent

- **GIVEN** 用户通过 CLI 启动 Agent
- **WHEN** 运行开始
- **THEN** CLI SHALL 输出可用于排查的 run id
