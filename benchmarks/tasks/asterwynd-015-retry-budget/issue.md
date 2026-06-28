# Implement TokenBudgetHook and RetryHook

The agent needs robustness against two common failure modes: exceeding token limits and transient failures in LLM calls or tool execution.

## Task

Implement two built-in hooks:

### TokenBudgetHook (`agent/hooks/builtin/token_budget.py`)
1. Track per-turn token usage
2. Raise a warning when approaching the token limit (e.g., 80% of max)
3. Signal the agent loop to stop when the hard limit is reached
4. Configurable `max_tokens` and `warning_ratio`

### RetryHook (`agent/hooks/builtin/retry.py`)
1. Catch failures in LLM calls and tool execution
2. Retry with exponential backoff (configurable max retries, base delay)
3. Log each retry attempt with the failure reason
4. Give up after max retries and propagate the error

## Requirements

- Create files under `agent/hooks/builtin/`
- Both must implement the `Hook` protocol
- Retry must not retry on permanent errors (e.g., PermissionError)
- Token budget must be calculated using tiktoken
