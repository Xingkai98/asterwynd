# Close Asterwynd Runner LLM Clients to Prevent Resource Leaks

The Asterwynd benchmark runner creates LLM HTTP clients (`httpx.AsyncClient`) for each run but never closes them. Over long benchmark sessions with many tasks, this leads to file descriptor exhaustion.

## Task

Fix the resource leak in `benchmarks/agent_runner.py`:

1. Identify where `httpx.AsyncClient` instances are created in the Asterwynd runner
2. Ensure each client is properly closed with `aclose()` after the run completes
3. Add a cleanup path that closes clients even when the run fails or times out
4. Add a `finally` block or context manager to guarantee cleanup

## Requirements

- Modify `benchmarks/agent_runner.py`
- All HTTP clients must be closed after use
- Cleanup must happen on both success and failure paths
- Long benchmark sessions must not leak file descriptors
