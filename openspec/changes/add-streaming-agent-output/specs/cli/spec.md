## ADDED Requirements

### Requirement: CLI 实时输出 assistant delta

CLI SHALL 在支持 streaming 的运行路径中实时打印 assistant text delta。

#### Scenario: CLI 收到 text delta

- **GIVEN** CLI 正在运行 Agent
- **WHEN** runtime 发布 assistant text delta
- **THEN** CLI SHALL 实时输出该 delta
