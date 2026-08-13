# web-ui 规格

## Purpose

定义 Web UI 的 FastAPI 服务、WebSocket 会话、Chat 页面和 Debug 页面。当前实现位于 `web/`。
## Requirements
### Requirement: FastAPI app 提供静态资源和 WebSocket

Web UI SHALL 通过 FastAPI 创建应用，提供静态页面、品牌资产静态路径和 WebSocket 交互入口。

#### Scenario: 创建 app

- **GIVEN** CLI 提供 LLM 实例
- **WHEN** 调用 `create_app(llm)`
- **THEN** 系统 SHALL 创建可由 uvicorn 运行的 FastAPI app
- **AND** Web UI SHALL 提供品牌 wordmark 静态资源访问路径

### Requirement: Web UI 展示品牌 wordmark

Web UI SHALL 在 header 中展示当前正式项目名的 wordmark，并在窄屏或图片不可用时保持可读文本降级。

#### Scenario: header 展示品牌

- **GIVEN** 用户打开 Web UI
- **WHEN** 页面静态资源加载完成
- **THEN** header SHALL 展示 Asterwynd wordmark 或等价文本
- **AND** 该展示 SHALL NOT 遮挡 session id、run id、mode 控件、tabs 或状态文本

#### Scenario: 小屏降级

- **GIVEN** 用户在很窄的移动端视口打开 Web UI
- **WHEN** wordmark 图像空间不足
- **THEN** header SHALL 使用可读文本形式展示品牌名

### Requirement: 每个 session 维护独立状态

Web session SHALL 维护独立消息历史和 AgentLoop，避免不同浏览器会话互相污染。

#### Scenario: 两个 session 并发

- **GIVEN** 两个不同 session id
- **WHEN** 它们分别发送消息
- **THEN** 系统 SHALL 使用各自消息历史运行

### Requirement: Web session 复用入口层配置

Web UI SHALL 使用 CLI/Web 入口层已经解析的统一配置构造 SessionManager 和 AgentLoop。SessionManager SHALL NOT 为每个 session 重新发现配置文件。

#### Scenario: Web 使用配置默认 mode

- **GIVEN** 入口层配置包含 `agent.default_mode`
- **WHEN** Web 创建新 session
- **THEN** session SHALL 使用配置默认 mode

#### Scenario: Web 复用工具策略

- **GIVEN** 入口层配置包含工具策略
- **WHEN** Web 创建 AgentLoop
- **THEN** 默认工具 registry SHALL 使用该工具策略

#### Scenario: Web 使用配置的 skill roots

- **GIVEN** 入口层配置包含 skill roots
- **WHEN** Web 创建新 session
- **THEN** session SHALL 创建独立 SkillRuntime
- **AND** SkillRuntime SHALL 使用入口层配置中的 skill roots

### Requirement: Chat 视图展示对话和工具过程

Web Chat SHALL 支持用户发送消息，并通过服务端事件展示 agent 回复和工具调用过程。

#### Scenario: 用户发送消息

- **GIVEN** WebSocket 已连接
- **WHEN** 用户提交聊天内容
- **THEN** 服务端 SHALL 触发 AgentLoop
- **AND** 前端 SHALL 接收并展示运行事件

### Requirement: Web Chat 支持 skill slash commands

Web Chat SHALL 在 slash command catalog 中展示用户可调用 skill commands，并在 WebSocket 收到 `/skill-name args` 时激活对应 skill 后启动 Agent run。

#### Scenario: Web command catalog includes skills

- **GIVEN** Web UI 已加载用户可调用 skills
- **WHEN** 浏览器请求 `/api/slash-commands`
- **THEN** 响应 SHALL 包含这些 skill commands
- **AND** 每个 skill command SHALL 标记 source `skill` 和 kind `prompt`

#### Scenario: Web skill command runs agent with args

