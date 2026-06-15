# Refactor AnthropicLLM to Use SSE Streaming

The `AnthropicLLM` currently uses a blocking HTTP request for chat completions. This is slow and doesn't support streaming responses. For a responsive agent, we need Server-Sent Events (SSE) streaming with incremental text and tool use accumulation.

## Task

Refactor `AnthropicLLM.chat()` in `agent/anthropic_llm.py`:

1. Replace the blocking HTTP request with SSE streaming
2. Parse SSE events: `content_block_start`, `content_block_delta`, `content_block_stop`
3. Accumulate text content incrementally from delta events
4. Accumulate tool use `input_json` incrementally across multiple delta events
5. Extract a shared `_stream_events()` method in the base `LLM` class for SSE parsing

## Requirements

- Modify `agent/anthropic_llm.py` and `agent/llm.py`
- The streaming implementation must handle partial JSON for tool arguments
- Must work with Anthropic's SSE event format
- Must not break the non-streaming code path for other providers
