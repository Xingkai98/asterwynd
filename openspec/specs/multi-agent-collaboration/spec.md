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

