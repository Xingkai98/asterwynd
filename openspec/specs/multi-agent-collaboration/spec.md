# 多Agent协作 规格

## Purpose

定义 多Agent协作 能力域的规格。当前为基线状态；深化需求通过 OpenSpec change 的 spec delta 演进。
## Requirements
### Requirement: 多Agent协作 能力域基线

多Agent协作 能力域 SHALL 提供基础能力，深化需求通过 OpenSpec change 的 ADDED Requirements 合入演进。

#### Scenario: 能力域可扩展

- **GIVEN** 一个针对 多Agent协作 能力域的 OpenSpec change
- **WHEN** 该 change 的 spec delta 被接受
- **THEN** 能力域的 requirement 随 ADDED Requirements 演进

### Requirement: State Snapshot and Recovery

The subagent system SHALL serialize subagent execution state to a JSON snapshot on interruption, SHALL support resuming from the checkpoint, and SHALL reuse the main session schema_version/fingerprint/dedup patterns.

#### Scenario: subagent resumes from snapshot

- Given a subagent execution interrupted mid-run
- When a JSON snapshot is serialized
- Then the subagent resumes from the checkpoint
- And execution continues toward the objective, retrying any in-flight tool call

### Requirement: Per-Subagent Budget Enforcement

The subagent system SHALL enforce per-subagent token/time budget limits, SHALL hard-kill subagents exceeding limits, and SHALL generate failure/cost summaries.

#### Scenario: budget exceeded hard-kill

- Given a subagent whose token/time budget is exceeded
- When the budget enforcer detects the overrun
- Then the subagent is hard-killed
- And a failure/cost summary is generated

### Requirement: Concurrency and Depth Guardrails

The subagent system SHALL enforce concurrency and nesting-depth limits. Spawns exceeding the **nesting depth** limit SHALL be rejected; spawns exceeding the **instantaneous concurrency** limit SHALL be queued (bounded by a queue limit that returns an explicit `queue_full` signal), rather than rejected.

#### Scenario: spawn rejected beyond depth limit

- Given a subagent spawn beyond the configured nesting depth
- When the guardrail detects the overrun
- Then the spawn is rejected with an error
- And no background task is started

#### Scenario: spawn queued beyond concurrency limit

- Given a subagent spawn while the instantaneous concurrency limit is reached but the queue is not full
- When the guardrail detects the concurrency saturation
- Then the spawn enters the queue
- And the run is marked `queued` until an execution slot frees

### Requirement: Lightweight Message Bus

The subagent system SHALL provide a lightweight message bus for exchanging summaries between subagents, with bounded/droppable/summarized semantics and strict token budget to prevent context explosion.

#### Scenario: subagents exchange summaries

- Given multiple subagents collaborating
- When one subagent publishes a summary to the bus
- Then the summary is delivered to the other subagents
- And the bus enforces a strict token budget

### Requirement: Orchestration Pattern Library

The subagent system SHALL provide an orchestration pattern library: orchestrator-worker, peer-review, hierarchical, and bidding patterns, via a common OrcPattern interface. The four patterns SHALL be compiled to Workflow DSL templates and executed through the unified scheduler, while `run_pattern()` SHALL remain a compatible adapter.

#### Scenario: bidding pattern selects best proposal

- Given multiple subagents proposing solutions via the bidding pattern
- When the selector evaluates the proposals
- Then the best proposal is selected
- And the pattern is driven by the common OrcPattern interface, compiled to a WorkflowSpec template

### Requirement: Orchestration Reuses Workflow Persistence Discipline

Subagent orchestration SHALL reuse the `agent/workflow/` persistence discipline (JSON serialization + schema_version + transition log style), SHALL NOT couple to the dev-workflow phase vocabulary, and SHALL NOT introduce a separate control plane.

#### Scenario: orchestration state persists without dev-workflow coupling

- Given an orchestration pattern run
- When pattern state is persisted
- Then it follows the workflow JSON/transition-log discipline
- And it does not depend on dev-workflow phases

### Requirement: 声明式 Workflow DSL

系统 SHALL 提供声明式 Workflow DSL，使模型能一次性声明协作拓扑（并行 / 汇合 / 条件分支 / 有限循环），并可退回逐工具自由调度。DSL SHALL 采用分离式入口：`DeclareWorkflow` 声明并返回 workflow_id，`StartWorkflow` 启动，`GetWorkflow` 查询 bounded 状态，`CancelWorkflow` 取消；`RunWorkflow` 为便捷语法，内部走 Declare+Start。

