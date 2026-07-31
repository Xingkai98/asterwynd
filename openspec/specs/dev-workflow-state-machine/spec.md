# dev-workflow-state-machine 规格

## Purpose

定义开发流程状态机，包括 change 生命周期 phase/sub_state 模型、`handoff.json` 全局状态文件 schema、合法流转规则、human review gate 和回退机制。

## Requirements

### Requirement: 工作流事件日志与 handoff.json projection

每个 change 目录下 SHALL 存在一个 `workflow-events.jsonl` 文件，作为该 change 开发流程的权威事实来源。`handoff.json` SHALL 作为由事件日志 replay 生成的 projection，供 agent 快速读取当前状态。Agent 不 SHALL 直接编辑 `handoff.json` 来声明状态变化；所有状态变化 SHALL 通过 WorkflowEngine/CLI 追加事件并重新生成 projection。

#### Scenario: 新建 change 时初始化 workflow event log 和 handoff.json

- **WHEN** 创建新的 OpenSpec change
- **THEN** 系统 SHALL 自动生成 `workflow-events.jsonl`
- **AND** 系统 SHALL 由初始化事件生成 `handoff.json`
- **AND** 初始状态为 `planning.exploring`

#### Scenario: agent 读取当前状态

- **WHEN** 任一角色 agent 开始处理 change
- **THEN** agent SHALL 首先读取 `handoff.json` 获取当前 state
- **AND** agent SHALL 根据 `state.phase` 和 `state.sub_state` 确定自己的工作起点

#### Scenario: WorkflowEngine 更新状态

- **WHEN** agent 完成一个 sub_state 内的任务并准备转移到下一个 sub_state 或 phase
- **THEN** agent SHALL 请求 WorkflowEngine/CLI 执行状态推进
- **AND** WorkflowEngine SHALL 追加一条 `workflow-events.jsonl` 事件
- **AND** WorkflowEngine SHALL 重新生成 `handoff.json` projection
- **AND** 校验器 SHALL 验证 `handoff.json` 与 `workflow-events.jsonl` replay 结果一致

#### Scenario: handoff.json 被手动篡改

- **GIVEN** `workflow-events.jsonl` replay 的当前状态与 `handoff.json` 中的 `state` 不一致
- **WHEN** 运行 gate 或 CI 校验
- **THEN** 系统 SHALL 拒绝通过
- **AND** SHALL 报告 `handoff.json` projection 与事件日志不一致

#### Scenario: 非状态 artifact 事件

- **WHEN** `workflow-events.jsonl` 包含不改变 workflow state 的 artifact 事件
- **THEN** replay `handoff.json` projection 时 SHALL 保留事件日志顺序校验
- **AND** SHALL 忽略这些事件对 `handoff.json` projection 的影响
- **AND** 支持的 artifact event type SHALL 至少包含 `protected_artifact_explained`、`current_spec_synced`、`backlog_updated`、`change_archived`

### Requirement: Protected artifact 变更解释

工作流保护的项目级 artifact 被修改时，CI/gate SHALL 要求对应 `workflow-events.jsonl` 中存在结构化解释事件。解释事件 SHALL 包含 `artifact_path`、`reason`、`approved_by` 和匹配的 `change_id`，不得只依赖自然语言对话或手写无证据 review 文本。

#### Scenario: known issues/debt 文档变更

- **GIVEN** PR diff 修改 `docs/known-issues.md` 或 `docs/known-debt.md`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 要求存在 `protected_artifact_explained` 事件
- **AND** 事件的 `artifact_path` SHALL 覆盖被修改路径

#### Scenario: current spec 变更

- **GIVEN** PR diff 修改 `openspec/specs/**`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 要求存在 `current_spec_synced` 事件
- **AND** 事件 SHALL 说明该 current spec 由哪个已批准变更同步而来

#### Scenario: backlog 变更

- **GIVEN** PR diff 修改 `docs/openspec-change-backlog.md`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 要求存在 `backlog_updated` 事件
- **AND** 事件 SHALL 说明 backlog 更新发生在 closing 收尾语境中

#### Scenario: archive 变更

- **GIVEN** PR diff 修改 `openspec/changes/archive/**`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 要求存在 `change_archived` 事件
- **AND** archive 目录名为 `YYYY-MM-DD-<change-id>` 时，事件 `change_id` SHALL 使用原始 `<change-id>`

