## ADDED Requirements

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

### Requirement: Approval records SHALL be observable

AgentLoop SHALL 在 trace/debug/display 路径记录审批请求和审批决定，包含 tool name、capability、risk level、origin、当前 mode、审批结果和安全的参数摘要。

#### Scenario: 审批 trace 包含权限上下文

- **GIVEN** 一个工具调用需要审批
- **WHEN** AgentLoop 创建审批请求
- **THEN** trace/debug/display 数据 SHALL 包含工具权限元数据和 profile 判定原因
- **AND** 当配置了敏感信息隐藏时，SHALL NOT 暴露未脱敏的敏感参数
