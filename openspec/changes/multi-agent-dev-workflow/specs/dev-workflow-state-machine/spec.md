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

开发流程 SHALL 建模为五个 phase：`planning`、`reviewing`、`building`、`code-review`、`closing`。每个 phase SHALL 包含若干 sub_state，最后一个 sub_state SHALL 为 `ready_for_review`，作为 human review gate。

#### Scenario: 正常五阶段流转

- **GIVEN** 一个 change 从 `init` 状态开始
- **WHEN** 按顺序完成 planning、reviewing、building、code-review、closing 五个阶段
- **THEN** change 到达 `closing.done` 终态

#### Scenario: 跳过设计审查阶段

- **GIVEN** change 处于 `planning.ready_for_review`
- **WHEN** 人确认跳过设计审查
- **THEN** 状态 SHALL 直接流转到 `building.writing_tests`
- **AND** transition trigger SHALL 为 `human_review`
- **AND** transition SHALL 包含 `skip_reason`

#### Scenario: 跳过代码审查阶段

- **GIVEN** change 处于 `building.ready_for_review`
- **WHEN** 人确认跳过代码审查
- **THEN** 状态 SHALL 直接流转到 `closing.syncing_specs`
- **AND** transition trigger SHALL 为 `human_review`
- **AND** transition SHALL 包含 `skip_reason`

### Requirement: Phase 内部 sub_state 定义

每个 phase SHALL 拥有明确的 sub_state 序列，用于追踪同一 agent 内部的工作进度。

#### Scenario: planning sub_state 序列

- **GIVEN** change 处于 `planning` phase
- **THEN** sub_state 序列 SHALL 为: `exploring` → `writing_proposal` → `writing_design` ⇄ `grilling_design` → `writing_specs` → `writing_tasks` → `ready_for_review`
- **AND** `writing_design` 和 `grilling_design` 之间可以来回流转（设计-追问-迭代循环）
- **AND** grill-with-docs 或等价设计追问 SHALL 在 `grilling_design` 中完成，逐项确认实现细节、依赖、风险、测试策略和文档影响
- **AND** 同 phase 内 sub_state 间流转 trigger SHALL 为 `auto`

#### Scenario: reviewing sub_state 序列

- **GIVEN** change 处于 `reviewing` phase
- **THEN** sub_state 序列 SHALL 为: `reading_docs` → `reviewing_design` → `ready_for_review`
- **AND** Reviewer SHALL 对已完成 grill 的完整设计文档做独立评审
- **AND** 审查不通过时 SHALL 从 `reviewing_design` 回退到 `planning.writing_design`

#### Scenario: building sub_state 序列

- **GIVEN** change 处于 `building` phase
- **THEN** sub_state 序列 SHALL 为: `writing_tests` ⇄ `test_failing` → `implementing` ⇄ `all_tests_passing` → `smoke_validating` → `ready_for_review`
- **AND** `writing_tests` 与 `test_failing` 之间可以来回（TDD 循环）
- **AND** `implementing` 与 `all_tests_passing` 之间可以来回
- **AND** `smoke_validating` 失败时 SHALL 回退到 `implementing`

#### Scenario: code-review sub_state 序列

- **GIVEN** change 处于 `code-review` phase
- **THEN** sub_state 序列 SHALL 为: `reading_diff` → `analyzing_tests` → `reviewing_code` ⇄ `requesting_changes` → `ready_for_review`
- **AND** `reviewing_code` 和 `requesting_changes` 之间可以来回流转
- **AND** 发现问题需修改时 SHALL 从 `requesting_changes` 回退到 `building` 的对应 sub_state

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

`handoff.json` SHALL 遵循固定 schema，包含 `change_id`、`state`、`transitions`、`current_agent`、`last_gate`、`blockers` 和 `routing` 字段。

#### Scenario: state 字段

- **WHEN** 读取 `handoff.json`
- **THEN** `state` SHALL 包含 `phase`（枚举值: `planning` / `reviewing` / `building` / `code-review` / `closing` / `blocked` / `done`）
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
- **AND** `type` 枚举值为 `planner` / `reviewer` / `builder` / `code-reviewer` / `closer`

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
  - `planning.ready_for_review` → `building.writing_tests`（skip 设计审查）
  - `reviewing.ready_for_review` → `building.writing_tests`
  - `building.ready_for_review` → `code-review.reading_diff`
  - `building.ready_for_review` → `closing.syncing_specs`（skip 代码审查）
  - `code-review.ready_for_review` → `closing.syncing_specs`
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

系统 SHALL 定义五种开发角色 agent 类型，分别对应五个开发阶段。

#### Scenario: Planner agent

- **WHEN** 路由系统选择 Planner agent
- **THEN** Planner SHALL 负责 `planning` phase 的全部 sub_state
- **AND** 产出 proposal.md、design.md、spec delta、tasks.md
- **AND** 到达 `ready_for_review` 后等待 human review

#### Scenario: Reviewer agent（设计审查）

