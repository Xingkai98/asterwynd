## Context

Agent 回复通常包含 Markdown。当前 Web UI 使用 `textContent` 显示所有消息，安全但可读性较差。

## Goals / Non-Goals

**Goals:**

- Web assistant 气泡支持 Markdown。
- 代码块、列表、链接和内联代码可读。
- 避免 XSS 和不受控 HTML 注入。

**Non-Goals:**

- 不实现完整文档编辑器。
- 不要求 CLI/TUI 在同一 change 中实现富文本。
- 不渲染工具结果中的任意 HTML。

## Decisions

### Decision 1: Web 先渲染 assistant Markdown

第一步只渲染 assistant 普通回复，用户消息和工具结果保持更保守的纯文本或受控展示。

### Decision 2: 渲染前必须有安全策略

如果引入 Markdown 库，必须禁用原始 HTML 或做 sanitizer；链接需要安全属性。

## Risks / Trade-offs

- [Risk] Markdown 渲染引入 XSS。Mitigation: 禁用 HTML / sanitizer / 浏览器测试覆盖。
- [Risk] 代码块过宽破坏布局。Mitigation: CSS 固定 overflow 和响应式约束。

## Testing Strategy

- 覆盖列表、代码块、链接和恶意 HTML。
- 浏览器测试确认消息不溢出、不执行脚本。
