# subagents spec delta: grill 环节加固

## MODIFIED Requirements

### Requirement: 角色 Agent 类型注册

系统 SHALL 支持注册五种开发角色 agent 类型：Planner、Reviewer、Builder、CodeReviewer、Closer。每种角色 agent SHALL 作为子 session 运行，使用现有 subagent runtime。

#### Scenario: 注册 Planner agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `planner` 类型 SHALL 映射到 `planning` phase
- **AND** Planner agent SHALL 负责从 `exploring` 到 `ready_for_review` 的所有 `planning` sub_state

#### Scenario: 注册 Reviewer agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `reviewer` 类型 SHALL 映射到 `reviewing` phase
- **AND** Reviewer agent SHALL 负责从 `reading_docs` 到 `ready_for_review` 的所有 `reviewing` sub_state
- **AND** Reviewer agent SHALL 对已完成 grill 自审的设计文档做独立评审，而非执行 `grilling`

#### Scenario: 注册 Builder agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `builder` 类型 SHALL 映射到 `building` phase
- **AND** Builder agent SHALL 负责从 `writing_tests` 到 `ready_for_review` 的所有 `building` sub_state

#### Scenario: 注册 Closer agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `closer` 类型 SHALL 映射到 `closing` phase
- **AND** Closer agent SHALL 负责从 `syncing_specs` 到 `ready_for_review` 的所有 `closing` sub_state

#### Scenario: 注册 CodeReviewer agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `code-reviewer` 类型 SHALL 映射到 `code-review` phase
- **AND** CodeReviewer agent SHALL 负责从 `reading_diff` 到 `ready_for_review` 的所有 `code-review` sub_state
