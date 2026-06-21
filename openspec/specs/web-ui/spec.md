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
