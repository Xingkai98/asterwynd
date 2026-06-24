## Why

当前仓库的 `swebench-*` benchmark 任务仍使用“clone 外部仓库 + 本地 Python/uv 环境装依赖”的半兼容方案，而不是真正的 SWE-bench Docker harness。这样有三个问题：

- 环境隔离不够清晰，任务结果容易受当前开发机 Python、系统包和网络状态影响。
- 运行链路与 SWE-bench 官方评测模型不一致，benchmark 结论解释力不足。
- 当前实现依赖 `swebench` Python 包中的常量，但 Docker 不可用时也没有清晰的 `unsupported` 语义。

对于面向 coding-agent 岗位的项目，这一块属于 benchmark 闭环的核心基础设施，应优先修正。

## Change Type

- primary: feature
- secondary: [research]

## What Changes

- `swebench-*` 外部任务 SHALL 切换到 Docker-based evaluation harness。
- benchmark runner SHALL 在运行 Docker-based 任务前做 Docker preflight。
- 当 Docker 不可用时，Docker-based 任务 SHALL 标记为 `unsupported` 状态，并记录清晰原因；系统 SHALL NOT 回退到本地 venv 安装依赖的旧路径。
- 本仓库 `myagent-*` 本地任务 SHALL 保持现有 worktree runner，不强制统一到 Docker。
- 针对“当前开发环境无 systemd”的场景，可补充开发文档和备用脚本，但它们不属于 benchmark 核心行为规格。

## Capabilities

### Modified Capabilities

- `benchmark`: 外部 SWE-bench 风格任务改用 Docker harness，并增加 Docker preflight / `unsupported` 语义。

## Impact

- 影响代码：
  - `benchmarks/runner.py`
  - `benchmarks/task_schema.py`
  - `benchmarks/models.py`
  - 可能新增 `benchmarks/docker_*` 或等价辅助模块
- 影响测试：
  - `tests/benchmark/`
  - benchmark CLI / summary / result model / external task runner 测试
- 影响文档：
  - `docs/development-guide.md`
  - `docs/testing-guide.md`
  - `README.md`
- 非目标：
  - 不要求 benchmark CLI 自动启动 Docker daemon
  - 不要求在核心 spec 中描述容器内无 systemd 的宿主环境细节
