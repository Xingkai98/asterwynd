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

**运行期不变量**：正常工具执行路径 SHALL 为每个 tool call 追加匹配的 tool result 消息；SHALL NOT 把最后一个工具结果伪造成 assistant 最终回复（max_iterations 场景保持既有受控终止语义）。

**持久化/恢复不变量**：每次 `AgentLoop.run` 开始、且在 resume 历史重建之后，系统 SHALL 扫描消息历史中的 assistant `tool_calls`，检查每个 id 是否被紧随其后的连续 `tool` 消息按 `tool_call_id` 配对。该不变量 SHALL 以 provider 中性方式表达：Anthropic 序列化为 assistant `tool_use` + 下一条 user 消息的 `tool_result`；OpenAI 兼容端点序列化为 assistant `tool_calls[].id` + 紧随的 `role="tool"` 消息（`tool_call_id` 一一对应）。对**整条历史中不存在同 id 任何 `role="tool"` 消息**的缺失结果 id（含末尾单个、同一 assistant 的并行多个、连续多个 assistant 的悬空调用），系统 SHALL 为每个 id 插入**一条明确标记为合成**的 `tool` 消息，使序列化后的请求 payload 不含未配对的 `tool_use` / `tool_calls[].id`。合成结果 SHALL：

- 使用固定前缀 `[asterwynd:synthetic-tool-result] Error:`，并说明该工具调用因 run 中断未完成、可能已部分执行、重试前应先检查状态；
- SHALL NOT 声称工具执行成功，SHALL NOT 伪造真实输出；Anthropic 序列化时该 `tool_result` SHALL 带 `is_error: true`；OpenAI 兼容路径 SHALL 用 `Error:` 文本前缀作为等价错误信号（OpenAI 无 `is_error` 字段）；
- 内容 SHALL 确定（不含时间戳、随机值或进程状态），同一历史重复修复 SHALL 产生相同字节；
- 携带原 `tool_call_id`，使重复加载/续跑/中断落盘时 SHALL 幂等（不追加重复合成结果）。

合成 SHALL 只在某 `tool_call_id` 于整条历史中都没有任何 `role="tool"` 消息时发生。若结果存在但位置不合法（在 assistant 之后但被非 tool 消息隔开，或在 assistant 之前），系统 SHALL 将其归类为 misplaced/orphan，只记录 warning，SHALL NOT 再合成一条同 id 的结果（避免同一 `tool_use_id` 出现两条 `tool_result`），也 SHALL NOT 做破坏性重排。

**范围**：上述「payload SHALL NOT 含未配对 `tool_use`」适用于**整条历史中不存在该 id 任何 `role="tool"` 消息**的悬空调用（这是 run 中断的典型可观测形态）。misplaced/orphan 畸形链（结果存在但位置不合法）、空 id、重复 id 属畸形输入，只记录、不承诺修复，以免用重复结果或破坏性重排把畸形链变成另一种畸形链。

修复 SHALL NOT 修改正常配对的历史链。**run 起点**修复发生且历史被改变时，系统 SHALL 发出有界的 `tool_pairing_repaired` 事件（含来源、数量与有界 tool call id 列表）并写日志；正常链 SHALL NOT 发出该事件。中断路径 SHALL 在 `AgentLoop.run` 的 `finally` 落盘前**尽力**补齐配对（取消/异常展开可覆盖；SIGKILL/断电不在保证范围）；该 finally 修复 SHALL 写 warning 日志，并在 `trace_recorder` 存在时**同步、异常隔离**地记录 `source="finally"` 的 `tool_pairing_repaired` trace step；它 SHALL NOT await Web 事件（取消中不保证可靠），SHALL NOT 因此改变取消/异常传播。

#### Scenario: 运行期工具调用正常配对

- **GIVEN** LLM 返回包含一个或多个 tool call 的 assistant 消息
- **WHEN** AgentLoop 解析工具名和参数并执行
- **THEN** 系统 SHALL 为每个 tool call 追加匹配的 tool result 消息
- **AND** SHALL 继续下一轮 LLM 调用

#### Scenario: 达到 max_iterations

- **GIVEN** AgentLoop 已达到最大迭代次数
- **WHEN** 最后一轮仍然产生工具调用或未形成最终 assistant 文本
- **THEN** 系统 SHALL 返回受控的终止结果
- **AND** SHALL NOT 把最后一个工具结果伪造成 assistant 最终回复

