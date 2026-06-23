# agent-modes 规格

## Purpose

定义当前 MyAgent 已有运行入口和 agent mode 边界。当前实现包含 CLI 单轮、CLI 交互、Web 会话和 benchmark runner，并支持 build、read_only、plan 和内部 bypass mode 的权限边界。

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

### Requirement: Plan mode 不得冒充真实计划模式

系统 SHALL 将当前 plan mode 视为只读权限边界。即使系统已经具备通用结构化 planning state，plan mode 也不得被描述为已经具备强制产出计划、禁止执行实现、或可验证计划优先工作流的真实计划模式，直到 `add-plan-mode` 或等价 change 被接受并实现。

#### Scenario: 文档描述 plan mode

- **GIVEN** 文档或路线图提到 plan mode
- **WHEN** 真实 plan mode 尚未实现
- **THEN** 规格 SHALL 明确 plan mode 当前仅提供只读权限边界
- **AND** MAY 提及通用 planning state 已存在，但不得把它等同于真实 plan mode
