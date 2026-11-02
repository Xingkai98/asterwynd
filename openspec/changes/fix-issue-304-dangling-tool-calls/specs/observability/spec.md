## MODIFIED Requirements

### Requirement: LLM 错误可观测化

可观测性系统 SHALL 在 LLM 调用失败时记录结构化 `llm_error` 事件（含 error_type），不改变 run 失败语义。

当失败是 provider 返回的 HTTP 错误（`httpx.HTTPStatusError`）且响应体可读时，`llm_error` 事件 SHALL 同时记录有界 `detail`（响应体文本，超出长度截断并标记）。`detail` SHALL 是附加字段：既有 `error_type`、`message` 与异常向上传播语义 SHALL 保持不变；非 HTTP 错误或无响应体时 SHALL NOT 新增 `detail`。

#### Scenario: LLM 网络错误记录

- **GIVEN** LLM 调用因连接错误失败
- **WHEN** loop 捕获该异常
- **THEN** trace SHALL 记录 error_type=`"network_timeout"` 的 llm_error 事件
- **AND** 异常 SHALL 继续向上传播（run 失败语义不变）

#### Scenario: LLM HTTP 400 记录响应体

- **GIVEN** LLM provider 返回 HTTP 400，响应体为 `{"type":"error","error":{"message":"..."}}`
- **WHEN** loop 捕获该 `httpx.HTTPStatusError`
- **THEN** trace 的 `llm_error` SHALL 记录 `detail` 为有界响应体文本
- **AND** `error_type` 与 `message` SHALL 保持既有口径
- **AND** 异常 SHALL 继续向上传播
