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

Web UI run SHALL 将需要审批的工具调用暴露为 pending approval request，并关联正确的 session 和 run。用户决定 SHALL 被路由回等待中的 AgentLoop instance，然后工具才能被执行或拒绝。每个 Web session 同一时刻 SHALL 只有一个 pending approval。WebSocket 断开 SHALL NOT 让 pending approval 立即失败；重连后服务端 SHALL 补发该卡片（见「pending 提问与审批跨 WebSocket 连接存活」与「重连补发 pending 交互卡片」）。

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

#### Scenario: 断连重连后审批仍可作答

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 浏览器 WebSocket 断开后重连同一 session
- **WHEN** 用户在重连后的页面批准该请求
- **THEN** AgentLoop SHALL 执行被批准的工具
- **AND** Web UI SHALL 展示该审批已批准

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

### Requirement: workflow 运行态流程图视图

Web UI SHALL 在模型触发多 Agent 流程（`StartWorkflow`/`RunWorkflow`/`RunPattern` 驱动的 workflow execution）时自动显示一个 Workflow 视图，SHALL 显示 workflow 的所有节点与边。该视图 SHALL 是用户态能力，SHALL NOT 受 debug 模式门禁约束。

#### Scenario: workflow 启动自动显示图

- **GIVEN** 模型调用 `StartWorkflow` 启动一个 workflow
- **WHEN** `workflow_started` 事件到达前端
- **THEN** Web UI SHALL 自动打开 Workflow 视图
- **AND** SHALL 显示该 workflow 的节点与边

### Requirement: workflow 图快照

scheduler SHALL 提供 `workflow_graph_snapshot()`，返回完整运行期图（nodes + edges + 每节点 status + 每边 status）。该快照 SHALL 基于运行期 `ExecutionPlan`（含自动插层 + foreach 展开），SHALL NOT 改变现有 `_envelope`/`parent_envelope` 的父 Agent 数据契约。快照 SHALL 显式挑选字段（节点不含 `subagent_ids`/`slots`/`raw`，边只含结构字段），SHALL NOT 复用 `NodeState.to_dict()` 直出或整包复用 `_envelope`。

快照 SHALL 额外包含供可读性展示的加法字段：节点 `reason`（**在投影层**截断到与 `summary` 同口径的 bounded 上限；`state.reason` 本体 SHALL NOT 改变，它是 `_envelope` 的字段）、节点 `task`、图级 `started_at`/`finished_at`（**无值统一为 `null`**——构造期哨兵 `0.0` SHALL NOT 直出，否则前端会渲染成 epoch 0）、图级 `budget`、`kind == "foreach"` 节点的 `item_states`/`items_running`/`items_completed`/`items_failed`、以及节点级 `failure_count`（本 run 执行 trace 里的失败步骤数，**三态**：`null` = 没有可用 trace、`0` = 已检查且零失败、`N` = N 条失败；它是**有界整数**，证据正文在 transcript 载荷的`failure_evidence` 里，快照 SHALL NOT 携带证据列表）。既有字段的语义 SHALL NOT 改变。

节点状态 SHALL 支持「**已派发但仍在等执行 slot**」的投影态 `queued`：该值 SHALL 只在图投影层按 run record 的 `status` 派生，SHALL NOT 写入 `NodeState.status`（后者参与调度器收敛判断）。

#### Scenario: 快照包含边与状态

- **GIVEN** 一个运行中的 workflow
- **WHEN** 调用 `workflow_graph_snapshot()`
- **THEN** 返回 SHALL 含 nodes（每节点 status）
- **AND** SHALL 含 edges（每边 status）

#### Scenario: 快照加法字段 bounded

- **GIVEN** 一个节点带超长错误文本的 workflow
- **WHEN** 调用 `workflow_graph_snapshot()`
- **THEN** 节点 `reason` SHALL 被截断到 bounded 上限
- **AND** 快照 SHALL NOT 出现 `subagent_ids`/`slots`/`raw` 等随规模膨胀的字段
- **AND** `_envelope`/`parent_envelope` 契约 SHALL NOT 漂移

#### Scenario: 排队与在跑可区分

- **GIVEN** 一个节点已派发但底层 run 仍在排队等执行 slot
- **WHEN** 调用 `workflow_graph_snapshot()`
- **THEN** 该节点在图上的状态 SHALL 为 `queued`
- **AND** `NodeState.status` SHALL NOT 被写成 `queued`

### Requirement: 节点与边状态高亮

前端 SHALL 按状态高亮节点（pending 灰 / started 蓝 / completed 绿 / failed 红 / cancelled 深灰 / blocked 黄 / budget_exceeded 橙 / skipped 冷灰蓝）。边 SHALL 按状态高亮（inactive / ready / active / passed / blocked / **satisfied**）。route 控制边 SHALL 单列表达（`kind: "control"`），SHALL 只高亮 `targets` 中实际选中的出口。

**边 `satisfied`（依赖已满足但产出未被消费）**：scheduler SHALL 对「`required` 边 + 未被下游消费 + 源 `completed` + 目标已越过 `pending`」判定为 `satisfied`，SHALL NOT 落 `inactive` 兜底。该档表达「这条边确实门控了下游派发，但上游产出没有流过去」——纯顺序依赖（如 foreach 用字面 `items` 而不读 source 产出）SHALL NOT 显示为「没有参与」。`passed` 的语义 SHALL NOT 改变（仍是「上游产出被下游读取」）。

`satisfied` SHALL 与 `inactive`、`passed` 在**非颜色维度**上可分辨（明度差 + 线宽差 + 有无流向箭头），SHALL NOT 仅靠色相区分。目标为 `skipped`（route 未选中）的边 SHALL NOT 判定为 `satisfied`（该边从未门控派发）。

#### Scenario: 节点状态高亮

- **GIVEN** 一个 workflow 有 completed、started、pending 三种状态的节点
- **WHEN** 前端渲染快照
- **THEN** 三种节点 SHALL 分别显示绿色、蓝色、灰色
- **AND** SHALL 直观区分运行状态

#### Scenario: route 分支高亮

- **GIVEN** 一个 route 节点命中某条分支
- **WHEN** 前端渲染快照
- **THEN** SHALL 只高亮该 route 选中的出口控制边
- **AND** 未选中的分支 SHALL 保持 inactive

#### Scenario: 动态 foreach 读取上游产出记 passed

- **GIVEN** 一个 `foreach` 节点以 `source`/`source_field` 从上游节点的产出里解析展开项（**确实读了**上游产出）
- **WHEN** 渲染该数据边
- **THEN** 该边 SHALL 判定为 `passed`，SHALL NOT 判定为 `satisfied`

#### Scenario: 纯门控边不显示为死线

- **GIVEN** 一条 `required` 数据边，其源节点 `completed`、目标节点已因该依赖被放行并越过 `pending`，但目标**没有读取**源的产出（例如 foreach 使用字面 `items`）
- **WHEN** 渲染该边
- **THEN** 该边 SHALL 判定为 `satisfied`，SHALL NOT 判定为 `inactive`
- **AND** SHALL 与「数据被读取」的 `passed` 边在视觉上可分辨

