Record real AgentLoop activity into the benchmark trace.

The benchmark runner can write final diff and test steps, but a real Asterwynd run
also needs trajectory details from inside `AgentLoop`.

Add optional trace recording to `AgentLoop.run()` so callers can pass a
`TraceRecorder`. The trace should capture:

- LLM iterations,
- tool calls,
- tool results,
- edit summaries for `Edit` tool calls.

Do not break existing `on_event` behavior or existing AgentLoop tests.

