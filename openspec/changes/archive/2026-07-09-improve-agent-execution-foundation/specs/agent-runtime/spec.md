## ADDED Requirements

### Requirement: 工具调用失败自动重试

AgentLoop SHALL 在工具执行抛出瞬时异常时自动重试。仅对 Exception 消息做模式匹配——工具正常返回的错误字符串（如 `[Error: ...]`）视为执行成功，不触发重试。可重试异常 SHALL 匹配 `timeout|timed out|connection|rate limit|429|503|temporary` 模式。不匹配此模式的异常（如 `permission denied|not found|invalid|no such file`）SHALL NOT 重试。

#### Scenario: 瞬时异常自动重试

- **GIVEN** 工具执行抛出 `TimeoutError`
- **WHEN** AgentLoop 检测到异常消息匹配可重试模式
- **THEN** AgentLoop SHALL 以指数退避间隔重试
- **AND** 最大重试次数 SHALL 为 3（1 次初始调用 + 最多 3 次重试 = 最多 4 次总尝试）

#### Scenario: 重试成功

- **GIVEN** 第一次执行抛出匹配可重试模式的异常
- **WHEN** 第二次重试成功
- **THEN** AgentLoop SHALL 使用成功的工具结果继续执行

#### Scenario: 不匹配的异常不重试

- **GIVEN** 工具执行抛出 `ValueError("invalid arguments")`
- **WHEN** AgentLoop 检测到异常消息不匹配可重试模式
- **THEN** AgentLoop SHALL NOT 重试
- **AND** 错误消息直接返回给 LLM

#### Scenario: 工具返回错误字符串不重试

- **GIVEN** 工具执行成功但返回 `[Error: connection timed out]` 字符串
- **WHEN** AgentLoop 收到此工具结果
- **THEN** AgentLoop SHALL NOT 重试——工具返回字符串视为正常执行结果

#### Scenario: 重试次数耗尽

- **GIVEN** 工具执行连续抛出可重试异常
- **WHEN** 所有重试均失败
- **THEN** AgentLoop SHALL 记录 `tool_retry` trace step，payload 包含 `tool_name`、`attempt`、`max_retries`、`error`、`delay_ms`、`final=true`
- **AND** 最后一次错误结果返回给 LLM

#### Scenario: 重试等待中记录 trace

- **GIVEN** 工具执行抛出可重试异常且仍有剩余重试次数
- **WHEN** AgentLoop 决定重试并等待退避间隔
- **THEN** AgentLoop SHALL 记录 `tool_retry` trace step，payload 包含 `tool_name`、`attempt`、`max_retries`、`error`、`delay_ms`、`final=false`

#### Scenario: 重试不重复触发审批

- **GIVEN** 第一次工具执行已通过 approval gate
- **WHEN** 后续重试执行
- **THEN** AgentLoop SHALL NOT 再次触发 approval handler

### Requirement: 执行期注入 todo 状态

AgentLoop SHALL 在 build mode 或 read_only mode 且存在非空 todo 列表时向系统消息注入当前 todo 状态摘要。

#### Scenario: build mode 下 todo 列表非空时注入

- **GIVEN** AgentMode 为 BUILD
- **AND** TodoWrite 工具维护了 3 个 todo item
- **WHEN** 构建系统消息
- **THEN** 系统消息 SHALL 包含 `## Current Progress` 段
- **AND** 段内 SHALL 按 status 分组展示（in_progress > pending > completed）

#### Scenario: read_only mode 下 todo 列表非空时注入

- **GIVEN** AgentMode 为 READ_ONLY
- **AND** TodoWrite 工具维护了 todo item
- **WHEN** 构建系统消息
- **THEN** 系统消息 SHALL 包含 `## Current Progress` 段

#### Scenario: todo 列表为空时不注入

- **GIVEN** AgentMode 为 BUILD 或 READ_ONLY
- **AND** todo 列表为空
- **WHEN** 构建系统消息
- **THEN** 系统消息 SHALL NOT 包含 `## Current Progress` 段

#### Scenario: Bash 命令不重试

- **GIVEN** 工具名称为 Bash
- **WHEN** 工具执行失败
- **THEN** AgentLoop SHALL NOT 重试
- **AND** 错误结果直接返回给 LLM
