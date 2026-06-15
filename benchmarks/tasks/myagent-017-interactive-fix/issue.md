# Fix Interactive Mode and MiniMax API Compatibility

The CLI interactive mode has multiple bugs that prevent reliable multi-turn conversations, especially with non-OpenAI API providers like MiniMax.

## Issues to Fix

1. **CLI event loop reuse**: `cli.py` creates a new event loop for each interactive call, causing `AsyncClient` to reference a closed loop on subsequent turns. Fix: reuse a persistent event loop.

2. **MiniMax API compatibility**: `AnthropicLLM` calls `response.json()` which returns a synchronous dict from MiniMax (not awaitable). Fix: handle both sync and async response types.

3. **Surrogate character handling**: Messages containing surrogate characters crash `json.dumps`. Fix: filter or replace surrogate characters before serialization.

4. **Tool call serialization**: Assistant `tool_calls` must be serialized as `tool_use` content blocks in the message format that Anthropic-compatible APIs expect.

5. **AgentLoop tool use messages**: After executing tool calls, the assistant's message (with `tool_use` blocks) must be appended to messages.

## Requirements

- Fix all 5 issues
- Interactive mode must support 3+ consecutive turns without crashing
- Must work with both OpenAI and Anthropic-compatible (MiniMax) APIs
