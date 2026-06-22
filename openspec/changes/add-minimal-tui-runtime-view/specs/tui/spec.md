## MODIFIED Requirements

### Requirement: TUI 当前为预留能力域

系统 SHALL 在本 change 实现后提供最小 TUI runtime view；在实现前不得声称已经支持独立 TUI。

#### Scenario: 当前用户入口

- **GIVEN** 用户使用当前仓库
- **WHEN** 查看可用入口
- **THEN** 系统 SHALL 只提供当前 CLI、Web 和 benchmark 入口
- **AND** 只有在本 change 实现后才 SHALL 提供 TUI 命令

## ADDED Requirements

### Requirement: TUI 展示运行事件

TUI SHALL 展示用户消息、assistant 回复、工具调用进度、planning state 和最终结果摘要。

#### Scenario: AgentLoop 产生工具事件

- **GIVEN** TUI 正在运行 AgentLoop
- **WHEN** 工具调用开始和结束
- **THEN** TUI SHALL 更新工具事件展示

### Requirement: TUI 复用核心运行协议

TUI SHALL 复用 AgentLoop、工具事件、planning state 和 session 语义，不得另起不兼容协议。

#### Scenario: TUI 启动运行

- **GIVEN** 用户通过 TUI 命令启动任务
- **WHEN** TUI 创建运行时
- **THEN** 系统 SHALL 使用现有 AgentLoop 构造路径