#### Scenario: 未被消费且无门控作用的边仍是 inactive

- **GIVEN** 一条 `required: false` 的边，下游未读取其产出
- **WHEN** 渲染该边
- **THEN** 该边 SHALL 保持 `inactive`（该边从未门控派发，未消费就是真的无关）

#### Scenario: 未选中目标的数据边不染绿

- **GIVEN** 一条 `required` 数据边，其源 `completed`，目标因 route 未选中而 `skipped`
- **WHEN** 渲染该边
- **THEN** 该边 SHALL 保持 `inactive`（决定目标不跑的是控制边，不是这条数据边）
- **AND** SHALL NOT 判定为 `satisfied`

#### Scenario: 等待消费仍是 ready

- **GIVEN** 一条 `required` 边，其源 `completed` 但目标仍为 `pending`
- **WHEN** 渲染该边
- **THEN** 该边 SHALL 判定为 `ready`（等待下游消费的**进行中**态），SHALL NOT 判定为 `satisfied`

### Requirement: workflow 事件通道

WebSocket SHALL 支持 `workflow_started` 与 `workflow_snapshot` 事件。`DeclareWorkflow` SHALL NOT 触发 `workflow_started`（只声明不启动）。断线重连后 SHALL 从 workflow 注册表补发当前快照。

`workflow_started` 的触发点 SHALL 在 `scheduler.run()` 的启动 hook（`agent/subagent/scheduler.py` 的 `_record_event("workflow_started")` 处），SHALL NOT 依赖 `StartWorkflowTool`/`RunWorkflowTool` 的工具层发事件（工具只持有 manager，拿不到 session 事件 sink）。

事件出口 SHALL 是 session 级、跨 run 存活的 sender（`StartWorkflow(wait=false)` 的后台图在父 run 结束后仍 SHALL 能推送快照）。快照推送 SHALL 按时间窗合并（同一 workflow 保留最新一帧，终态立即发送）。

快照推送失败（例如 ws 已断开）SHALL NOT 影响 workflow 的执行状态或节点终态。

#### Scenario: 断线重连恢复快照

- **GIVEN** 一个 workflow 运行中、前端 ws 断线后重连
- **WHEN** 重连完成
- **THEN** 服务端 SHALL 补发当前 workflow 快照（当前 running + 最近 5 张终态，按 `started` 过滤掉仅声明未启动的图）
- **AND** 前端 SHALL 恢复图状态

### Requirement: workflow 图跨端适配

Workflow 视图 SHALL 在桌面（>720px）显示横向 DAG（左→右）、在手机/平板（≤720px）显示纵向 DAG（上→下）。SHALL 支持 pinch 缩放 + pan 平移。50–200 节点 SHALL 折叠 foreach/自动插层（折叠组聚合状态）。

折叠组的展开/收起 SHALL 由**节点详情面板**承担（不再由「点击节点」承担，也不在节点上单独画控件）：点击节点 SHALL 一律打开节点详情面板（见「workflow 节点详情面板」），面板 SHALL 为折叠组组长提供「展开成员 / 收起成员」动作。`max_nodes` 超限 SHALL 表现为「声明期被拒（无图）/ 运行期 `status == "graph_recursion_exceeded"` + `diagnostics`」两种，前端 SHALL NOT 依赖 `nodes.length > 200` 判断超限，也不存在「渲染一张 >200 节点的图再截断」的路径；超限时 SHALL 仍然绘制图并在画布上方叠加告警条（告警条 SHALL 含 `diagnostics.current_nodes` 与 `steps`）。

分层布局、状态映射与折叠归类 SHALL 与 DOM 解耦为可单独测试的纯函数。

#### Scenario: 手机端纵向布局

- **GIVEN** 一个 ≤720px 视口的移动端
- **WHEN** 渲染 workflow 图
- **THEN** SHALL 显示纵向 DAG（根在上、叶在下）
- **AND** SHALL 支持 pinch 缩放与 pan 平移

#### Scenario: 折叠组展开与节点点击语义分离

- **GIVEN** 一个折叠的 foreach 容器节点
- **WHEN** 用户点击该节点
- **THEN** SHALL 打开节点详情面板
- **AND** SHALL NOT 因此展开/收起该折叠组（展开由详情面板中的动作承担）

#### Scenario: 图超限时仍可见

- **GIVEN** 一张运行期超限的图（`status == "graph_recursion_exceeded"`）
- **WHEN** 前端渲染该快照
- **THEN** SHALL 绘制图并在画布上方显示告警条
- **AND** 告警条 SHALL 给出超限原因、超限时仍就绪的节点与已跑 superstep 数

### Requirement: workflow 图图例

Workflow 视图 SHALL 提供常驻可折叠的图例（legend），说明节点类型（`S` subagent / `F` foreach / `R` route / `A` aggregate）、节点状态八档、边状态**六档**与 channel 线型语义。图例 SHALL 在桌面（>720px）默认展开、在手机（≤720px）默认折叠。图例每条目 SHALL 包含人话解释（而非仅状态词）。图例内容 SHALL 与状态词表（颜色/线型/代号/状态名）同源生成。

#### Scenario: 手机端图例可折叠且可见

- **GIVEN** 一个 ≤720px 视口的移动端打开 Workflow 视图
- **WHEN** 图渲染完成
- **THEN** SHALL 显示一行折叠态图例入口（`图例 ▾`）
- **AND** 点击后 SHALL 展开显示节点类型、状态、边状态的完整图例

#### Scenario: 图例与状态词表同源

- **GIVEN** 状态词表（`NODE_COLORS`/`NODE_LABELS`/`EDGE_STYLES`/`KIND_GLYPHS`）发生变化
- **WHEN** 重建图例内容
- **THEN** 图例条目 SHALL 自动反映新词表，SHALL NOT 出现图例与图不一致

#### Scenario: 图例覆盖六档边状态

- **GIVEN** 边状态词表为六档（inactive / ready / active / passed / blocked / satisfied）
- **WHEN** 构建图例内容
- **THEN** 图例 SHALL 含全部六档，SHALL NOT 遗漏 `satisfied`
- **AND** 每档 SHALL 带人话解释（`satisfied` 的解释 SHALL 说明「依赖已满足但产出未被读取」）

### Requirement: workflow 未选中分支状态（skipped）

scheduler 对「只被 route 控制边门控、且没有任何 route 选中它的未派发节点」SHALL 标记为 `skipped`（未选中），SHALL NOT 标记为 `blocked`（被上游连累）。若节点同时满足「被上游失败/取消/受阻连累」与「未被选中」，SHALL 优先记 `blocked`。`skipped` SHALL 是良性终态（不使整图 failed），SHALL 进独立计数桶。

「是否被选中」的判据 SHALL 同时满足以下两条，缺一不可：

