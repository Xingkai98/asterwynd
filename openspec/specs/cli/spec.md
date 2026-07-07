# cli 规格

## Purpose

定义 Typer CLI 的命令入口、参数、非交互运行、Web 启动和 benchmark 启动。当前入口为 `cli.py`。
## Requirements
### Requirement: CLI 构造默认 AgentLoop

CLI SHALL 通过 provider、model、ToolRegistry、HookManager 和 MemoryManager 构造默认 AgentLoop。

#### Scenario: build_agent

- **GIVEN** 用户选择 provider 和可选 model
- **WHEN** CLI 调用 `build_agent`
- **THEN** 系统 SHALL 构造 LLM
- **AND** 注册默认工具
- **AND** 配置 LoggingHook、TracingHook 和 MemoryManager

### Requirement: CLI 接入统一配置

CLI `main`、`web` 和 `benchmark` 命令 SHALL 支持 `--config <path>`，并在入口层解析统一配置。未显式传入 `--mode` 时，CLI SHALL 使用配置中的 `agent.default_mode`。

#### Scenario: main 使用配置默认 mode

- **GIVEN** `asterwynd.yaml` 设置了 `agent.default_mode`
- **AND** 用户未传入 `--mode`
- **WHEN** CLI 执行 `main`
- **THEN** CLI SHALL 使用配置默认 mode 构造 AgentLoop

#### Scenario: CLI mode 覆盖配置

- **GIVEN** `asterwynd.yaml` 设置了默认 mode
- **AND** 用户显式传入 `--mode`
- **WHEN** CLI 构造运行配置
- **THEN** CLI SHALL 使用显式 mode

### Requirement: main 命令支持单轮和交互

`main` 命令 SHALL 支持默认单轮模式和 `--interactive` 交互模式。交互模式 SHOULD 显示项目品牌 banner；单轮模式 SHALL NOT 默认显示品牌 banner。

#### Scenario: 单轮 prompt

- **GIVEN** 用户提供 prompt
- **WHEN** 未设置 `--interactive`
- **THEN** CLI SHALL 执行 `run_single`
- **AND** CLI SHALL NOT 输出品牌 banner

#### Scenario: 交互模式

- **GIVEN** 用户设置 `--interactive`
- **WHEN** CLI 启动
- **THEN** CLI SHALL 执行 `run_interactive`
- **AND** CLI SHOULD 输出 Asterwynd wordmark 和 slogan

#### Scenario: 交互模式关闭 banner

- **GIVEN** 用户设置 `--interactive --no-banner`
- **WHEN** CLI 启动
- **THEN** CLI SHALL 执行 `run_interactive`
- **AND** CLI SHALL NOT 输出 Asterwynd wordmark

### Requirement: CLI 支持 plan mode

CLI SHALL 支持通过 `--mode plan` 启动 plan mode，并将该 mode 传入 AgentLoop。

#### Scenario: CLI plan mode

- **GIVEN** 用户通过 CLI 指定 `--mode plan`
- **WHEN** CLI 运行 AgentLoop
- **THEN** 系统 SHALL 使用 plan mode 工具策略
- **AND** 输出计划说明

### Requirement: CLI interactive slash command registry

CLI 交互模式 SHALL 通过 central command registry 处理独立 slash command。未知 slash command SHALL 被本地拦截并提示 `/help`，不得作为普通用户消息发送给 AgentLoop/LLM，也不得产生新的 Run ID。普通文本中的 `/` 不应触发 command registry。具体命令处理器可以在命令语义需要时显式调用模型服务、AgentLoop 或工作流服务。command registry SHALL 支持 builtin、skill、plugin 或 MCP 等动态命令来源的元数据，并保留命令名后的完整参数文本。

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

### Requirement: CLI 交互模式支持基本 session slash commands

CLI 交互模式 SHALL 提供 `/exit`、`/quit`、`/status`、`/mode`、`/clear` 和 `/compact`。CLI 单次运行 SHALL 继续只通过 `--mode` 指定初始 mode，不提供运行中的人工切换入口。

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

#### Scenario: 交互模式切换到 read_only

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/mode read_only`
- **THEN** CLI SHALL 通过 slash command registry 更新当前 session mode
- **AND** 输出切换结果
- **AND** 之后的 run SHALL 使用 `read_only`

#### Scenario: 交互模式拒绝 bypass

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/mode bypass`
- **THEN** CLI SHALL 输出可读错误
- **AND** 当前 session mode SHALL 保持不变

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

### Requirement: CLI exposes skill slash commands

CLI 交互模式 SHALL 通过 central slash command registry 暴露 `/skills`、`/skills reload` 和用户可调用 skill commands。`/skills` 系列命令属于本地控制面命令，不启动 Agent run；`/skill-name args` 属于 prompt command，会显式激活 skill 并用 args 启动 Agent run。

#### Scenario: List skills

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/skills`
- **THEN** CLI SHALL 输出当前已加载 skills
- **AND** 输出 SHALL 包含每个 skill 的名称、来源和 always/user-invocable 标记

#### Scenario: Reload skills

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/skills reload`
- **THEN** CLI SHALL 重新加载 configured skill roots
- **AND** 输出加载数量和诊断摘要
- **AND** 后续 run SHALL 使用刷新后的 skill set