- **WHEN** 路由系统选择 Reviewer agent
- **THEN** Reviewer SHALL 负责 `reviewing` phase 的全部 sub_state
- **AND** 读取已完成 grill 自审的完整设计文档（design.md / proposal / spec delta / tasks.md）
- **AND** 对方案的完整性、逻辑自洽性、风险覆盖和可行性进行独立评审
- **AND** 产出设计审查结论（通过或打回及理由）
- **AND** 到达 `ready_for_review` 后等待 human review

#### Scenario: Builder agent

- **WHEN** 路由系统选择 Builder agent
- **THEN** Builder SHALL 负责 `building` phase 的全部 sub_state
- **AND** 产出测试代码和实现代码
- **AND** 到达 `ready_for_review` 后等待 human review

#### Scenario: CodeReviewer agent（代码审查）

- **WHEN** 路由系统选择 CodeReviewer agent
- **THEN** CodeReviewer SHALL 负责 `code-review` phase 的全部 sub_state
- **AND** 审查 git diff、测试覆盖、实现质量和与设计文档的一致性
- **AND** 发现问题时 SHALL 进入 `requesting_changes` 并回退到 `building`
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

#### Scenario: routing 字段

- **WHEN** 读取 `handoff.json`
- **THEN** `routing` SHALL 为 object，key 为 phase 名称
- **AND** 每个 phase entry SHALL 包含 `executor` 和 `session_mode`
- **AND** `executor` 枚举值为 `inline` / `subagent` / `claude-code` / `codex`
- **AND** `session_mode` 枚举值为 `same` / `new` / `ask`

### Requirement: 路由配置

系统 SHALL 支持为每个 phase 配置独立的 executor 和 session 模式。项目 SHALL 维护全局默认路由配置，per-change 配置 SHALL 可覆盖全局默认值。

#### Scenario: 全局默认路由配置

- **WHEN** 创建新 change 时
- **THEN** `handoff.json` 的 `routing` 字段 SHALL 从项目配置文件（`openspec/config.yaml` 的路由段）继承默认值
- **AND** 四个 phase 均 SHALL 有默认 executor 和 session_mode

#### Scenario: Per-change 路由覆盖

- **WHEN** 人在创建 change 或 gate 点修改路由配置
- **THEN** `handoff.json` 的 `routing` SHALL 更新被修改的 phase entry
- **AND** 未修改的 phase SHALL 保持原值

#### Scenario: 创建 change 时提示路由配置

- **WHEN** 用户通过自然语言启动一个新 change
- **THEN** 系统 SHALL 读取项目默认路由配置
- **AND** SHALL 向人展示当前路由配置并询问是否需要调整
- **AND** 人可接受默认值或覆盖任意 phase 的 executor / session_mode

#### Scenario: Gate 点询问路由

- **GIVEN** change 当前 phase 的 `session_mode` 为 `ask`
- **WHEN** 人在 gate 点确认通过
- **THEN** 系统 SHALL 询问下一个 phase 使用哪个 executor 和 session 模式
- **AND** 人的选择 SHALL 写入 `handoff.json` 的 `routing`

#### Scenario: executor inline 行为

- **GIVEN** phase 的 `executor` 为 `inline`
- **WHEN** 进入该 phase
- **THEN** 系统 SHALL 在当前 agent session 中直接处理
- **AND** 不启动新的子 session 或外部进程

#### Scenario: executor subagent 行为

- **GIVEN** phase 的 `executor` 为 `subagent`
- **WHEN** 进入该 phase
- **THEN** 系统 SHALL 创建对应角色 agent 类型的子 session
- **AND** 子 session SHALL 接收 handoff note 和 change 文档路径作为上下文

#### Scenario: executor claude-code 行为

- **GIVEN** phase 的 `executor` 为 `claude-code`
- **WHEN** 进入该 phase
- **THEN** 系统 SHALL 通过 `claude` CLI 子进程执行
- **AND** 子进程 SHALL 接收 handoff note 内容和 change 目录路径

#### Scenario: executor codex 行为

- **GIVEN** phase 的 `executor` 为 `codex`
- **WHEN** 进入该 phase
- **THEN** 系统 SHALL 通过 Codex CLI 子进程执行
- **AND** 子进程 SHALL 接收 handoff note 内容和 change 目录路径

#### Scenario: session_mode same

- **GIVEN** phase 的 `session_mode` 为 `same`
- **WHEN** 进入该 phase
- **THEN** 系统 SHALL 尽可能复用当前 session（仅在 `executor` 为 `inline` 时有效）

#### Scenario: session_mode new

- **GIVEN** phase 的 `session_mode` 为 `new`
- **WHEN** 进入该 phase
- **THEN** 系统 SHALL 创建新的 session 或进程

#### Scenario: session_mode ask

- **GIVEN** phase 的 `session_mode` 为 `ask`
- **WHEN** 该 phase 即将进入
- **THEN** 系统 SHALL 询问人：使用哪个 executor、是否新 session

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