#### Scenario: 恢复含末尾悬空 tool_call 的会话

- **GIVEN** 会话历史包含一条 assistant 消息，其 `tool_calls` 在消息链末尾没有对应的 tool 消息（run 在工具执行中被取消）
- **WHEN** 下一次 `AgentLoop.run` 开始（resume 或同进程重试）
- **THEN** 系统 SHALL 为该 tool call id 插入一条带 `[asterwynd:synthetic-tool-result] Error:` 前缀的合成 `tool` 消息
- **AND** 下一次 LLM 请求的 payload SHALL NOT 含未配对的 `tool_use`
- **AND** 系统 SHALL 发出 `tool_pairing_repaired` 事件并写 warning 日志

#### Scenario: 同一 assistant 的并行多个悬空 tool_call

- **GIVEN** 一条 assistant 消息含 3 个 `tool_calls`，其中只有 1 个已有配对结果
- **WHEN** 下一次 run 开始
- **THEN** 系统 SHALL 只为缺失的 2 个 id 各插入一条合成 `tool` 消息，按原 `tool_calls` 顺序
- **AND** 修复后的序列化 payload SHALL 把同一轮的所有 `tool_result` 放在同一条紧随 assistant 的 user 消息中
- **AND** 已存在的真实结果 SHALL NOT 被修改或替换

#### Scenario: 连续多个 assistant 悬空

- **GIVEN** 消息历史中有两个 assistant 消息各自留下未配对 `tool_calls`，中间可能隔着 user 文本
- **WHEN** 下一次 run 开始
- **THEN** 系统 SHALL 在每个 assistant 之后分别补齐其缺失的合成结果
- **AND** 后一个 assistant 的插入 SHALL NOT 因前一个插入造成的索引变化而错位

#### Scenario: 修复幂等

- **GIVEN** 一段已经修复过的历史（合成结果已存在）
- **WHEN** 再次加载/续跑/中断落盘触发修复
- **THEN** 系统 SHALL NOT 追加第二条合成结果
- **AND** 修复后的消息序列化字节 SHALL 与上一次修复一致

#### Scenario: 位置错误的结果不得被重复合成

- **GIVEN** 某 assistant 的 `tool_call` 对应结果存在于历史中，但不紧邻该 assistant（在后续 user 文本之后，或出现在 assistant 之前）
- **WHEN** 下一次 run 开始执行配对检查
- **THEN** 系统 SHALL 将其归类为 misplaced/orphan 并记录 warning
- **AND** 修复 SHALL NOT **新增**该 id 的第二条 `tool_result`（若输入本身已有重复结果，属畸形输入，SHALL NOT 被本修复承诺清理）
- **AND** SHALL NOT 为修复该畸形做消息重排（超出本要求范围）

#### Scenario: 合成结果的 provider 错误信号

- **GIVEN** 一条带 `[asterwynd:synthetic-tool-result] Error:` 前缀的合成 `tool` 消息
- **WHEN** 序列化为 Anthropic 或 OpenAI 兼容请求
- **THEN** Anthropic `tool_result` SHALL 带 `is_error: true`
- **AND** OpenAI 兼容路径的 `role="tool"` content SHALL 保留 `Error:` 文本前缀（OpenAI 无 `is_error` 字段）
- **AND** 真实工具结果 SHALL NOT 被加上该标记

#### Scenario: OpenAI 序列化配对

- **GIVEN** 一段经修复的 Case A 历史（输入中不存在 orphan `role="tool"` / 重复 id；assistant `tool_calls` 与合成 `role="tool"` 消息）
- **WHEN** 使用 OpenAI 兼容序列化（`_build_openai_messages`）
- **THEN** 每个 `tool_calls[].id` SHALL 恰有一条 `role="tool"` 消息匹配其 `tool_call_id`
- **AND** 修复 SHALL NOT **新增** orphan `role="tool"` 或同一 id 的重复结果（输入已有的畸形结果属范围外，不承诺清理）

#### Scenario: 正常链不被修改

