# dev-workflow-state-machine 规格

## Purpose

定义开发流程状态机，包括 change 生命周期 phase/sub_state 模型、`handoff.json` 全局状态文件 schema、合法流转规则、human review gate 和回退机制。

## ADDED Requirements

### Requirement: 全局状态文件 handoff.json

每个 change 目录下 SHALL 存在一个 `handoff.json` 文件，作为该 change 开发流程的全局状态 source of truth。所有参与开发的 agent SHALL 在状态变化时更新此文件。工具链 SHALL 可读取此文件进行机械校验和路由。

#### Scenario: 新建 change 时初始化 handoff.json

- **WHEN** 创建新的 OpenSpec change
- **THEN** 系统 SHALL 自动生成 `handoff.json`
- **AND** 初始状态为 `planning.exploring`

#### Scenario: agent 读取当前状态

- **WHEN** 任一角色 agent 开始处理 change
- **THEN** agent SHALL 首先读取 `handoff.json` 获取当前 state
- **AND** agent SHALL 根据 `state.phase` 和 `state.sub_state` 确定自己的工作起点

#### Scenario: agent 更新状态

- **WHEN** agent 完成一个 sub_state 内的任务并准备转移到下一个 sub_state 或 phase
- **THEN** agent SHALL 更新 `handoff.json` 的 `state` 字段
- **AND** agent SHALL 在 `transitions` 数组中追加一条变更记录

### Requirement: 四阶段生命周期

开发流程 SHALL 建模为四个 phase：`planning`、`reviewing`、`building`、`closing`。每个 phase SHALL 包含若干 sub_state，最后一个 sub_state SHALL 为 `ready_for_review`，作为 human review gate。

#### Scenario: 正常四阶段流转

- **GIVEN** 一个 change 从 `init` 状态开始
- **WHEN** 按顺序完成 planning、reviewing、building、closing 四个阶段
- **THEN** change 到达 `closing.done` 终态

#### Scenario: 跳过审查阶段

- **GIVEN** change 处于 `planning.ready_for_review`
- **WHEN** 人确认跳过审查
- **THEN** 状态 SHALL 直接流转到 `building.writing_tests`
- **AND** transition trigger SHALL 为 `human_review`
- **AND** transition SHALL 包含 `skip_reason`

#### Scenario: 跳过收尾阶段

- **GIVEN** change 处于 `building.ready_for_review`
- **WHEN** 人确认跳过单独收尾
- **THEN** 状态 SHALL 直接流转到 `closing.syncing_specs`
- **AND** transition trigger SHALL 为 `human_review`

### Requirement: Phase 内部 sub_state 定义

每个 phase SHALL 拥有明确的 sub_state 序列，用于追踪同一 agent 内部的工作进度。

#### Scenario: planning sub_state 序列

- **GIVEN** change 处于 `planning` phase
- **THEN** sub_state 序列 SHALL 为: `exploring` → `writing_proposal` → `writing_design` → `writing_specs` → `writing_tasks` → `ready_for_review`
- **AND** 同 phase 内 sub_state 间流转 trigger SHALL 为 `auto`

#### Scenario: reviewing sub_state 序列

- **GIVEN** change 处于 `reviewing` phase
- **THEN** sub_state 序列 SHALL 为: `reading_docs` → `questioning` ⇄ `resolving` → `ready_for_review`
- **AND** `questioning` 和 `resolving` 之间可以来回流转
- **AND** 审查不通过时 SHALL 从 `resolving` 直接回退到 `planning` 的对应 sub_state

#### Scenario: building sub_state 序列

- **GIVEN** change 处于 `building` phase
- **THEN** sub_state 序列 SHALL 为: `writing_tests` ⇄ `test_failing` → `implementing` ⇄ `all_tests_passing` → `smoke_validating` → `ready_for_review`
- **AND** `writing_tests` 与 `test_failing` 之间可以来回（TDD 循环）
- **AND** `implementing` 与 `all_tests_passing` 之间可以来回
- **AND** `smoke_validating` 失败时 SHALL 回退到 `implementing`

#### Scenario: closing sub_state 序列

- **GIVEN** change 处于 `closing` phase
- **THEN** sub_state 序列 SHALL 为: `syncing_specs` → `archiving` → `updating_backlog` → `validating` → `pr_ready` → `merged` → `ready_for_review`
- **AND** `ready_for_review` 通过后到达 `done` 终态