1. **控制激活信号为负**：`_has_control_incoming` 且 `activations <= 0`；
2. **已完成控制源的本次选中出口不含本节点**：对每条控制入边，源头 route 已 `completed` 时，本节点 id SHALL NOT 出现在该 route 的 `targets` 中。

条件 2 是必需的：`activations` 会被子树复位（`_reset_subtree`）清零，而回边场景下 route 可能**已经选中并派发过**本节点，仅凭 `activations <= 0` 会把「选过、也跑过」的节点报成 `route did not select this branch`——**用户读到的是假话**。`targets` 是「选没选它」的权威信号（它受发起者豁免保护，不被回边复位清空）。该判据 SHALL NOT 引入新的记账字段（只读既有 `targets`）。

前端 SHALL 用与 `blocked` 明显区分的编码表达 `skipped`（冷灰蓝 + 虚边框 + `—` 角标 + 状态词），图例 SHALL 说明「未选中：条件判断没走这条分支」。

#### Scenario: 未选中的 route 分支记为 skipped

- **GIVEN** 一个 route 节点命中 `APPROVED` 出口，`DEFAULT` 出口的下游节点未被激活
- **WHEN** workflow 正常完成
- **THEN** `DEFAULT` 下游节点 SHALL 标记为 `skipped`，SHALL NOT 标记为 `blocked`
- **AND** 前端 SHALL 以「未选中」语义（非失败、非受阻）展示该节点

#### Scenario: 控制它的 route 从未运行时不报 skipped

- **GIVEN** 一个节点 T 只被 route R 的控制边门控，而 R 自身因某个**未满足的 required 数据依赖**从未运行（R 最终为 `blocked`）
- **WHEN** workflow 收尾
- **THEN** T SHALL 标记为 `blocked`（真因是「R 没跑」，不是「R 没选它」）
- **AND** SHALL NOT 标记为 `skipped`（否则用户读到「条件没走这条」这句假话）

#### Scenario: 被上游连累优先于未选中

- **GIVEN** 一个节点既未被 route 选中，其数据上游又已 `failed`/`cancelled`/`blocked`
- **WHEN** workflow 收尾
- **THEN** 该节点 SHALL 标记为 `blocked`（反映真实阻塞原因），SHALL NOT 标记为 `skipped`

#### Scenario: 被选中且已执行过的节点不得因复位被报 skipped

- **GIVEN** 一张含数据边回边的图：`route` 节点已 `completed` 且其 `targets` 含节点 T，T 因此被派发并执行过；随后子树复位把 T 的 `activations` 清零
- **WHEN** workflow 收尾
- **THEN** T SHALL NOT 被标记为 `skipped`
- **AND** T 的因由 SHALL NOT 为 `route did not select this branch`（route 确实选中了它）

### Requirement: route 数据入边的消费记账

scheduler SHALL 在 route 节点读取数据上游产出（`_route_verdict`）处记录该数据入边已被消费，使该边的状态 SHALL 判定为 `passed`（而非 `inactive`）。记账 SHALL 与既有 per-edge 记账同构（旁加，`_mark_consumed` 本体不改），SHALL NOT 改变 `_consumed_run_ids` 基数或 C5 的 `useful_runs`/`redundancy` 口径。

#### Scenario: route 的上游数据边显示为已消费

- **GIVEN** 一个 route 节点读取了已完成上游节点的产出并据此判定
- **WHEN** 渲染该 route 的数据入边
- **THEN** 该边 SHALL 判定为 `passed`，SHALL NOT 落到 `inactive` 兜底

### Requirement: workflow 图级终态区分「有失败」

scheduler SHALL 在图收敛时按**实际执行结果**区分图级终态，判据按以下优先级（先命中先返回）：

1. 存在**任何**节点 `failed` 且**至少一个**节点 `completed` → `completed_with_failures`
2. **至少一个**节点 `completed` 且无节点 `failed` → `completed`
3. **零**节点 `completed` 且存在节点 `failed` → `failed`
4. **零**节点 `completed` 且**零**节点 `failed`（图根本没跑起来——入口互等 / 全部被挡）→ `stalled`

`completed` SHALL NOT 用于「零节点成功」的收敛：图说「完成」而实际什么都没跑，会让用户不去排查，并让外部消费方（`GetWorkflow` / benchmark / CI）把「图根本没跑起来」判为通过。

`stalled` SHALL 表达「图收敛时没有任何节点成功执行」。`stalled` 对**所有消费方**的语义 SHALL 为**非成功**：消费方 SHALL NOT 用「`status == "failed"` 才算失败」判定整图结果（该写法会把 `stalled` 悄悄算成成功，等于换一种骗法）；判「通过」的消费方 SHALL 要求 `status == "completed"`。`stalled` SHALL NOT 使整图算作 `failed`（二者对用户的行动指引不同：`failed` 指向「哪个节点失败了」，`stalled` 指向「为什么一个都没跑」）。

`completed` 的计数口径 SHALL 为 `status == "completed"` 的**节点**数，SHALL NOT 计入 `skipped`（未选中 ≠ 跑成功），也 SHALL NOT 与快照的 `completed` 计数（来自 `_unit_counts()['completed_units']`，是 `_logical_units` 口径——`foreach` 容器按展开项数计）混用；二者**不同源**。

`budget_exceeded` / `cancelled` / `graph_recursion_exceeded` SHALL 优先于以上四档（预算停与取消是更强的停止原因），SHALL NOT 被 `stalled` 覆盖。

终态集合的**三个副本** SHALL 保持集合相等：

- scheduler 侧 `_SNAPSHOT_TERMINAL_STATUSES`（`agent/subagent/scheduler.py`）
- 前端 `web/static/workflow.js` 的 `TERMINAL_STATUSES`（`pruneGraphs` 的消费方）
- 前端 `web/static/workflow_graph.js` 的 `isGraphTerminal()`（`graphTabMeta` 的计时判据）

任一副本缺失该档，图会被当成 running、永不进入 tab 淘汰池、每次 ws 重连都被补发。

#### Scenario: 有节点失败的图不再报 completed

- **GIVEN** 一张图中某个节点 `failed`，其余节点正常收敛
- **WHEN** workflow 收敛
- **THEN** 图级 status SHALL 为 `completed_with_failures`，SHALL NOT 为 `completed`
- **AND** 视图头 / tab 徽标 SHALL 明确标示「有失败」，SHALL NOT 只显示成功语义

#### Scenario: 全部成功的图仍是 completed

- **GIVEN** 一张图所有节点都 `completed`
- **WHEN** workflow 收敛
- **THEN** 图级 status SHALL 为 `completed`

#### Scenario: 零节点成功的图不得报 completed

- **GIVEN** 一张图的所有节点都未成功（如 `route` 回边的入口互等导致全部 `blocked`，或节点全被上游挡住）
- **WHEN** workflow 收敛且没有任何节点 `completed`
- **THEN** 图级 status SHALL NOT 为 `completed`
- **AND** 无节点 `failed` 时 SHALL 为 `stalled`；有节点 `failed` 时 SHALL 为 `failed`

#### Scenario: stalled 与 budget_exceeded 的优先级