### Requirement: Review evidence manifest

每个阶段的独立 review report SHALL 绑定机器可验证的 manifest。review report 文件为 `.handoff/<change-id>/<phase>-review.md`，manifest 文件为 `.handoff/<change-id>/<phase>-review-manifest.json`。gate/CI 不得只根据 review report 文本中的 `PASS` 判断审查通过。

#### Scenario: review report 缺少 manifest

- **GIVEN** `.handoff/<change-id>/<phase>-review.md` 存在
- **AND** 对应 review manifest 不存在
- **WHEN** 运行 gate 或项目 artifact checker
- **THEN** 系统 SHALL 拒绝通过
- **AND** SHALL 报告 review manifest 缺失

#### Scenario: manifest 字段和 hash 校验

- **WHEN** 校验 review manifest
- **THEN** manifest SHALL 声明 `schema`、`change_id`、`phase`、`verdict`、`reviewer_run_id`、`base_sha`、`head_sha`、`tasks_hash`、`spec_hash`、`diff_hash`、`report_hash`
- **AND** `verdict` SHALL 为 `PASS`
- **AND** checker SHALL 验证 `report_hash`、`tasks_hash`、`spec_hash`
- **AND** 当 repo root 是 git repo 时，checker SHALL 验证 `head_sha` 匹配当前 `HEAD`，`base_sha` / `head_sha` 均为 commit，且 `diff_hash` 匹配 `git diff --binary <base_sha> <head_sha>` 的 sha256

### Requirement: Workflow 总开关

`scripts/workflow_methods.json` SHALL 提供 `workflow.enabled` 布尔开关，默认值为 `true`。当其为 `false` 时，workflow automation SHALL 视为未启用：`discover` 不 SHALL 暴露活跃 change，PreToolUse 门禁不 SHALL 阻止写操作，`check_phase_done.py` 不 SHALL 因 phase gate 阻塞，`WorkflowDispatcher` 不 SHALL 继续分发 workflow phase。

#### Scenario: workflow 未启用时不暴露活跃 change

- **GIVEN** `workflow.enabled = false`
- **WHEN** agent 运行 `python3 scripts/workflow_state.py discover`
- **THEN** 系统 SHALL 报告没有活跃 change
- **AND** existing handoff state SHALL 不影响 discover 结果

#### Scenario: workflow 未启用时 gate 和门禁退化

- **GIVEN** `workflow.enabled = false`
- **WHEN** PreToolUse 门禁或 `check_phase_done.py` 运行
- **THEN** 系统 SHALL 不阻止写操作
- **AND** 系统 SHALL 视 workflow gate 为 no-op

### Requirement: 四阶段生命周期

开发流程 SHALL 建模为四个活跃 phase：`wayfinding`、`planning`、`building`、`closing`。独立设计审查和代码审查 SHALL 内嵌为各 phase 的 `reviewing_*` sub_state。每个活跃 phase SHALL 包含若干 sub_state，最后一个 sub_state SHALL 为 `ready_for_review`，作为 human review gate。

#### Scenario: 正常四阶段流转

- **GIVEN** 一个 change 从 `init` 状态开始
- **WHEN** 按顺序完成 wayfinding、planning、building、closing 四个阶段
- **THEN** change 到达 `done` 终态

#### Scenario: 内嵌设计审查

- **GIVEN** change 处于 `planning.writing_tickets`
- **WHEN** planning 产物已完成
- **THEN** 状态 SHALL 进入 `planning.reviewing_artifacts`
- **AND** 独立子 Agent SHALL 审阅 proposal、design、spec delta 和 tasks
- **AND** 审阅通过后才可进入 `planning.ready_for_review`

#### Scenario: 内嵌代码审查

- **GIVEN** change 处于 `building.smoke_validating`
- **WHEN** 实现和验证已完成
- **THEN** 状态 SHALL 进入 `building.reviewing_impl`
- **AND** 独立子 Agent SHALL 对照 tasks、spec 和 diff 审阅实现
- **AND** 审阅通过后才可进入 `building.ready_for_review`

### Requirement: Phase 内部 sub_state 定义

每个 phase SHALL 拥有明确的 sub_state 序列，用于追踪同一 agent 内部的工作进度。

#### Scenario: planning sub_state 序列