### Requirement: Human review gate

每个 phase 末端 SHALL 设置 human review gate。gate 的 sub_state 名称为 `ready_for_review`。从 gate 发起的 phase 间流转 trigger SHALL 为 `human_review`。从 gate 发起的回退流转 trigger SHALL 为 `human_rollback`。

#### Scenario: 人在 gate 点确认通过

- **GIVEN** change 处于某 phase 的 `ready_for_review`
- **WHEN** 人确认通过
- **THEN** 状态 SHALL 流转到下一 phase 的第一个 sub_state
- **AND** transition trigger SHALL 为 `human_review`

#### Scenario: 人在 gate 点发起回退

- **GIVEN** change 处于某 phase 的 `ready_for_review`
- **WHEN** 人发现问题并发起回退
- **THEN** 状态 SHALL 流转到指定 phase 的指定 sub_state
- **AND** transition trigger SHALL 为 `human_rollback`
- **AND** transition SHALL 包含 `rollback_reason`

#### Scenario: 人在任意时刻发起回退

- **GIVEN** change 处于任意 phase 和 sub_state
- **WHEN** 人发现问题并发起回退
- **THEN** 状态 SHALL 流转到指定 phase 的指定 sub_state
- **AND** transition trigger SHALL 为 `human_rollback`
- **AND** transition SHALL 包含 `rollback_reason`
- **AND** 回退前的状态 SHALL 保留在 `transitions` 日志中

### Requirement: Agent 间 handoff

phase 间交接时，完成当前 phase 的 agent SHALL 生成 handoff note，为接手下一 phase 的 agent 提供上下文。

#### Scenario: 生成 handoff note

- **WHEN** agent 完成一个 phase 并准备交接给下一个 agent
- **THEN** agent SHALL 在 `.handoff/<change-id>/` 目录下生成 handoff note
- **AND** handoff note SHALL 包含: 本阶段完成内容、关键决策及原因、未选方案、待解决问题或风险、下一阶段入口点和优先级

#### Scenario: handoff skill 可用时

- **GIVEN** 当前环境可用 `handoff` skill
- **WHEN** 需要生成 handoff note
- **THEN** agent SHALL 优先使用 `handoff` skill 生成交接笔记

#### Scenario: handoff skill 不可用时

- **GIVEN** 当前环境无 `handoff` skill
- **WHEN** 需要生成 handoff note
- **THEN** agent SHALL 使用内置等价 prompt 生成交接笔记
- **AND** 笔记内容 SHALL 覆盖相同的必含要素

#### Scenario: 同一 agent 连续处理多阶段

- **GIVEN** 同一个 agent 连续完成多个 phase
- **THEN** agent 可以在最后一个 phase 结束时生成一份汇总 handoff note
- **AND** phase 间的 `human_review` trigger 仍然需要人确认

### Requirement: handoff.json schema

`handoff.json` SHALL 遵循固定 schema，包含 `change_id`、`state`、`transitions`、`current_agent`、`last_gate` 和 `blockers` 字段。

#### Scenario: state 字段

- **WHEN** 读取 `handoff.json`
- **THEN** `state` SHALL 包含 `phase`（枚举值: `planning` / `reviewing` / `building` / `closing` / `blocked` / `done`）
- **AND** `state` SHALL 包含 `sub_state`（string）

#### Scenario: transitions 字段

- **WHEN** 读取 `handoff.json`
- **THEN** `transitions` SHALL 为数组，每项包含: `from`、`to`、`trigger`、`agent_run_id`、`timestamp`
- **AND** `trigger` 枚举值为 `auto` / `handoff` / `human_review` / `human_rollback`
- **AND** `trigger` 为 `handoff` 时 SHALL 包含 `handoff_note` 路径
- **AND** `trigger` 为 `human_rollback` 时 SHALL 包含 `rollback_reason`
- **AND** trigger 为 `human_review` 且跳过了下一阶段时 SHALL 包含 `skip_reason`

#### Scenario: current_agent 字段

- **WHEN** 读取 `handoff.json`
- **THEN** `current_agent` SHALL 包含 `run_id` 和 `type`
- **AND** `type` 枚举值为 `planner` / `reviewer` / `builder` / `closer`

