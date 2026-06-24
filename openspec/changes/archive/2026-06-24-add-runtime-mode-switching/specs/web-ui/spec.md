## ADDED Requirements

### Requirement: Web UI 支持实时切换 session mode

Web UI SHALL 支持用户在现有 session 中切换当前 agent mode，并通过 WebSocket 同步 mode 变化事件。第一版 Web UI SHALL 至少保证 mode 切换影响同一 session 的后续 run；不要求在一次 Agent run 正在执行时处理新的 mode 切换消息。

#### Scenario: WebSocket 切换 mode

- **GIVEN** WebSocket 已连接到某个 session
- **WHEN** 前端发送 mode 切换请求
- **THEN** 服务端 SHALL 更新该 session 的当前 mode
- **AND** 向前端发送 `mode_changed` 事件
- **AND** 后续 run SHALL 使用更新后的 mode

#### Scenario: Web UI 展示当前 mode

- **GIVEN** session 已创建
- **WHEN** 前端收到 session_created 或 mode_changed 事件
- **THEN** UI SHALL 展示当前实际 mode