- **GIVEN** Web Chat 已加载名为 `code-review` 的用户可调用 skill
- **WHEN** 用户发送 `/code-review 帮我审一下这个 change`
- **THEN** WebSocket SHALL 先发送 command result
- **AND** SHALL queue `code-review` activation，source 为 `slash_command`
- **AND** SHALL 用 `帮我审一下这个 change` 作为用户消息启动 Agent run
- **AND** SHALL NOT 将原始 slash command 作为普通用户消息发送给 AgentLoop

### Requirement: Chat 视图渲染 assistant Markdown

Web Chat SHALL 将 assistant 文本按安全 Markdown 渲染，支持常见段落、列表、代码和链接展示，同时不得执行 raw HTML 或 unsafe link。

#### Scenario: assistant 返回 Markdown

- **GIVEN** assistant 回复包含列表或代码块
- **WHEN** Chat 页面展示回复
- **THEN** 前端 SHALL 渲染对应 Markdown 结构
- **AND** 保留原始文本作为后续增量拼接来源

#### Scenario: assistant 返回不安全 HTML

- **GIVEN** assistant 回复包含 raw HTML 或 unsafe link
- **WHEN** Chat 页面展示回复
- **THEN** 前端 SHALL 转义 HTML
- **AND** SHALL 阻断 unsafe link

### Requirement: Chat 视图按 display metadata 展示工具结果

Web Chat SHALL 使用服务端 tool_result 事件中的 display metadata 展示工具结果。长结果 SHALL 默认展示 preview 并允许展开全文；工具结果 SHALL 作为纯文本展示，不按 Markdown 或 HTML 渲染。

#### Scenario: 工具结果过长

- **GIVEN** tool_result 事件包含 collapsed display metadata
- **WHEN** Chat 页面展示工具结果
- **THEN** 页面 SHALL 展示 preview、字符数和行数
- **AND** 用户 SHALL 能展开查看完整结果

#### Scenario: 工具结果包含 HTML

- **GIVEN** 工具结果包含 HTML 字符串
- **WHEN** Chat 页面展示工具结果
- **THEN** 页面 SHALL 以纯文本展示该字符串
- **AND** SHALL NOT 执行或解析为 HTML

### Requirement: Debug 视图由环境变量控制

Debug 功能 SHALL 通过 `ASTERWYND_DEBUG=enabled` 开启；DebugHook SHALL 捕获 before_iteration、after_llm_call、before_tool_execute、after_tool_execute、on_error 和 on_completion 事件。当前 DebugHook 不直接捕获 MemoryManager compact 事件。

#### Scenario: Debug 未开启

- **GIVEN** 环境变量未开启 debug
- **WHEN** Web 服务启动
- **THEN** CLI SHALL 显示 debug disabled
- **AND** DebugHook 不应作为默认运行依赖

### Requirement: Web UI 展示 planning state

Web UI SHALL 接收 `planning_state_updated` 事件，并在 Chat 或 Debug 视图中展示当前计划状态。

#### Scenario: 接收 planning 事件

- **GIVEN** WebSocket 已连接
- **WHEN** 服务端发送 planning state 事件
- **THEN** 前端 SHALL 更新计划展示
- **AND** 不影响普通聊天消息和工具事件展示

### Requirement: Web UI 展示 Plan Document

Web UI SHALL 接收 `plan_document_updated` 和 `plan_document_submitted` 事件，并在 Chat 视图中展示本轮 plan mode 产出的 Markdown Plan Document。

#### Scenario: 接收 Plan Document 事件

- **GIVEN** WebSocket 已连接
- **WHEN** 服务端发送 `plan_document_updated` 或 `plan_document_submitted` 事件
- **THEN** 前端 SHALL 展示 Plan Document 标题和 Markdown 内容
- **AND** SHALL 区分草案和定稿状态
- **AND** SHALL 继续展示 planning state 和最终 assistant 回复

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

### Requirement: Web UI 展示并切换 session mode

Web UI SHALL 展示当前 session mode，并允许用户在现有 session 中切换 mode。当前实现至少保证 mode 切换影响同一 session 的后续 run。

#### Scenario: session 创建后展示 mode