- **GIVEN** 一张图既零节点成功、又因预算耗尽而停
- **WHEN** workflow 收敛
- **THEN** 图级 status SHALL 为 `budget_exceeded`（更强的停止原因）

#### Scenario: stalled 的视觉与文案可分辨

- **GIVEN** 一张图收敛为 `stalled`
- **WHEN** 用户在 tab 与图上查看该图
- **THEN** 前端 SHALL 以与 `completed`（绿）和 `budget_exceeded`（橙）均可分辨的编码表达它
- **AND** tab 徽标 SHALL 显示「停滞（无节点完成）」，图例 SHALL 说明「图收敛时没有任何节点成功执行」
- **AND** 该图 SHALL 立即进入终态 tab 淘汰池（三个副本同步），SHALL NOT 被当成 running

### Requirement: workflow 节点异常态语义表达

Workflow 视图 SHALL NOT 仅靠颜色区分节点状态。非成功状态（`failed` / `blocked` / `budget_exceeded` / `cancelled`）SHALL 至少以颜色 + 形状/角标 + 状态词三重编码表达。视图 SHALL 为异常节点提供「为什么是这个状态」的因果说明（如 `blocked` 指明被哪个上游失败挡住、`budget_exceeded` 指明预算维度）。因果说明 SHALL 可在节点上或详情面板中看到，SHALL NOT 仅依赖在移动端不显示的 `<svg:title>`。

节点因由 SHALL 指向该节点**未执行或未成功的真实成因**，SHALL NOT 用一句无区分度的兜底文案覆盖多种成因。至少 SHALL 区分：

- **图级闸门触发**（`max_routes` / `recursion_limit` / `max_nodes` / `max_runs`）：因由 SHALL 含闸门名与被牵连的事实（例：`图级闸门 max_routes 触发（…超过上限 2），本节点未派发`）
- **入边互相等待**（无图级闸门，节点因入边永远不就绪而未派发）：因由 SHALL 说明是「入边互等/永远未就绪」，SHALL NOT 表达为「工作流提前结束」——后者读起来像外部原因、被动受牵连，而真实成因是结构性的

注入的图级诊断文本 SHALL bounded（与 `summary` 同口径截断）。`state.reason` 本体的语义 SHALL NOT 改变（它是 `_envelope` 的字段，被截断的投影只发生在出口层）。

**用户可见性**：上述因由 SHALL 真正出现在用户看到的那句话里。前端因果合成（`explainNode()`）对 `blocked` 节点的取因顺序 SHALL 让**节点自身的具体因由**（含图级闸门信息的 `reason`）优先于泛化的图级停止文案（如「流程因图超限被停止，该节点没来得及执行」）；具体因由缺失时才 SHALL 回退到泛化文案。「后端写了但因前端优先级遮蔽而用户看不到」SHALL NOT 被视为满足本 Requirement。

#### Scenario: 区分 failed 与 blocked

- **GIVEN** 一张图同时存在 `failed`（红）与 `blocked`（黄）节点
- **WHEN** 用户查看该图（含色觉障碍或灰度屏场景）
- **THEN** 两者 SHALL 通过形状/角标或状态词区分，SHALL NOT 仅靠色相
- **AND** `blocked` 节点 SHALL 指明其被上游失败挡住或预算/流程原因未执行

#### Scenario: 预算超限节点的因果

- **GIVEN** 一个 foreach workflow 触发预算超限，图中出现 `failed`/`blocked`/`budget_exceeded` 混合状态
- **WHEN** 用户查看这些异常节点
- **THEN** 每个异常节点 SHALL 显示对应的人话因果（自身失败原因 / 被上游挡住 / 预算超限）
- **AND** 用户 SHALL 能分清「自己失败」「被挡住没跑」「预算停下」三种语义

#### Scenario: 图级闸门停下时节点因由说明真因

- **GIVEN** 一张图因 `max_routes` 闸门而停（`diagnostics.reason == "max_routes"`）
- **WHEN** 用户查看被牵连节点（含详情面板与节点上的因果说明）
- **THEN** 用户看到的因由 SHALL 指明是图级闸门 `max_routes` 导致未派发，SHALL NOT 仅为「workflow ended before the node became ready」或泛化的「流程因图超限被停止」

#### Scenario: 无图级闸门的死锁也要说明真因

- **GIVEN** 一张图因 `route` 回边的入口互等而死锁（**无任何图级闸门触发**、`diagnostics` 为空）
- **WHEN** 用户查看该节点的因由
- **THEN** 因由 SHALL 说明是「入边互相等待、永远未就绪」，SHALL NOT 仅为「workflow ended before the node became ready」

### Requirement: workflow 节点详情面板

Workflow 视图 SHALL 支持点击任意节点打开节点详情面板。详情 SHALL 包含该节点的 id、kind、status、因果说明、起止/耗时、runs 次数、task 与产出 summary。面板 SHALL 在桌面（>720px）以右侧抽屉、在手机（≤720px）以底部抽屉呈现（同一 DOM，按断点切换）。面板 SHALL 提供 `role="dialog"` + `aria-modal` + focus trap + Esc/遮罩/关闭按钮三种关闭方式，开合 SHALL NOT 改变图的 viewBox。点击节点的语义 SHALL 与折叠组展开/收起分离（见「workflow 图跨端适配」的 MODIFIED 口径）。

#### Scenario: 点节点打开详情

- **GIVEN** 一张已渲染的 workflow 图
- **WHEN** 用户点击任意非容器节点
- **THEN** SHALL 打开该节点的详情面板并显示其状态、因果说明与元信息
- **AND** 桌面端 SHALL 从右侧滑入、手机端 SHALL 从底部滑入

### Requirement: workflow 节点 transcript 只读接口

Web 服务 SHALL 提供只读接口 `GET /api/sessions/{session_id}/workflows/{workflow_id}/nodes/{node_id}/transcript`，复用 `SubAgentManager.inspect_transcript()`，按节点的**对话形态**返回三态之一：`single`（1 个对应 subagent：`subagent` / `aggregate(strategy="llm")` / 自动插层聚合）、`candidates`（foreach 容器，N 个展开项）、`none`（`route` / `aggregate(strategy="collect")` / 从未派发的节点——这些节点不产生 run）。接口 SHALL bounded（条数上限 + 单条内容截断 + 候选集分页上限），SHALL 默认排除工具结果。接口 SHALL NOT 调用 LLM、写盘或改变 workflow 执行状态。

`candidates` 的候选集 SHALL 以 index 空间（`item_states`）为索引源且保持完整，SHALL NOT 依赖可能稀疏的 `subagent_ids`；每条候选 SHALL 含 `index`/`subagent_id`/`run_id`/`status`/`task`/`reason`/`summary`。三个形态 SHALL 返回 scheduler 侧 `reason` 的**全文**（附 `reason_truncated` 布尔标志——前端比长度会把恰好等于上限的 reason 误判成已截断）。

#### Scenario: 读取单 subagent 节点的 transcript