- **GIVEN** change 处于 `planning` phase
- **THEN** sub_state 序列 SHALL 为: `exploring` → `writing_proposal` → `writing_design` → `writing_spec` → `writing_tickets` → `reviewing_artifacts` → `ready_for_review`
- **AND** grill-with-docs 或等价设计追问 SHALL 在 `exploring` 到 `writing_design` 期间完成，逐项确认实现细节、依赖、风险、测试策略和文档影响
- **AND** 同 phase 内 sub_state 间流转 trigger SHALL 为 `auto`
- **AND** `writing_tickets` 生成的 tracer-bullet tickets SHALL 发布到配置的 issue tracker backend，默认 backend 为 GitHub Issues

#### Scenario: wayfinding sub_state 序列

- **GIVEN** change 处于 `wayfinding` phase
- **THEN** sub_state 序列 SHALL 为: `charting_map` → `working_tickets` → `map_cleared` → `reviewing_map` → `ready_for_review`
- **AND** `reviewing_map` SHALL 由独立子 Agent 审阅探路地图、决策闭合度和子 change 依赖关系
- **AND** `working_tickets` 阶段生成的 decision tickets SHALL 发布到配置的 issue tracker backend，默认 backend 为 GitHub Issues

#### Scenario: building sub_state 序列

- **GIVEN** change 处于 `building` phase
- **THEN** sub_state 序列 SHALL 为: `writing_tests` ⇄ `test_failing` → `implementing` ⇄ `all_tests_passing` → `smoke_validating` → `reviewing_impl` → `ready_for_review`
- **AND** `writing_tests` 与 `test_failing` 之间可以来回（TDD 循环）
- **AND** `implementing` 与 `all_tests_passing` 之间可以来回
- **AND** `smoke_validating` 失败时 SHALL 回退到 `implementing`
- **AND** `reviewing_impl` SHALL 由独立子 Agent 审阅代码实现、任务完成度、测试覆盖和安全性

#### Scenario: closing sub_state 序列

- **GIVEN** change 处于 `closing` phase
- **THEN** sub_state 序列 SHALL 为: `syncing_specs` → `archiving` → `updating_backlog` → `validating` → `pr_ready` → `reviewing_archive` → `ready_for_review`
- **AND** `ready_for_review` 通过后到达 `done` 终态
- **AND** `merged` 为 done 之后的 post-merge 确认步骤，不作为 gate 前状态

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

`handoff` trigger 标记 agent 完成工作并生成 handoff note 的时刻，但不改变 state.phase。实际跨 phase 状态变更由 human gate 的 `human_review` trigger 驱动。handoff note 在 agent 到达 `ready_for_review` 时生成，transition 中记录 `trigger: handoff` 和 handoff note 路径；人确认后追加 `trigger: human_review` 的 transition 完成 phase 流转。

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

`handoff.json` SHALL 遵循固定 schema，包含 `schema_version`、`change_id`、`state`、`transitions`、`current_agent`、`last_gate`、`blockers` 和 `routing` 字段。

#### Scenario: schema_version 字段

- **WHEN** 读取 `handoff.json`
- **THEN** `schema_version` SHALL 为语义化版本字符串
- **AND** 初始版本 SHALL 为 `"1.0"`
- **AND** 解析器 SHALL 检查 schema_version 兼容性

#### Scenario: state 字段

- **WHEN** 读取 `handoff.json`
- **THEN** `state` SHALL 包含 `phase`（枚举值: `wayfinding` / `planning` / `building` / `closing` / `blocked` / `done`）
- **AND** `state` SHALL 包含 `sub_state`（string），当 phase 为 `blocked` 或 `done` 时可为 `null`

#### Scenario: transitions 字段

- **WHEN** 读取 `handoff.json`
- **THEN** `transitions` SHALL 为数组，每项包含: `from`、`to`、`trigger`、`actor_type`、`actor_id`、`timestamp`
- **AND** `actor_type` 枚举值为 `agent` / `human`
- **AND** `actor_id` 为 agent 的 `run_id` 或人的标识
- **AND** `trigger` 枚举值为 `auto` / `handoff` / `human_review` / `human_rollback`
- **AND** `trigger` 为 `handoff` 时 SHALL 包含 `handoff_note` 路径
- **AND** `trigger` 为 `human_review` 时 SHALL 包含 `decision`（approved / skip / rollback）和可选的 `reason`
- **AND** `trigger` 为 `human_rollback` 时 SHALL 包含 `rollback_reason`
- **AND** trigger 为 `human_review` 且跳过了下一阶段时 SHALL 包含 `skip_reason`

