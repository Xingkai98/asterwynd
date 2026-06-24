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

AgentLoop 对外发布统一 `assistant_delta` / `assistant_stream_complete` 事件，各端只消费 runtime 事件，不直接依赖 provider SSE 格式。

- `assistant_delta` payload SHALL 至少包含 `delta`，MAY 包含当前累计 `content`。
- `assistant_stream_complete` payload SHALL 包含完整 `content` 和 `stop_reason`。
- 完整响应仍通过现有 `llm_response` 发出；流式路径中该事件 SHALL 带 `streamed: true`，展示层 SHALL NOT 再展示其中的 `content`。
- 非流式路径 SHALL 保持现有 `llm_response` 展示语义，`streamed` 省略或为 `false`。

### Decision 2: partial delta 不写入 messages

流式 partial text 只用于展示；最终 assistant message 仍在完整响应确定后写入 messages，避免破坏 provider 协议。

### Decision 3: 第一版不暴露 tool-call argument streaming

调研 Codex、OpenCode、OpenClaw 后，本 change 只落地 assistant text streaming。provider 可以在内部聚合 tool-call arguments，但 AgentLoop 第一版只在完整 `LLMResponse.tool_calls` 确定后追加 assistant tool-call message 并执行工具。后续若需要实时展示 tool argument，可单独设计 `tool_input_delta`，避免和 assistant text delta 混用。

## Risks / Trade-offs

- [Risk] tool call streaming 与文本 streaming 混杂。Mitigation: 第一版先明确事件顺序和最终消息落点。
- [Risk] streaming 与最终 `llm_response` 重复展示。Mitigation: 流式路径给 `llm_response` 标记 `streamed: true`，Web/CLI 跳过其文本展示。
- [Risk] 多 provider streaming 能力不一致。Mitigation: 保留 non-stream fallback。
- [Risk] Web/CLI/TUI 展示语义分叉。Mitigation: 统一 AgentLoop event 类型。

## Testing Strategy

- Provider fake stream 测试覆盖 text delta 和 tool call stop reason。
- AgentLoop 测试覆盖 delta event 和最终 message 一致性。
- Web/CLI 测试覆盖实时追加输出。
- benchmark smoke 覆盖非 streaming fallback 不回退。
