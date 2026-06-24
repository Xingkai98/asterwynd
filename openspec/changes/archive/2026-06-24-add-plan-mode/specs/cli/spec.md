## ADDED Requirements

### Requirement: CLI 支持 plan mode

CLI SHALL 支持通过参数启动 plan mode。

#### Scenario: CLI plan mode

- **GIVEN** 用户通过 CLI 指定 plan mode
- **WHEN** CLI 运行 AgentLoop
- **THEN** 系统 SHALL 使用 plan mode 工具策略
- **AND** 输出计划说明
