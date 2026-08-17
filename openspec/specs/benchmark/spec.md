# benchmark 规格

## Purpose

定义本地 Coding Agent benchmark 的任务 schema、runner、artifact、hidden tests、trace 和结果汇总。当前实现位于 `benchmarks/`。

> 渲染边界：结果页渲染义务（`$/resolved-task`/cache hit rate/定价表版本展示、reason × fault_owner 交叉表、报告元组、SWE-bench 污染注记、部分成功档、采样参数、小样本声明、过程效率展示）归 C3 `evaluation-protocol-reporting`，本规格的 benchmark-evaluation 指标 Requirement 在 C2 仅实现数据/统计/CLI 层。
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

benchmark result artifact SHALL 在保留既有字段的基础上，新增可选的重复运行、场景/难度标签与统计字段；这些字段存在时 SHALL 携带 `benchmark-evaluation` 结果，缺失时 SHALL 保持既有向后兼容行为。

#### Scenario: 记录场景与统计字段

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 写入 result artifact
- **THEN** artifact SHALL 记录任务场景与难度标签
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

benchmark task schema SHALL 支持 `scenario` 与 `difficulty` 显式标签：`scenario` 使用代码改动类型 5 枚举（`bug-fix`/`feature-dev`/`refactor`/`debug`/`integration`），`difficulty` 使用 3 档枚举（`easy`/`medium`/`hard`），供评测按场景、难度聚合统计。能力层 SHALL NOT 要求任务级正交标签，改用套件级能力覆盖矩阵表达：任务集 manifest SHALL 声明覆盖的能力域（如 `tool-usage`/`context-planning`/`multi-step-solving`/`error-recovery`/`safety-boundary`/`long-term-memory`/`long-context`），结果页按套件展示能力覆盖度。

#### Scenario: 任务声明场景与难度

- **GIVEN** 某 benchmark 任务填写了 `scenario` 与 `difficulty` 标签
- **WHEN** runner 读取 task schema
- **THEN** 系统 SHALL 保留该双标签用于按场景/难度汇总
- **AND** 结果页 SHALL 能按场景与难度展示通过率与统计指标

#### Scenario: 任务未声明场景或难度

- **GIVEN** 某 benchmark 任务未填写 `scenario` 或 `difficulty`
- **WHEN** 评测汇总结果
- **THEN** 系统 SHALL 将缺失维度归入默认值
- **AND** 不得因缺少标签导致评测失败

#### Scenario: 任务集 manifest 声明能力覆盖矩阵

- **GIVEN** 某任务集 manifest 声明了能力域覆盖矩阵
- **WHEN** 评测渲染结果页
- **THEN** 结果页 SHALL 按能力域展示任务覆盖度与聚合指标
- **AND** 每个已声明能力域 SHALL 至少覆盖一个任务

### Requirement: 输出统计指标与置信区间

benchmark-evaluation SHALL 对重复运行结果计算均值、标准差，并给出置信区间；对通过类任务支持 `pass^k` 稳定性指标，并区分 `pass@1`（有效轮次经验通过率，用户实际获得的质量）、`pass@k`（k 次任一成功，能力上限）、`pass^k`（全部 k 轮成功，可靠性）。统计方法 SHALL 可复现（固定随机种子或记录统计参数）；统计语义 SHALL 声明 n 与 k 关系（n=k 时仅 pass@1 与 pass^k 有统计意义，中间档 1<k<n 高方差不推荐展示）。

#### Scenario: 计算分布统计

- **GIVEN** 某任务已完成 N>=3 次重复运行
- **WHEN** 评测汇总统计
- **THEN** 结果 SHALL 包含均值与标准差
- **AND** SHALL 包含置信区间（如 95% CI）
- **AND** SHALL 包含任务通过率与 `pass^k` 稳定性指标

#### Scenario: 声明统计有效性条件

- **GIVEN** 某任务的重复运行次数 N 与 pass@k 的 k
- **WHEN** 结果页展示统计指标
- **THEN** 系统 SHALL 声明 n 与 k 的有效性条件
- **AND** 无效轮次（`unsupported`/`approval-unavailable`/`docker_unavailable`）SHALL NOT 计入 pass@1 与 pass^k 的分母

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
### Requirement: 任务集由三来源组成

benchmark 任务集 SHALL 由三来源组成：A 轨历史重建任务（存量回归基线）、B 轨当前演进任务（当前 HEAD 真实缺陷/增强，面试核心）、外部开源测试集精选子集（如 SWE-bench Verified）。任务集 manifest SHALL 为每个任务标注 `track`（`A`/`B`/`verified`）。

#### Scenario: 任务集声明三来源

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 汇总任务集组成
- **THEN** 任务集 SHALL 按 track 分组展示数量与占比
- **AND** 每个 track SHALL 至少包含一个任务
### Requirement: 外部测试集精选子集接入