#### Scenario: 声明并运行一个并行汇合拓扑

- **GIVEN** 模型需要「A/B/C 并行调研 → 汇合给 D」
- **WHEN** 调用 `DeclareWorkflow` 声明该拓扑并 `StartWorkflow` 启动
- **THEN** 系统 SHALL 调度 A/B/C 并行执行
- **AND** 在 A/B/C 全部完成后才运行 D

### Requirement: DSL 节点类型

系统 SHALL 支持 4 种节点：`subagent`（一个子 agent run）、`aggregate`（多上游汇聚）、`route`（按结构化结果选下一条边）、`foreach`（对有限集合展开并行）。动态并行 SHALL 用 `foreach` 表达。

#### Scenario: foreach 动态展开

- **GIVEN** 上游产出 N 个任务项
- **WHEN** `foreach` 节点消费该集合
- **THEN** 系统 SHALL 为每个任务项展开一个子任务（受 max 展开数约束）

### Requirement: DSL 汇合语义

系统 SHALL 支持 2 种汇合语义：`all_required`（全部 required 上游完成才汇合）与 `best_effort`（等截止时间，消费已完成结果，保留失败记录）。「失败不 fail-fast」SHALL 只在 aggregate 层实现。

#### Scenario: all_required 等齐

- **GIVEN** 一个 aggregate 节点的 join 语义为 all_required，且有 3 个 required 上游
- **WHEN** 任一上游失败
- **THEN** 系统 SHALL 保留失败记录并等待其余上游完成（不 fail-fast）
- **AND** aggregate 在所有 required 上游都终态后才运行

### Requirement: reducer 声明与图级递归上限

系统 SHALL 要求并行分支写同一结果槽时声明 reducer（无损合并），校验阶段对「多入边写同字段」无 reducer 时报 schema 错。系统 SHALL 施加图级 recursion_limit（默认 25），超限 SHALL 报错。

#### Scenario: 图级递归上限

- **GIVEN** 一个 workflow 的执行步数达到 recursion_limit
- **WHEN** 调度器尝试再前进一步
- **THEN** 系统 SHALL 报 GraphRecursionError
- **AND** SHALL NOT 无限循环

### Requirement: 内置编排模式降级为 DSL 模板

系统 SHALL 将 4 个内置编排模式（orchestrator-worker / peer-review / hierarchical / bidding）编译为 DSL 模板，`run_pattern()` 保留兼容 adapter，返回字段兼容并新增 workflow_id / workflow_spec_hash / critical_path_s / peak_active / total_cost（哈希字段命名为 `workflow_spec_hash`，避免与 OpenSpec artifact 的 `spec_hash` 同名不同义）。

#### Scenario: run_pattern 编译为 DSL 模板

- **GIVEN** 调用 `run_pattern(pattern="orchestrator-worker", ...)`
- **WHEN** 执行
- **THEN** 系统 SHALL 内部编译为 WorkflowSpec 并走统一调度器
- **AND** 返回字段 SHALL 保留既有 pattern 聚合字段并新增 workflow_id / workflow_spec_hash

### Requirement: result_ref 落盘 artifact

系统 SHALL 将 workflow 节点的完整结果/transcript 落盘到 workflow store，`result_ref` SHALL 指向文件路径；内存 SHALL 只持 bounded summary。`SubagentRunRecord` 的返回 SHALL 增 `summary_ref`/`transcript_ref`/`artifact_refs`。

#### Scenario: 完整结果落盘、内存只持摘要

- **GIVEN** 一个 workflow 节点完成并产出完整 transcript
- **WHEN** 该节点结果被记录
- **THEN** 系统 SHALL 将完整结果落盘
- **AND** 内存中 SHALL 只持 bounded summary + result_ref

### Requirement: 树状分层汇聚

系统 SHALL 支持树状汇聚：模型显式声明 aggregate 树（leaf→shard→domain→root）；调度器 SHALL 在「单 aggregate 直接上游 >10」或「总叶子数 >10」时自动插入分层 aggregate。每层输出 SHALL 遵守 token 预算（leaf 300 / shard 800 / domain 1500 / root 3000，可配置）。

#### Scenario: 上百个叶子不撑爆父上下文

