## ADDED Requirements

### Requirement: Web session 可携带 agent mode

Web session SHALL 在创建 AgentLoop 时携带 agent mode，并确保同一 session 内 mode 语义一致。

#### Scenario: Web session 使用 mode

- **GIVEN** Web session 创建时指定 mode
- **WHEN** 用户发送消息
- **THEN** session SHALL 使用该 mode 对应的工具权限运行 AgentLoop