benchmark SHALL 支持接入外部开源测试集精选子集（如 SWE-bench Verified 50 条）：从轻量/中等难度实例池逐条过滤已知坏实例（KNOWN_BAD）与重实例（如 django/sphinx），验证路径按资源可用性分级（L1 本地轻量验证、L2 Docker harness 验证、L3 金补丁自检剔除 flaky/坏实例），结果页携带子集污染与偏置披露。

#### Scenario: 精选子集元数据校验

- **GIVEN** 某 external 子集 fixture 已生成
- **WHEN** runner 读取任务
- **THEN** fixture SHALL 提供完整实例元数据（instance_id/dataset_name/dataset_split）
- **AND** SHALL 不包含 KNOWN_BAD 或重实例

#### Scenario: 验证路径分级

- **GIVEN** 某 external 子集任务可本地轻量验证（L1）
- **WHEN** runner 尝试验证
- **THEN** 系统 SHALL 优先走本地 test_command 验证
- **AND** Docker 不可用或内存不足时 L2 路径 SHALL 标记为 `unsupported` 而非伪造结果
- **AND** 子集接入时 SHALL 提供 L3 金补丁自检能力以剔除 flaky/坏实例
### Requirement: 反作弊泄漏披露

benchmark SHALL 对存在反作弊泄漏面的任务集（如 A 轨历史重建任务在完整 git 历史中运行、agent 可见后续提交）在结果页/任务集 manifest 披露泄漏事实，并声明任务集定位（如"回归基线、非公平评测"），不得冒充公平评测。

#### Scenario: A 轨任务披露泄漏

- **GIVEN** 某任务集包含 A 轨历史重建任务
- **WHEN** 评测产出结果页
- **THEN** 结果页 SHALL 披露该任务集的反作弊泄漏面（任务集来源、运行环境、训练 cutoff 未知性）
- **AND** SHALL 声明该 track 定位为回归基线而非公平评测
### Requirement: 评测采样显式化

benchmark-evaluation SHALL 支持显式采样：重复运行次数 `--repeat N` 取 3–5（N>=3 才有 pass^k 意义）；每次运行记录采样参数（`seed`、`temperature`、模型版本）；`seed` 使用固定集合（如 seed 0..N-1）保证可复现；`temperature` 默认 0.2（pass@1 口径）。CLI SHALL 提供 `--seeds`（显式 seed 集合，缺省推导为 0..N-1）、`--temperature`（缺省 0.2）与 `--model-version` 参数；每轮 run artifact SHALL 记录 (temperature, seed, model version)。可复现声明 SHALL 限定在（模型版本、provider、harness）内，部分 provider 不承诺 seed 语义。

#### Scenario: 采样参数记录

- **GIVEN** 一次带重复运行的评测
- **WHEN** 写入 run artifact
- **THEN** 每轮 SHALL 记录 (temperature, seed, model version)
- **AND** 结果页 SHALL 展示采样参数

#### Scenario: 显式 seed 集合

- **GIVEN** 用户传入 `--seeds 0 1 2` 与 `--repeat 3`
- **WHEN** benchmark 命令执行
- **THEN** 三轮 run SHALL 分别使用 seed 0/1/2
- **AND** 每轮 artifact SHALL 记录对应 seed
### Requirement: 成本与延迟联合展示

benchmark-evaluation SHALL 在结果页并列展示 Pass@1 与成本指标 `$/resolved-task`，并报告 token 缓存命中率（cache hit rate）。成本 SHALL 采用 cache-aware 定价（区分 fresh input / cache read / cache write / output 四档），声明定价表版本与日期，并显式定义 `$/resolved-task` 口径（层内全部 run 总成本含失败 run / resolved 数；仅 LLM token 计费，不含沙箱/CI/计算）。成本核算 SHALL 使用 cache-aware 计费函数与四档定价表，未知模型 SHALL 回退为估算并警告（不得静默返回 0），self-hosted 模型 SHALL 标注不计费或估算口径。

#### Scenario: 成本指标展示

- **GIVEN** 一次带统计的评测完成
- **WHEN** 结果页渲染成本
- **THEN** 结果 SHALL 包含 Pass@1 与 `$/resolved-task` 并列
- **AND** SHALL 包含 cache hit rate（按模型、能力层拆分）
- **AND** SHALL 声明定价表版本/日期与成本口径

#### Scenario: 未知模型成本回退

- **GIVEN** 某 run 使用的模型不在定价表
- **WHEN** 核算该 run 成本
- **THEN** 系统 SHALL 输出估算成本并标注未知模型警告
- **AND** SHALL NOT 静默输出零成本
### Requirement: 失败归因与 fault_owner

