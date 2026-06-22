## ADDED Requirements

### Requirement: AgentLoop 可发出 planning state 事件

AgentLoop SHALL 支持在计划创建或状态更新时发出 planning state 事件，并保持原有 tool-call 协议不变量。

#### Scenario: 计划状态更新

- **GIVEN** AgentLoop 运行中产生 planning state 更新
- **WHEN** 更新被应用
- **THEN** 系统 SHALL 通过事件或 hook 暴露更新后的 planning state
- **AND** SHALL NOT 插入破坏 provider tool-call 链的消息