- **GIVEN** 一个每个 assistant `tool_call` 都有配对结果的正常历史
- **WHEN** 下一次 run 开始
- **THEN** 系统 SHALL NOT 插入任何合成消息、SHALL NOT 修改既有消息
- **AND** SHALL NOT 发出 `tool_pairing_repaired` 事件

#### Scenario: resume 早期取消不丢历史

- **GIVEN** 一个含多条历史消息的 resume 快照，且恢复时 mode 变化会在 `set_mode` 处 await
- **WHEN** run 在该 await 点被取消
- **THEN** 消息历史 SHALL 已在任何 await 之前重建完成，finally 落盘的快照 SHALL 包含原历史 + 新用户输入（不是只剩新输入）
- **AND** `_execution_todos`、active skills、`user_system_prompt` 等同步恢复状态 SHALL 也已在 await 之前恢复，落盘快照 SHALL NOT 丢失这些状态
- **AND** 落盘前 SHALL 继续执行配对修复

#### Scenario: finally 修复的 trace 记录

- **GIVEN** run 在工具执行中被取消，finally 的配对修复是唯一修复点
- **WHEN** run 带 `trace_recorder`
- **THEN** trace SHALL 同步记录一条 `source="finally"` 的 `tool_pairing_repaired` step（count/bounded ids）
- **AND** SHALL NOT await Web 事件、SHALL NOT 改变原始取消/异常传播

#### Scenario: 中断落盘前尽力补齐

- **GIVEN** run 在 assistant `tool_calls` 已写入、`tool_result` 未写入之间被取消或抛异常
- **WHEN** `AgentLoop.run` 的 `finally` 执行并落盘
- **THEN** 系统 SHALL 在 `_save_session` 前同步补齐该轮缺失的配对结果
- **AND** 取消/原始异常 SHALL 继续向上传播（失败语义不变）
- **AND** 该保证 SHALL NOT 被解释为覆盖 SIGKILL/断电（这两种场景进程不执行 `finally`）

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

### Requirement: 流式 tool call 参数不完整时降级而非崩溃

Agent runtime SHALL 在流式响应中拿到**不完整**的 tool call 参数时**降级处理**，SHALL NOT 因解析失败而让 run 崩溃。

具体地，当流式 tool call 的累积参数不是合法 JSON 时：

- 若该响应的 `stop_reason` 为 `max_tokens`（输出被上限截断），runtime SHALL **丢弃**该不完整 tool call，并 SHALL 保留 `stop_reason` 为 `max_tokens`，使 `AgentLoop` 的既有续接路径得以接管（不完整调用 SHALL NOT 进入消息历史中的 assistant tool_calls，以维护 tool_use/tool_result 配对不变量）。
- 其它情况（流中断、端点异常等），runtime SHALL 保留该 tool call 并把**原始参数串**交给上层解析，使其降级为可恢复的 tool error。

依据（issue #249）：流式 tool call 的参数是分片到达的（Anthropic `input_json_delta`），在收到终局事件前不完整；`max_tokens` 截断或连接中断会留下未闭合的 JSON。业界标准处置是「先看 stop/finish reason，截断时让模型继续或大声失败，**绝不把 fragment 当结果执行**」。

#### Scenario: max_tokens 截断丢弃不完整 tool call 并续接

- **GIVEN** provider 的流式响应因输出上限被截断（`stop_reason == "max_tokens"`）
- **AND** 该响应中某个 tool call 的累积参数不是合法 JSON
- **WHEN** AgentLoop 处理该响应
- **THEN** runtime SHALL NOT 抛出 JSON 解析异常
- **AND** `LLMResponse.tool_calls` SHALL NOT 包含该不完整 tool call
- **AND** `LLMResponse.stop_reason` SHALL 仍为 `max_tokens`
- **AND** 消息历史 SHALL NOT 出现无配对 `tool_result` 的 `tool_use` block
- **AND** 若该响应中**没有**其它参数完整的 tool call，AgentLoop SHALL 走既有续接路径（追加续接消息并继续迭代），而不是终止 run
- **AND** 若该响应中**存在**其它参数完整的 tool call，AgentLoop SHALL 照常执行它们并继续运行（不因截断而终止；此时本 Scenario 不要求追加续接消息）

#### Scenario: 非截断场景保留原始参数串并降级为 tool error

