## ADDED Requirements

### Requirement: CLI 提供 TUI 入口

CLI SHALL 提供启动 TUI 的命令或参数。

#### Scenario: 启动 TUI

- **GIVEN** 用户执行 TUI 命令
- **WHEN** 当前终端支持交互式渲染
- **THEN** CLI SHALL 启动 TUI runtime view

#### Scenario: 启动多轮 TUI

- **GIVEN** 用户执行 TUI 命令且未提供 prompt
- **WHEN** 当前终端支持交互式渲染
- **THEN** CLI SHALL 启动空白多轮 TUI session
- **AND** 用户 SHALL 能在 TUI 输入区发送第一条消息

#### Scenario: 带初始 prompt 启动 TUI

- **GIVEN** 用户执行 TUI 命令并提供初始 prompt
- **WHEN** 当前终端支持交互式渲染
- **THEN** CLI SHALL 启动多轮 TUI session
- **AND** TUI SHALL 自动发送该初始 prompt 作为第一轮用户消息
