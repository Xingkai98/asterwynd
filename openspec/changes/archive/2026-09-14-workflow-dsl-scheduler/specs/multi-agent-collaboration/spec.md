# multi-agent-collaboration spec delta: Workflow DSL 调度器

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Orchestration Pattern Library

The subagent system SHALL provide an orchestration pattern library: orchestrator-worker, peer-review, hierarchical, and bidding patterns, via a common OrcPattern interface. The four patterns SHALL be compiled to Workflow DSL templates and executed through the unified scheduler, while `run_pattern()` SHALL remain a compatible adapter.

#### Scenario: bidding pattern selects best proposal

- Given multiple subagents proposing solutions via the bidding pattern
- When the selector evaluates the proposals
- Then the best proposal is selected
- And the pattern is driven by the common OrcPattern interface, compiled to a WorkflowSpec template
