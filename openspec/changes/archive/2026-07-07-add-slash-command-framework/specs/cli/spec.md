## ADDED Requirements

### Requirement: CLI interactive slash command registry

CLI 交互模式 SHALL 通过 central command registry 路由 slash command。独立 slash command SHALL NOT 作为普通用户消息发送给 AgentLoop/LLM；具体命令处理器可以在命令语义需要时显式调用模型服务、AgentLoop 或工作流服务。command registry SHALL 支持 builtin、skill、plugin 或 MCP 等动态命令来源的元数据，并保留命令名后的完整参数文本。

#### Scenario: Slash command help

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/help`
- **THEN** CLI SHALL 输出可用 slash command 列表
- **AND** 每个命令 SHALL 包含简短说明或用法

#### Scenario: Skill-shaped command preserves natural language args

- **GIVEN** registry 中存在名为 `review-skill` 的 slash command
- **WHEN** 用户输入 `/review-skill 帮我审一下这个 change`
- **THEN** registry SHALL 将 `review-skill` 解析为命令名
- **AND** SHALL 将 `帮我审一下这个 change` 作为完整 args 传给命令处理器

#### Scenario: Unknown slash command

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入未知 slash command
- **THEN** CLI SHALL 输出可读错误
- **AND** SHALL NOT 将该输入作为普通用户消息发送给 AgentLoop/LLM
- **AND** SHALL NOT 产生新的 Run ID
- **AND** 会话 SHALL 继续

### Requirement: CLI interactive basic session commands

CLI 交互模式 SHALL 提供退出、状态查看、mode 切换、清理上下文和压缩上下文等基础 session slash command。

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
- **AND** SHALL NOT 将 `/clear` 作为普通用户消息发送给 AgentLoop/LLM
- **AND** SHALL NOT 产生新的 Run ID

#### Scenario: Slash compact command

- **GIVEN** 用户处于 CLI 交互模式并已有多轮对话
- **WHEN** 用户输入 `/compact`
- **THEN** CLI SHALL 主动请求压缩当前会话上下文
- **AND** 输出压缩结果或无需压缩的可读说明
- **AND** SHALL NOT 将 `/compact` 作为普通用户消息发送给 AgentLoop/LLM
- **AND** SHALL NOT 产生新的 Run ID

### Requirement: Web slash command suggestions

Web Chat SHALL 基于后端 command catalog 提供 slash command 提示。

#### Scenario: Web command catalog

- **GIVEN** Web UI 正在运行
- **WHEN** 浏览器请求 `/api/slash-commands`
- **THEN** 响应 SHALL 包含可用 slash command 的命令名、用法、说明、别名、参数提示、来源和执行类型

#### Scenario: Slash 前缀实时更新提示

- **GIVEN** 用户在 Web Chat 输入框中输入 `/`
- **WHEN** 用户继续输入命令前缀
- **THEN** Web UI SHALL 将提示列表更新为命令名或别名匹配当前前缀的命令
- **AND** 包含 `/` 的普通文本 SHALL NOT 显示 slash command 提示

#### Scenario: Web slash command 作为控制面输入处理

- **GIVEN** 用户处于 Web Chat
- **WHEN** 用户发送独立 slash command
- **THEN** WebSocket SHALL 执行该命令并发送 command result
- **AND** SHALL NOT 启动普通 Agent run
- **AND** SHALL NOT 将该输入作为普通用户消息发送给 AgentLoop/LLM
