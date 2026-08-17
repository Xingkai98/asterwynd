# 沙箱命令执行结果携带命令审计字段

当前沙箱后端是可插拔的 `ExecutionBackend`（`agent/tools/sandbox/base.py`），`ProcessBackend`（`agent/tools/sandbox/process_backend.py`）通过 `SandboxResult` 返回命令执行结果（`exit_code`/`stdout`/`stderr`/`duration_ms`/`timed_out`/`oom_killed`/`degraded`）。`SandboxResult` **没有记录「执行的是哪条命令」**——trace/审计/复现时需要从上下文自行拼回命令，且 `run()` 与 `run_sync()` 路径返回的结果不自述命令。

## Task

给 `SandboxResult` 增加 `command: str = ""` 字段（缺省空串，向后兼容），并让 `ProcessBackend` 的 `run()`（正常/超时/异常三条路径）与 `run_sync()`（正常/超时/异常三条路径）在所有构造 `SandboxResult` 的位置填入实际执行的 `command`。这样任何拿到 `SandboxResult` 的调用方都能自证「这是哪条命令的结果」。

## Requirements

- `SandboxResult` 新增可选字段 `command`，既有构造（不传）保持兼容（缺省 `""`）
- `await ProcessBackend().run("echo hello")` 的 `result.command == "echo hello"`
- `ProcessBackend().run_sync("echo hello")` 的 `result.command == "echo hello"`
- 超时/异常路径的 `SandboxResult` 同样携带 `command`
- 既有沙箱测试不得回归
