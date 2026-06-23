# web-ui 规格

## Purpose

定义 Web UI 的 FastAPI 服务、WebSocket 会话、Chat 页面和 Debug 页面。当前实现位于 `web/`。
## Requirements
### Requirement: FastAPI app 提供静态资源和 WebSocket

Web UI SHALL 通过 FastAPI 创建应用，提供静态页面和 WebSocket 交互入口。

#### Scenario: 创建 app

- **GIVEN** CLI 提供 LLM 实例
- **WHEN** 调用 `create_app(llm)`
- **THEN** 系统 SHALL 创建可由 uvicorn 运行的 FastAPI app

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

### Requirement: Chat 视图展示对话和工具过程

Web Chat SHALL 支持用户发送消息，并通过服务端事件展示 agent 回复和工具调用过程。

#### Scenario: 用户发送消息

- **GIVEN** WebSocket 已连接
- **WHEN** 用户提交聊天内容
- **THEN** 服务端 SHALL 触发 AgentLoop
- **AND** 前端 SHALL 接收并展示运行事件

### Requirement: Debug 视图由环境变量控制

Debug 功能 SHALL 通过 `MYAGENT_DEBUG=enabled` 开启；DebugHook SHALL 捕获 before_iteration、after_llm_call、before_tool_execute、after_tool_execute、on_error 和 on_completion 事件。当前 DebugHook 不直接捕获 MemoryManager compact 事件。

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

