## ADDED Requirements

### Requirement: Web UI 消费 assistant 流式输出

Web UI SHALL 通过 WebSocket 消费 `assistant_delta` 事件，并实时追加到当前 assistant 消息。Web UI SHALL 在 `llm_response.streamed` 为 `true` 时跳过该 `llm_response.content` 的展示；非 streaming 路径 SHALL 继续展示普通 `llm_response.content`。

#### Scenario: WebSocket 收到 text delta

- **GIVEN** WebSocket 已连接
- **WHEN** 前端收到 `assistant_delta`
- **THEN** 当前 assistant 气泡 SHALL 实时追加文本

#### Scenario: WebSocket 收到 streamed llm_response

- **GIVEN** 当前 assistant 气泡已展示 streaming 文本
- **WHEN** 前端收到 `llm_response` 且 `streamed` 为 `true`
- **THEN** 前端 SHALL NOT 再次追加 `llm_response.content`
