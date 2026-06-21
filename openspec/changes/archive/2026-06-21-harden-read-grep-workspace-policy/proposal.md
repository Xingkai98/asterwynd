## Why

当前 ReadTool 和 GrepTool 直接使用传入路径读取文件，没有经过 WorkspacePolicy。审计探针已确认它们可以读取 workspace 外文件和 `.env` 内容，这与 MyAgent 的 workspace safety 能力目标冲突。

## What Changes

- ReadTool 改为使用 WorkspacePolicy 校验读取路径。
- GrepTool 改为使用 WorkspacePolicy 校验搜索起点，并在递归搜索时跳过 denied pattern 命中的文件和目录。
- WorkspacePolicy 的 read 校验从“只限制 workspace 内”升级为“workspace 内 + 默认敏感路径拒绝”。
- **BREAKING**: 通过 Read/Grep 读取 workspace 外路径、`.env`、`.git`、`.venv`、`node_modules`、`benchmarks/runs` 等 denied patterns 的行为将从允许变为拒绝。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `coding-tools`: Read 和 Grep 的读取行为从直接读路径改为受 WorkspacePolicy 约束。
- `workspace-safety`: read policy 从仅校验 workspace root 改为同时应用 denied patterns。

## Impact

- 影响代码：
  - `agent/tools/builtin/read.py`
  - `agent/tools/builtin/grep.py`
  - `agent/tools/__init__.py`
  - `agent/workspace_policy.py`
- 影响测试：
  - `tests/agent/tools/test_read_write_tools.py`
  - `tests/agent/tools/test_find_tool.py` / `test_list_files_tool.py` 如 read policy 影响共享行为则同步调整
  - `tests/agent/test_workspace_policy.py`
  - benchmark runner 相关测试需要确认任务 workspace policy 注入仍然正常
- 不引入新外部依赖。
- 不处理 Bash allowlist、Memory compact summary、DebugHook 和 benchmark 文档口径问题；这些已记录在审计文档，后续单独 change。
