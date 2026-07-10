# agent-runtime 规格

## Purpose

定义 Asterwynd 的核心运行循环、消息状态、工具调用协议和停止条件。当前实现以 `agent/loop.py` 的 `AgentLoop` 为核心。
## Requirements
### Requirement: AgentLoop 执行消息循环

系统 SHALL 以消息列表作为主要运行状态，在每轮中调用 LLM、解析 assistant 响应、执行工具调用并把工具结果追加回消息历史。

#### Scenario: assistant 返回最终文本

- **GIVEN** 输入消息列表和可用 LLM
- **WHEN** LLM 返回不包含工具调用的 assistant 消息
- **THEN** AgentLoop SHALL 将最终 assistant 回复加入消息历史
- **AND** 返回包含最终内容的运行结果

#### Scenario: assistant 返回工具调用

- **GIVEN** LLM 返回包含一个或多个 tool call 的 assistant 消息
- **WHEN** AgentLoop 解析工具名和参数
- **THEN** 系统 SHALL 通过 ToolRegistry 执行对应工具
- **AND** 为每个 tool call 追加匹配的 tool result 消息
- **AND** 继续下一轮 LLM 调用

### Requirement: tool-call 消息链合法

系统 SHALL 保持 assistant tool call 与 tool result 的匹配关系，不得生成缺失、错配或伪造的工具结果链。

#### Scenario: 达到 max_iterations

- **GIVEN** AgentLoop 已达到最大迭代次数
- **WHEN** 最后一轮仍然产生工具调用或未形成最终 assistant 文本
- **THEN** 系统 SHALL 返回受控的终止结果
- **AND** SHALL NOT 把最后一个工具结果伪造成 assistant 最终回复

### Requirement: 生命周期扩展点

系统 SHALL 支持 HookManager 在 AgentLoop 运行过程中接入日志、trace、debug 和 token budget 等通过 Hook protocol 表达的横切能力。

#### Scenario: 配置 hooks

- **GIVEN** AgentLoop 构造时传入 HookManager
- **WHEN** AgentLoop 执行 LLM 调用和工具调用
- **THEN** hooks MAY 观察或影响对应生命周期事件
- **AND** 核心 tool-call 协议不变量 SHALL 保持有效

### Requirement: 运行轨迹记录

系统 SHALL 支持通过 TraceRecorder 记录 LLM 迭代、工具调用、工具结果、编辑、diff、测试和完成状态。

#### Scenario: benchmark 注入 trace_recorder

- **GIVEN** benchmark runner 为一次任务提供 TraceRecorder
- **WHEN** AgentLoop 执行任务
- **THEN** 系统 SHALL 记录可序列化 trace
- **AND** trace 可写入 benchmark artifact

### Requirement: AgentLoop 可发出 planning state 事件

AgentLoop SHALL 支持在计划创建或状态更新时发出 `planning_state_updated` 事件，并支持在 plan mode 更新或提交 Plan Document 时发出 `plan_document_updated` / `plan_document_submitted` 事件，同时保持原有 tool-call 协议不变量。`planning_state_updated` payload SHALL 包含完整 planning state snapshot，至少包含 `items` 列表和可选 `summary`。

#### Scenario: 计划状态更新

- **GIVEN** AgentLoop 运行中产生 planning state 更新
- **WHEN** 更新被应用
- **THEN** 系统 SHALL 通过事件或 hook 暴露更新后的 planning state
- **AND** SHALL NOT 插入破坏 provider tool-call 链的消息

#### Scenario: LLM 调用包含只读 planning context

- **GIVEN** AgentLoop 持有非空 planning state
- **WHEN** AgentLoop 调用 LLM
- **THEN** 系统 SHALL 将当前 planning state 作为临时只读上下文提供给 LLM
- **AND** SHALL NOT 将该上下文持久 append 到 messages

#### Scenario: Plan Document 更新或提交

- **GIVEN** AgentLoop 以 plan mode 运行
- **WHEN** 模型通过 `UpdatePlan` 更新草案或通过 `ExitPlanMode` 提交 Plan Document
- **THEN** 系统 SHALL 发出对应的 `plan_document_updated` 或 `plan_document_submitted` 事件
- **AND** SHALL 在 trace 中记录该 Plan Document

### Requirement: Agent runtime 提供 session id 和 run id

Agent runtime SHALL 为一次 Agent 运行提供 run id，并在存在交互式会话时关联 session id，用于日志、事件、trace 和 UI 展示。

#### Scenario: 运行事件包含 run id

