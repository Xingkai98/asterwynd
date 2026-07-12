## ADDED Requirements

### Requirement: Plan 和 Todo 状态作为 ContextSource

当前 plan、todo 和 plan mode 状态 SHALL 通过 ContextSource adapter 注入运行上下文，并在预算不足时允许裁剪。

#### Scenario: 当前存在计划状态

- **GIVEN** AgentLoop 中存在 plan 或 todo 状态
- **WHEN** ContextBuilder 构建上下文
- **THEN** planning adapter SHALL 渲染当前计划状态
