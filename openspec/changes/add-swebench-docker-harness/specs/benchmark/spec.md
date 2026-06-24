## ADDED Requirements

### Requirement: Docker-based SWE-bench 任务使用显式环境前置条件

benchmark SHALL 支持一类需要 Docker daemon 的外部 SWE-bench 风格任务。该类任务运行前，runner SHALL 做 Docker preflight；当 Docker 可用时，任务 SHALL 使用 Docker-based evaluation harness 执行。

#### Scenario: Docker 可用时运行 SWE-bench 任务

- **GIVEN** 某 benchmark 任务被标记为 Docker-based SWE-bench 风格任务
- **AND** 当前环境能连接 Docker daemon
- **WHEN** runner 执行该任务
- **THEN** 系统 SHALL 使用 Docker-based evaluation harness
- **AND** SHALL NOT 回退到本地 venv 安装依赖路径

### Requirement: Docker 不可用时显式 skip Docker-based 任务

当 Docker-based SWE-bench 风格任务的 Docker preflight 失败时，benchmark SHALL 将该任务标记为 `skipped` 或等价 `unsupported` 状态，并在 artifact 中记录环境不满足的原因。

#### Scenario: Docker daemon 不可用

- **GIVEN** 某 benchmark 任务被标记为 Docker-based SWE-bench 风格任务
- **AND** 当前环境无法连接 Docker daemon
- **WHEN** runner 尝试执行该任务
- **THEN** 该任务 SHALL 写入 `result.json`、`trace.json` 和 `runner.log`
- **AND** 结果状态 SHALL 为 `skipped` 或等价 `unsupported`
- **AND** 原因 SHALL 明确指出 Docker 环境不可用
- **AND** 系统 SHALL NOT 将该结果计为 agent `failed` 或 `error`

### Requirement: 本地 benchmark 任务不受 Docker 依赖影响

本仓库本地 benchmark 任务 SHALL 保持现有本地 worktree 执行路径，不得因为 Docker-based SWE-bench 任务的引入而强制要求 Docker。

#### Scenario: 混合任务集包含本地任务和 Docker-based 任务

- **GIVEN** 同一次 benchmark run 同时包含本地 `myagent-*` 任务和 Docker-based SWE-bench 风格任务
- **AND** 当前环境 Docker 不可用
- **WHEN** runner 执行该任务集
- **THEN** 本地 `myagent-*` 任务 SHALL 继续执行
- **AND** Docker-based 任务 SHALL 显式 skip
