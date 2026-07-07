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
