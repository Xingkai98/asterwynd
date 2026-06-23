## ADDED Requirements

### Requirement: CLI Markdown 展示策略与 Web 兼容

CLI SHOULD 保持 assistant Markdown 的可读性；如果不渲染富文本，SHALL 至少保持原始 Markdown 不被破坏。

#### Scenario: CLI 输出 Markdown

- **GIVEN** assistant 回复包含 Markdown
- **WHEN** CLI 输出回复
- **THEN** 用户 SHALL 能阅读原始 Markdown 或终端渲染后的等价内容
