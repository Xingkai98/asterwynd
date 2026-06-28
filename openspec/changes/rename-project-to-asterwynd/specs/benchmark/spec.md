## MODIFIED Requirements

### Requirement: 支持多种 agent runner

benchmark SHALL 支持 fake、shell、asterwynd 和 claude runner。

#### Scenario: 选择 asterwynd runner

- **GIVEN** 用户传入 `--agent asterwynd`
- **WHEN** benchmark 命令构造 runner
- **THEN** 系统 SHALL 使用当前 LLM 和 max_iterations 创建 AsterwyndRunner
- **AND** 系统 SHALL NOT 接受旧 `--agent myagent` 作为兼容入口

### Requirement: benchmark 支持 Docker-based SWE-bench harness 验证

benchmark SHALL 保持本地任务与 Docker 任务分流。本地 `asterwynd-*` 任务继续沿用现有 worktree + hidden test 验证路径；`task_family=swebench` 且 `execution_environment=docker` 的任务 SHALL 使用 SWE-bench Docker harness 做标准验证。

#### Scenario: 本地任务使用新任务名前缀

- **GIVEN** tasks 目录包含 `asterwynd-*` 本地任务
- **WHEN** BenchmarkRunner 读取任务
- **THEN** 系统 SHALL 按活动本地 benchmark 任务执行
- **AND** 活动任务目录和 task id SHALL 使用 `asterwynd-*` 前缀
