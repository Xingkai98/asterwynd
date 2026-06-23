## Why

当前系统虽然部分 provider 内部支持 SSE 解析，但 AgentLoop 对外仍在完整 LLMResponse 返回后才发 `llm_response`。长回复时 Web UI / CLI 没有即时反馈，未来 TUI 也无法展示实时生成过程。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 扩展 LLM 协议或新增 streaming path，支持 assistant text delta 事件。
- AgentLoop SHALL 发布流式 token / text delta 事件，同时保持 tool-call 消息链合法。
- Web UI、CLI 和未来 TUI SHALL 复用同一 streaming event 语义。
- 非 streaming provider SHALL 保持兼容，仍可一次性返回完整回复。

## Capabilities

### Modified Capabilities

- `agent-runtime`: 发布流式 assistant 输出事件。
- `web-ui`: WebSocket 消费流式输出。
- `cli`: CLI 实时打印 assistant 输出。
- `tui`: 未来 TUI 复用 streaming event。

## Impact

- 影响代码：
  - `agent/llm.py`
  - `agent/openai_llm.py`
  - `agent/anthropic_llm.py`
  - `agent/loop.py`
  - `cli.py`
  - `web/`
- 影响测试：
  - LLM provider streaming tests
  - AgentLoop event tests
  - CLI/Web streaming tests
- 后续需要仔细设计 tool call streaming、partial text 和最终 assistant message 的关系。