#### Scenario: Skill command starts agent run with args

- **GIVEN** 已加载一个名为 `code-review` 的用户可调用 skill
- **WHEN** 用户输入 `/code-review 帮我审一下这个 change`
- **THEN** CLI SHALL queue `code-review` activation，source 为 `slash_command`
- **AND** SHALL 用 `帮我审一下这个 change` 作为用户消息启动 Agent run
- **AND** SHALL NOT 将原始 `/code-review ...` 作为普通用户消息发送给 AgentLoop

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
- **WHEN** 用户发送本地控制面 slash command
- **THEN** WebSocket SHALL 执行该命令并发送 command result
- **AND** SHALL NOT 启动 Agent run
- **AND** SHALL NOT 将该输入作为普通用户消息发送给 AgentLoop/LLM

#### Scenario: Web skill command starts agent run with args

- **GIVEN** Web Chat 已加载一个名为 `code-review` 的用户可调用 skill
- **WHEN** 用户发送 `/code-review 帮我审一下这个 change`
- **THEN** WebSocket SHALL 先发送 command result
- **AND** SHALL queue `code-review` activation，source 为 `slash_command`
- **AND** SHALL 用 `帮我审一下这个 change` 作为用户消息启动 Agent run
- **AND** SHALL NOT 将原始 `/code-review ...` 作为普通用户消息发送给 AgentLoop

### Requirement: web 命令启动 Web UI

`web` 命令 SHALL 接收 host、port、provider 和 model 参数，构造 LLM 并启动 FastAPI 应用。启动提示 SHOULD 使用当前正式项目名，同时保留运行时配置和 debug 状态。

#### Scenario: 启动 web

- **GIVEN** 用户执行 `uv run python cli.py web --port 8000`
- **WHEN** 命令启动成功
- **THEN** CLI SHALL 输出访问地址、provider、model 和 debug 状态
- **AND** 使用 uvicorn 运行 app

### Requirement: benchmark 命令选择 runner

`benchmark` 命令 SHALL 支持 fake、shell、asterwynd 和 claude runner，并把任务目录交给 BenchmarkRunner。

#### Scenario: shell runner 缺少命令

- **GIVEN** 用户选择 `--agent shell`
- **WHEN** 未提供 `--shell-command`
- **THEN** CLI SHALL 输出错误
- **AND** 退出

### Requirement: CLI 展示 session id 和 run id

CLI SHALL 在启动会话时展示 session id，并在每次 Agent 运行开始时展示 run id。

#### Scenario: CLI 启动 agent

- **GIVEN** 用户通过 CLI 启动 Agent
- **WHEN** 运行开始
- **THEN** CLI SHALL 输出可用于排查的 run id

#### Scenario: CLI 交互模式复用 session id

- **GIVEN** 用户通过 CLI 交互模式启动 Agent
- **WHEN** 用户连续发送多轮消息
- **THEN** CLI SHALL 为该交互会话保持同一个 session id
- **AND** 每轮 Agent 运行 SHALL 输出新的 run id

### Requirement: CLI 实时输出 assistant delta

CLI SHALL 在支持 streaming 的运行路径中实时打印 `assistant_delta.delta`。当最终 `llm_response` 带 `streamed: true` 时，CLI SHALL NOT 再次打印该完整文本；非 streaming 路径 SHALL 继续打印 `llm_response.content`。

#### Scenario: CLI 收到 text delta

- **GIVEN** CLI 正在运行 Agent
- **WHEN** runtime 发布 `assistant_delta`
- **THEN** CLI SHALL 实时输出该 delta
- **AND** 当 runtime 随后发布 `llm_response(streamed=true)` 时，CLI SHALL NOT 重复输出该 content

#### Scenario: CLI 非流式输出

- **GIVEN** provider 不支持 streaming
- **WHEN** runtime 发布普通 `llm_response`
- **THEN** CLI SHALL 输出 `llm_response.content`

### Requirement: CLI 入口回归复用共享测试 LLM harness

CLI 测试 SHALL 覆盖通过真实 `build_agent` 和 AgentLoop 执行的 fake LLM runtime smoke。已有 adapter 级 `FakeAgent` 测试 MAY 保留，但不得作为 CLI 入口逻辑的唯一回归形态。

#### Scenario: CLI 单轮 fake LLM smoke

- **GIVEN** CLI 测试注入共享 fake LLM harness
- **WHEN** 执行 CLI 单轮 prompt
- **THEN** CLI SHALL 通过真实 `build_agent` 构造 AgentLoop
- **AND** 输出 fake LLM 返回的 assistant 内容
- **AND** 测试 SHALL 能断言 fake LLM 收到的用户消息

#### Scenario: CLI streaming fake LLM smoke

- **GIVEN** fake LLM 脚本返回 streaming delta 和 streamed completion
- **WHEN** CLI 执行单轮 prompt
- **THEN** CLI SHALL 实时输出 delta
- **AND** SHALL NOT 重复打印最终完整文本

#### Scenario: CLI control command 不触发 LLM

- **GIVEN** CLI 交互模式使用共享 fake LLM harness
- **WHEN** 用户输入 `/status`、`/clear` 或未知独立 slash command
- **THEN** CLI SHALL 按控制面输入处理该命令
- **AND** fake LLM 调用次数 SHALL 保持不变