- **GIVEN** WebSocket 创建新 session
- **WHEN** 前端收到 `session_created`
- **THEN** 页面 SHALL 展示该 session 当前 mode

#### Scenario: WebSocket 切换 mode

- **GIVEN** WebSocket 已连接到某个 session
- **WHEN** 前端发送 `set_mode`
- **THEN** 服务端 SHALL 更新该 session 的当前 mode
- **AND** 前端 SHALL 收到 `mode_changed`
- **AND** 之后的 run SHALL 使用新 mode

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

### Requirement: Web UI 命名品牌 wordmark

Web UI SHALL 在 header 中命名当前正式项目名的 wordmark，并在窄屏或图片不可用时保持可读文本降级。

#### Scenario: header 命名品牌

- **GIVEN** 用户打开 Web UI
- **WHEN** 页面静态资源加载完成
- **THEN** header SHALL 命名 Asterwynd wordmark 或等价文本
- **AND** 该命名 SHALL NOT 遮挡 session id、run id、mode 控件、tabs 或状态文本

#### Scenario: 小屏降级

- **GIVEN** 用户在很窄的移动端视口打开 Web UI
- **WHEN** wordmark 图像空间不足
- **THEN** header SHALL 使用可读文本形式命名品牌名

### Requirement: Web UI 回归复用共享测试 LLM harness

Web server、WebSocket 和浏览器回归 SHALL 能通过共享 fake LLM harness 运行，不依赖真实 API key 或模型输出。真实 API 浏览器 E2E MAY 保留为显式 opt-in 验证。

#### Scenario: WebSocket fake LLM smoke

- **GIVEN** Web app 使用共享 fake LLM harness 创建
- **WHEN** 浏览器或测试客户端通过 WebSocket 发送聊天消息
- **THEN** Web session SHALL 通过真实 SessionManager 和 AgentLoop 运行
- **AND** WebSocket SHALL 返回 run event 和 fake assistant 回复

#### Scenario: Playwright fake LLM browser smoke

- **GIVEN** Playwright 打开使用共享 fake LLM harness 的 Web UI
- **WHEN** 用户发送普通消息
- **THEN** 页面 SHALL 展示 fake assistant 回复
- **AND** 测试 SHALL 不需要真实 API key

#### Scenario: Browser smoke 覆盖控制面基础交互

- **GIVEN** Playwright 打开 Web Chat
- **WHEN** 用户输入 slash command 前缀、执行 `/status`、执行 `/clear` 或切换 mode
- **THEN** 页面 SHALL 展示对应 suggestions、command result、消息清理和 mode 变化
- **AND** 这些控制面操作 SHALL NOT 启动普通 Agent run

### Requirement: Web UI SHALL support tool approval requests

Web UI run SHALL 将需要审批的工具调用暴露为 pending approval request，并关联正确的 session 和 run。用户决定 SHALL 被路由回等待中的 AgentLoop instance，然后工具才能被执行或拒绝。每个 Web session 同一时刻 SHALL 只有一个 pending approval。

#### Scenario: Web 用户批准 pending 工具调用

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 用户批准该请求
- **WHEN** 决定被投递给 AgentLoop
- **THEN** AgentLoop SHALL 执行被批准的工具
- **AND** Web UI SHALL 展示该审批已批准

#### Scenario: Web 用户拒绝 pending 工具调用

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 用户拒绝该请求
- **WHEN** 决定被投递给 AgentLoop
- **THEN** AgentLoop SHALL NOT 执行工具
- **AND** Web UI SHALL 展示该审批已拒绝

#### Scenario: 并发 session 的审批路由互相隔离

- **GIVEN** 两个 Web UI session 都有 pending approval request
- **WHEN** 用户处理其中一个请求
- **THEN** 该决定 SHALL 只恢复匹配的 session/run
- **AND** SHALL NOT 影响其他 session 的 pending approval

### Requirement: Web session 本地持久化与恢复