- **GIVEN** 一个已执行、恰好对应 1 个 subagent 的节点（普通节点 / LLM 聚合 / 自动插层聚合）
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回 `kind: "single"` 与该节点的 messages（bounded）与 `truncated` 标志
- **AND** SHALL NOT 触发任何 LLM 调用或状态变更

#### Scenario: foreach 容器返回候选集

- **GIVEN** 一个 foreach 容器节点（N 个展开项各自独立 subagent，且 N>1）
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回 `kind: "candidates"` 与至多 `limit` 条候选（每条含 `index`/`subagent_id`/`run_id`/`status`/`task`/`reason`/`summary`），附 `total`/`has_more`
- **AND** 用户点某一项后 SHALL 能按该项的 `subagent_id` 取到该项自己的 transcript，SHALL NOT 混入同容器其它项的 messages
- **AND** 被取消/失败的展开项 SHALL 仍出现在候选集里

#### Scenario: 不产生 run 的节点优雅降级

- **GIVEN** 一个 `route` 节点、一个 `strategy="collect"` 的聚合节点，或一个从未派发的 `pending`/`blocked` 节点
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回 `kind: "none"` 与结构化说明（route 附命中标签与选中出口、collect 附合并产出、未派发节点说明未执行）
- **AND** SHALL NOT 编造 transcript

前端 SHALL 在切到「对话」tab 时才请求（懒加载），SHALL 按**定死的刷新节律**按需重取（节点已到终态或用户暂停后 SHALL NOT 再重取），且对话区 SHALL 提供暂停/继续实时更新的动作。transcript 的渲染 SHALL 按行聚簇做 UI 虚拟化（SHALL NOT 按行建 DOM）。

#### Scenario: 对话内容的刷新与暂停

- **GIVEN** 一个仍在运行的节点，用户已切到该节点的「对话」tab
- **WHEN** 达到刷新节律
- **THEN** SHALL 重取该节点的 transcript
- **AND** 用户点「暂停实时更新」后 SHALL NOT 再重取（节点到终态后同样不再重取）

### Requirement: workflow 节点失败证据只读投影

Web 服务的 workflow 节点 transcript 只读接口 SHALL 在同一个载荷中以键名 `failure_evidence` 提供该 run 的**失败证据**投影（bounded）——`candidates` 容器形态下该键 SHALL 挂在**每个候选**上而不是容器顶层（容器没有单一的 run，见下方该 Scenario），数据来源 SHALL 是该 run 的执行 trace（`run.trace.steps`）中 `status` 不为 `ok` 的 `tool_result` step 与全部 `llm_error` step；该投影 SHALL NOT 新增采集、SHALL NOT 调用 LLM、SHALL NOT 写盘或改变 workflow 执行状态。

`failure_evidence` SHALL 含 `state`（节点级状态枚举）、`total`（**真实失败总数**，不是返回条数）、`truncated`（布尔，`total` 是否大于返回条数）、`message`（可读原因文案）与 `items`（条目列表）。

`state` 的取值集合 SHALL 为且仅为：`present`、`clean`、`running`、`empty_trace`、`no_trace`、`unavailable`、`not_applicable`。该枚举 SHALL NOT 把「没有 trace」与「trace 里没有失败步骤」折叠成同一个取值——用户在后者可以放心，在前者不能；`not_applicable`（结构上不可能产生 run）SHALL NOT 与 `unavailable`（本该有 run 但取不到）折叠。

`items` 的每条 SHALL 含 `type`（`tool_result` 或 `llm_error`）、`step`（trace 步骤序号）、`status`、`error_type`、`tool_name`（`llm_error` 条目为 `null`）、`text_truncated`（布尔），并按条目类型二选一携带文本：`tool_result` 条目 SHALL 用 `observation`，`llm_error` 条目 SHALL 用 `message`。`llm_error` 的 trace step 不携带 `status` 字段，其条目 `status` SHALL 由投影固定为 `"error"`。

投影 SHALL bounded：`items` 只含**最近** `N` 条失败条目（按 trace 步骤序号），且每条的可变长文本 SHALL 不超过节点 transcript 的单条内容上限（`content_limit`），超出 SHALL 置 `text_truncated` 为 `true` 并把文本截到该上限。「是否被截断」SHALL 由 `truncated` 标量给出，使调用方不必靠长度比较推断。

被截断或不可用时 SHALL 给出**可读的原因文案**（`message`），SHALL NOT 只给空列表或 `null`。

该投影 SHALL NOT 改变前端取数时机：前端 SHALL 保持「切到『对话』tab 才请求该载荷」的懒加载行为。

#### Scenario: run 完成但中途有工具失败

- **GIVEN** 某个 subagent run 已到终态 `completed`，其 trace 中存在 `status` 为 `error` 的 `tool_result` step（例如一次失败的 `Bash`）
- **WHEN** 请求该节点的 transcript
- **THEN** 载荷 SHALL 携带 `failure_evidence`，其 `state` SHALL 为 `present`
- **AND** 每条条目 SHALL 至少包含 `tool_name`、`step`、`status` 与 `error_type`
- **AND** 条目的变长文本 SHALL 不超过单条内容上限，超出时 SHALL 置 `text_truncated` 为 `true`

#### Scenario: trace 存在且没有任何失败步骤

- **GIVEN** run 已到终态，其 trace 存在且 `steps` 非空，但没有任何 `status` 不为 `ok` 的 `tool_result`、也没有 `llm_error`
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `clean`（「已检查、未发现失败」），SHALL NOT 为 `no_trace`
- **AND** `items` SHALL 为空，且 SHALL 带一个说清「已检查过」的 `message`

#### Scenario: run 仍在运行

- **GIVEN** run 尚未到终态（trace 按设计只在终态写入）
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `running`（「运行中，尚无失败证据」），SHALL NOT 为 `clean`
- **AND** SHALL NOT 因 trace 为 `None` 而报 `no_trace`

#### Scenario: run 到终态但从未记录 trace

- **GIVEN** run 已到终态，且 `run.trace` 为 `None`
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `no_trace`（「未记录执行 trace」），SHALL NOT 为 `clean`
- **AND** `message` SHALL 说明这是「没有采集到」而不是「采集到了、是空的」

#### Scenario: trace 存在但该 run 没有执行过任何步骤

- **GIVEN** run 已到终态，其 trace 存在但 `steps` 为空（run 在排队阶段被取消、或取消路径新建了空 trace）
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `empty_trace`（「该 run 未执行任何步骤」），SHALL NOT 为 `no_trace`、SHALL NOT 为 `clean`
- **AND** 该取值 SHALL 与 `no_trace` 是两个不同的取值

#### Scenario: 解析不到该节点的 run 记录

- **GIVEN** 节点本该有 run，但对应 run 记录已不在 session 的 runs 列表里（例如被队列上限拒绝而弹出），或节点尚未派发
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `unavailable`（「无法解析该 run」），SHALL NOT 为 `clean`
- **AND** 该取值 SHALL 与 `no_trace` 是两个不同的取值

#### Scenario: 结构上不可能产生 run 的节点

