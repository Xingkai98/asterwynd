# agent-runtime 规格

## Purpose

定义 MyAgent 的核心运行循环、消息状态、工具调用协议和停止条件。当前实现以 `agent/loop.py` 的 `AgentLoop` 为核心。
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
