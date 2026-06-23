## Context

AnthropicLLM 已有 SSE 解析测试，但 AgentLoop 的外部事件模型仍是非流式。要让 Web / CLI / TUI 像主流 coding agent 一样实时显示回复，需要把 provider streaming、AgentLoop event 和各端展示打通。

## Goals / Non-Goals

**Goals:**

- assistant 文本可以流式输出到 Web / CLI / TUI。
- 非 streaming provider 保持兼容。
- 最终 messages 仍保持合法，tool-call 链不被 partial delta 破坏。

**Non-Goals:**

- 不实现语音、二进制或多模态 streaming。
- 不要求所有 provider 第一版都支持同等粒度。
- 不改变工具执行本身的同步/异步模型。

## Decisions

### Decision 1: 先定义 runtime streaming event

AgentLoop 对外发布统一 text delta / completion 事件，各端只消费事件，不直接依赖 provider SSE 格式。

### Decision 2: partial delta 不写入 messages

流式 partial text 只用于展示；最终 assistant message 仍在完整响应确定后写入 messages，避免破坏 provider 协议。

## Risks / Trade-offs

- [Risk] tool call streaming 与文本 streaming 混杂。Mitigation: 第一版先明确事件顺序和最终消息落点。
- [Risk] 多 provider streaming 能力不一致。Mitigation: 保留 non-stream fallback。
- [Risk] Web/CLI/TUI 展示语义分叉。Mitigation: 统一 AgentLoop event 类型。

## Testing Strategy

- Provider fake stream 测试覆盖 text delta 和 tool call stop reason。
- AgentLoop 测试覆盖 delta event 和最终 message 一致性。
- Web/CLI 测试覆盖实时追加输出。
- benchmark smoke 覆盖非 streaming fallback 不回退。
