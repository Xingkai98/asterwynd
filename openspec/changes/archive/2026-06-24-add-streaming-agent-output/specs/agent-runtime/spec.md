## ADDED Requirements

### Requirement: Agent runtime 发布 assistant 流式输出事件

Agent runtime SHALL 支持在 LLM 生成过程中发布 `assistant_delta` 事件，并在 streaming 响应完成时发布 `assistant_stream_complete` 事件。最终响应完成后，runtime SHALL 继续发布完整 `llm_response`，并保持 messages 中的 assistant 消息合法。

#### Scenario: assistant 文本流式输出

- **GIVEN** provider 支持 streaming text
- **WHEN** AgentLoop 调用 LLM
- **THEN** runtime SHALL 发布一个或多个 `assistant_delta` 事件
- **AND** `assistant_delta` payload SHALL 包含 `delta`
- **AND** runtime SHALL 发布 `assistant_stream_complete`
- **AND** 最终 `llm_response` SHALL 包含 `streamed: true`
- **AND** 最终 SHALL 只写入完整 assistant message，不写入 partial delta message

#### Scenario: provider 不支持 streaming

- **GIVEN** provider 不支持 streaming
- **WHEN** AgentLoop 调用 LLM
- **THEN** runtime SHALL 不发布 `assistant_delta`
- **AND** runtime SHALL 保持非流式 `llm_response` 行为兼容

#### Scenario: streaming tool calls

- **GIVEN** provider 在 streaming 响应中返回 tool call arguments
- **WHEN** AgentLoop 收到完整 LLM response
- **THEN** runtime SHALL 只在 `LLMResponse.tool_calls` 完整后执行工具
- **AND** runtime SHALL NOT 将 tool arguments 作为 assistant text delta 暴露
