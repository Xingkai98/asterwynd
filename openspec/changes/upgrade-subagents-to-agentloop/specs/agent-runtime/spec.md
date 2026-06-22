## ADDED Requirements

### Requirement: 父 AgentLoop 可接收子 agent 结果

父 AgentLoop SHALL 能通过 ParentChannel 接收子 agent 结果，并以合法消息或事件形式注入当前运行上下文。

#### Scenario: 子 agent 结果回传

- **GIVEN** 子 agent 已完成
- **WHEN** 父 AgentLoop 检查 ParentChannel
- **THEN** 系统 SHALL 注入子 agent 结果
- **AND** SHALL NOT 破坏当前 tool-call 消息链