#### Scenario: last_gate 字段

- **WHEN** change 处于某 phase 的 `ready_for_review` sub_state
- **THEN** `last_gate` SHALL 包含当前 gate 的 `phase`、`sub_state` 和 `awaiting: "human_review"`

#### Scenario: blockers 字段

- **WHEN** change 状态为 `blocked`
- **THEN** `blockers` SHALL 为非空数组
- **AND** 每项 SHALL 包含 `phase`、`reason`、`blocked_at`
- **AND** 阻塞解除时 SHALL 填写 `resolved_at`

### Requirement: 合法流转表

系统 SHALL 校验所有流转是否符合预定义的合法流转表。

#### Scenario: 合法跨 phase 流转

- **WHEN** 验证流转 `from` → `to`
- **THEN** 以下流转 SHALL 视为合法:
  - `planning.ready_for_review` → `reviewing.reading_docs`
  - `planning.ready_for_review` → `building.writing_tests`（skip）
  - `reviewing.ready_for_review` → `building.writing_tests`
  - `building.ready_for_review` → `closing.syncing_specs`
  - `closing.ready_for_review` → done

#### Scenario: 合法回退流转

- **WHEN** 验证回退流转
- **THEN** 从任意 phase 回退到 `planning` 或 `reviewing` 或 `building` 或 `closing` SHALL 视为合法
- **AND** 回退到 `planning` 时 sub_state 可为 `exploring` / `writing_design` / `writing_specs` / `writing_tasks`

#### Scenario: 非法流转拒绝

- **WHEN** 尝试执行不在合法流转表中的流转
- **THEN** 系统 SHALL 拒绝
- **AND** SHALL 提示最近的合法目标

### Requirement: 角色 Agent 类型

系统 SHALL 定义四种开发角色 agent 类型，分别对应四个开发阶段。

#### Scenario: Planner agent

- **WHEN** 路由系统选择 Planner agent
- **THEN** Planner SHALL 负责 `planning` phase 的全部 sub_state
- **AND** 产出 proposal.md、design.md、spec delta、tasks.md
- **AND** 到达 `ready_for_review` 后等待 human review

#### Scenario: Reviewer agent

- **WHEN** 路由系统选择 Reviewer agent
- **THEN** Reviewer SHALL 负责 `reviewing` phase 的全部 sub_state
- **AND** 产出设计审查结论和追问记录
- **AND** 到达 `ready_for_review` 后等待 human review

#### Scenario: Builder agent

- **WHEN** 路由系统选择 Builder agent
- **THEN** Builder SHALL 负责 `building` phase 的全部 sub_state
- **AND** 产出测试代码和实现代码
- **AND** 到达 `ready_for_review` 后等待 human review

#### Scenario: Closer agent

- **WHEN** 路由系统选择 Closer agent
- **THEN** Closer SHALL 负责 `closing` phase 的全部 sub_state
- **AND** 完成 spec 同步、归档、backlog 更新、校验
- **AND** 到达 `done` 终态

### Requirement: 单 Agent 全流程兼容

系统 SHALL 允许同一个 agent 连续完成全部四个 phase，不强制切换 agent。

#### Scenario: 同一 agent 贯穿全流程

- **GIVEN** 同一个 agent 的 `run_id` 贯穿全部 phase
- **WHEN** 每个 phase 到达 `ready_for_review`
- **THEN** human review gate SHALL 仍然要求人确认
- **AND** phase 间 handoff note 可简化或合并
- **AND** `transitions` 日志 SHALL 仍然逐条记录

### Requirement: 阻塞状态

系统 SHALL 支持任意 phase 进入 `blocked` 状态，用于等待外部依赖或决策。

#### Scenario: 进入阻塞

- **WHEN** agent 或人判断 change 需要等待外部输入
- **THEN** 状态 SHALL 变为 `blocked`（无 sub_state）
- **AND** `blockers` 数组 SHALL 追加新的阻塞项
- **AND** transition trigger SHALL 为 `auto` 或 `human_rollback`

#### Scenario: 解除阻塞

- **WHEN** 阻塞条件解除
- **THEN** 状态 SHALL 恢复到进入 `blocked` 之前的 phase + sub_state
- **AND** `blockers[i].resolved_at` SHALL 填写解除时间
