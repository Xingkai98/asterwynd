## ADDED Requirements

### Requirement: CLI 支持选择 agent mode

CLI SHALL 支持为 AgentLoop 选择 agent mode，并在运行输出或日志中记录实际 mode。

#### Scenario: CLI 传入 mode

- **GIVEN** 用户执行 CLI 并指定 mode
- **WHEN** CLI 构造 AgentLoop
- **THEN** 系统 SHALL 使用对应 mode 配置工具集合
- **AND** 输出或日志 SHALL 记录实际 mode
