## ADDED Requirements

### Requirement: 工具调用失败自动重试

AgentLoop SHALL 在工具调用返回瞬时错误时自动重试。可重试错误 SHALL 匹配 `timeout|timed out|connection|rate limit|429|503|temporary` 模式。确定性错误（`permission denied|not found|invalid|no such file`）SHALL NOT 重试。

#### Scenario: 瞬时错误自动重试

- **GIVEN** 工具执行因 timeout 失败
- **WHEN** AgentLoop 检测到错误匹配可重试模式
- **THEN** AgentLoop SHALL 以指数退避间隔重试
- **AND** 最大重试次数 SHALL 为 3

#### Scenario: 重试成功

- **GIVEN** 第一次执行因 rate limit 失败
- **WHEN** 第二次重试成功
- **THEN** AgentLoop SHALL 使用成功的工具结果继续执行

#### Scenario: 确定性错误不重试

- **GIVEN** 工具执行因 `permission denied` 失败
- **WHEN** AgentLoop 检测到错误不匹配可重试模式
- **THEN** AgentLoop SHALL NOT 重试
- **AND** 错误结果直接返回给 LLM

#### Scenario: 重试次数耗尽

- **GIVEN** 工具执行连续 3 次因 timeout 失败
- **WHEN** 第 3 次重试也失败
- **THEN** AgentLoop SHALL 记录 `tool_error` trace step
- **AND** 最后一次错误结果返回给 LLM

#### Scenario: 重试不重复触发审批

- **GIVEN** 第一次工具执行已通过 approval gate
- **WHEN** 后续重试执行
- **THEN** AgentLoop SHALL NOT 再次触发 approval handler

### Requirement: build mode 注入执行期 todo 状态

AgentLoop SHALL 在 build mode 且存在非空 todo 列表时向系统消息注入当前 todo 状态摘要。

#### Scenario: todo 列表非空时注入

- **GIVEN** AgentMode 为 BUILD
- **AND** TodoWrite 工具维护了 3 个 todo item
- **WHEN** 构建系统消息
- **THEN** 系统消息 SHALL 包含 `## Current Progress` 段
- **AND** 段内 SHALL 按 status 分组展示

#### Scenario: todo 列表为空时不注入

- **GIVEN** AgentMode 为 BUILD
- **AND** todo 列表为空
- **WHEN** 构建系统消息
- **THEN** 系统消息 SHALL NOT 包含 `## Current Progress` 段
