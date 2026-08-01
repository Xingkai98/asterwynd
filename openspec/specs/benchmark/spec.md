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
- **AND** 系统 SHALL NOT 接受旧 `--agent myagent` 作为兼容入口

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

#### Scenario: 本地任务使用新任务名前缀

- **GIVEN** tasks 目录包含 `asterwynd-*` 本地任务
- **WHEN** BenchmarkRunner 读取任务
- **THEN** 系统 SHALL 按活动本地 benchmark 任务执行
- **AND** 活动任务目录和 task id SHALL 使用 `asterwynd-*` 前缀

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

### Requirement: Benchmark runs SHALL fail closed for approval-required tools

Benchmark run 是无人值守运行，SHALL NOT 阻塞等待用户审批。当 benchmark task 触发被判定为 `require_approval` 的工具时，runtime SHALL fail closed，并记录 approval-unavailable 结果。

#### Scenario: benchmark 工具调用需要审批

- **GIVEN** 一个 benchmark run 正在执行
- **AND** 模型调用的工具被判定为 `require_approval`
- **WHEN** AgentLoop 请求审批
- **THEN** benchmark runtime SHALL 返回 approval unavailable
- **AND** 工具 SHALL NOT 执行
- **AND** benchmark result SHALL 记录被阻止的工具调用

### Requirement: 结果 artifact 记录重复运行与统计字段

benchmark result artifact SHALL 在保留既有字段的基础上，新增可选的重复运行、能力分层与统计字段；这些字段存在时 SHALL 携带 `benchmark-evaluation` 结果，缺失时 SHALL 保持既有向后兼容行为。

#### Scenario: 记录分层与统计字段

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 写入 result artifact
- **THEN** artifact SHALL 记录任务能力分层标签
- **AND** SHALL 记录重复运行轮次与分布统计（如均值/标准差/置信区间）
- **AND** 既有 `status`/`reason`/`run_id` 语义 SHALL NOT 改变

### Requirement: benchmark CLI 支持重复运行参数

benchmark CLI SHALL 支持传入重复运行次数（如 `--repeat N`），用于评测聚合；不传时 SHALL 默认单次运行以保持既有行为。

#### Scenario: 传入重复运行次数

- **GIVEN** 用户传入 `--repeat 3`
- **WHEN** benchmark 命令执行
- **THEN** 系统 SHALL 对任务集合执行 3 次重复运行
- **AND** 汇总到评测聚合层

#### Scenario: 未传入重复运行次数

- **GIVEN** 用户未传入 `--repeat`
- **WHEN** benchmark 命令执行
- **THEN** 系统 SHALL 按既有单次运行执行

### Requirement: 任务支持显式能力分层

benchmark task schema SHALL 支持显式能力分层字段，将任务归入可复用的能力层级。分层使用标签表达（如 `execution`、`tool-usage`、`context-planning`、`multi-step-solving`），供评测按层聚合统计。

#### Scenario: 任务声明能力层级

- **GIVEN** 某 benchmark 任务填写了能力分层标签
- **WHEN** runner 读取 task schema
- **THEN** 系统 SHALL 保留该分层标签用于按层汇总
- **AND** 结果页 SHALL 能按层展示通过率与统计指标

#### Scenario: 任务未声明能力层级

- **GIVEN** 某 benchmark 任务未填写能力分层字段
- **WHEN** 评测汇总结果
- **THEN** 系统 SHALL 将该任务归入默认层级
- **AND** 不得因缺少分层字段导致评测失败

### Requirement: 输出统计指标与置信区间

benchmark-evaluation SHALL 对重复运行结果计算均值、标准差，并给出置信区间；对通过类任务支持 `Pass@k` 稳定性指标。统计方法 SHALL 可复现（固定随机种子或记录统计参数）。

#### Scenario: 计算分布统计

- **GIVEN** 某任务已完成 N>=3 次重复运行
- **WHEN** 评测汇总统计
- **THEN** 结果 SHALL 包含均值与标准差
- **AND** SHALL 包含置信区间（如 95% CI）
- **AND** SHALL 包含任务通过率与 `Pass@k`

### Requirement: 判分统一走确定性 VerifierAdapter

