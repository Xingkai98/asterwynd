# Add Timeout Safeguard to MyAgent Benchmark Runner

When running MyAgent as a benchmark agent, there is no timeout enforcement. If the agent gets stuck (e.g., LLM hangs or infinite loop), the benchmark run hangs indefinitely.

## Task

Add a timeout safeguard to the MyAgent benchmark runner in `benchmarks/agent_runner.py`:

1. Accept a per-task `timeout_seconds` configuration
2. Before starting the agent run, set up an `asyncio.wait_for()` or equivalent timeout wrapper
3. If the agent exceeds the timeout, forcefully terminate the run
4. Record the timeout as a failure with `failure_category = "test_timeout"`

## Requirements

- Modify `benchmarks/agent_runner.py`
- The timeout must be per-task, not global
- A timed-out run must still produce valid artifacts (trace, result.json)
- The timeout error must be distinguishable from test failures