benchmark-evaluation SHALL 保留失败 `reason` 分类，并新增正交的 `fault_owner` 维度（`agent`/`task`/`environment`/`unknown`）。fault_owner 标注来源 SHALL 声明（主选人审抽样 + 双人标注 κ 报告，可选强 judge 首标 + 人审抽样校准）；未标注的失败 SHALL 归入 `unknown` 聚合。统计层 SHALL 提供 reason × fault_owner 交叉表聚合；fault_owner 绑定 (task, round) 标注，不做 reason→owner 查表推导。

#### Scenario: 失败归因交叉表

- **GIVEN** 一次带失败归因的评测
- **WHEN** 结果页渲染失败
- **THEN** 结果 SHALL 按 reason 展示失败模式占比
- **AND** SHALL 展示 reason × fault_owner 交叉表
- **AND** 每个失败 SHALL 可回查到具体任务与运行轮次
- **AND** 未标注 fault_owner 的失败 SHALL 归入 `unknown` 并单独展示
### Requirement: 报告元组结构化披露

benchmark 报告 SHALL 以结构化元组披露运行环境：模型（`model`: name/version/provider/seed 支持）、harness（`harness`: adapter/prompt_version/tools/max_turns/timeout/patch_collection/network on-off）、`task_set_hash`（任务集版本钉住）、grader 版本、成本口径（定价表版本/日期 + cache hit rate）。run artifact SHALL 记录对应字段（task_set_hash、adapter/grader 版本、max_iterations、timeout、network、温度/seed、cache tokens）；缺失字段 SHALL 保持向后兼容（可空）。

#### Scenario: 报告元组完整

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 写入报告/run artifact
- **THEN** 报告 SHALL 包含 model/harness/task_set_hash/grader/成本口径元组
- **AND** 缺失字段 SHALL 保持向后兼容（可空）
### Requirement: SWE-bench 污染披露

引用 SWE-bench 数字时，benchmark 报告 SHALL 携带污染与缺陷披露：OpenAI 2026-02 已弃用 SWE-bench Verified（审计 138 个高失败率实例中 59.4% 有实质缺陷），数字只能作为对照参考、不得作为无保留金标准；披露 SHALL 覆盖子集层面风险（KNOWN_BAD 过滤条数、现有 fixture 偏置、数据集版本与 swebench 包版本钉住）。run metadata SHALL 记录 swebench 数据集版本与 swebench 包版本，供披露引用。

#### Scenario: 结果页污染注记

- **GIVEN** 结果页引用 SWE-bench 数字
- **WHEN** 渲染结果页
- **THEN** 结果页 SHALL 带保留条件域的污染注记
- **AND** SHALL 注明子集过滤与版本钉住信息
### Requirement: 配对比较统计

compare 路径 SHALL 支持配对比较统计：per-task delta + 差异置信区间（paired bootstrap / McNemar）+ win-rate，用于"同任务同 harness 换 agent/模型"的对照展示，不得只给两个点估计。统计方法 SHALL 可复现（固定随机种子）。

#### Scenario: 换 agent 对照

- **GIVEN** 两组 run 在同一任务集、同一 harness 下使用不同 agent/模型
- **WHEN** compare 渲染对照
- **THEN** 结果 SHALL 包含 per-task delta、差异 CI 与 win-rate
- **AND** SHALL 按任务展示逐项差异

#### Scenario: 配对统计可复现

- **GIVEN** 同一对 run 重复执行 paired comparison
- **WHEN** 计算差异 CI 与 win-rate
- **THEN** 结果 SHALL 可复现（固定 seed）
### Requirement: SWE-bench 部分成功保留

SWE-bench adapter SHALL 保留 report.json 的部分成功字段（`f2p_rate`/`p2p_rate`/`reward`），失败归因与结果页建立在更细粒度信息上，不得只保留整体 resolved 布尔值。

#### Scenario: 部分成功字段透传

- **GIVEN** SWE-bench harness 返回 report.json
- **WHEN** adapter 标准化 Verdict
- **THEN** Verdict SHALL 保留 f2p_rate/p2p_rate/reward 字段
- **AND** 结果页 SHALL 展示部分成功档
### Requirement: 小样本统计声明

小样本（N=3–5）下 per-task bootstrap CI 统计意义弱，结果页渲染层 SHALL 添加小样本声明，或仅在 layer/aggregate 层级展示 CI 权重。统计层 SHALL 输出样本量 N 供渲染层判断。

#### Scenario: 小 N 声明

- **GIVEN** 某任务重复运行次数 N 为 3–5
- **WHEN** 结果页渲染 per-task CI
- **THEN** 结果页 SHALL 附带小样本统计声明
### Requirement: 过程效率指标

benchmark-evaluation SHALL 从 trace 记录采集过程效率指标：time-to-first-successful-edit（首次成功编辑耗时）与 exploration fraction（探索占比），作为结果页可选项展示。

#### Scenario: 过程效率采集

- **GIVEN** 某任务 trace.json 记录了步骤事件
- **WHEN** 结果页渲染过程指标
- **THEN** 结果 SHALL 可展示 time-to-first-successful-edit 与 exploration fraction
