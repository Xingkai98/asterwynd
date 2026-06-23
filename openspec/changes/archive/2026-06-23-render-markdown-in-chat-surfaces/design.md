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
- 不引入前端构建链、前端框架或 CDN 依赖。

## Decisions

### Decision 1: Web 先渲染 assistant Markdown

第一步只渲染 assistant 普通回复，用户消息和工具结果保持更保守的纯文本或受控展示。

### Decision 2: 渲染前必须有安全策略

如果引入 Markdown 库，必须禁用原始 HTML 或做 sanitizer；链接需要安全属性。

### Decision 3: 当前 change 使用轻量安全 Markdown 子集

当前 Web 静态资源没有 npm/Vite 构建链。为了保持变更小范围，本 change 使用独立静态 `markdown.js` 实现安全 Markdown 子集，不引入第三方依赖或前端架构重构。

支持的子集包括 fenced code block、inline code、无序/有序列表、段落、标题、链接、粗体和斜体。原始 HTML 永远作为文本转义；链接只允许 `http:`、`https:`、`mailto:`、站内路径和锚点，并为外链加安全属性。

### Decision 4: streaming assistant 内容保留原始 Markdown 源

WebSocket 增量到达时，assistant 气泡保存原始 Markdown 文本并重新渲染当前气泡；用户消息、工具结果、错误和 debug 面板不进入 Markdown renderer。

## Risks / Trade-offs

- [Risk] Markdown 渲染引入 XSS。Mitigation: 禁用 HTML / sanitizer / 浏览器测试覆盖。
- [Risk] 代码块过宽破坏布局。Mitigation: CSS 固定 overflow 和响应式约束。
- [Risk] 自研 renderer 覆盖不完整。Mitigation: 明确只支持本 change 需要的 Markdown 子集；完整前端重构或成熟 Markdown 库接入留给后续独立需求。

## Testing Strategy

- 覆盖列表、代码块、链接和恶意 HTML。
- 静态资源测试确认 assistant 使用 Markdown renderer，工具结果保持 `textContent`。
- Node 测试直接执行 `markdown.js`，验证 raw HTML 转义和不安全链接降级。
