## ADDED Requirements

### Requirement: 未来 TUI 复用 Markdown 展示语义

未来 TUI SHALL 复用 Web / CLI 的 Markdown 安全边界，不得渲染不受信任 HTML。

#### Scenario: TUI 展示 assistant Markdown

- **GIVEN** assistant 回复包含 Markdown
- **WHEN** TUI 展示回复
- **THEN** TUI SHALL 保持内容可读
- **AND** SHALL 遵守与 Web 一致的安全边界
