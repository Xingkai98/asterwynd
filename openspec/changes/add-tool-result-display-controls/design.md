## Context

工具结果既是模型上下文的一部分，也是用户调试界面的信息。展示层需要减少噪声，但不能丢失 trace 中的真实内容。

## Goals / Non-Goals

**Goals:**

- WebFetch 默认折叠展示。
- 长工具结果有统一摘要。
- 展示折叠不影响 trace、messages 或工具返回值。

**Non-Goals:**

- 不改变工具真实返回内容。
- 不压缩 LLM 上下文。
- 不做长期 artifact 浏览器。

## Decisions

### Decision 1: 折叠属于展示策略

工具执行结果和 trace 仍保留完整内容，Web/CLI/TUI 只决定如何展示。

### Decision 2: WebFetch 先默认折叠

WebFetch 是最明确的长内容来源；后续可按长度阈值扩展到 Bash、Read 等工具结果。

## Risks / Trade-offs

- [Risk] 折叠隐藏关键信息。Mitigation: 展示摘要、长度和展开入口。
- [Risk] 各端行为不一致。Mitigation: 抽象 display policy 并写入 CLI/Web/TUI 规格。

## Testing Strategy

- Web 测试覆盖默认折叠和展开。
- CLI 测试覆盖长结果摘要。
- Trace 测试确认完整 observation 不变。
