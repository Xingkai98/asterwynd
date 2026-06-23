## Why

当前 Web UI 对话气泡使用纯文本渲染，assistant 回复里的 Markdown 列表、代码块、链接和表格不可读。Coding agent 输出天然包含 diff、命令、代码片段和步骤说明，缺少 Markdown 渲染会降低调试和演示体验。

## Change Type

- primary: feature
- secondary: []

## What Changes

- Web UI 对 assistant 消息进行安全 Markdown 渲染。
- 明确用户消息、工具结果和 assistant 消息的渲染边界。
- 使用无构建链的轻量静态 renderer；不在本 change 引入前端框架、npm 构建链或 CDN 依赖。
- 为 CLI 和未来 TUI 记录兼容策略：可以保留纯文本，也可以使用终端安全的 Markdown/ANSI renderer，但语义不应与 Web 冲突。

## Capabilities

### Modified Capabilities

- `web-ui`: 对话气泡支持安全 Markdown 展示。
- `cli`: 记录 CLI Markdown 展示兼容策略。
- `tui`: 未来 TUI 复用相同展示语义。

## Impact

- 影响代码：
  - `web/static/`
  - 新增轻量静态 Markdown renderer。
- 影响测试：
  - Web 静态渲染测试或浏览器测试。
- 后续需要确认允许的 Markdown 子集和链接安全策略。