- **GIVEN** AgentLoop 开始一次运行
- **WHEN** runtime 发布运行事件
- **THEN** 事件 SHALL 包含可用于排查的 run id
- **AND** 如果调用方提供了 session id，事件 SHALL 包含该 session id

### Requirement: Agent runtime 管理 session 当前 mode

Agent runtime SHALL 维护交互式 session 的当前 mode，并支持通过统一 transition API 更新该 mode。`AgentRunConfig.mode` SHALL 表示入口初始 mode；当前实际 mode SHALL 来自 runtime state。

#### Scenario: mode transition 发布事件和 trace

- **GIVEN** session 当前 mode 为 `build`
- **WHEN** runtime transition API 将 mode 切换为 `read_only`
- **THEN** runtime SHALL 发布 `mode_changed` 事件
- **AND** 事件 SHALL 至少包含 `old_mode`、`new_mode` 和 `source`
- **AND** trace SHALL 记录该 transition

#### Scenario: mode transition 不写入 provider messages

- **GIVEN** session 发生 mode transition
- **WHEN** runtime 更新当前 mode
- **THEN** 系统 SHALL NOT 把该 transition 追加到 provider messages
- **AND** tool-call 消息链 SHALL 保持合法

### Requirement: Agent runtime 发布 assistant 流式输出事件

Agent runtime SHALL 支持在 LLM 生成过程中发布 `assistant_delta` 事件，并在 streaming 响应完成时发布 `assistant_stream_complete` 事件。最终响应完成后，runtime SHALL 继续发布完整 `llm_response`，并保持 messages 中的 assistant 消息合法。

#### Scenario: assistant 文本流式输出

- **GIVEN** provider 支持 streaming text
- **WHEN** AgentLoop 调用 LLM
- **THEN** runtime SHALL 发布一个或多个 `assistant_delta` 事件
- **AND** `assistant_delta` payload SHALL 包含 `delta`
- **AND** runtime SHALL 发布 `assistant_stream_complete`
- **AND** 最终 `llm_response` SHALL 包含 `streamed: true`
- **AND** 最终 SHALL 只写入完整 assistant message，不写入 partial delta message

#### Scenario: provider 不支持 streaming

- **GIVEN** provider 不支持 streaming
- **WHEN** AgentLoop 调用 LLM
- **THEN** runtime SHALL 不发布 `assistant_delta`
- **AND** runtime SHALL 保持非流式 `llm_response` 行为兼容

#### Scenario: streaming tool calls

- **GIVEN** provider 在 streaming 响应中返回 tool call arguments
- **WHEN** AgentLoop 收到完整 LLM response
- **THEN** runtime SHALL 只在 `LLMResponse.tool_calls` 完整后执行工具
- **AND** runtime SHALL NOT 将 tool arguments 作为 assistant text delta 暴露

### Requirement: 父 run 通过显式运行时接口管理子 session

父 AgentLoop SHALL 通过显式运行时接口创建、启动、查询、等待、取消和检查子 session / 子 run，而不是通过自动消息注入或伪造 tool result 把子结果并入父 messages。

#### Scenario: 父 run 查询子 run 结果

- **GIVEN** 一个已存在的子 session 和其最近一次子 run
- **WHEN** 父 agent 调用 `GetSubagentRun`
- **THEN** 系统 SHALL 返回结构化结果
- **AND** SHALL NOT 直接修改父 run 的 messages transcript

### Requirement: 子 session mode 是 session 级状态

子 session SHALL 拥有独立的 session 级 mode。对子 session mode 的修改 SHALL 只影响后续 run，不影响当前已在运行的子 run。

#### Scenario: 运行中修改子 session mode

- **GIVEN** 一个子 session 当前正在以某个 mode 运行
- **WHEN** 父 agent 修改该子 session 的 mode
- **THEN** 当前子 run SHALL 继续沿用原 mode
- **AND** 后续新的子 run SHALL 使用更新后的 mode

### Requirement: Agent runtime 入口回归使用共享测试 LLM harness

项目 SHALL 提供共享测试 LLM harness，用于在测试中以确定性 fake LLM 或显式 opt-in real LLM 驱动真实 AgentLoop 和入口层 smoke。默认 fake LLM SHALL 兼容现有 `LLM` protocol，并支持普通文本、streaming、tool call、错误路径和调用记录。

#### Scenario: Fake LLM 驱动真实 AgentLoop

