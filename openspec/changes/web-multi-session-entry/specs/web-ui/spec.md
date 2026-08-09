## ADDED Requirements

### Requirement: Web UI 提供 session hub 列表

Web UI SHALL 提供 session 入口页（hub），列出已保存会话并允许按 workspace 切换与新建。hub 通过 `GET /api/workspaces` 获取允许的 workspace 列表，通过 `GET /api/sessions?workspace=<path>` 获取指定 workspace 的会话列表（复用 `SessionStore.list_sessions()` 元数据：session_id、mode、created_at、updated_at、messages）。workspace 不在 allowlist 或路径不存在时 SHALL 返回结构化拒绝（HTTP 403 + `{"error": "workspace_not_allowed"}`）。缺省 `workspace` SHALL 使用主 workspace。

#### Scenario: 获取 workspace 列表

- **GIVEN** Web UI 配置了主 workspace 与 allowlist
- **WHEN** 前端请求 `GET /api/workspaces`
- **THEN** 响应 SHALL 包含主 workspace 与 allowlist 内存在的路径
- **AND** 每个 workspace SHALL 标注是否为主 workspace

#### Scenario: 获取会话列表

- **GIVEN** 主 workspace 下存在已保存会话
- **WHEN** 前端请求 `GET /api/sessions`
- **THEN** 响应 SHALL 返回会话列表，字段含 session_id、mode、created_at、updated_at、messages
- **AND** 列表 SHALL 按 updated_at 倒序

#### Scenario: 未授权 workspace 被拒绝

- **GIVEN** 请求指定了一个不在 allowlist 的 workspace
- **WHEN** 前端请求 `GET /api/sessions?workspace=<path>`
- **THEN** 响应 SHALL 返回 HTTP 403 与结构化错误
- **AND** SHALL NOT 返回任何会话数据

### Requirement: 新建会话可指定 mode 与 workspace

Web UI SHALL 允许通过 WebSocket 连接参数新建指定 mode 与 workspace 的会话：`GET /ws/new?mode=<mode>&workspace=<path>`。mode SHALL 为 build / read_only / plan / bypass 之一；workspace SHALL 命中 allowlist 且路径存在。非法 mode 或未授权 workspace 时 SHALL 返回结构化 error 事件且不创建 session。`/ws/new` 携带显式参数时 SHALL 跳过 `--resume` 拦截直接新建；仅裸 `/ws/new` 保留 `--resume` 语义。

#### Scenario: 指定 mode 与 workspace 新建会话

- **GIVEN** 用户请求 `/ws/new?mode=plan&workspace=<allowlist 内路径>`
- **WHEN** WebSocket 连接建立
- **THEN** 服务端 SHALL 以 plan mode 与指定 workspace 创建 session
- **AND** 前端 SHALL 收到 `session_created` 事件（含 session_id、mode、workspace）

#### Scenario: 非法 mode 被拒绝

- **GIVEN** 用户请求 `/ws/new?mode=invalid`
- **WHEN** WebSocket 连接建立
- **THEN** 服务端 SHALL 返回 `{"error": "invalid_mode"}` 事件
- **AND** SHALL NOT 创建 session

#### Scenario: 未授权 workspace 被拒绝

- **GIVEN** 用户请求 `/ws/new?workspace=<不在 allowlist 的路径>`
- **WHEN** WebSocket 连接建立
- **THEN** 服务端 SHALL 返回 `{"error": "workspace_not_allowed"}` 事件
- **AND** SHALL NOT 创建 session

### Requirement: session 按 workspace 分区存储与恢复

每个 Web session SHALL 拥有独立的 workspace_root，其持久化目录为 `<workspace>/.asterwynd/sessions/<session_id>/`。不同 workspace 的会话 SHALL 存储在其各自 workspace 目录下。恢复会话时 workspace 显式传入则用该 workspace 的 store；未传时 SHALL 按确定顺序搜索（主 workspace → allowlist 配置序）并返回首个命中。

#### Scenario: 会话归属其创建时的 workspace

