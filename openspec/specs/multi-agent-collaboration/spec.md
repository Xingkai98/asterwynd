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

The subagent system SHALL enforce concurrency and nesting-depth limits (max_concurrent_runs / max_depth) and SHALL reject spawns exceeding the limits.

#### Scenario: spawn rejected beyond depth limit

- Given a subagent spawn beyond the configured nesting depth
- When the guardrail detects the overrun
- Then the spawn is rejected with an error
- And no background task is started

### Requirement: Lightweight Message Bus

The subagent system SHALL provide a lightweight message bus for exchanging summaries between subagents, with bounded/droppable/summarized semantics and strict token budget to prevent context explosion.

#### Scenario: subagents exchange summaries

- Given multiple subagents collaborating
- When one subagent publishes a summary to the bus
- Then the summary is delivered to the other subagents
- And the bus enforces a strict token budget

### Requirement: Orchestration Pattern Library

The subagent system SHALL provide an orchestration pattern library: orchestrator-worker, peer-review, hierarchical, and bidding patterns, via a common OrcPattern interface.

#### Scenario: bidding pattern selects best proposal

- Given multiple subagents proposing solutions via the bidding pattern
- When the selector evaluates the proposals
- Then the best proposal is selected
- And the pattern is driven by the common OrcPattern interface

### Requirement: Orchestration Reuses Workflow Persistence Discipline

Subagent orchestration SHALL reuse the `agent/workflow/` persistence discipline (JSON serialization + schema_version + transition log style), SHALL NOT couple to the dev-workflow phase vocabulary, and SHALL NOT introduce a separate control plane.

#### Scenario: orchestration state persists without dev-workflow coupling

- Given an orchestration pattern run
- When pattern state is persisted
- Then it follows the workflow JSON/transition-log discipline
- And it does not depend on dev-workflow phases
