## ADDED Requirements

### Requirement: Web UI 消费 assistant 流式输出

Web UI SHALL 通过 WebSocket 消费 assistant text delta 事件，并实时追加到当前 assistant 消息。

#### Scenario: WebSocket 收到 text delta

- **GIVEN** WebSocket 已连接
- **WHEN** 前端收到 assistant text delta
- **THEN** 当前 assistant 气泡 SHALL 实时追加文本
