## ADDED Requirements

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
