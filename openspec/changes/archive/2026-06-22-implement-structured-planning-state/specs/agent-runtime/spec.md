## ADDED Requirements

### Requirement: AgentLoop 可发出 planning state 事件

AgentLoop SHALL 支持在计划创建或状态更新时发出 `planning_state_updated` 事件，并保持原有 tool-call 协议不变量。事件 payload SHALL 包含完整 planning state snapshot，至少包含 `items` 列表和可选 `summary`。

#### Scenario: 计划状态更新

- **GIVEN** AgentLoop 运行中产生 planning state 更新
- **WHEN** 更新被应用
- **THEN** 系统 SHALL 通过事件或 hook 暴露更新后的 planning state
- **AND** SHALL NOT 插入破坏 provider tool-call 链的消息

#### Scenario: LLM 调用包含只读 planning context

- **GIVEN** AgentLoop 持有非空 planning state
- **WHEN** AgentLoop 调用 LLM
- **THEN** 系统 SHALL 将当前 planning state 作为临时只读上下文提供给 LLM
- **AND** SHALL NOT 将该上下文持久 append 到 messages
