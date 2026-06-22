## ADDED Requirements

### Requirement: Web session 可携带 agent mode

Web session SHALL 在创建 AgentLoop 时携带 `build`、`read_only` 或 `plan` agent mode，并确保同一 session 内 mode 语义一致。Web SHALL 接受 `read_only` 和 `read-only` 两种用户输入，并在内部规范化为 `read_only`。未指定 mode 时 SHALL 默认使用 `build`。Web session SHALL NOT 接受 `bypass` 作为用户可选 mode。

#### Scenario: Web session 使用 mode

- **GIVEN** Web session 创建时指定 mode
- **WHEN** 用户发送消息
- **THEN** session SHALL 使用该 mode 对应的工具权限运行 AgentLoop

#### Scenario: Web session 默认 build mode

- **GIVEN** Web session 创建时未指定 mode
- **WHEN** 用户发送消息
- **THEN** session SHALL 使用 `build` mode

#### Scenario: Web 事件暴露 mode

- **GIVEN** Web session 已创建
- **WHEN** 服务端发送 session_created 或 run_started 事件
- **THEN** 事件 SHALL 包含当前实际 mode
