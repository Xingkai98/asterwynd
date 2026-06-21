# agent-modes 规格

## Purpose

定义当前 MyAgent 已有运行入口和未来模式边界。当前实现包含 CLI 单轮、CLI 交互、Web 会话和 benchmark runner；尚未实现显式只读、plan、build、bypass 模式开关。

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

### Requirement: 模式预留不得冒充实现

系统 SHALL 将只读、plan、build、bypass 等显式 agent mode 视为未来能力，直到对应 change 被接受并实现。

#### Scenario: 文档描述未来模式

- **GIVEN** 文档或路线图提到未来运行模式
- **WHEN** 这些模式尚无代码入口或测试
- **THEN** 规格 SHALL 标注为预留或未实现

