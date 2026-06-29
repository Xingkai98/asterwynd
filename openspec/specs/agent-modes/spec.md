# agent-modes 规格

## Purpose

定义当前 Asterwynd 已有运行入口和 agent mode 边界。当前实现包含 CLI 单轮、CLI 交互、Web 会话和 benchmark runner，并支持 build、read_only、plan 和内部 bypass mode。`plan` mode 是只读计划讨论模式，用于迭代 Plan Document 草案、定稿 Plan Document 和结构化 planning state，不执行实现。

## Requirements

### Requirement: 支持单轮 CLI 模式

系统 SHALL 通过 `cli.py main` 接收单个 prompt，构造 AgentLoop 并输出最终回复。

#### Scenario: 非交互运行

- **GIVEN** 用户执行 `uv run python cli.py main "<prompt>"`
- **WHEN** prompt 非空
- **THEN** CLI SHALL 执行一次 AgentLoop
- **AND** 输出最终 agent 内容和工具调用次数

#### Scenario: 非交互缺少 prompt

- **GIVEN** 用户未开启交互模式
- **WHEN** 未提供 prompt
- **THEN** CLI SHALL 输出错误
- **AND** 以非零状态退出

### Requirement: 支持 CLI 交互模式

系统 SHALL 通过 `--interactive` 进入多轮输入循环，并复用同一个 event loop 和消息历史。

#### Scenario: 用户连续输入

- **GIVEN** CLI 已进入交互模式
- **WHEN** 用户输入多轮内容
- **THEN** 系统 SHALL 将每轮用户消息追加到同一消息列表
- **AND** 使用同一个 AgentLoop 继续运行

### Requirement: 支持 Web 会话模式

系统 SHALL 通过 Web UI 为每个 session 维护独立消息历史和 AgentLoop。

#### Scenario: WebSocket 消息

- **GIVEN** 用户在 Web Chat 发送消息
- **WHEN** 服务端收到 session 消息
- **THEN** 系统 SHALL 使用该 session 的 AgentLoop 运行
- **AND** 通过 WebSocket 返回事件和结果

### Requirement: Agent mode 约束工具权限

系统 SHALL 使用当前 Agent Mode 约束工具 schema 暴露和工具执行权限。`build` mode 默认允许已注册工具；`read_only` 和 `plan` mode SHALL 只允许 read-only 且 non-dangerous 的工具；`bypass` 为内部保留 mode，默认 fail closed。

#### Scenario: read_only mode 过滤工具 schema

- **GIVEN** ToolRegistry 注册了读写工具
- **WHEN** 系统以 `read_only` mode 获取工具 schema
- **THEN** 写入或 dangerous 工具 SHALL 不出现在 schema 中

#### Scenario: 被 mode 禁止的工具执行

- **GIVEN** 工具调用命中当前 mode 禁止的工具
- **WHEN** ToolRegistry 执行该调用
- **THEN** 系统 SHALL 返回可读权限错误作为 tool result

### Requirement: session mode 支持运行时切换

系统 SHALL 支持在同一个交互式 session 内切换当前 Agent Mode。mode transition 完成后 SHALL 更新该 session 的当前 mode，并影响同一 session 后续 run 的工具 schema 暴露和工具执行权限。

#### Scenario: session 切换到 read_only

- **GIVEN** CLI 交互、Web 或未来 TUI session 当前 mode 为 `build`
- **WHEN** 用户将该 session 切换到 `read_only`
- **THEN** 该 session 后续 run SHALL 使用 `read_only` mode
- **AND** 工具 schema SHALL 不再暴露当前 mode 禁止的工具

#### Scenario: session 切换到 plan

- **GIVEN** session 当前 mode 为 `build`
- **WHEN** 用户将该 session 切换到 `plan`
- **THEN** 后续 run SHALL 使用 plan mode 工具策略
- **AND** SHALL 暴露 `UpdatePlan` 和 `ExitPlanMode`

#### Scenario: session 切换到 bypass 被拒绝

- **GIVEN** 用户处于交互式 session
- **WHEN** 用户请求将 mode 切换到 `bypass`
- **THEN** 系统 SHALL 返回可读错误
- **AND** 当前 mode SHALL 保持不变

### Requirement: mode deny override 来自统一配置

系统 SHALL 支持从统一配置对象读取按 mode 定义的 `deny_tools` override。`deny_tools` SHALL 使用工具公开名，大小写敏感；未知工具名 SHALL 在入口构造工具 registry 时 fail fast。

#### Scenario: deny override 过滤 schema

- **GIVEN** 配置为当前 mode deny 某个已注册工具
- **WHEN** 系统获取工具 schema
- **THEN** 被 deny 的工具 SHALL 不出现在 schema 中

#### Scenario: 未知 deny tool

- **GIVEN** 配置包含未知工具名
- **WHEN** 入口构造工具 registry
- **THEN** 系统 SHALL fail fast 并返回可读配置错误

### Requirement: Plan mode 产出可审阅计划

系统 SHALL 将 `plan` mode 作为只读计划讨论模式。AgentLoop 以 `plan` mode 运行时 SHALL 允许只读调研工具、`UpdatePlan` 和 `ExitPlanMode` 工具，拒绝写入、编辑和 dangerous 工具；模型 MAY 通过 `UpdatePlan` 更新 Markdown Plan Document 草案，并 SHALL 在计划定稿时通过 `ExitPlanMode` 提交最终 Markdown Plan Document，同时将高层步骤同步为结构化 planning state。

#### Scenario: plan mode 只读运行

- **GIVEN** AgentLoop 以 `plan` mode 运行
- **WHEN** 系统暴露工具 schema
- **THEN** schema SHALL 只包含只读 non-dangerous 工具、`UpdatePlan` 和 `ExitPlanMode`
- **AND** 系统 SHALL 拒绝写入和 dangerous 工具调用

#### Scenario: plan mode 提交计划

- **GIVEN** 用户请求先规划任务
- **WHEN** AgentLoop 以 `plan` mode 完成
- **THEN** 系统 SHALL 允许模型通过自然语言继续讨论计划
- **AND** MAY 记录 Markdown Plan Document 草案
- **AND** 在计划定稿时 SHALL 记录最终 Markdown Plan Document
- **AND** SHALL 将 Plan Document 中的高层步骤同步为结构化 planning state
- **AND** 最终回复 SHALL 给出自然语言计划说明
- **AND** 系统 SHALL NOT 自动切换到 `build` mode 或执行计划
