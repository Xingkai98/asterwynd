## ADDED Requirements

### Requirement: 未来 TUI 复用 streaming event

未来 TUI SHALL 复用 Agent runtime 的 `assistant_delta` 和 `assistant_stream_complete` event，不得定义不兼容的流式输出协议。未来 TUI SHALL 将 `llm_response(streamed=true)` 作为完成态数据，而不是重复展示文本。

#### Scenario: TUI 展示 streaming 回复

- **GIVEN** runtime 发布 `assistant_delta`
- **WHEN** TUI 消费事件
- **THEN** TUI SHALL 实时更新 assistant 消息区域
