## Why

当前 `WorkspacePolicy.assert_command_allowed()` 先匹配 allowlist，命中后直接放行，导致 `python -c`、`cp /etc/passwd`、`mv .env ...` 等宽泛前缀命令绕过 denylist。Bash 是 dangerous tool，这个行为削弱了 workspace safety 的命令边界。

## What Changes

- 命令策略改为 denylist 优先；命中 denylist 的命令 SHALL 一律拒绝。
- 收窄高风险 allowlist 前缀，避免 `python -c`、`python -m` 以外任意脚本执行、`cp`/`mv` 访问敏感路径等被直接放行。
- 明确允许常见验证命令，例如 `pytest`、`python -m pytest`、`uv run pytest`、`git diff`、`rg`、`cat` 等。
- 保持 BashTool 返回行为不变：policy 拒绝时返回 `Error: Command denied by workspace policy`。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `workspace-safety`: Bash command policy 从 allowlist 优先改为 denylist 优先，并收紧宽泛命令前缀。

## Impact

- 影响代码：
  - `agent/workspace_policy.py`
  - `agent/tools/builtin/bash.py` 如错误信息需要同步时调整
- 影响测试：
  - `tests/agent/test_workspace_policy.py`
  - `tests/agent/tools/test_bash_tool_workspace.py`
  - `tests/agent/tools/test_bash_tool_structured_output.py`
- 不处理 Read/Grep read policy、Memory compact 和 benchmark artifact 文档问题。

