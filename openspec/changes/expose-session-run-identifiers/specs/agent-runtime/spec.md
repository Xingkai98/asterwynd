## ADDED Requirements

### Requirement: Agent runtime 提供可关联运行标识

Agent runtime SHALL 为 session 或 run 提供可关联标识，用于日志、事件、trace 和 UI 展示。

#### Scenario: 运行事件包含 correlation id

- **GIVEN** AgentLoop 开始一次运行
- **WHEN** runtime 发布运行事件
- **THEN** 事件 SHOULD 包含可用于排查的 correlation id
