# Implement SandboxExecutor

The project needs a sandboxed execution environment for running shell commands safely. Currently, tools like Bash need to execute shell commands, but there's no controlled way to do this with timeout and output capture.

## Task

Implement `SandboxExecutor` in `agent/tools/sandbox.py` that:

1. Wraps `asyncio.subprocess` for async shell command execution
2. Accepts a configurable `timeout` (default 30 seconds)
3. Captures `stdout` and `stderr` output
4. Imposes `max_memory_mb` limit (default 512MB)
5. Provides both `async run()` and `run_sync()` methods
6. Returns command output as a string, including exit code on failure

## Requirements

- Create `agent/tools/sandbox.py`
- Use `asyncio.create_subprocess_shell()` for async execution
- Use `subprocess.run()` for synchronous execution
- Handle `TimeoutError` gracefully (return timeout message, don't crash)
- Handle generic exceptions gracefully

The sandbox is the security boundary for all tool execution. It must be reliable.