- **GIVEN** 一个含 100 个叶子节点的 workflow
- **WHEN** 汇聚执行
- **THEN** 系统 SHALL 分层汇聚
- **AND** 父 agent 上下文 SHALL NOT 被 100 个完整结果注入

### Requirement: 父 agent 永远 bounded envelope

父 agent SHALL 只接收 bounded envelope（workflow_id/status/completed/failed/pending/root_result_ref），SHALL NOT 默认接收子级详细结果；子级结果 SHALL 通过显式 inspect（GetWorkflow detail 参数 / InspectSubagentTranscript）按需读取。

#### Scenario: 父 agent 收 bounded envelope

- **GIVEN** 一个 workflow 完成
- **WHEN** 父 agent 获取结果
- **THEN** 系统 SHALL 返回 bounded envelope
- **AND** SHALL NOT 默认展开子级详细结果

### Requirement: bus 降级为非权威

MessageBus SHALL 只承担低延迟广播/非关键提示；权威状态、依赖完成、结果完整性、重试、重放 SHALL 进 workflow store/事件日志。bus 丢消息 SHALL NOT 影响 workflow 完成与结果正确性。

#### Scenario: bus 丢消息不影响结果

- **GIVEN** 协作中的子 agent 通过 bus 广播一条非关键提示
- **WHEN** 该消息因队列满被丢弃
- **THEN** workflow SHALL 仍正常完成
- **AND** 结果正确性 SHALL NOT 受影响

### Requirement: workflow 级四维度总预算

系统 SHALL 对一个 workflow run 施加四维度总预算：`max_total_tokens` / `max_total_cost_usd` / `max_total_runs` / `max_wall_time_s`。四维度**默认均为 `0`（不限）**——只有显式配置（`subagents.workflow.budget.*`）才设上限，`0` SHALL 表示「该维度不限」，但 `max_total_runs=0` SHALL NOT 解除 C2 的 `max_runs` 结构闸。配置 `subagents` / `subagents.workflow` / `subagents.workflow.budget` 中任一段落**键存在但值为 `null`** 时，系统 SHALL 报配置错误（`ConfigError`），SHALL NOT 静默视为「未配置 = 不限」。任一维度超限时系统 SHALL 停止派发新节点、取消排队中未执行的 run、drain 已启动的 run、并将根节点标记为 `budget_exceeded`。

#### Scenario: 未配置预算时不设上限

- **GIVEN** 一份未配置 `subagents.workflow.budget` 的配置
- **WHEN** 一个 workflow run 的累计 token / cost / 挂钟时间超过旧默认值（200k tokens / 5.0 USD / 1800 s）
- **THEN** 系统 SHALL NOT 因预算中止派发
- **AND** workflow SHALL 正常跑完，envelope 的 `budget.exceeded` SHALL 为 `false`
- **AND** run 数维度 SHALL NOT 被本 Requirement 中止（仍受 C2 `max_runs` 结构闸约束，见下方 Scenario）

#### Scenario: token 预算超限停止派发

- **GIVEN** 一个 workflow run 的累计 token 达到显式配置的 `max_total_tokens`
- **WHEN** 调度器尝试派发下一个节点
- **THEN** 系统 SHALL 停止派发新节点
- **AND** 已启动的 run SHALL drain 到终态
- **AND** 根节点 SHALL 标记 `budget_exceeded`

#### Scenario: runs 预算派发前预扣拒绝

- **GIVEN** 一个 workflow 的累计 run 数达到显式配置的 `max_total_runs`
- **WHEN** 调度器预扣下一个 run 的预算
- **THEN** 系统 SHALL 拒绝派发
- **AND** envelope SHALL 报 `budget.exceeded = true`

#### Scenario: 超限出口不逃出 run

- **GIVEN** 任一维度预算超限触发 stop_new
- **WHEN** 调度器收敛
- **THEN** 系统 SHALL 返回 envelope（`status="budget_exceeded"`）
- **AND** SHALL NOT 向父 agent 抛未捕获异常

#### Scenario: 段落级 null 判为配置错误

- **GIVEN** 一份配置在 `subagents.workflow.budget`（或 `subagents.workflow` / `subagents`）处**写了键但值为 `null`**
- **WHEN** 加载配置
- **THEN** 系统 SHALL 抛 `ConfigError`
- **AND** SHALL NOT 静默把该段视为「未配置」（否则会静默把四维预算全部置为不限）

