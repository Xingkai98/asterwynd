## ADDED Requirements

### Requirement: Web assistant 消息支持安全 Markdown

Web UI SHALL 对 assistant 普通回复支持安全 Markdown 子集渲染，并防止原始 HTML 注入。用户消息、工具结果、错误消息和 debug 面板 SHALL NOT 使用该 assistant Markdown renderer。

#### Scenario: assistant 返回代码块

- **GIVEN** assistant 回复包含 Markdown 代码块
- **WHEN** Web UI 展示该消息
- **THEN** 消息 SHALL 以代码块形式展示
- **AND** SHALL NOT 破坏聊天布局

#### Scenario: assistant 返回列表、链接和内联代码

- **GIVEN** assistant 回复包含列表、链接和内联代码
- **WHEN** Web UI 展示该消息
- **THEN** 列表 SHALL 以列表形式展示
- **AND** 内联代码 SHALL 以代码样式展示
- **AND** 安全链接 SHALL 包含 `rel="noopener noreferrer"`

#### Scenario: assistant 返回原始 HTML

- **GIVEN** assistant 回复包含 `<script>` 或带事件处理器的 HTML
- **WHEN** Web UI 展示该消息
- **THEN** 原始 HTML SHALL 作为文本展示
- **AND** SHALL NOT 作为 DOM HTML 执行或插入

#### Scenario: assistant 返回不安全链接

- **GIVEN** assistant 回复包含 `javascript:` 链接
- **WHEN** Web UI 展示该消息
- **THEN** 链接 SHALL NOT 渲染为可点击链接

#### Scenario: 工具结果包含 Markdown 或 HTML

- **GIVEN** 工具结果包含 Markdown 或 HTML
- **WHEN** Web UI 展示工具结果
- **THEN** 工具结果 SHALL 保持纯文本或受控展示
- **AND** SHALL NOT 使用 assistant Markdown renderer