- **GIVEN** 该节点是 route 节点，或是 `aggregate(strategy="collect")` 纯逻辑聚合节点
- **WHEN** 请求该节点的 transcript
- **THEN** `state` SHALL 为 `not_applicable`，SHALL NOT 为 `unavailable`
- **AND** `message` SHALL 说明该节点类型不产生 run

#### Scenario: 失败条目超过上限

- **GIVEN** 某 run 的 trace 中有多于 `N` 条失败步骤
- **WHEN** 请求该节点的 transcript
- **THEN** `items` 的条数 SHALL 不超过 `N`
- **AND** `total` SHALL 为**真实失败总数**（大于返回条数），且 `truncated` SHALL 为 `true`
- **AND** 返回的条目 SHALL 是**最近**的 `N` 条（按 trace 步骤序号），显示顺序 SHALL 为时间正序

#### Scenario: 候选集形态只带轻量证据

- **GIVEN** 某个 foreach 容器节点展开出多个候选，每个候选各自有 run
- **WHEN** 请求该容器节点的 transcript
- **THEN** 每个候选 SHALL 各自携带 `failure_evidence`，且其为**轻量**形态：`state` / `total` / `truncated` 齐全，`items` SHALL 至多 1 条最新失败条目且该条文本 SHALL 不超过 400 字符
- **AND** 候选项下钻（指名 `subagent_id`）时，载荷顶层的 `failure_evidence` SHALL 为**完整**形态（最近 `N` 条 × 单条内容上限），SHALL NOT 被轻量上限约束

### Requirement: workflow 多图与 foreach 可读性

Workflow 视图的多图 tab SHALL 显示可区分不同运行的元信息（序号 + 起止/相对时间 + 耗时 + 完成计数）。`#N` SHALL 是按图级 `started_at` 排序的秩，且 tab 的空间顺序 SHALL 与编号一致（运行中 SHALL 用徽标而非位置区分）；`started_at` 缺失的图 SHALL 排在最后。foreach 容器节点 SHALL 常显并行计数（`完成 M/N`，缺失信息时退化为项数）并表达并行项的状态分布。图的统计行 SHALL 如实反映实际绘制的边数，SHALL 在存在同对节点并行边或折叠合并时给出可解释的口径差异；同一对节点的多条可见边 SHALL 在法向等距铺开，SHALL NOT 完全重合。

#### Scenario: 区分多次运行

- **GIVEN** 同一 session 内模型启动了 3 次 workflow
- **WHEN** 用户查看多图 tab
- **THEN** 每个 tab SHALL 显示序号、时间与完成计数等可区分信息
- **AND** 用户 SHALL 能判断「第几次 run」「何时起」「结果差异」

#### Scenario: foreach 并行可见

- **GIVEN** 一个 foreach 容器节点（含 N 个并行项）
- **WHEN** 渲染该节点（无论是否折叠）
- **THEN** SHALL 常显「完成 M/N」计数并表达项的状态分布

#### Scenario: 边统计与可见线条一致

- **GIVEN** 一个图有 11 条边，其中若干为同一对节点的并行边 / 被折叠合并
- **WHEN** 渲染统计行
- **THEN** SHALL 显示实际绘制的路径数
- **AND** 存在差异时 SHALL 给出可解释口径（如原始边数）

### Requirement: workflow 运行过程可见性与取消

Workflow 视图 SHALL 为运行中的节点显示本地跳动的耗时，SHALL 显示图的「最后更新于 N 秒前」以区分「慢」与「死」；这两者 SHALL 由独立于快照到达的本地计时器驱动，SHALL NOT 只在快照到达时更新。

Web 服务 SHALL 支持经 WebSocket 消息 `cancel_workflow` 取消一张正在运行的图，`reset` SHALL 在替换会话前取消该会话内所有在跑的图。取消 SHALL 与既有 `{"type":"cancel"}` 的消息语义区分（后者只让待审批失败、不停止 run）。

#### Scenario: 运行中的节点耗时跳动

- **GIVEN** 一个节点处于 `started` 状态且没有新快照到达
- **WHEN** 用户在 Workflow 视图停留观察
- **THEN** 该节点的耗时 SHALL 按秒继续增长
- **AND** 节点进入终态后耗时 SHALL 冻结为起止之差

#### Scenario: 取消运行中的图

- **GIVEN** 一张正在运行的图
- **WHEN** 用户经 WebSocket 发送 `cancel_workflow`
- **THEN** 该图的 scheduler SHALL 收到取消
- **AND** `reset` 场景下 SHALL NOT 留下仍在后台继续跑的图

### Requirement: pending 提问与审批跨 WebSocket 连接存活

Web session SHALL 把「运行中等待用户响应的 pending 提问/审批」当作 session 级状态，而不是某条 WebSocket 连接的状态。WebSocket 断开 SHALL NOT 让仍在等待用户响应的 pending 提问/审批失败；服务端 SHALL NOT 因断开而返回 `[Error: websocket disconnected]` 之类的失败答复给 AgentLoop。

pending 状态 SHALL 由 `WebQuestionHandler` / `WebApprovalHandler` 在建立时保留完整的可重放载荷（提问的 `title`/`body`/`options`、审批的 `tool_name`/`risk`/`redacted_args` 等 `to_event_data()` 全部字段），供重连补发使用。

#### Scenario: 切后台断连不判定 pending 审批失败

- **GIVEN** 一个 Web session 有 pending approval request，AgentLoop 正在等待用户决定
- **WHEN** 浏览器 WebSocket 断开（移动端切后台）
- **THEN** pending approval SHALL 保持有效，SHALL NOT 被判定为 `unavailable`
- **AND** AgentLoop SHALL 继续等待用户响应，SHALL NOT 收到 `websocket disconnected` 失败

#### Scenario: 切后台断连不判定 pending 提问失败

- **GIVEN** 一个 Web session 有 pending question，AgentLoop 正在等待用户作答
- **WHEN** 浏览器 WebSocket 断开
- **THEN** pending question SHALL 保持有效，SHALL NOT 被判定为超时或失败

### Requirement: 重连补发 pending 交互卡片

WebSocket 重连（`GET /ws/<session_id>` 命中同一内存 session）时，服务端 SHALL 在推送 `session_resumed` 与 `session_history` 之后，补发当前仍然 pending 的交互卡片事件：pending question 补发 `user_question`，pending approval 补发 `approval_request`。补发的载荷 SHALL 与首次发出时一致，并 SHALL 带上 `session_id` 字段。

补发 SHALL 排在 `session_history` 之后（前端收到 `session_history` 会整体重绘消息区）。

已作答、已超时、已被拒绝或已取消的请求 SHALL NOT 被补发。

#### Scenario: 重连后补发 pending 提问卡片

- **GIVEN** 一个 Web session 有 pending question，客户端 WebSocket 断开后重新连上同一 session
- **WHEN** 服务端完成 `session_resumed` 与 `session_history` 推送
- **THEN** 服务端 SHALL 补发一条 `user_question` 事件，`question_id` 与该 pending question 一致
- **AND** 前端 SHALL 重新渲染提问卡片，用户 SHALL 能提交答案

