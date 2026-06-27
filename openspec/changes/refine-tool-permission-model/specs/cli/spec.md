## ADDED Requirements

### Requirement: Interactive CLI SHALL support tool approval

Interactive CLI run SHALL 提供 ApprovalHandler，在执行被判定为 `require_approval` 的工具调用前提示用户审批。

#### Scenario: 用户在 interactive CLI 批准

- **GIVEN** AgentLoop 请求审批一个工具调用
- **AND** 用户在 interactive CLI 中批准
- **WHEN** AgentLoop 恢复该工具调用
- **THEN** 工具 SHALL 执行
- **AND** CLI SHALL 在运行输出中展示审批决定

#### Scenario: 用户在 interactive CLI 拒绝

- **GIVEN** AgentLoop 请求审批一个工具调用
- **AND** 用户在 interactive CLI 中拒绝
- **WHEN** AgentLoop 恢复该工具调用
- **THEN** 工具 SHALL NOT 执行
- **AND** CLI SHALL 展示该工具调用已被拒绝

### Requirement: Non-interactive CLI SHALL fail closed for approval-required tools

Single-prompt 和非 TTY CLI run SHALL NOT 阻塞等待审批。它们 SHALL 对被判定为 `require_approval` 的工具调用使用 fail-closed 审批行为。

#### Scenario: single-prompt run 需要审批

- **GIVEN** 一个 single-prompt CLI run
- **AND** 模型调用的工具被判定为 `require_approval`
- **WHEN** AgentLoop 请求审批
- **THEN** CLI SHALL 返回 approval unavailable
- **AND** 工具 SHALL NOT 执行
