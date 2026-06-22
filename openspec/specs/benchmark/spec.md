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

benchmark CLI SHALL 在入口层解析统一配置，并将最终 mode、并发度、超时和工具策略传入 runner。BenchmarkRunner 和 MyAgentRunner SHALL NOT 在任务 worktree 中重新发现 `myagent.yaml`。

#### Scenario: benchmark 使用配置默认 mode

- **GIVEN** `myagent.yaml` 设置了 `agent.default_mode`
- **AND** 用户未显式传入 `--mode`
- **WHEN** benchmark 运行任务
- **THEN** run artifact、task result 和 trace SHALL 记录最终解析后的 mode

#### Scenario: benchmark 使用配置并发度

- **GIVEN** 配置设置了 `benchmark.parallel`
- **WHEN** BenchmarkRunner 执行多个任务
- **THEN** runner SHALL 使用该并发度限制任务执行

### Requirement: 支持多种 agent runner

benchmark SHALL 支持 fake、shell、myagent 和 claude runner。

#### Scenario: 选择 myagent runner

- **GIVEN** 用户传入 `--agent myagent`
- **WHEN** benchmark 命令构造 runner
- **THEN** 系统 SHALL 使用当前 LLM 和 max_iterations 创建 MyAgentRunner

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
