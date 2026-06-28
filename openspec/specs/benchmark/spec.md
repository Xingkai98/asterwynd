# benchmark 规格

## Purpose

定义本地 Coding Agent benchmark 的任务 schema、runner、artifact、hidden tests、trace 和结果汇总。当前实现位于 `benchmarks/`。
## Requirements
### Requirement: benchmark 使用任务目录运行

BenchmarkRunner SHALL 从 tasks 目录读取任务定义，并逐个执行。

#### Scenario: 运行全部任务

- **GIVEN** tasks_dir 包含多个任务子目录
- **WHEN** CLI 调用 benchmark 命令
- **THEN** BenchmarkRunner SHALL 执行所有可识别任务
- **AND** 在 runs_dir 下创建一次 run 输出

### Requirement: benchmark 复用入口层配置

benchmark CLI SHALL 在入口层解析统一配置，并将最终 mode、并发度、超时和工具策略传入 runner。BenchmarkRunner 和 AsterwyndRunner SHALL NOT 在任务 worktree 中重新发现 `asterwynd.yaml`。

#### Scenario: benchmark 使用配置默认 mode

- **GIVEN** `asterwynd.yaml` 设置了 `agent.default_mode`
- **AND** 用户未显式传入 `--mode`
- **WHEN** benchmark 运行任务
- **THEN** run artifact、task result 和 trace SHALL 记录最终解析后的 mode

#### Scenario: benchmark 使用配置并发度

- **GIVEN** 配置设置了 `benchmark.parallel`
- **WHEN** BenchmarkRunner 执行多个任务
- **THEN** runner SHALL 使用该并发度限制任务执行

### Requirement: 支持多种 agent runner

benchmark SHALL 支持 fake、shell、asterwynd 和 claude runner。

#### Scenario: 选择 asterwynd runner

- **GIVEN** 用户传入 `--agent asterwynd`
- **WHEN** benchmark 命令构造 runner
- **THEN** 系统 SHALL 使用当前 LLM 和 max_iterations 创建 AsterwyndRunner

### Requirement: 每个任务保存核心 artifact

BenchmarkRunner SHALL 为每个任务保存 result、trace 和 runner log。final diff SHALL 在 agent 运行并完成 diff capture 后保存；test output SHALL 在验证命令实际运行后保存。

#### Scenario: 任务执行完成

- **GIVEN** 某任务运行结束
- **WHEN** runner 汇总结果
- **THEN** 任务目录 SHALL 包含 result.json、trace.json 和 runner.log

#### Scenario: setup 阶段失败

- **GIVEN** 任务在创建 workspace、clone 或安装依赖阶段失败
- **WHEN** runner 进入 finally 写入 artifact
- **THEN** 系统 SHALL 写入 result.json、trace.json 和 runner.log
- **AND** final.diff 或 test_output.txt MAY 不存在

### Requirement: hidden test patch 用于验证

benchmark SHALL 在 agent 运行后保存 agent diff；当任务提供 test patch 时，系统 SHALL 应用该 patch，再执行验证命令。

#### Scenario: hidden tests 失败

- **GIVEN** agent 修改未通过隐藏测试
- **WHEN** 验证命令返回非零
- **THEN** 结果 SHALL 标记为 failed 或 error
- **AND** 保留测试输出

### Requirement: passed_with_warnings 不等于 clean pass

benchmark SHALL 区分 clean pass 和带警告通过。

#### Scenario: 测试通过但过程不干净

- **GIVEN** 验证命令通过但 runner 发现警告
- **WHEN** 写入 result
- **THEN** 状态 SHALL 使用 `passed_with_warnings`
- **AND** 不得统计为 clean pass

### Requirement: benchmark artifact 记录 planning state 和 Plan Document

Benchmark trace SHALL 记录 planning state 和 Plan Document 事件，便于分析 agent 未完成任务时卡在哪个步骤以及计划阶段的方案。Benchmark result artifact SHOULD 包含最终 planning summary；如果运行中没有 planning state 或 Plan Document，artifact SHALL 保持向后兼容。

#### Scenario: benchmark 任务包含 planning 事件

- **GIVEN** AsterwyndRunner 运行任务时产生 planning state
- **WHEN** 写入 trace artifact
- **THEN** trace SHALL 包含 planning state 事件序列

#### Scenario: benchmark 任务包含 Plan Document 事件

- **GIVEN** AsterwyndRunner 运行任务时产生 Plan Document
- **WHEN** 写入 trace artifact
- **THEN** trace SHALL 包含 Plan Document 事件