- **GIVEN** provider 的流式响应正常结束（`stop_reason != "max_tokens"`）
- **AND** 该响应中某个 tool call 的累积参数不是合法 JSON
- **WHEN** AgentLoop 处理该响应
- **THEN** runtime SHALL NOT 抛出 JSON 解析异常
- **AND** `LLMResponse.tool_calls` SHALL 保留该 tool call，其 `arguments` SHALL 为原始（不完整）字符串
- **AND** AgentLoop SHALL 将其降级为可恢复的 tool error 并继续运行

#### Scenario: 合法参数行为不变

- **GIVEN** provider 的流式响应中 tool call 的累积参数是合法 JSON
- **WHEN** AgentLoop 处理该响应
- **THEN** runtime SHALL 按现状产出该 tool call，`arguments` 的规范化结果 SHALL NOT 改变
- **AND** runtime SHALL NOT 因本降级逻辑改变任何合法输入路径的行为

#### Scenario: 重放历史中的非法 tool 参数不崩溃

- **GIVEN** 会话历史中存在一个 assistant 消息，其某个 tool call 的 `arguments` 不是合法 JSON
  （来源为「非截断场景保留原始串」的降级结果）
- **WHEN** runtime 构造下一次 LLM 请求（重放该 assistant 消息）
- **THEN** runtime SHALL NOT 抛出 JSON 解析异常
- **AND** 该 tool call 的 `input` SHALL 降级为空对象
- **AND** 该 tool call SHALL NOT 因重放而被执行

### Requirement: SSE 可观测性区分协议控制帧与坏行

Agent runtime 的 SSE 解析 SHALL 区分「协议规定的非 JSON 控制帧」与「真正无法解析的数据行」，SHALL NOT 把前者报告为后者。

具体地，OpenAI 协议的流结束哨兵 `data: [DONE]` 按约定不是 JSON 对象，SHALL 在进入 JSON 解析**之前**被识别并跳过；runtime SHALL NOT 因该哨兵产生「解析失败 / 丢弃坏行」类告警。真实无法解析的数据行 SHALL 仍然产生告警（不得以消除误报为由关闭可观测性）。

依据（issue #251）：issue #249 为让静默丢行可观测而新增了解析失败告警，但未特判 `[DONE]`，导致每次 OpenAI 请求结束都刷一条误导性「Dropping unparseable SSE data line」告警——文案与事实不符（该行本就不产生事件、无数据被丢）。修复须同时保住两个性质：哨兵不告警、坏行仍告警。

#### Scenario: 流结束哨兵不产生解析失败告警

- **GIVEN** SSE 流中出现 `data: [DONE]` 结束哨兵
- **WHEN** runtime 解析该流
- **THEN** runtime SHALL NOT 因该行产生「解析失败 / 丢弃坏行」类告警
- **AND** runtime SHALL NOT 因该行产生任何事件（与哨兵出现前的行为一致）
- **AND** 该流其余可解析行 SHALL 照常产生事件

#### Scenario: 真实坏行仍然告警

- **GIVEN** SSE 流中出现无法解析为 JSON 的数据行（非协议控制帧）
- **WHEN** runtime 解析该流
- **THEN** runtime SHALL 为该行产生一条可观测的告警
- **AND** runtime SHALL 继续处理该流其余可解析行，SHALL NOT 因该行中断整个流

#### Scenario: 含哨兵字面量的合法 JSON 不被误判

- **GIVEN** SSE 流中某数据行是合法 JSON，且其内容恰好包含 `[DONE]` 字面量（如 `{"text":"[DONE]"}`）
- **WHEN** runtime 解析该流
- **THEN** runtime SHALL 按正常 JSON 解析该行
- **AND** runtime SHALL NOT 因该行包含该字面量而把它当作流结束哨兵跳过

### Requirement: 父 run 通过显式运行时接口管理子 session

父 AgentLoop SHALL 通过显式运行时接口创建、启动、查询、等待、取消和检查子 session / 子 run，而不是通过自动消息注入或伪造 tool result 把子结果并入父 messages。

这些接口返回给**模型面**的 run envelope SHALL bounded：`summary` 字段 SHALL 不超过一个**固定**的
单条内容上限，SHALL NOT 默认返回子 agent 的全文输出。全文 SHALL 通过 envelope 里的显式引用
（`result_ref` / `summary_ref`）按需读取。

