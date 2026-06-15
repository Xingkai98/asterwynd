# Scope BashTool Execution to Workspace Directory

The `BashTool` currently runs commands without a specific working directory. For coding agent use, bash commands must run inside the configured workspace. Additionally, the `SandboxExecutor` needs to support a `cwd` parameter for directory-aware execution.

## Task

1. Add a `cwd` parameter to `SandboxExecutor.run()` and `SandboxExecutor.run_sync()` in `agent/tools/sandbox.py`
2. Update `BashTool` in `agent/tools/builtin/bash.py` to pass the workspace root as `cwd` to the sandbox
3. Extend `WorkspacePolicy` to validate that the command's working directory is within the workspace
4. Ensure the benchmark runner passes the task workspace directory

## Requirements

- `SandboxExecutor` methods must accept an optional `cwd` parameter
- `BashTool` must run commands in the workspace root by default
- Commands running outside the workspace must be rejected
- Existing tests must continue to pass