#### Scenario: benchmark 任务完成后保存 planning 摘要

- **GIVEN** AsterwyndRunner 运行任务时产生 planning state
- **WHEN** 写入 result artifact
- **THEN** result SHALL 包含最终 planning summary

### Requirement: benchmark artifact 记录 Agent 运行标识

Benchmark artifact SHALL 记录 `agent_run_id`，便于从 benchmark result 反查 trace 和日志，同时 SHALL 保持 benchmark 批次 `run_id` 的既有含义。

#### Scenario: benchmark 任务完成

- **GIVEN** benchmark runner 完成一个任务
- **WHEN** 写入 result 和 trace artifact
- **THEN** task result artifact SHALL 包含 `agent_run_id`
- **AND** trace artifact SHALL 包含 Agent 运行的 `run_id`
- **AND** benchmark run metadata SHALL 继续使用既有 `run_id` 表示 benchmark 批次

### Requirement: benchmark 任务显式声明执行环境与任务族

benchmark task schema SHALL 支持显式字段 `task_family` 与 `execution_environment`。首版允许 `execution_environment` 为 `local` 或 `docker`；未显式填写时，系统 SHALL 默认使用 `task_family=local` 与 `execution_environment=local`。

#### Scenario: 本地任务使用默认执行环境

- **GIVEN** 某 benchmark 任务未填写 `task_family` 与 `execution_environment`
- **WHEN** runner 读取 task schema
- **THEN** 系统 SHALL 将该任务视为本地任务
- **AND** SHALL 使用当前本仓库 worktree 执行路径

#### Scenario: SWE-bench Docker 任务声明实例元数据

- **GIVEN** 某 benchmark 任务填写 `task_family=swebench`
- **WHEN** runner 读取 task schema
- **THEN** 该任务 SHALL 显式提供 `instance_id`
- **AND** SHALL 显式提供 `dataset_name`
- **AND** SHALL 显式提供 `dataset_split`
- **AND** SHALL 使用 `execution_environment=docker`

### Requirement: benchmark 支持 Docker-based SWE-bench harness 验证

benchmark SHALL 保持本地任务与 Docker 任务分流。本地 `asterwynd-*` 任务继续沿用现有 worktree + hidden test 验证路径；`task_family=swebench` 且 `execution_environment=docker` 的任务 SHALL 使用 SWE-bench Docker harness 做标准验证。

#### Scenario: Docker 可用时运行 SWE-bench 任务

- **GIVEN** 某 benchmark 任务的 `task_family` 为 `swebench`
- **AND** `execution_environment` 为 `docker`
- **AND** 当前环境能连接 Docker daemon
- **WHEN** runner 执行该任务
- **THEN** 系统 SHALL 跳过本地 venv 依赖安装路径
- **AND** SHALL 复用 agent 产出的 git patch 作为 harness 输入
- **AND** SHALL 以 harness 验证结果决定最终 `status`

### Requirement: Docker preflight 失败时显式标记 unsupported

当 Docker-based 任务的 Docker preflight 失败时，benchmark SHALL 将该任务标记为 `unsupported`，并在 artifact 中记录明确原因。该结果 SHALL NOT 被计入 agent 失败。

#### Scenario: Docker daemon 不可用

- **GIVEN** 某 benchmark 任务的 `execution_environment` 为 `docker`
- **AND** 当前环境无法连接 Docker daemon
- **WHEN** runner 尝试执行该任务
- **THEN** 系统 SHALL 写入 `result.json`、`trace.json` 和 `runner.log`
- **AND** 结果状态 SHALL 为 `unsupported`
- **AND** `reason` SHALL 为 `docker_unavailable`
- **AND** 系统 SHALL NOT 写入伪造的 `final.diff` 或 `test_output.txt`

### Requirement: benchmark 结果使用 status + reason

benchmark 结果模型 SHALL 使用顶层 `status` 表示状态类别，并使用统一 `reason` 字段表达细节原因。`RunMetadata`、summary、compare 和 analyze 路径 SHALL 以 `status` 做统计分类，以 `reason` 展示细节归因。

#### Scenario: run-level 统计包含 unsupported

- **GIVEN** 某次 benchmark run 同时包含通过任务和 Docker unsupported 任务
- **WHEN** runner 写入 `run.json`
- **THEN** run metadata SHALL 单独统计 `unsupported`
- **AND** SHALL NOT 将该数量并入 `failed`
