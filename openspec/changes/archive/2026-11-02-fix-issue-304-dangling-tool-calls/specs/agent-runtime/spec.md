## MODIFIED Requirements

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

## ADDED Requirements

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