#### Scenario: 预算不限不解除 C2 结构闸

- **GIVEN** 四维度预算均未配置（默认不限）
- **WHEN** 一个 workflow 的累计 run 数达到 C2 的 `max_runs`
- **THEN** 系统 SHALL 仍按 C2 结构闸拒绝派发（reason `max_runs`）
- **AND** SHALL NOT 因预算为「不限」而放行超限的 run 数

### Requirement: 成本归因四维账单

`CostLedger` SHALL 增四维成本归因：by_workflow / by_node / by_depth / by_edge。每个 LLM 调用 SHALL 携带其 workflow_id / node_id / depth / edge 归因键，使系统能回答「哪个节点最贵、哪层重复 token 最多、动态 vs 固定 pattern 差多少」。不带归因键的记录 SHALL 保持既有 by_session/by_phase/by_tool 三维账单不变。`by_depth` 的分层口径 SHALL 为 workflow 图距（0=leaf / 1=shard / 2=domain / 3+=root），与 `spawn_depth` 无关。归因分桶值 SHALL round 到 9 位小数、tokens 口径为 input+output（不含 cache）、cost 单位为 USD、未知模型 SHALL 标 `estimated: true`。

#### Scenario: 找出最贵节点

- **GIVEN** 一个含 N 个节点的 workflow run 完成后
- **WHEN** 查询 `CostLedger.bill()` 的 `by_node` 分桶
- **THEN** 系统 SHALL 返回每个节点的 token/cost 聚合
- **AND** SHALL 能定位最贵的节点

#### Scenario: 按图距归因层级成本

- **GIVEN** 一个 leaf→shard→domain→root 的分层汇聚 workflow 完成后
- **WHEN** 查询 `bill()` 的 `by_depth` 分桶
- **THEN** 系统 SHALL 按图距分桶（0/1/2/3+）
- **AND** SHALL 能定位重复 token 最多的层

### Requirement: 动态 route 条件源

route 节点的 `when` SHALL 支持 `$ref:<node_id>:<slot>` 引用上游结果槽；运行时解析 SHALL 只读已声明/已落盘的 `NodeState.slots`，SHALL NOT 执行模型生成代码。`$ref` 解析出的槽值 SHALL 取首个非空行作为期望标签，SHALL 传入 `matches_route` 做行首匹配。`$ref` 引用的 slot 无键命中 SHALL 视为不匹配，SHALL 保留 `default` 兜底。

#### Scenario: $ref 引用命中分支

- **GIVEN** 一个 route 节点的 `when` 为 `$ref:reviewer:verdict` 且上游 reviewer 的 verdict 槽为 "APPROVED"
- **WHEN** route 执行
- **THEN** 系统 SHALL 命中该 case 的目标边
- **AND** SHALL NOT 匹配字面文本标签

#### Scenario: $ref 槽缺失走 default

- **GIVEN** 一个 route 节点的 `when` 为 `$ref:planner:items` 但上游无 `items` 槽
- **WHEN** route 执行
- **THEN** 系统 SHALL 视为不匹配
- **AND** SHALL 保留 `default` 兜底（不报错，diagnostics 记录未命中原因）

### Requirement: 动态 foreach 跨层 source

foreach 节点的 `source` SHALL 支持跨层递归解析（沿数据边向上解析上游产出，优先读 source 节点自身 `result` 槽、无唯一数据上游则报 schema 歧义）；环回边（source 指向 route 参与环内）SHALL 在校验期拒绝。`source_field` SHALL 只应用一次。`max_items=0` SHALL 表示「不静态截断、展开到图级 run 预算耗尽为止」。

#### Scenario: 跨层 source 递归解析

- **GIVEN** 一个 foreach 节点的 `source` 指向一个「自身还有数据上游」的 aggregate 节点
- **WHEN** foreach 执行
- **THEN** 系统 SHALL 先递归解析该 aggregate 的上游产出
- **AND** 再取 `source_field` 展开集合

#### Scenario: max_items=0 按剩余预算截断

- **GIVEN** 一个 foreach 节点 `max_items=0` 且图级 run 预算未耗尽
- **WHEN** foreach 执行
- **THEN** 系统 SHALL 展开全部集合项（不做静态截断）
- **AND** SHALL 在剩余 run/节点预算耗尽时按剩余容量截断停止派发