#### Scenario: 重连后补发 pending 审批卡片

- **GIVEN** 一个 Web session 有 pending approval request，客户端 WebSocket 断开后重新连上同一 session
- **WHEN** 服务端完成 `session_resumed` 与 `session_history` 推送
- **THEN** 服务端 SHALL 补发一条 `approval_request` 事件，`approval_id` 与该 pending approval 一致
- **AND** 用户 SHALL 能批准或拒绝，决定 SHALL 被路由回等待中的 AgentLoop

#### Scenario: 没有 pending 时不补发

- **GIVEN** 一个 Web session 没有 pending 提问也没有 pending 审批
- **WHEN** 客户端重连该 session
- **THEN** 服务端 SHALL NOT 发送 `user_question` 或 `approval_request` 事件

### Requirement: pending 交互的放弃语义

pending 审批 SHALL 有显式超时：等待时长 SHALL 由配置项 `WebConfig.approval_timeout_seconds` 决定（缺省 600 秒），从 pending 建立时开始计时，连接断开与保持 SHALL NOT 影响计时。超时且仍无用户响应时，服务端 SHALL 判定为失败（`ApprovalDecisionStatus.UNAVAILABLE`，fail-closed）并让 AgentLoop 继续。

提问保留既有超时，等待时长 SHALL 由配置项 `WebConfig.question_timeout_seconds` 决定（缺省 300 秒），该超时 SHALL NOT 因 WebSocket 断开而重置或提前。

会话被显式重置（`reset`）或取消（`cancel`）、或 run 真正结束时，pending SHALL 立即失败（保持既有语义）。

#### Scenario: 超时窗口内断连后仍可作答

- **GIVEN** 一个 Web session 有 pending approval，WebSocket 断开
- **WHEN** 用户在超时窗口内重连并提交决定
- **THEN** 该决定 SHALL 被接受并路由回 AgentLoop
- **AND** AgentLoop SHALL 按该决定执行或拒绝工具

#### Scenario: 超过超时窗口判定失败

- **GIVEN** 一个 Web session 有 pending approval，WebSocket 断开且用户始终未重连
- **WHEN** `approval_timeout_seconds` 到期
- **THEN** pending approval SHALL 被判定为 `unavailable`
- **AND** AgentLoop SHALL 收到失败答复并继续运行，SHALL NOT 永久挂起

#### Scenario: 超时时长可配置

- **GIVEN** 配置中将 `approval_timeout_seconds` / `question_timeout_seconds` 设为某正整数
- **WHEN** pending 审批或提问建立
- **THEN** 其超时窗口 SHALL 按该配置值生效
- **AND** 非法值（0 / 负数 / 非整数）SHALL 被拒绝并给出结构化错误

#### Scenario: reset 或 cancel 立即失败

- **GIVEN** 一个 Web session 有 pending 提问或审批
- **WHEN** 收到 `reset` 或 `cancel`
- **THEN** pending SHALL 立即被判定为失败
- **AND** SHALL NOT 等待超时窗口到期

#### Scenario: 多连接首答者胜

- **GIVEN** 一个 Web session 有多条连接且存在 pending 审批
- **WHEN** 两条连接先后提交了不同的决定
- **THEN** 先提交的决定 SHALL 胜出并路由回 AgentLoop
- **AND** 后提交者 SHALL 收到 `unavailable`，SHALL NOT 覆盖先到的决定
- **AND** 作答成功后所有连接 SHALL 收到该审批的终态事件

#### Scenario: 各作答路径的终态广播行为一致

- **GIVEN** 一个 Web session 有多条连接，存在 pending 审批
- **WHEN** 一条连接提交决定，无论 run 是否仍在执行
- **THEN** 所有连接 SHALL 收到一致的终态事件
- **AND** SHALL NOT 出现「run 存活广播、run 不存活只回提交者」的不一致

「被接受的决定」与「被拒绝的回执」区分对待，两条路径 SHALL 一致地遵循同一规则：被接受的
决定（先答者胜出的那次）SHALL 广播给所有连接；被拒绝的回执（提交时已无匹配 pending，
status `unavailable`）SHALL 只回提交者，SHALL NOT 广播——它表示「你这条提交没有生效」，
不是该审批的状态变更，广播会违背终态单调（会把已收到终态的胜出方卡片改写成 `unavailable`）。

### Requirement: run 事件出口跨连接存活

Web session 的 run 事件出口 SHALL 是 session 级、与单条 WebSocket 连接解耦的：WebSocket 断开 SHALL 只解绑该连接，SHALL NOT 终止正在执行的 run。断连期间 run SHALL 继续执行；重连 SHALL 把新连接绑上同一个出口，之后产生的事件 SHALL 送达当前所有已绑定连接。

同一 session 存在多条已绑定连接（多 tab / 多设备）时，run 事件 SHALL 广播给全部连接；某条连接断开 SHALL NOT 影响其他连接继续接收。

断连期间无人接收的事件 SHALL 允许丢弃（该期间的消息历史由重连后的 `session_history` 兜底）。

#### Scenario: 断连不终止运行中的 run

- **GIVEN** 一个 Web session 的 run 正在执行
- **WHEN** WebSocket 断开
- **THEN** run SHALL 继续执行
- **AND** 重连后 SHALL 能继续收到该 run 的后续事件

#### Scenario: 多连接广播

- **GIVEN** 一个 Web session 有两条已绑定的 WebSocket 连接
- **WHEN** run 产生事件
- **THEN** 两条连接 SHALL 都收到该事件
- **AND** 其中一条断开后另一条 SHALL 继续收到后续事件

#### Scenario: 断连期间没有 pending 时 run 可正常跑完

- **GIVEN** 一个 Web session 的 run 正在执行且没有 pending 交互
- **WHEN** WebSocket 断开且 run 在断连期间完成
- **THEN** run SHALL 正常结束并释放 session 的 run 锁
- **AND** 重连后 SHALL 通过 `session_history` 看到完整消息历史

#### Scenario: run 进行中断连重连后发新消息被拒

- **GIVEN** 一个 Web session 的 run 因断连仍在后台执行
- **WHEN** 用户重连后在页面发送新消息
- **THEN** 服务端 SHALL 拒绝该 run（同一 session 并发 run 被拒）
- **AND** SHALL 把拒绝错误只回发起连接，SHALL NOT 广播到其他连接
- **AND** 前端 SHALL 给出用户可读的提示

### Requirement: 前端交互卡片幂等渲染

前端 SHALL 按 `question_id` / `approval_id` 幂等渲染交互卡片：同一 id 的卡片事件重复到达时 SHALL NOT 产生第二张卡片，SHALL 复用已存在的卡片。

前端收到 `session_history` 整体重绘消息区时 SHALL 清理该会话的卡片注册表，避免留下指向已移除 DOM 的条目。

