## MODIFIED Requirements

### Requirement: 当前子 agent 仍是轻量委托

在本 change 实现前，当前子 agent SHALL 被视为轻量 LLM 委托，而不是完整子 session runtime。文档和实现 SHALL 明确区分这一现状与本 change 目标，避免声称当前子 agent 已具备独立工具循环、多次 run 或显式 inspect 能力。

#### Scenario: 文档描述当前能力

- **GIVEN** 当前实现只直接调用 `llm.chat`
- **WHEN** 编写能力说明
- **THEN** 文档 SHALL 避免声称子 agent 已具备完整子 session runtime 语义

## ADDED Requirements

### Requirement: 子 agent 是完整子 session runtime

实现后，系统 SHALL 将子 agent 建模为不直接与用户交互的受限子 session。每个子 session SHALL 拥有独立 transcript、当前 mode、run 历史和可关联的 trace / usage / artifact 信息。

#### Scenario: 创建子 agent

- **GIVEN** 调用方提供创建子 agent 所需的 task、context 和运行时约束
- **WHEN** 调用创建子 agent 的运行时接口
- **THEN** 系统 SHALL 创建一个新的 `subagent_id`
- **AND** SHALL 初始化该子 session 的 transcript、mode 和元数据

### Requirement: 子 session 支持多次 run

系统 SHALL 允许在同一个子 session 中发起多次 run。每次 run SHALL 拥有独立 `run_id` 和独立 trace 关联，但共享该子 session 的 transcript 与 session 级 mode。

#### Scenario: 在已有子 session 中再次运行

- **GIVEN** 一个已存在的子 session 且当前没有正在运行的子 run
- **WHEN** 父 agent 对该子 session 发起新的 run
- **THEN** 系统 SHALL 创建新的 `run_id`
- **AND** SHALL 复用当前子 session 的 mode 和 transcript 继续运行

### Requirement: 系统支持多个子 session 并发存在

系统 SHALL 支持多个子 session 同时存在并并发运行。

#### Scenario: 并发创建多个子 agent

- **GIVEN** 父 agent 需要并行处理多个子问题
- **WHEN** 调用方创建多个子 session 并发运行
- **THEN** 系统 SHALL 为每个子 session 分配独立 `subagent_id`
- **AND** SHALL 维护彼此独立的状态、transcript 和 run 结果

### Requirement: 子 session 默认使用 isolated 上下文

子 session 默认 SHALL 使用 `isolated` 上下文。子 session SHALL NOT 默认复制父 session 的 message transcript。

#### Scenario: 默认创建子 session

- **GIVEN** 调用方未显式请求 `fork parent transcript`
- **WHEN** 创建子 session
- **THEN** 子 session SHALL 仅接收显式传入的 task / context
- **AND** SHALL NOT 自动继承父 session 的完整消息历史
