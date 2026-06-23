## ADDED Requirements

### Requirement: Web UI 展示 session id

Web UI SHALL 展示当前 session id，便于用户复制并关联日志。

#### Scenario: session 创建后展示 id

- **GIVEN** WebSocket 创建新 session
- **WHEN** 前端收到 session_created 事件
- **THEN** 页面 SHALL 展示该 session id

### Requirement: Web UI 接收 run id

Web UI SHALL 接收每次 Agent 运行的 run id，便于把用户消息和运行日志关联。

#### Scenario: Agent 运行开始后展示 run id

- **GIVEN** 用户在 Web UI 发送消息
- **WHEN** 前端收到 run_started 事件
- **THEN** 页面 SHALL 展示该 run id
