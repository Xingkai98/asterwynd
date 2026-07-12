## ADDED Requirements

### Requirement: Agent 可主动请求上下文压缩

系统 SHALL 提供 `compact_context` 工具，允许 agent 在长任务中主动请求压缩当前会话上下文。

#### Scenario: Agent 调用 compact_context

- **GIVEN** 当前上下文接近预算上限
- **WHEN** agent 调用 `compact_context`
- **THEN** 系统 SHALL 执行配置的压缩策略
- **AND** 返回压缩报告