- **GIVEN** 测试使用共享 fake LLM harness
- **WHEN** 入口 smoke 构造 AgentLoop
- **THEN** 系统 SHALL 使用真实 AgentLoop、ToolRegistry、Memory 和 runtime event 路径
- **AND** SHALL 只替换 LLM provider 行为

#### Scenario: Harness 记录 LLM 调用

- **GIVEN** AgentLoop 通过共享 fake LLM harness 执行一次 run
- **WHEN** 测试检查 harness 状态
- **THEN** harness SHALL 暴露调用次数、messages、tools 和 model 等断言信息

#### Scenario: Real LLM smoke 显式开启

- **GIVEN** 测试 harness 支持真实 provider profile
- **WHEN** 未显式传入 real API flag 或对应环境变量
- **THEN** 默认回归 SHALL 使用 fake LLM
- **AND** SHALL NOT 要求真实 API key、外部网络或真实模型输出

### Requirement: AgentLoop SHALL mediate approval-required tool calls

AgentLoop SHALL 在工具执行前处理工具权限判定。对于 `allow`，AgentLoop MAY 通过 ToolRegistry 执行工具。对于 `deny`，AgentLoop SHALL NOT 执行工具，并 SHALL 追加可读的权限拒绝 tool result。对于 `require_approval`，AgentLoop SHALL 在执行前通过注入的 ApprovalHandler 请求审批。

#### Scenario: 用户批准后执行工具

- **GIVEN** 一个工具调用被判定为 `require_approval`
- **AND** ApprovalHandler 返回 approved
- **WHEN** AgentLoop 处理该工具调用
- **THEN** AgentLoop SHALL 执行工具
- **AND** SHALL 将实际 tool result 追加到 conversation

#### Scenario: 用户拒绝后不执行工具

- **GIVEN** 一个工具调用被判定为 `require_approval`
- **AND** ApprovalHandler 返回 denied
- **WHEN** AgentLoop 处理该工具调用
- **THEN** AgentLoop SHALL NOT 执行工具
- **AND** SHALL 将可读的审批拒绝 tool result 追加到 conversation

#### Scenario: 审批不可用时 fail closed

- **GIVEN** 一个工具调用被判定为 `require_approval`
- **AND** 当前 runtime 没有可交互审批通道
- **WHEN** AgentLoop 处理该工具调用
- **THEN** AgentLoop SHALL NOT 执行工具
- **AND** SHALL 将可读的审批不可用 tool result 追加到 conversation

### Requirement: 后台任务执行

系统 SHALL 支持通过 `Bash` 工具的 `run_in_background=True` 参数启动后台命令。启动后台命令后 SHALL 返回 task_id。`BackgroundTaskManager` SHALL 维护所有活跃后台任务的状态，并在任务完成时通过 AgentLoop 自动注入结果。

#### Scenario: 启动后台任务

- **GIVEN** agent 调用 Bash 且 run_in_background=True
- **WHEN** 命令为 `pytest -q tests/`
- **THEN** 系统 SHALL 返回 `"Task started: <task_id>"`
- **AND** 命令 SHALL 在后台异步执行

#### Scenario: 后台任务完成后注入结果

- **GIVEN** 有一个活跃的后台任务正在执行
- **WHEN** 任务完成（exit_code=0）
- **THEN** AgentLoop SHALL 在下一次迭代开始时将该任务的输出作为 tool result 注入消息
- **AND** 该 task_id SHALL 从活跃列表移至历史

#### Scenario: AgentLoop 退出时清理后台任务

- **GIVEN** AgentLoop 退出时仍有一个运行中的后台任务
- **WHEN** AgentLoop.run() 返回
- **THEN** BackgroundTaskManager SHALL 发送 SIGTERM 给所有活跃进程
- **AND** 等待 5 秒后发送 SIGKILL

### Requirement: 会话持久化

系统 SHALL 支持将会话状态序列化到 `.asterwynd/sessions/<session_id>/` 目录。持久化内容 SHALL 包含消息历史、mode、todo 列表、技能激活状态。CLI SHALL 提供 `--resume` 参数恢复会话。

#### Scenario: 会话自动保存

- **GIVEN** AgentLoop 在一次运行结束后
- **AND** 调用方提供了 session_id
- **WHEN** AgentLoop.run() 返回
- **THEN** 系统 SHALL 将会话快照写入 `.asterwynd/sessions/<session_id>/`

#### Scenario: 会话恢复