该上限 SHALL **独立于 run 预算**（`max_tokens` 等）：`max_tokens` 由发起调用的模型自行设定且无上界
校验，若上限随其浮动，则「被检视的子 agent」可通过调大自身预算来放大父 agent 收到的内容——
上限 SHALL NOT 具有这一性质。该上限 SHALL 与消息 `content` 的单条上限同值（两者都是子 agent
撰写的原始文本，SHALL NOT 有两套口径）。

bounded 化 SHALL 只发生在**出口投影**：run 记录本身 SHALL 保留全文（下游聚合依赖它）。
调度器等内部消费方 SHALL 能显式取得全量 summary，SHALL NOT 因出口 bounded 而丢失聚合输入。

截断发生时返回体 SHALL 说明这一点（截断标记 / 可导航的引用），SHALL NOT 出现「声称全文在某个引用、
而该引用不存在」的表述。

#### Scenario: 父 run 查询子 run 结果

- **GIVEN** 一个已存在的子 session 和其最近一次子 run
- **WHEN** 父 agent 调用 `GetSubagentRun`
- **THEN** 系统 SHALL 返回结构化结果
- **AND** SHALL NOT 直接修改父 run 的 messages transcript

#### Scenario: 超长子 agent 输出在模型面被 bounded

- **GIVEN** 子 run 输出了远超单条上限的文本（例如 30,000 字）
- **WHEN** 父 agent 调用 `GetSubagentRun`
- **THEN** 返回的 `summary` SHALL 不超过固定的单条内容上限
- **AND** 返回体 SHALL 提供可取回全文的引用
- **AND** run 记录本身的 `summary` SHALL 仍为全文（受影响的是出口投影，不是记录）

#### Scenario: 上限不随 run 预算放大

- **GIVEN** 同一个子 run 的输出长度固定且远超单条上限
- **AND** 该 run 的预算配置（`max_tokens`）取一个很大的值
- **WHEN** 父 agent 调用 `GetSubagentRun`
- **THEN** 返回的 `summary` SHALL 仍不超过该固定上限
- **AND** 结果 SHALL NOT 随 `max_tokens` 的取值变化

#### Scenario: 截断标记不指向不存在的引用

- **GIVEN** 一个没有 workflow 身份、因而全文未落盘的子 run，其输出超过摘要预算
- **WHEN** 该 run 的结果经模型面出口返回
- **THEN** 截断相关的文本 SHALL NOT 声称全文可从某个引用取得
- **AND** SHALL 仍然如实表达「内容已被截断」

#### Scenario: 调度器内部消费仍取全量

- **GIVEN** 一个 workflow 节点由子 run 的结果驱动，其输出超过摘要预算
- **WHEN** 调度器读取该 run 的结果用于下游聚合
- **THEN** 调度器 SHALL 取得**全量** summary
- **AND** SHALL NOT 使用被出口投影截断后的版本

### Requirement: 编排结果中的 bus 快照有界

编排中 `MessageBus.snapshot_payload()` 的产出 SHALL bounded：每条消息的 `summary` SHALL 不超过与其它模型面出口同值的固定单条上限，返回的消息条数 SHALL 有固定上限。该 Requirement SHALL 适用于**任何仍向模型面暴露 bus 快照的出口**（当前为 `ReadBus` 工具与调度器权威 `_envelope()`）；父 agent 的 workflow 结果投影（`parent_envelope()`）SHALL NOT 携带 `bus`，因此不在此列。

该快照是一次编排里所有 worker 发布消息折进模型上下文的注入路径，故条数上限 SHALL 存在——否则「一次调用注入多少上下文」由被检视的子 agent 决定。

超出条数上限时，快照 SHALL **显式报告**被省略的条数（例如 `messages_omitted` / `messages_total`），SHALL NOT 静默丢弃。

该界 SHALL 施加在 `snapshot_payload()` **本身**（`agent/subagent/bus.py`），SHALL NOT 只在某个调用点加固：`ReadBus` 与调度器 `_envelope()` 共用该方法，只加固一处等于留一个同类漏口。

本 Requirement 只约束 `bus` 快照这一项。历史 `RunPattern` 返回体中的 `workers[]` 与顶层 `summary` 的条数维**不在**本 Requirement 范围内（随该返回体退役一并消失）。