交互卡片提交时若 WebSocket 未处于 OPEN 状态，前端 SHALL 给出可见反馈并保留卡片可提交（SHALL NOT 静默丢弃用户的决定）。

#### Scenario: 重复卡片事件不产生第二张卡片

- **GIVEN** 前端已经渲染了某个 `approval_id` 的审批卡片
- **WHEN** 服务端因重连补发再次推送同一 `approval_id` 的 `approval_request`
- **THEN** 消息区 SHALL 只有一张该 `approval_id` 的卡片
- **AND** 该卡片 SHALL 可正常提交决定

#### Scenario: ws 未就绪时提交不被静默丢弃

- **GIVEN** 前端渲染了提问卡片但 WebSocket 尚未重连完成
- **WHEN** 用户提交答案
- **THEN** 前端 SHALL 给出可见反馈（例如提示连接未就绪）
- **AND** 卡片 SHALL 保持可提交状态，用户 SHALL 能在重连后再次提交

### Requirement: 回边重跑不得清空本次派发的发起者

当 `route` 节点完成并派发下游时，若下游完成触发的子树复位沿**数据边回边**递归走回该 `route` 自身，复位 SHALL NOT 清空该 `route` 刚写入的执行结果（`status` / `targets` / `summary` / `verdict`）。

发起者豁免 SHALL 只豁免**本次派发链的发起者**这一个节点，SHALL NOT 停止复位的传播——回边环上的其它节点 SHALL 仍按既有语义重跑。

复位 SHALL 仍然让环上的其它节点按既有语义重跑（清 `reason` / `error` / `summary` / `finished_at` / `status` / `activations` / `verdict` / `targets`），SHALL NOT 因本豁免而减少任何清理项。

#### Scenario: 数据边回边不清空发起者

- **GIVEN** 一张图含回边 `body → cycle_gate`（`body` 为聚合节点，即该边为**数据边**）
- **WHEN** `cycle_gate` 完成并派发 `body`，`body` 完成触发子树复位
- **THEN** `cycle_gate` 的 `status` SHALL 保持 `completed`，SHALL NOT 被复位成 `pending`
- **AND** `cycle_gate` 的 `targets` SHALL 保持其选中的出口，SHALL NOT 为空
- **AND** 该 `route` 选中的控制边 SHALL 判为 `passed`，SHALL NOT 为 `inactive`


### Requirement: 多标签页瞬态交互状态按标签页隔离

Web UI 的**瞬态交互状态**（以 slash 建议列表为代表：随输入实时出现/收起、不进入消息历史的 UI 状态）SHALL 按标签页归属。任一标签页的输入框失焦、定时器回调或其他异步事件 SHALL NOT 改变**其他**标签页的瞬态 UI 状态。

切换标签页 SHALL 使目标标签页的 slash 建议可见性收敛到**由该标签页自身的输入内容与命令匹配结果所决定**的状态：输入框内容匹配到命令时可见，否则收起。该收敛 SHALL 由「切换」这一动作触发，SHALL NOT 依赖切换动作的墙钟时序（例如「切走与切回之间的间隔是否超过某个宽限期」），也 SHALL NOT 因同一标签页内的按键处理而触发。

收敛 SHALL NOT 因**同一标签页内的按键处理**而触发：`input` / `keydown` 处理器会调切换入口，但那是「确保当前标签页处于活跃状态」，不是切换，SHALL NOT 借机重算可见性。

用户按 `Enter` 时的意图判定 SHALL 以「应用建议项是否为空操作」为准，而 SHALL NOT 仅以「列表当前是否可见」为准：当被选中的建议项的插入文本与输入框现有内容相同时（例如 `/status`），`Enter` SHALL 发送消息，SHALL NOT 把它重填一遍并吞掉发送。列表可见本身不表示用户想选它——收敛会让列表重新可见（见「收起后切走再切回」Scenario），而用户此前可能已经用 `Escape` 表达过「不从列表里选」。

既有「Web UI 支持多标签会话」Requirement 覆盖的是**消息历史与运行状态**的隔离，不覆盖瞬态 UI 状态；本条补充后者。

#### Scenario: 切入再切回不丢失本标签页的建议

- **GIVEN** 标签页 A 的输入框内容为 `/s` 且其 slash 建议可见
- **AND** 标签页 B 已打开
- **WHEN** 用户切到标签页 B 后切回标签页 A
- **THEN** 标签页 A 的 slash 建议 SHALL 可见
- **AND** 该结果 SHALL 在**切走时挂起的延迟收起动作已经执行之后**仍然成立
  （即断言点必须落在内部宽限期之后；仅断言「切回瞬间可见」不足以覆盖本 Scenario，
  因为挂起的收起动作可能尚未触发，坏实现也能读到可见）

#### Scenario: 非活跃标签页的失焦不干扰活跃标签页

- **GIVEN** 标签页 A 与标签页 B 各自输入过内容，标签页 B 的 slash 建议可见
- **WHEN** 一个属于标签页 A 的失焦事件在标签页 B 为活跃标签页之后才被处理
- **THEN** 标签页 B 的 slash 建议 SHALL 保持可见
- **AND** 标签页 A 的失焦 SHALL NOT 收起标签页 B 的建议列表

#### Scenario: 收起后切走再切回按输入内容重新判定

- **GIVEN** 标签页 A 的输入框内容为 `/s` 且其 slash 建议**已被收起**
- **WHEN** 用户切到标签页 B 后再切回标签页 A
- **THEN** 标签页 A 的 slash 建议 SHALL 按输入内容重新判定为**可见**
- **AND** 该行为 SHALL 区别于「切回后仍保持收起」的实现

#### Scenario: 同标签页内按键不触发收敛

- **GIVEN** 某标签页的输入框内容匹配到命令且建议可见
- **WHEN** 用户按 `Escape` 收起建议后按 `Enter`
- **THEN** `Enter` SHALL 发送消息（该输入 SHALL 作为普通消息进入消息历史）
- **AND** SHALL NOT 被解释为「应用建议项」而吞掉发送

#### Scenario: 收敛重新展开的列表不劫持发送

- **GIVEN** 某标签页的输入框内容为 `/status`，用户曾按 `Escape` 收起其建议
- **WHEN** 用户切到另一标签页后切回（列表按输入内容收敛为可见），然后按 `Enter`
- **THEN** `Enter` SHALL 发送消息
- **AND** SHALL NOT 因「被选中的建议项插入文本与输入框内容相同」而吞掉发送

#### Scenario: 关闭当前活跃标签页后被切到的标签页按输入内容收敛

- **GIVEN** 标签页 A 与标签页 B 均已打开，B 的输入框内容为 `/s` 且其 slash 建议**已被收起**
- **WHEN** 用户切到标签页 A 并将 A（当前活跃标签页）关闭
- **THEN** 被切到的标签页 B 的 slash 建议 SHALL 按其自身输入内容重新判定为**可见**
- **AND** 该行为 SHALL 区别于「关闭后停在未收敛的收起状态」的实现

关闭当前活跃标签页会走到「切换到下一个标签页」的路径；本条约束该路径同样执行收敛。