- **GIVEN** 存在一个有效的 session 快照
- **WHEN** 用户通过 `--resume <session_id>` 启动
- **THEN** 系统 SHALL 加载消息历史和 mode
- **AND** 注入会话恢复标记消息
- **AND** 正常进入交互循环

#### Scenario: 损坏的会话文件

- **GIVEN** session 文件的 JSON 格式损坏或不兼容
- **WHEN** 用户尝试 --resume
- **THEN** 系统 SHALL 返回明确错误而非静默失败

#### Scenario: 不存在的 session

- **GIVEN** session_id 对应的目录不存在
- **WHEN** 用户尝试 --resume
- **THEN** 系统 SHALL 返回 "Session <id> not found"

### Requirement: TaskOutput 和 TaskStop 工具

系统 SHALL 提供 `TaskOutput` 和 `TaskStop` 工具用于后台任务的控制。

#### Scenario: 阻塞等待任务完成

- **GIVEN** 后台任务 5 秒后完成
- **WHEN** agent 调用 TaskOutput(task_id, block=True)
- **THEN** TaskOutput SHALL 阻塞等待直到任务完成
- **AND** 返回 exit_code、stdout、stderr

#### Scenario: 非阻塞查询

- **GIVEN** 后台任务仍在运行
- **WHEN** agent 调用 TaskOutput(task_id, block=False)
- **THEN** TaskOutput SHALL 立即返回
- **AND** status SHALL 为 "running"

#### Scenario: 终止任务

- **GIVEN** 后台任务仍在运行
- **WHEN** agent 调用 TaskStop(task_id)
- **THEN** 进程 SHALL 被终止
- **AND** TaskStop SHALL 返回最终输出

### Requirement: Approval records SHALL be observable

AgentLoop SHALL 在 trace/debug/display 路径记录审批请求和审批决定，包含 tool name、capability、risk level、origin、当前 mode、审批结果和安全的参数摘要。参数摘要 SHALL 脱敏常见 secret/key/token/password/authorization 字段和值模式，并限制长度。

#### Scenario: 审批 trace 包含权限上下文

- **GIVEN** 一个工具调用需要审批
- **WHEN** AgentLoop 创建审批请求
- **THEN** trace/debug/display 数据 SHALL 包含工具权限元数据和 profile 判定原因
- **AND** SHALL NOT 暴露未脱敏的敏感参数

### Requirement: 多模态 Message 内容

Message 的 `content` 字段 SHALL 支持 `str`（纯文本）和 `list[ContentBlock]`（多模态）两种类型。`ContentBlock` SHALL 支持 `text` 和 `image_url` 两种类型。`ImageBlock` SHALL 包含 `file_path` 字段用于 compact/trace 引用。`str` 类型 SHALL 保持完全向后兼容（序列化后仍为字符串）。

#### Scenario: 纯文本内容不变

- **GIVEN** Message 的 content 为 `str` 类型
- **WHEN** 任意现有代码路径处理该 Message
- **THEN** 行为 SHALL 与改动前完全一致

#### Scenario: 多模态 content 序列化

- **GIVEN** Message 的 content 为 `[TextBlock("解读这张图"), ImageBlock(url="data:image/png;base64,...", file_path="/path/to/file.png")]`
- **WHEN** 序列化为 JSON
- **THEN** content SHALL 序列化为 content blocks 数组
- **AND** TextBlock 序列化为 `{"type": "text", "text": "..."}`
- **AND** ImageBlock 序列化为 `{"type": "image_url", "image_url": {"url": "data:...", "detail": "auto"}, "file_path": "/path/to/file"}`
- **AND** deserialize 后 SHALL 还原为相同的 content blocks 数组

### Requirement: 工具多模态返回值

`Tool.execute()` SHALL 返回 `str | list[ContentBlock]`。当工具返回了图片内容时，返回值 SHALL 为包含 ImageBlock 的列表。AgentLoop 在构建消息时 SHALL 直接将返回值赋给 `Message.content`。

#### Scenario: Read 工具读取图片

- **GIVEN** Read 工具读取了一个 PNG 文件
- **WHEN** 工具执行完成
- **THEN** `execute()` 返回值 SHALL 为 `[TextBlock, ImageBlock]`
- **AND** AgentLoop 在构建消息时 SHALL 将该列表赋给 `Message.content`

#### Scenario: 普通文本工具结果

- **GIVEN** Read 工具读取了一个 .py 文件
- **WHEN** 工具执行完成
- **THEN** `execute()` 返回值 SHALL 为 `str` 类型
- **AND** AgentLoop 在构建消息时 SHALL 照常使用该字符串
