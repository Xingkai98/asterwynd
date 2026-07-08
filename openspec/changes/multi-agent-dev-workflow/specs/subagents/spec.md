# subagents 规格 delta

## ADDED Requirements

### Requirement: 角色 Agent 类型注册

系统 SHALL 支持注册四种开发角色 agent 类型：Planner、Reviewer、Builder、Closer。每种角色 agent SHALL 作为子 session 运行，使用现有 subagent runtime。

#### Scenario: 注册 Planner agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `planner` 类型 SHALL 映射到 `planning` phase
- **AND** Planner agent SHALL 负责从 `exploring` 到 `ready_for_review` 的所有 `planning` sub_state

#### Scenario: 注册 Reviewer agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `reviewer` 类型 SHALL 映射到 `reviewing` phase
- **AND** Reviewer agent SHALL 负责从 `reading_docs` 到 `ready_for_review` 的所有 `reviewing` sub_state

#### Scenario: 注册 Builder agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `builder` 类型 SHALL 映射到 `building` phase
- **AND** Builder agent SHALL 负责从 `writing_tests` 到 `ready_for_review` 的所有 `building` sub_state

#### Scenario: 注册 Closer agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `closer` 类型 SHALL 映射到 `closing` phase
- **AND** Closer agent SHALL 负责从 `syncing_specs` 到 `ready_for_review` 的所有 `closing` sub_state

### Requirement: 角色 Agent 路由

系统 SHALL 根据 `handoff.json` 的当前 state 自动选择对应的角色 agent 类型。

#### Scenario: 根据 phase 路由 agent

- **GIVEN** 一个 change 的 `handoff.json` 中 `state.phase` 为 `planning`
- **WHEN** 启动角色 agent
- **THEN** 系统 SHALL 创建类型为 `planner` 的子 session

#### Scenario: human review gate 后路由

- **GIVEN** change 处于 `planning.ready_for_review`
- **WHEN** 人确认通过
- **THEN** 系统 SHALL 更新 state 到 `reviewing.reading_docs`
- **AND** 系统 SHALL 创建类型为 `reviewer` 的子 session

#### Scenario: 同一 agent 继续下一阶段

- **GIVEN** 当前 agent 完成了 `planning.ready_for_review`
- **WHEN** 人确认通过且选择不切换 agent
- **THEN** 系统 SHALL 允许同一 agent 进入 `reviewing` phase
- **AND** `handoff.json` 中 `current_agent.type` SHALL 更新为 `reviewer`
