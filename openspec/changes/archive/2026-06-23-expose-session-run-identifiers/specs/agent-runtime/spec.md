## ADDED Requirements

### Requirement: Agent runtime 提供 session id 和 run id

Agent runtime SHALL 为一次 Agent 运行提供 run id，并在存在交互式会话时关联 session id，用于日志、事件、trace 和 UI 展示。

#### Scenario: 运行事件包含 run id

- **GIVEN** AgentLoop 开始一次运行
- **WHEN** runtime 发布运行事件
- **THEN** 事件 SHALL 包含可用于排查的 run id
- **AND** 如果调用方提供了 session id，事件 SHALL 包含该 session id
