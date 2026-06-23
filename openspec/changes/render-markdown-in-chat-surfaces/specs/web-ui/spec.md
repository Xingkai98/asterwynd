## ADDED Requirements

### Requirement: Web assistant 消息支持安全 Markdown

Web UI SHALL 对 assistant 普通回复支持安全 Markdown 渲染，并防止原始 HTML 注入。

#### Scenario: assistant 返回代码块

- **GIVEN** assistant 回复包含 Markdown 代码块
- **WHEN** Web UI 展示该消息
- **THEN** 消息 SHALL 以代码块形式展示
- **AND** SHALL NOT 破坏聊天布局
