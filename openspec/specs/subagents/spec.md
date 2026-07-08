# subagents 规格

## Purpose

定义子 agent 的子 session runtime 语义、子 run 生命周期、并发边界和 transcript inspect 能力。当前实现位于 `agent/subagent/`。

## Requirements

### Requirement: 子 agent 是完整子 session runtime

系统 SHALL 将子 agent 建模为不直接与用户交互的受限子 session。每个子 session SHALL 拥有独立 transcript、当前 mode、run 历史和可关联的 trace / usage / artifact 信息。

#### Scenario: 创建子 agent

- **GIVEN** 调用方提供创建子 agent 所需的名称、描述或 mode
- **WHEN** 调用 `CreateSubagent`
- **THEN** 系统 SHALL 创建一个新的 `subagent_id`
- **AND** SHALL 初始化该子 session 的 transcript、mode 和元数据

### Requirement: 子 session 支持多次 run

系统 SHALL 允许在同一个子 session 中发起多次 run。每次 run SHALL 拥有独立 `run_id` 和独立 trace 关联，但共享该子 session 的 transcript 与 session 级 mode。

#### Scenario: 在已有子 session 中再次运行

- **GIVEN** 一个已存在的子 session 且当前没有正在运行的子 run
- **WHEN** 调用 `RunSubagent`
- **THEN** 系统 SHALL 创建新的 `run_id`
- **AND** SHALL 复用当前子 session 的 mode 和 transcript 继续运行

### Requirement: 多个子 session 可并发，同一子 session 内 run 串行

系统 SHALL 支持多个子 session 同时存在并并发运行。同一个 `subagent_id` 任一时刻 SHALL 最多只有一个 active run。

#### Scenario: 已有 active run 时再次运行同一子 session

- **GIVEN** 某个子 session 当前已有运行中的子 run
- **WHEN** 再次调用 `RunSubagent`
- **THEN** 系统 SHALL 拒绝该请求
- **AND** SHALL 要求先等待或取消当前 run

### Requirement: 子 session 默认使用 isolated 上下文

子 session 默认 SHALL 使用 `isolated` 上下文。子 session SHALL NOT 默认复制父 session 的 message transcript。

#### Scenario: 默认创建子 session

- **GIVEN** 调用方未显式请求 `fork parent transcript`
- **WHEN** 创建子 session
- **THEN** 子 session SHALL 仅接收显式传入的 task / context
- **AND** SHALL NOT 自动继承父 session 的完整消息历史

### Requirement: 子 transcript inspect 默认受限

系统 SHALL 通过专用 inspect 接口提供子 transcript 摘要或最近消息读取，但 SHALL 默认限制返回范围。

#### Scenario: 查看最近消息

- **GIVEN** 父 agent 需要检查某个子 run 最近的执行情况
- **WHEN** 调用 `InspectSubagentTranscript`
- **THEN** 系统 SHALL 返回摘要或最近 `N` 条消息
- **AND** SHALL NOT 默认返回整份子 transcript

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
- **AND** Reviewer agent SHALL 对已完成 grill 自审的设计文档做独立评审，而非执行 grill-with-docs

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