#### Scenario: bus 快照的界施加在方法本身

- **GIVEN** `snapshot_payload()` 是 `ReadBus` 与调度器 `_envelope()` 的共同来源
- **WHEN** 直接调用 `MessageBus.snapshot_payload()`
- **THEN** 返回体的条数与单条上限 SHALL 已生效（不依赖任何调用点额外处理）

#### Scenario: 父 agent 的编排结果投影不含 bus

- **GIVEN** 一次编排里 100 个 worker 各发布了一条 1600 字的 bus 消息
- **WHEN** 父 agent 收到统一 Workflow 入口的返回体
- **THEN** 该返回体 SHALL NOT 含 `bus` 键
- **AND** 同一批消息经 `ReadBus` 读取时 SHALL 满足条数与单条上限，并显式报告被省略的条数

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

### Requirement: reasoning 内容的采集、持久化与回传

Agent runtime SHALL 从 provider 响应中采集思维链（reasoning / thinking）内容，按 provider 的原生形态保存，并在后续请求中按该 provider 的规则回传。

具体地：

- runtime SHALL 把 reasoning 表达为**结构化的段**，每段含**可展示文本**与**可选的 opaque 回传载荷**（如 Anthropic 的 `signature`）。
- opaque 载荷 SHALL 在「采集 → 持久化 → 回放」全链路**逐字节不变**：SHALL NOT 解析、SHALL NOT 改写、SHALL NOT 重排。该不变量适用于**合法 Unicode 文本**（真实端点的签名均为 ASCII）；若 opaque 含 lone surrogate（非合法 Unicode 文本、无法持久化），runtime SHALL 降级丢弃该 opaque 并保留同段的可展示文本，SHALL NOT 让持久化崩溃。
- 采集 SHALL 覆盖 Anthropic Messages 的 `thinking` block（流式经 `thinking_delta` + `signature_delta`）与 OpenAI 兼容端点的 `reasoning_content`。
- 回传 SHALL 按 provider 规则：Anthropic 系 SHALL 在 assistant 消息中带回 thinking block（含 opaque 载荷）；OpenAI 兼容路径 SHALL 回传 `reasoning_content`。
- provider 未返回 reasoning 时，runtime SHALL NOT 产生该字段，且全链路行为 SHALL NOT 改变。

依据（issue #256）：DeepSeek V4 系列默认开启 thinking，两条协议（Anthropic / OpenAI 兼容）都要求回传、不回传报 400。官方还要求 Anthropic 的 thinking block 顺序不可重排、`signature` 不可解析。

#### Scenario: 采集 Anthropic 流式 thinking

- **GIVEN** provider 的流式响应含 `thinking` block（`thinking_delta` 增量文本 + `signature_delta` 签名）
- **WHEN** runtime 消费该响应
- **THEN** runtime SHALL 产出一个 reasoning 段，其可展示文本为累积的 thinking 文本、opaque 载荷为该签名
- **AND** 该段 SHALL 随 assistant 消息持久化

#### Scenario: 回传 Anthropic thinking block

- **GIVEN** 历史中存在带 reasoning 的 assistant 消息
- **WHEN** runtime 构造下一次 Anthropic 请求
- **THEN** 该 assistant 消息的 content SHALL 包含 thinking block
- **AND** 该 block 的 opaque 载荷 SHALL 与采集时逐字节一致
- **AND** thinking block 的相对顺序 SHALL 与原始响应一致

#### Scenario: 采集与回传 OpenAI 兼容 reasoning_content

- **GIVEN** provider 的响应含 `reasoning_content`
- **WHEN** runtime 消费该响应并构造下一次请求
- **THEN** runtime SHALL 采集该内容为 reasoning 段的可展示文本
- **AND** 后续请求的 assistant 消息 SHALL 回传 `reasoning_content`

#### Scenario: 无 reasoning 的 provider 行为不变

- **GIVEN** provider 的响应不含任何 reasoning 字段
- **WHEN** runtime 消费该响应并构造下一次请求
- **THEN** runtime SHALL NOT 产生 reasoning 段
- **AND** 请求体与响应处理 SHALL 与未引入本能力时逐字段一致

### Requirement: reasoning 的流式事件与正文隔离

Agent runtime SHALL 为思维链的流式增量发布**独立于** `assistant_delta` 的事件，使消费方能区分「思考过程」与「可见回复」。

