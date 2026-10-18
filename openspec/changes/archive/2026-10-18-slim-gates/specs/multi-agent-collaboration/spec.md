# multi-agent-collaboration 规格 delta

## MODIFIED Requirements

### Requirement: Orchestration Reuses Workflow Persistence Discipline

Subagent orchestration SHALL reuse the persistence discipline of `agent/subagent/workflow_store.py` (atomic per-key artifact writes + authoritative `events.jsonl` transition log) and the schema-version discipline of `agent/subagent/workflow.py` (`SCHEMA_VERSION`), SHALL NOT couple to the dev-workflow phase vocabulary, and SHALL NOT introduce a separate control plane. 本 Requirement 的主语是 **Subagent orchestration**：它 SHALL NOT 覆盖非 subagent 的交互式编排（例如群聊轮次编排器——后者不复用 `SubAgentManager`，不属本 Requirement 的约束范畴）。已删除的 `agent/workflow/` 模块 SHALL NOT 再被本 Requirement 引用为持久化纪律来源。

#### Scenario: orchestration state persists without dev-workflow coupling

- Given an orchestration pattern run
- When pattern state is persisted
- Then it follows the workflow JSON/transition-log discipline
- And it does not depend on dev-workflow phases

#### Scenario: 非 subagent 编排不受本 Requirement 约束

- **GIVEN** 一个不基于 `SubAgentManager` 的交互式编排（群聊轮次编排器）
- **WHEN** 它维护自己的房间日志与轮次状态
- **THEN** 该行为 SHALL NOT 被判定为「引入独立控制面」的违规
