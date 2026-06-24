# tui 规格

## Purpose

定义未来 Claude Code 风格终端 UI 的能力边界、入口约束和与现有核心运行时的关系。当前仓库尚未实现 TUI。
## Requirements
### Requirement: TUI 当前为预留能力域

系统 SHALL NOT 声称已经支持独立 TUI、终端多面板、实时工具流展示或键盘交互式计划管理。

#### Scenario: 当前用户入口

- **GIVEN** 用户使用当前仓库
- **WHEN** 查看可用入口
- **THEN** 系统 SHALL 只提供当前 CLI、Web 和 benchmark 入口
- **AND** 不提供 TUI 命令

### Requirement: 未来 TUI 必须复用核心语义

未来 TUI SHALL 复用 AgentLoop、工具事件、planning 状态和 session 语义，不得另起一套不兼容运行协议。

#### Scenario: 准备实现 TUI

- **GIVEN** 需求提出终端 UI
- **WHEN** 创建 OpenSpec change
- **THEN** change SHALL 描述与 CLI、Web、planning 和 tool-system 的共享边界

### Requirement: 未来 TUI 展示 session id 和 run id

未来 TUI SHALL 展示当前交互式 session id 和最近一次 Agent 运行的 run id。

#### Scenario: TUI 启动 session

- **GIVEN** 用户打开 TUI
- **WHEN** 创建或恢复运行
- **THEN** TUI SHALL 展示可用于日志关联的 session id
- **AND** 当 Agent 运行开始时，TUI SHALL 展示 run id

### Requirement: 未来 TUI 复用 streaming event

未来 TUI SHALL 复用 Agent runtime 的 `assistant_delta` 和 `assistant_stream_complete` event，不得定义不兼容的流式输出协议。未来 TUI SHALL 将 `llm_response(streamed=true)` 作为完成态数据，而不是重复展示文本。

#### Scenario: TUI 展示 streaming 回复

- **GIVEN** runtime 发布 `assistant_delta`
- **WHEN** TUI 消费事件
- **THEN** TUI SHALL 实时更新 assistant 消息区域
