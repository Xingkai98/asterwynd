## ADDED Requirements

### Requirement: 未来 TUI 复用工具结果 display policy

未来 TUI SHALL 复用 Web / CLI 的工具结果折叠策略，不得定义不兼容的长结果展示语义。

#### Scenario: TUI 展示长工具结果

- **GIVEN** 工具返回长内容
- **WHEN** TUI 展示该结果
- **THEN** TUI SHALL 默认展示摘要
- **AND** SHALL 提供展开或查看完整内容的入口
