# Implement the Core AgentLoop

All the plugin systems (tools, hooks, memory, skills, sub-agents) are in place. The missing piece is the central orchestrator: the `AgentLoop` that drives the main conversation cycle.

## Task

Implement `AgentLoop` in `agent/loop.py`:

1. Accept `llm`, `tool_registry`, `hooks`, and `max_iterations` in constructor
2. The main `run(messages, tools, model) -> RunResult` method executes the agent cycle:
   - Call `hooks.before_iteration()`
   - Send messages to LLM via `llm.chat()`
   - If no tool calls: return the LLM response content
   - If tool calls: execute each tool via `tool_registry.execute()`, append results to messages, repeat
3. Handle `max_tokens` stop reason: append a continuation prompt
4. Track iteration count and stop at `max_iterations`

## Requirements

- Create `agent/loop.py`
- Use the existing `Message` and `LLM` types
- Integrate with `HookManager` for lifecycle events
- Return a `RunResult` with content, messages, and iteration count