- 思维链增量 SHALL NOT 混入 `assistant_delta`（后者语义是 assistant 可见回复的增量，消费方会写入正文）。
- 无 reasoning 时 runtime SHALL NOT 发布该事件。

依据（issue #256）：若把 thinking 混入 `assistant_delta`，Web 端会把它渲染进 markdown 正文，既污染正文也违背「思维链与正文分离展示」的需求。

#### Scenario: reasoning 增量走独立事件

- **GIVEN** provider 的流式响应开始产出思维链
- **WHEN** runtime 转发该增量
- **THEN** runtime SHALL 发布 reasoning 增量事件，SHALL NOT 发布 `assistant_delta`
- **AND** 随后产出的可见回复 SHALL 仍通过 `assistant_delta` 发布

### Requirement: 上下文压缩对 reasoning 的处理

上下文压缩（compaction）SHALL 保留**最新 assistant 轮**的 reasoning，使下一轮请求能按其 provider 规则回传；更早轮的 reasoning MAY 被丢弃。

依据（issue #256 / 官方规则）：Anthropic 要求多轮 / tool use 时**最新** assistant 轮的 thinking block 必须原样回传，而更早轮可省略（API 自动过滤）；压缩据此获得「旧轮可丢、新轮必留」的自由度。

#### Scenario: 压缩后最新轮 reasoning 仍在

- **GIVEN** 历史中存在多轮带 reasoning 的 assistant 消息
- **WHEN** compaction 重写历史
- **THEN** 压缩后最新 assistant 消息的 reasoning SHALL 仍存在（若压缩前存在）
- **AND** 更早轮的 reasoning MAY 被移除


### Requirement: LLM HTTP 错误保留响应体

当 LLM provider 返回 HTTP status >= 400 时，系统 SHALL 保留可读响应体，并使其可用于诊断；该保留 SHALL NOT 改变异常类型、重试逻辑或 run 的失败语义。

- 流式与非流式请求路径 SHALL 使用同一提取语义：在 `raise_for_status()` 前读取响应体（流式先 `aread()`），失败时允许为空串；
- 提取到的 body SHALL 附加到 `httpx.HTTPStatusError` 的可识别属性上，异常本身 SHALL 继续抛出；
- `_http_error_text` SHALL 优先返回该属性，其次回退到既有 `response.text` 读取；
- trace 的 `llm_error` 记录 MAY 增加有界 `detail` 字段；既有 `error_type` / `message` 字段与 run 失败传播 SHALL 保持不变；
- body 对外暴露时 SHALL 有界（超出截断并标记），SHALL NOT 拼接请求 payload 或 API key。

#### Scenario: 流式 HTTP 400 保留响应体

- **GIVEN** 流式 LLM 请求收到 HTTP 400，响应体为 Anthropic 风格错误 JSON
- **WHEN** `_stream_events` 处理该响应
- **THEN** 抛出的 `httpx.HTTPStatusError` SHALL 带可读响应体属性
- **AND** `_http_error_text(exc)` SHALL 返回该响应体原文
- **AND** 既有 reasoning/cache_control/vision 400 重试判定 SHALL 不受影响

#### Scenario: 非流式 HTTP 400 保留响应体

- **GIVEN** 非流式 Anthropic 或 OpenAI 请求收到 HTTP 400，响应体可读
- **WHEN** 非流式路径调用统一的 raise-with-body helper
- **THEN** 抛出的异常 SHALL 带同一响应体属性
- **AND** 既有错误日志 SHALL 与当前行为兼容

#### Scenario: 响应体不可读

- **GIVEN** provider 返回 HTTP 400，但响应体读取失败或为空
- **WHEN** 系统提取 body
- **THEN** 系统 SHALL NOT 因读取失败而崩溃或改变原始 HTTPStatusError
- **AND** 对外传播时 SHALL 不增加空 `detail`

#### Scenario: 非 HTTP 错误语义不变

- **GIVEN** LLM 调用因连接错误或非 HTTPStatusError 异常失败
- **WHEN** AgentLoop 捕获并记录 llm_error
- **THEN** 异常类型、error_type、message 与向上传播 SHALL 与现状一致
- **AND** SHALL NOT 因本要求新增 `detail` 字段
