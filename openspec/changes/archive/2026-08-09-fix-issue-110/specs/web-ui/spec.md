## ADDED Requirements

### Requirement: Web session 本地持久化与恢复

Web session SHALL 在每次 Agent run 结束后持久化到 `<workspace>/.asterwynd/sessions/<session_id>/`（复用 `SessionStore`，与 CLI 同一存储位置），保存消息、mode、todos、skills 和 system prompt。WebSocket 连接 `GET /ws/<session_id>` SHALL 按 session id 恢复：内存命中则复用；未命中则从持久化快照恢复并推送 `session_resumed` 与 `session_history` 事件；快照不可用才新建 session。刷新/重开页面 SHALL 优先回到原 session，不自动新建。Web UI SHALL 提供显式恢复入口（URL `?session=<id>` 与 `GET /resume`）。

#### Scenario: run 结束后自动落盘

- **GIVEN** Web session 完成一次 Agent run
- **WHEN** AgentLoop 结束 run
- **THEN** session 的消息、mode、todos、skills、system prompt SHALL 写入持久化目录

#### Scenario: 进程重启后按 id 恢复

- **GIVEN** 服务端进程重启，本地存在该 session 快照
- **WHEN** 浏览器连接 `/ws/<session_id>`
- **THEN** 服务端 SHALL 从快照恢复 session
- **AND** 前端 SHALL 收到 `session_resumed` 事件与 `session_history` 历史消息

#### Scenario: 刷新页面回到原 session

- **GIVEN** 用户在 Web UI 中已有 session 且本地已记忆该 session id
- **WHEN** 刷新或重开页面
- **THEN** 前端 SHALL 使用记忆的 session id 重连原 session
- **AND** SHALL NOT 自动新建 session

#### Scenario: 显式恢复入口

- **GIVEN** 用户想显式恢复某个 session
- **WHEN** 访问 `/resume?session=<session_id>` 或使用 URL 参数
- **THEN** Web UI SHALL 进入指定 session 并展示其历史

#### Scenario: 未知 session id 回退新建

- **GIVEN** 浏览器连接不存在的 session id 且无快照
- **WHEN** WebSocket 连接建立
- **THEN** 服务端 SHALL 新建 session
- **AND** 前端 SHALL 收到 `session_created` 事件