Web session SHALL 在每次 Agent run 结束后持久化到 `<workspace>/.asterwynd/sessions/<session_id>/`（复用 `SessionStore`，与 CLI 同一存储位置），保存消息、mode、todos、skills 和 system prompt。WebSocket 连接 `GET /ws/<session_id>` SHALL 按 session id 恢复：内存命中则复用；未命中则从持久化快照恢复并推送 `session_resumed` 与 `session_history` 事件；快照不可用才新建 session。刷新/重开页面 SHALL 优先回到原 session，不自动新建。Web UI SHALL 提供显式恢复入口（URL `?session=<id>` 与 `GET /resume`）。恢复会话时若带 `?workspace=` 则用该 workspace 的 store 恢复；未带则按确定顺序（主 workspace → allowlist）搜索。Web 默认 host 绑定策略为 `127.0.0.1`，显式 `--host 0.0.0.0` 才开放局域网访问。

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

### Requirement: Web UI 提供 session hub 列表

Web UI SHALL 提供 session 入口页（hub），列出已保存会话并允许按 workspace 切换与新建。hub 通过 `GET /api/workspaces` 获取允许的 workspace 列表，通过 `GET /api/sessions?workspace=<path>` 获取指定 workspace 的会话列表（复用 `SessionStore.list_sessions()` 元数据：session_id、mode、created_at、updated_at、messages）。workspace 不在 allowlist 或路径不存在时 SHALL 返回结构化拒绝（HTTP 403 + `{"error": "workspace_not_allowed"}`）。缺省 `workspace` SHALL 使用主 workspace。

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

#### Scenario: 未带 workspace 恢复时会话归属命中 workspace

- **GIVEN** workspace A 下存在会话快照且未带 workspace 参数
- **WHEN** 浏览器连接 `/ws/<session_id>` 且搜索命中 A 的 store
- **THEN** 恢复的 session SHALL 以 A 为 workspace_root
- **AND** 该 session 后续 run SHALL 仍写入 A 的 store

#### Scenario: 恢复时指定未授权 workspace 被拒

- **GIVEN** 请求 `/ws/<session_id>?workspace=<不在 allowlist 的路径>`
- **WHEN** WebSocket 连接建立
- **THEN** 服务端 SHALL 返回 `{"error": "workspace_not_allowed"}` 事件并关闭连接
- **AND** SHALL NOT 创建或恢复 session

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

Web UI hub SHALL 通过 `DELETE /api/sessions/{session_id}?workspace=<path>` 提供会话删除。删除 SHALL 移除内存中的会话（若在）与指定 workspace store 下的持久化快照；workspace 参数 SHALL 经 allowlist 校验。删除已打开会话时 SHALL 关闭对应标签页。

#### Scenario: 删除会话

- **GIVEN** hub 列表中某会话已被删除请求
- **WHEN** 前端调用 `DELETE /api/sessions/<session_id>?workspace=<path>`
- **THEN** 该会话从内存与磁盘快照移除
- **AND** 列表 SHALL 不再展示该会话
- **AND** 若存在打开的同 id 标签页，该标签页 SHALL 被关闭

#### Scenario: 删除冷会话

- **GIVEN** 某会话未在内存中打开（仅存在磁盘快照）
- **WHEN** 前端调用 `DELETE /api/sessions/<session_id>?workspace=<path>`
- **THEN** 服务端 SHALL 按请求 workspace 定位 store 并删除磁盘快照
- **AND** 返回 `{"deleted": true, "session_id": <id>, "workspace": "<resolved>"}`

#### Scenario: 删除时缺 workspace 参数

- **GIVEN** 前端调用 `DELETE /api/sessions/<session_id>`（无 `?workspace=`）
- **WHEN** 发起删除
- **THEN** 响应 SHALL 返回 HTTP 400 与结构化错误
- **AND** SHALL NOT 删除任何快照

#### Scenario: 删除时未授权 workspace 被拒

- **GIVEN** 请求 `DELETE /api/sessions/<session_id>?workspace=<不在 allowlist 的路径>`
- **WHEN** 前端发起删除
- **THEN** 响应 SHALL 返回 HTTP 403 与结构化错误
- **AND** SHALL NOT 删除任何快照
