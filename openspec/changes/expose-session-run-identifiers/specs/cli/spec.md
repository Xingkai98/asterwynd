## ADDED Requirements

### Requirement: CLI 展示 session id 和 run id

CLI SHALL 在启动会话时展示 session id，并在每次 Agent 运行开始时展示 run id。

#### Scenario: CLI 启动 agent

- **GIVEN** 用户通过 CLI 启动 Agent
- **WHEN** 运行开始
- **THEN** CLI SHALL 输出可用于排查的 run id

#### Scenario: CLI 交互模式复用 session id

- **GIVEN** 用户通过 CLI 交互模式启动 Agent
- **WHEN** 用户连续发送多轮消息
- **THEN** CLI SHALL 为该交互会话保持同一个 session id
- **AND** 每轮 Agent 运行 SHALL 输出新的 run id
