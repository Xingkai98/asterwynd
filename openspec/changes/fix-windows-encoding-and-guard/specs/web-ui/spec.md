# web-ui spec delta: 会话持久化的编码纪律与列表容错

> **MODIFIED 是整块替换**：本块逐字保留原 requirement 的全部 5 条 Scenario，再追加本次新增的
> 3 条（emoji/CJK 往返、非 UTF-8 locale 往返、单条损坏不拖垮列表）。

## MODIFIED Requirements

### Requirement: Web session 本地持久化与恢复

Web session SHALL 在每次 Agent run 结束后持久化到 `<workspace>/.asterwynd/sessions/<session_id>/`（复用 `SessionStore`，与 CLI 同一存储位置），保存消息、mode、todos、skills 和 system prompt。WebSocket 连接 `GET /ws/<session_id>` SHALL 按 session id 恢复内存会话；未命中但存在持久化数据时按序恢复（先发 `session_resumed` 与 `session_history` 事件）；均未命中则新建 session。刷新/重开页面 SHALL 优先回到原 session，SHALL NOT 自动新建。Web UI SHALL 提供显式恢复入口（URL `?session=<id>` 与 `GET /resume`）。恢复会话时可用 `?workspace=` 指定该 workspace 的 store 恢复（未指定则按顺序 workspace 与 allowlist）。另外，Web 默认 host 绑定不得为 `127.0.0.1`，显式 `--host 0.0.0.0` 才开放局域网访问。

**编码 SHALL 显式且与 locale 无关**：存储层的所有本地文件 I/O（读与写）SHALL 显式使用 UTF-8，SHALL NOT 依赖进程 locale 的默认编码。含非 ASCII 文本（CJK、emoji、生僻字）的会话 SHALL 能完整往返（写入成功且读回逐字一致）——在 locale 非 UTF-8 的平台上（如 Windows 中文机器的 GBK/cp936）同样 SHALL 成立。读侧遇到历史脏数据（不可解码字节）SHALL 降级（`errors="replace"` 语义）而不是抛异常。

**读取 SHALL 容忍单条损坏**：列举会话（`GET /api/sessions`）时，某一条会话的数据不可解码/损坏 SHALL NOT 让整个列表失败——该条 SHALL 被跳过并在响应里**如实标注**（可区分的标记 + 原因），其余会话 SHALL 正常返回。写入失败 SHALL NOT 静默：SHALL 以结构化日志如实记录（本 change 之前是 WARNING + traceback）。

#### Scenario: run 结束后自动保存

- **GIVEN** Web session 完成一次 Agent run
- **WHEN** AgentLoop 结束 run
- **THEN** session 的消息、mode、todos、skills、system prompt SHALL 写入持久化目录

#### Scenario: 按 session id 恢复

- **GIVEN** 服务端进程重启，但磁盘存在该 session 数据
- **WHEN** 客户端连接 `/ws/<session_id>`
- **THEN** 服务端 SHALL 从快照恢复 session
- **AND** 前端 SHALL 收到 `session_resumed` 事件与 `session_history` 历史消息

#### Scenario: 刷新页面回到原 session

- **GIVEN** 用户在 Web UI 打开了一个 session 且本地已记住 session id
- **WHEN** 刷新或重开页面
- **THEN** 前端 SHALL 使用记住的 session id 恢复原 session
- **AND** SHALL NOT 自动新建 session

#### Scenario: 显式恢复入口

- **GIVEN** 用户想显式恢复某个 session
- **WHEN** 访问 `/resume?session=<session_id>` 或 `/resume?session=<session_id>&workspace=<path>`
- **THEN** Web UI SHALL 加载该 session 并展示其历史
- **AND** 指定 workspace 时 SHALL 使用该 workspace 的 store 恢复

#### Scenario: 未知 session id 则新建

- **GIVEN** 客户端连接不存在的 session id（无快照）
- **WHEN** WebSocket 连接建立
- **THEN** 服务端 SHALL 新建 session
- **AND** 前端 SHALL 收到 `session_created` 事件
- **AND** 若请求 URL 携带合法 `?workspace=`，新建的 session SHALL 使用该 workspace

#### Scenario: 含 emoji 与 CJK 的会话完整往返

- **GIVEN** 一条会话的消息里含 emoji（如 `👋`）、中文与生僻字
- **WHEN** 该会话被持久化后再读回
- **THEN** 读回的消息内容 SHALL 与写入前逐字一致
- **AND** SHALL NOT 因字符超出 locale 编码范围而保存失败

#### Scenario: 非 UTF-8 locale 下同样往返成功

- **GIVEN** 进程运行在非 UTF-8 locale（Windows 中文机器的 GBK，或 `LC_ALL=C` 的 ASCII 环境）
- **WHEN** 含非 ASCII 文本的会话被持久化并读回
- **THEN** 结果 SHALL 与 UTF-8 locale 下一致
- **AND** 存储层 SHALL NOT 使用 locale 默认编码（实现层以 `EncodingWarning` 与静态扫描双重固定）

#### Scenario: 单条会话损坏不拖垮列表

- **GIVEN** 存储目录里存在一条不可解码/损坏的会话数据
- **WHEN** 客户端请求 `GET /api/sessions`
- **THEN** 接口 SHALL 返回 200
- **AND** 该条 SHALL 被跳过并在响应里如实标注（标记 + 原因）
- **AND** 其余会话的元数据 SHALL 正常返回
