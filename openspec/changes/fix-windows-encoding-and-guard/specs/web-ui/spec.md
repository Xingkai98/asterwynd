# web-ui spec delta: 会话持久化的编码纪律与列表容错

> **MODIFIED 是整块替换**（OpenSpec `buildUpdatedSpec` 的语义）。因此本文件的两个 MODIFIED 块
> **逐字保留**现行 spec 的 requirement 正文与全部既有 Scenario（`Web session 本地持久化与恢复`
> 5 条、`Web UI 提供 session hub 列表` 4 条），只在末尾追加本次新增的 SHALL 与 Scenario。
> 审查方式：用 `buildUpdatedSpec` 只读模拟 apply，断言 Scenario 数只增不减、既有 Scenario 正文
> 逐字节不变。

## MODIFIED Requirements

### Requirement: Web session 本地持久化与恢复

Web session SHALL 在每次 Agent run 结束后持久化到 `<workspace>/.asterwynd/sessions/<session_id>/`（复用 `SessionStore`，与 CLI 同一存储位置），保存消息、mode、todos、skills 和 system prompt。WebSocket 连接 `GET /ws/<session_id>` SHALL 按 session id 恢复：内存命中则复用；未命中则从持久化快照恢复并推送 `session_resumed` 与 `session_history` 事件；快照不可用才新建 session。刷新/重开页面 SHALL 优先回到原 session，不自动新建。Web UI SHALL 提供显式恢复入口（URL `?session=<id>` 与 `GET /resume`）。恢复会话时若带 `?workspace=` 则用该 workspace 的 store 恢复；未带则按确定顺序（主 workspace → allowlist）搜索。Web 默认 host 绑定策略为 `127.0.0.1`，显式 `--host 0.0.0.0` 才开放局域网访问。

**编码 SHALL 显式且与 locale 无关**：存储层的本地文件 I/O（读与写）SHALL 显式使用 UTF-8，SHALL NOT 依赖进程 locale 的默认编码——在 locale 非 UTF-8 的平台（如 Windows 中文机器的 GBK/cp936）上，依赖默认编码会让含非 ASCII 文本（CJK、emoji、生僻字）的会话**保存失败**。含此类文本的会话 SHALL 能完整往返（写入成功且读回逐字一致）。读取时遇到不可解码的历史脏数据 SHALL 判为「损坏」并如实暴露（见 hub 列表 requirement），SHALL NOT 用替换字符把半损内容当完整会话交付。

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
- **WHEN** 访问 `/resume?session=<session_id>` 或 `/resume?session=<session_id>&workspace=<path>`
- **THEN** Web UI SHALL 进入指定 session 并展示其历史
- **AND** 指定了 workspace 时 SHALL 使用该 workspace 的 store 恢复

#### Scenario: 未知 session id 回退新建

- **GIVEN** 浏览器连接不存在的 session id 且无快照
- **WHEN** WebSocket 连接建立
- **THEN** 服务端 SHALL 新建 session
- **AND** 前端 SHALL 收到 `session_created` 事件
- **AND** 若连接 URL 携带合法 `?workspace=`，新建的 session SHALL 使用该 workspace

#### Scenario: 含 emoji 与 CJK 的会话完整往返

- **GIVEN** 一条会话的消息里含 emoji（如 `👋`）、中文与生僻字
- **WHEN** 该会话被持久化后再读回
- **THEN** 读回的消息内容 SHALL 与写入前逐字一致
- **AND** SHALL NOT 因字符超出 locale 编码范围而保存失败

#### Scenario: 非 UTF-8 locale 下同样往返成功

- **GIVEN** 进程运行在非 UTF-8 locale（Windows 中文机器的 GBK，或 `LC_ALL=C` 的 ASCII 环境）
- **WHEN** 含非 ASCII 文本的会话被持久化并读回
- **THEN** 结果 SHALL 与 UTF-8 locale 下一致
- **AND** 存储层 SHALL NOT 使用 locale 默认编码（以 `EncodingWarning` 告警断言与静态扫描双重固定）

### Requirement: Web UI 提供 session hub 列表

Web UI SHALL 提供 session 入口页（hub），列出已保存会话并允许按 workspace 切换与新建。hub 通过 `GET /api/workspaces` 获取允许的 workspace 列表，通过 `GET /api/sessions?workspace=<path>` 获取指定 workspace 的会话列表（复用 `SessionStore.list_sessions()` 元数据：session_id、mode、created_at、updated_at、messages）。workspace 不在 allowlist 或路径不存在时 SHALL 返回结构化拒绝（HTTP 403 + `{"error": "workspace_not_allowed"}`）。缺省 `workspace` SHALL 使用主 workspace。

**单条损坏 SHALL NOT 打掉整个列表**：某条会话的落盘数据不可解码/损坏时，`GET /api/sessions` SHALL 仍返回 200；该条 SHALL 以可区分的降级形态出现在列表里——带 `damaged` 标记与可读 `reason`（`session_id` 取目录名，因为文件不可读时目录名是唯一可信标识）——SHALL NOT 静默消失（「少了几个会话但没人解释」与「不显示 = 没事」是同一种误读）。其余会话的元数据 SHALL 正常返回。

#### Scenario: 获取 workspace 列表

- **GIVEN** Web UI 配置了主 workspace 与 allowlist
- **WHEN** 前端请求 `GET /api/workspaces`
- **THEN** 响应 SHALL 包含主 workspace 与 allowlist 内存在的路径
- **AND** 每个 workspace SHALL 标注是否为主 workspace
- **AND** 每个 workspace SHALL 标注运行期是否存在

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

#### Scenario: 单条会话损坏不拖垮列表

- **GIVEN** 存储目录里存在一条不可解码/损坏的会话数据（例如 locale 非 UTF-8 时代写入的脏文件）
- **WHEN** 客户端请求 `GET /api/sessions`
- **THEN** 接口 SHALL 返回 200
- **AND** 该条 SHALL 以 `damaged` 标记 + 可读 `reason` 出现在列表里（`session_id` 取目录名）
- **AND** 其余会话的元数据 SHALL 正常返回
