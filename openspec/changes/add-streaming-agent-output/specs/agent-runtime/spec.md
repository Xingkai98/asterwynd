## ADDED Requirements

### Requirement: Agent runtime 发布 assistant 流式输出事件

Agent runtime SHALL 支持在 LLM 生成过程中发布 assistant text delta 事件，并在最终响应完成后保持 messages 中的 assistant 消息合法。

#### Scenario: assistant 文本流式输出

- **GIVEN** provider 支持 streaming text
- **WHEN** AgentLoop 调用 LLM
- **THEN** runtime SHALL 发布 text delta 事件
- **AND** 最终 SHALL 写入完整 assistant message

#### Scenario: provider 不支持 streaming

- **GIVEN** provider 不支持 streaming
- **WHEN** AgentLoop 调用 LLM
- **THEN** runtime SHALL 保持非流式行为兼容
