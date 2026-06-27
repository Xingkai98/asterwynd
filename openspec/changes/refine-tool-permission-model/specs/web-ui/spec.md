## ADDED Requirements

### Requirement: Web UI SHALL support tool approval requests

Web UI run SHALL 将需要审批的工具调用暴露为 pending approval request，并关联正确的 session 和 run。用户决定 SHALL 被路由回等待中的 AgentLoop instance，然后工具才能被执行或拒绝。

#### Scenario: Web 用户批准 pending 工具调用

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 用户批准该请求
- **WHEN** 决定被投递给 AgentLoop
- **THEN** AgentLoop SHALL 执行被批准的工具
- **AND** Web UI SHALL 展示该审批已批准

#### Scenario: Web 用户拒绝 pending 工具调用

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 用户拒绝该请求
- **WHEN** 决定被投递给 AgentLoop
- **THEN** AgentLoop SHALL NOT 执行工具
- **AND** Web UI SHALL 展示该审批已拒绝

#### Scenario: 并发 session 的审批路由互相隔离

- **GIVEN** 两个 Web UI session 都有 pending approval request
- **WHEN** 用户处理其中一个请求
- **THEN** 该决定 SHALL 只恢复匹配的 session/run
- **AND** SHALL NOT 影响其他 session 的 pending approval
