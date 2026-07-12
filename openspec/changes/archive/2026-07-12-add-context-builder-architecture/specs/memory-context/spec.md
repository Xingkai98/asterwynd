## ADDED Requirements

### Requirement: 记忆上下文作为 ContextSource

持久记忆索引和自动召回记忆 SHALL 通过 ContextSource adapter 注入运行上下文。

#### Scenario: 记忆索引可用

- **GIVEN** 当前项目存在持久记忆索引
- **WHEN** ContextBuilder 构建上下文
- **THEN** 记忆 adapter SHALL 按预算渲染记忆索引或召回结果