- **GIVEN** 会话在 workspace A 下创建并完成一次 run
- **WHEN** AgentLoop 结束 run
- **THEN** 快照 SHALL 写入 `A/.asterwynd/sessions/<session_id>/`
- **AND** 不写入其他 workspace 的目录

#### Scenario: 按 workspace 恢复会话

- **GIVEN** workspace A 下存在会话快照
- **WHEN** 浏览器连接 `/ws/<session_id>?workspace=A`
- **THEN** 服务端 SHALL 从 A 的 store 恢复该 session
- **AND** 前端 SHALL 收到 `session_resumed` 与 `session_history`

### Requirement: 同一 session 并发发送被拒绝

Web UI SHALL 对同一 session 的并发 Agent run 提供互斥：同一 session 已有 run 进行中时，新发送 SHALL 被拒绝并返回 error 事件，不得并发执行同一 AgentLoop。

#### Scenario: 并发 chat 第二个被拒

- **GIVEN** 某 session 正在执行一次 run
- **WHEN** 该 session 收到新的 `chat` 消息
- **THEN** 服务端 SHALL 返回 `{"error": "another run is already in progress"}` 事件
- **AND** SHALL NOT 启动第二次 run

### Requirement: Web UI 支持多标签会话

Web UI SHALL 允许同时打开多个会话标签页，每个标签页独立维护 WebSocket 连接、消息历史与运行状态；切换标签页 SHALL 只切换展示，不中断其他标签页的连接与运行状态。前端刷新 SHALL 回到最近使用的会话（localStorage 记忆 session_id 与 workspace），不自动重连全部历史标签。

#### Scenario: 两个标签页并行会话

- **GIVEN** 用户打开两个不同会话的标签页
- **WHEN** 两个标签页分别发送消息
- **THEN** 每个标签页 SHALL 使用各自会话的消息历史与 WebSocket
- **AND** 一方消息与运行状态 SHALL NOT 影响另一方

#### Scenario: 刷新回到最近会话

- **GIVEN** 用户在 Web UI 使用过某会话且本地记忆其 id
- **WHEN** 刷新或重开页面
- **THEN** 前端 SHALL 回到该会话
- **AND** 除最近会话外不自动打开其他标签

### Requirement: Web UI 提供会话删除

Web UI hub SHALL 提供会话删除，删除 SHALL 移除内存中的会话与持久化目录下的快照。删除已打开会话时 SHALL 关闭对应标签页。

#### Scenario: 删除会话

- **GIVEN** hub 列表中某会话已被删除请求
- **WHEN** 用户确认删除
- **THEN** 该会话从内存与磁盘快照移除
- **AND** 列表 SHALL 不再展示该会话
- **AND** 若存在打开的同 id 标签页，该标签页 SHALL 被关闭

## MODIFIED Requirements

### Requirement: Web session 本地持久化与恢复

更新恢复优先级：刷新/重开页面 SHALL 优先回到原 session，支持显式恢复入口（URL `?session=<id>`，可带 `?workspace=`）。恢复会话时若带 `?workspace=` 则用该 workspace 的 store 恢复；未带则按确定顺序（主 workspace → allowlist）搜索。Web 默认 host 绑定策略为 `127.0.0.1`，显式 `--host 0.0.0.0` 才开放局域网访问。

#### Scenario: 刷新页面回到原 session

- **GIVEN** 用户在 Web UI 中已有 session 且本地已记忆该 session id
- **WHEN** 刷新或重开页面
- **THEN** 前端 SHALL 使用记忆的 session id 重连原 session
- **AND** SHALL NOT 自动新建 session

#### Scenario: 显式恢复入口

- **GIVEN** 用户想显式恢复某个 session
- **WHEN** 访问 `/resume?session=<session_id>` 或 `/resume?session=<session_id>&workspace=<path>`
- **THEN** Web UI SHALL 进入指定 session 并展示其历史
- **AND** 指定了 workspace 时 SHALL 使用该 workspace 的 store 恢复
