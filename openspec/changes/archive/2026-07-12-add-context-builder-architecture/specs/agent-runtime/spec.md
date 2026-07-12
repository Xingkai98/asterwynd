## ADDED Requirements

### Requirement: AgentLoop 使用 ContextBuilder 构建运行上下文

AgentLoop SHALL 使用 ContextBuilder 统一注册、排序、预算、裁剪和渲染运行上下文来源。

#### Scenario: 构建包含多个来源的上下文

- **GIVEN** system prompt、memory index、active skill 和 plan state 同时存在
- **WHEN** AgentLoop 构建模型消息
- **THEN** 系统 SHALL 通过 ContextBuilder 按优先级生成最终上下文
- **AND** 返回上下文构建报告

### Requirement: ContextBuilder 生成构建报告

ContextBuilder SHALL 记录每个 ContextSource 的 id、优先级、预算、token 估算、裁剪状态和渲染结果状态。

#### Scenario: 低优先级来源被裁剪

- **GIVEN** 总上下文超过预算
- **WHEN** ContextBuilder 裁剪低优先级来源
- **THEN** 构建报告 SHALL 记录被裁剪来源和原因
