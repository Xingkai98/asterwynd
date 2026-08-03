## ADDED Requirements

### Requirement: error_type 在产生点打标

可观测性系统 SHALL 在关键错误产生点打标结构化 `error_type`，使 `record_tool_result` 收到的是结构化 signal 而非文本猜测。文本分类 SHALL 仅作为对未打标工具的兜底。

#### Scenario: Bash 超时打标

- **GIVEN** Bash 命令在沙箱中超时（`SandboxResult.timed_out=True`）
- **WHEN** loop 记录该工具结果
- **THEN** trace 的 tool_result SHALL 携带 status=`"error"`
- **AND** error_type SHALL 为 `"timeout"`

#### Scenario: approval 预拒绝打标

- **GIVEN** 工具调用要求审批但被拒绝（approval DENIED）
- **WHEN** loop 记录该工具结果
- **THEN** trace 的 tool_result SHALL 携带 status=`"error"`
- **AND** error_type SHALL 为 `"approval_denied"`

#### Scenario: 结构化优先于文本兜底

- **GIVEN** 一个打标工具返回 error_type=`"permission_denied"` 的结构化结果
- **WHEN** loop 判定该工具结果状态
- **THEN** 系统 SHALL 使用结构化 error_type 判定 status=`"error"`
- **AND** SHALL NOT 依赖文本前缀猜测

#### Scenario: 未打标工具仍走文本兜底

- **GIVEN** 一个未打标工具返回 `"[Error: timed out]"` 文本
- **WHEN** loop 判定该工具结果状态
- **THEN** 系统 SHALL 通过文本兜底分类为 `"network_timeout"`（文本兜底返回粗粒度 category.value）
- **AND** status SHALL 为 `"error"`

### Requirement: LLM 错误可观测化

可观测性系统 SHALL 在 LLM 调用失败时记录结构化 `llm_error` 事件（含 error_type），不改变 run 失败语义。

#### Scenario: LLM 网络错误记录

- **GIVEN** LLM 调用因连接错误失败
- **WHEN** loop 捕获该异常
- **THEN** trace SHALL 记录 error_type=`"network_timeout"` 的 llm_error 事件
- **AND** 异常 SHALL 继续向上传播（run 失败语义不变）
