## ADDED Requirements

### Requirement: CLI interactive slash command registry

CLI interactive mode SHALL route slash commands through a central command registry.

#### Scenario: Slash command help

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/help`
- **THEN** CLI SHALL 输出可用 slash command 列表
- **AND** 每个命令 SHALL 包含简短说明或用法

#### Scenario: Unknown slash command

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入未知 slash command
- **THEN** CLI SHALL 输出可读错误
- **AND** SHALL NOT 将该输入发送给 LLM
- **AND** SHALL NOT 产生新的 Run ID
- **AND** 会话 SHALL 继续

### Requirement: CLI interactive basic session commands

CLI interactive mode SHALL provide basic session slash commands for exit, status, mode switching, clear, and compact.

#### Scenario: Slash exit command

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/exit` 或 `/quit`
- **THEN** CLI SHALL 结束交互会话

#### Scenario: Bare exit remains compatible

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `exit`、`quit` 或 `q`
- **THEN** CLI SHALL 结束交互会话

#### Scenario: Slash status command

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/status`
- **THEN** CLI SHALL 输出当前 session id、mode、provider 和 model
- **AND** SHOULD 输出当前消息数量或 token 估算

#### Scenario: Slash mode command uses registry

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/mode read_only`
- **THEN** CLI SHALL 通过 slash command registry 调用统一 mode transition
- **AND** 后续 run SHALL 使用 `read_only`

#### Scenario: Slash clear command

- **GIVEN** 用户处于 CLI 交互模式并已有多轮对话
- **WHEN** 用户输入 `/clear`
- **THEN** CLI SHALL 清空当前会话的非 system 消息
- **AND** SHALL 保留当前 Session ID
- **AND** 输出可读确认
- **AND** SHALL NOT 将 `/clear` 发送给 LLM
- **AND** SHALL NOT 产生新的 Run ID

#### Scenario: Slash compact command

- **GIVEN** 用户处于 CLI 交互模式并已有多轮对话
- **WHEN** 用户输入 `/compact`
- **THEN** CLI SHALL 主动请求压缩当前会话上下文
- **AND** 输出压缩结果或无需压缩的可读说明
- **AND** SHALL NOT 将 `/compact` 发送给 LLM
- **AND** SHALL NOT 产生新的 Run ID
