## ADDED Requirements

### Requirement: Web UI 支持实时切换 session mode

Web UI SHALL 支持用户在现有 session 中切换当前 agent mode，并通过 WebSocket 同步 mode 变化事件。

#### Scenario: WebSocket 切换 mode

- **GIVEN** WebSocket 已连接到某个 session
- **WHEN** 前端发送 mode 切换请求
- **THEN** 服务端 SHALL 更新该 session 的当前 mode
- **AND** 向前端发送 `mode_changed` 事件

#### Scenario: Web UI 展示当前 mode

- **GIVEN** session 已创建
- **WHEN** 前端收到 session_created 或 mode_changed 事件
- **THEN** UI SHALL 展示当前实际 mode
