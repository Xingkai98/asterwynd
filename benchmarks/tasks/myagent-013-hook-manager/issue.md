# Implement HookManager and Hook Protocol

The agent needs a lifecycle extension system so that cross-cutting concerns (logging, tracing, retry, token budgeting) can be added without modifying the core agent loop.

## Task

Implement two components:

### Hook Protocol (`agent/hooks/__init__.py`)
Define a `Hook` ABC with lifecycle methods:
- `before_iteration(iteration, messages)`
- `after_iteration(iteration, messages)`
- `before_tool_execute(tool_call)`
- `after_tool_execute(tool_call, result)`
- `before_llm_call(messages, tools)`
- `after_llm_call(response)`

### HookManager (`agent/hooks/manager.py`)
1. Maintain an ordered list of `Hook` instances
2. Provide a `CompositeHook` that dispatches events to all registered hooks
3. Each event calls the corresponding method on every hook in sequence

## Requirements

- Create `agent/hooks/__init__.py` and `agent/hooks/manager.py`
- Use `Protocol` or `ABC` for the Hook type
- The manager must call hooks in registration order
- Hook failures in one hook must not prevent other hooks from running