#### Scenario: current_agent 字段

- **WHEN** 读取 `handoff.json`
- **THEN** `current_agent` SHALL 包含 `run_id` 和 `type`
- **AND** `type` 枚举值为 `wayfinder` / `planner` / `builder` / `closer`

#### Scenario: last_gate 字段

- **WHEN** change 处于某 phase 的 `ready_for_review` sub_state
- **THEN** `last_gate` SHALL 包含当前 gate 的 `phase`、`sub_state` 和 `awaiting: "human_review"`
- **AND** 当 change 不处于 gate 状态时 `last_gate` SHALL 为 `null`

#### Scenario: blockers 字段

- **WHEN** change 状态为 `blocked`
- **THEN** `blockers` SHALL 为非空数组
- **AND** 每项 SHALL 包含 `blocked_from`（被阻塞时的 phase + sub_state）、`reason`、`blocked_at`
- **AND** 阻塞解除时 SHALL 填写 `resolved_at`

### Requirement: 合法流转表

系统 SHALL 校验所有流转是否符合预定义的合法流转表。

#### Scenario: 合法跨 phase 流转

- **WHEN** 验证流转 `from` → `to`
- **THEN** 以下流转 SHALL 视为合法:
  - `wayfinding.ready_for_review` → `planning.exploring`
  - `planning.ready_for_review` → `building.writing_tests`
  - `building.ready_for_review` → `closing.syncing_specs`
  - `closing.ready_for_review` → `done`

#### Scenario: 合法回退流转

- **WHEN** 验证回退流转
- **THEN** 从任意 phase 回退到 `wayfinding` / `planning` / `building` / `closing` SHALL 视为合法
- **AND** 回退目标 phase SHALL 早于当前 phase（禁止回退到自身或更晚的阶段）
- **AND** 回退到 `planning` 时 sub_state 可为 `exploring` / `writing_design` / `writing_spec` / `writing_tickets`

#### Scenario: 合法阻塞流转

- **WHEN** 验证阻塞相关流转
- **THEN** 以下流转 SHALL 视为合法:
  - 任意 phase.sub_state → `blocked`（trigger: `auto` 或 `human_rollback`）
  - `blocked` → 进入阻塞前的 phase.sub_state（trigger: `auto`，从 `blockers[i].blocked_from` 恢复）

#### Scenario: 非法流转拒绝

- **WHEN** 尝试执行不在合法流转表中的流转
- **THEN** 系统 SHALL 拒绝
- **AND** SHALL 提示最近的合法目标

### Requirement: 角色 Agent 类型

系统 SHALL 定义四种开发角色 agent 类型，分别对应四个活跃开发阶段。

#### Scenario: Wayfinder agent

- **WHEN** 路由系统选择 Wayfinder agent
- **THEN** Wayfinder SHALL 负责 `wayfinding` phase 的全部 sub_state
- **AND** 产出决策地图、decision tickets 和子 change 依赖关系
- **AND** 到达 `ready_for_review` 后等待 human review

#### Scenario: Planner agent

- **WHEN** 路由系统选择 Planner agent
- **THEN** Planner SHALL 负责 `planning` phase 的全部 sub_state
- **AND** 产出 proposal.md、design.md、spec delta、tasks.md
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

系统 SHALL 允许同一个 agent 连续完成全部四个活跃 phase，不强制切换 agent。

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
- **AND** 四个活跃 phase 均 SHALL 有默认 executor 和 session_mode

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

- **GIVEN** change 处于某 phase 的 `ready_for_review`
- **AND** 下一 phase 的路由配置中 `session_mode` 为 `ask`
- **WHEN** 人在 gate 点确认通过
- **THEN** 系统 SHALL 询问下一 phase 使用哪个 executor 和 session 模式
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
- **THEN** 系统 SHALL 尽可能复用当前 session
- **AND** 仅在 `executor` 为 `inline` 时 `same` 语义有效
- **AND** 当 `executor` 非 `inline`（`subagent` / `claude-code` / `codex`）且 `session_mode` 为 `same` 时，系统 SHALL 降级为 `new` 并记录警告

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