benchmark SHALL 以确定性验证为判分主干：任务通过确定性 hidden test/脚本/状态比对判定（产出 diff 应用 hidden test、跑 test 命令等），不使用 LLM 主观 judge 打分。judge 判分（含 LLM judge 与人工回流校准）作为开放产出评测的可选后续项，不在当前判分主干中实现。

#### Scenario: 代码任务确定性判定

- **GIVEN** 某任务产出 diff 且提供 test 命令/hidden test
- **WHEN** 评测验证该任务
- **THEN** 系统 SHALL 用确定性验证（应用 hidden test、跑 test 命令）判定通过/失败
- **AND** 不使用 LLM 主观 judge 打分

#### Scenario: 无 hidden test 任务的确定性验证

- **GIVEN** 某任务无 test_patch 但仍可通过确定性命令验证（如 `grep`）
- **WHEN** 评测验证该任务
- **THEN** 系统 SHALL 使用该确定性命令判定，不引入 judge

### Requirement: 失败归因分类

benchmark-evaluation SHALL 按失败 `reason` 对重复运行结果分类统计，输出失败模式占比与样例回查入口，供性能退化定位（如 git bisect）使用。

#### Scenario: 失败模式占比

- **GIVEN** 某次评测包含多种失败原因
- **WHEN** 结果页渲染失败归因
- **THEN** 结果 SHALL 按 reason 展示失败模式占比
- **AND** 每个失败模式 SHALL 可回查到具体任务与运行轮次

### Requirement: 渲染可引用的量化结果页

benchmark-evaluation SHALL 把上述指标汇总渲染为一个可在面试中直接引用的结果页（markdown/HTML），覆盖 Pass@k、均值/标准差、置信区间、延迟分布和 token 成本。

#### Scenario: 生成结果页

- **GIVEN** 一次带重复运行和统计的评测完成
- **WHEN** 评测输出结果页
- **THEN** 结果页 SHALL 包含 Pass@k、均值/标准差、置信区间、延迟分布与 token 成本
- **AND** SHALL 按能力层级组织，便于按层引用
- **AND** SHALL 保留并展示任务所属评测框架（task_family），可按框架标注或过滤

### Requirement: 评测框架用 VerifierAdapter 抽象验证阶段

benchmark SHALL 用 adapter 模式抽象评测框架的验证/评分阶段，支持无缝接入不同评测框架。adapter 的 input 为任务定义 + agent 产出，output 为标准化 Verdict；选择逻辑 SHALL 以 `task_family` 为 key 查 registry，不得在共享 runner 中累积 if 分支。新增框架 SHALL 通过新增 adapter + 注册实现，不修改共享 runner/统计/结果页。

#### Scenario: 通过 registry 选择框架验证器

- **GIVEN** 某任务声明 `task_family=swebench`
- **WHEN** runner 对该任务做验证
- **THEN** 系统 SHALL 按 `task_family` 从 registry 选择对应 adapter 执行验证
- **AND** 输出标准化 Verdict（status/reason/detail/score?）

#### Scenario: 未知任务族回退

- **GIVEN** 某需要通过框架 adapter 验证的任务（如 docker 任务）声明了 registry 中不存在的 `task_family`
- **WHEN** runner 尝试验证该任务
- **THEN** 系统 SHALL 将任务标记为 `unsupported`
- **AND** 记录明确 reason（`task_family_unsupported`），不得伪造验证结果
- **AND** 本地任务（`execution_environment=local`）仍走确定性 `test_command` 判定，不受 adapter registry 影响

#### Scenario: adapter 契约可测试

- **GIVEN** 某 adapter 已注册
- **WHEN** 运行 adapter 契约测试
- **THEN** 每个 adapter SHALL 通过同一套契约断言（Verdict 的 status/reason/detail/score? 映射）
- **AND** 契约测试 SHALL 锁住接口，防止 adapter 漂移破坏下游

#### Scenario: 迁移既有 SWE-bench 验证

- **GIVEN** 既有 `_run_swebench_harness` 逻辑迁移为 `swebench` adapter（SWE-bench Verified 验证协议）
- **WHEN** 运行既有 SWE-bench 兼容测试
- **THEN** 迁移前后 status/reason 映射 SHALL 一致
