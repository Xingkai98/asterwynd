# Implement LoggingHook and TracingHook

The `HookManager` is in place, but no built-in hooks exist yet. The agent needs basic observability: logging of events and structured tracing of execution.

## Task

Implement two built-in hooks:

### LoggingHook (`agent/hooks/builtin/logging.py`)
1. Log agent events (LLM calls, tool executions, errors) to stdout
2. Configurable detail level (info, debug)
3. Include iteration number and timing in log messages

### TracingHook (`agent/hooks/builtin/tracing.py`)
1. Record a structured execution timeline
2. Capture tool call parameters and results
3. Track LLM request/response pairs
4. Export the trace as a dict for later analysis

## Requirements

- Create files under `agent/hooks/builtin/`
- Both must implement the `Hook` protocol from `agent/hooks/manager.py`
- Logging must be readable for human operators
- Tracing must be machine-parseable for analysis
