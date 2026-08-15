# dev-workflow-state-machine 规格

## Purpose

定义开发流程状态机，包括 change 生命周期 phase/sub_state 模型、`handoff.json` 全局状态文件 schema、合法流转规则、human review gate 和回退机制。

## Requirements

### Requirement: 工作流事件日志与 handoff.json projection

每个 change 目录下 SHALL 存在一个 `workflow-events.jsonl` 文件，作为该 change 开发流程的权威事实来源。投影分为两代：老世代（归档 change）SHALL 由事件日志 replay 生成 `handoff.json` projection；当代（新 change）SHALL 由事件日志 replay 生成 `workflow-state.json` projection。Agent 不 SHALL 直接编辑投影文件来声明状态变化；所有状态变化 SHALL 通过 CLI 追加事件并重新生成投影。

#### Scenario: 当代 change 投影为 workflow-state.json

- **WHEN** change 的事件日志以 `change_created` 开头（当代事件，无 handoff.json）
- **THEN** 系统 SHALL 由其事件 replay 生成 `workflow-state.json`
- **AND** 投影 SHALL 包含 `state`、`milestones` 与 `source_event_seq`（投影来源的最大事件 seq）
- **AND** 投影 SHALL 不包含 `updated_at` 字段

#### Scenario: 老世代 change 仍可投影

- **WHEN** change 的事件日志以 `initialized` 开头且存在 `handoff.json`（老世代，归档 change）
- **THEN** replay SHALL 沿用既有 handoff.json projection 路径，不抛错
- **AND** 与修复前行为保持一致

#### Scenario: 任意 change 可查询状态

- **WHEN** 对任一 change（老或新世代）运行 `flow status`
- **THEN** 系统 SHALL 输出该 change 的投影状态（state / milestones / source_event_seq）
- **AND** SHALL 不要求首事件为 `change_created`（容忍异构派生）

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

工作流保护的项目级 artifact 被修改时，CI/gate SHALL 要求对应 `workflow-events.jsonl` 中存在结构化解释事件。解释事件 SHALL 包含 `artifact_path`、`reason`、`approved_by` 和匹配的 `change_id`，不得只依赖自然语言对话或手写无证据 review 文本。受保护路径清单 SHALL 从 `scripts/flow-policy.json` 中 `governance == event_explained` 的规则子集加载（flow-policy-source P0 单一策略源），checker 不保留独立硬编码清单；策略文件缺失/损坏时 checker SHALL fail-closed。

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

`scripts/workflow_methods.json` SHALL 提供 `workflow.enabled` 布尔开关，默认值为 `true`。当其为 `false` 时，workflow automation SHALL 视为未启用：`discover` 不 SHALL 暴露活跃 change，PreToolUse 门禁不 SHALL 阻止写操作，`check_phase_done.py` 不 SHALL 因 phase gate 阻塞，`WorkflowDispatcher` 不 SHALL 继续分发 workflow phase。系统 SHALL 支持本地 resume audit baseline；通过 workflow CLI 禁用 workflow 时 SHALL 记录当前 git `HEAD`，重新启用时 SHALL 对 baseline 之后的非 workflow 管理文件改动执行恢复审计。

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

#### Scenario: 禁用期间存在未恢复改动

- **GIVEN** workflow CLI 禁用 workflow 时已写入 resume baseline
- **AND** baseline 之后存在非 workflow 管理文件改动
- **WHEN** workflow 被重新启用或 agent 运行 `discover`
- **THEN** 系统 SHALL 报告需要 resume audit reconciliation
- **AND** PreToolUse 门禁 SHALL 阻止继续写入，直到改动被归入某个 change

#### Scenario: 禁用期间改动被恢复确认

- **GIVEN** baseline 之后存在非 workflow 管理文件改动
- **WHEN** 人通过 `workflow_state.py resume-audit --reconcile-change <id>` 将改动归入某个 change
- **THEN** 系统 SHALL 向该 change 的 `workflow-events.jsonl` 追加 `resume_audit_reconciled` 事件
- **AND** 事件 SHALL 记录 `baseline_sha`、`head_sha`、`changed_paths_hash`、`changed_paths`、`reason` 和 `approved_by`
- **AND** replay `handoff.json` projection 时 SHALL 忽略该非状态事件

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
- **AND** batch-grill-me 或等价设计追问 SHALL 在 `exploring` 到 `writing_design` 期间完成，逐项确认实现细节、依赖、风险、测试策略和文档影响
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
- **AND** awaiting 态（`blocked.awaiting_*`）SHALL 承载 sub_state，普通 `blocked`（非 awaiting）sub_state 仍为 `null`

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

系统 SHALL 支持任意 phase 进入 awaiting 态，用于等待外部依赖或决策。等待合法化不弱化执法：awaiting 期间写操作 SHALL 仍被 guard 拦截（exit 2），用户确认后才放行。awaiting 态 SHALL 建模为 `blocked` phase 的 sub_state（如 `blocked.awaiting_proposal_confirmation`），普通 `blocked`（非 awaiting）sub_state 为 null。awaiting 态集合 SHALL 包含 `awaiting_proposal_confirmation`（激活，proposal 完成后进入）、`awaiting_human_review` 与 `awaiting_user_confirmation`；`review_blocked` 不 SHALL 计入 awaiting 集。

#### Scenario: 进入等待态

- **WHEN** agent 完成 proposal 阶段（含调研结论）或用户主动 block，进入需要外部确认的状态
- **THEN** 完成命令或 `flow block` SHALL 追加 `blocked_entered` 事件（复用 v1 blocked 事件类型，不新增类型）
- **AND** 投影状态 SHALL 变为对应的 `blocked.awaiting_*` 态
- **AND** `blocked_entered` SHALL 只由进入 awaiting 的完成命令或 `flow block` 写入（写路径唯一化）
- **AND** proposal 完成后写 `blocked_entered` 进入 `awaiting_proposal_confirmation`，用户 `flow confirm` 写 `blocked_resolved` 后才允许进入开发

#### Scenario: 解除等待态

- **WHEN** 用户确认解除等待
- **THEN** `flow confirm` SHALL 追加 `blocked_resolved` 事件（复用 v1 blocked 事件类型）
- **AND** `blocked_resolved` SHALL 只由 `flow confirm` 写入（写路径唯一化）
- **AND** `blocked_resolved` 的 payload SHALL 从当前投影 awaiting 态推导（from=当前 `blocked.awaiting_*`，to=恢复目标），兼容无 `blocked_entered` 前置记录的 change
- **AND** 状态 SHALL 恢复到进入 awaiting 之前的阶段

#### Scenario: flow approve 阶段 gate 通过

- **WHEN** change 处于某 phase 的 `ready_for_review`（gate）且运行 `flow approve --phase <phase>`
- **THEN** 系统 SHALL 追加 `transition_applied` 事件（trigger: `human_review`）完成跨阶段推进到下一 phase 首 sub_state
- **AND** 不写 `blocked_resolved`（awaiting 解除只由 `flow confirm` 承担）
- **AND** phase 机械检查未通过时 SHALL 拒绝批准

#### Scenario: checker 派生物一致性

- **WHEN** 项目 artifact checker 校验 tasks 全勾的 change
- **THEN** 它 SHALL 校验磁盘投影（workflow-state.json）与从事件 replay 重建的投影一致（投影 == replay）
- **AND** 不一致时 SHALL 失败（exit 2），防止自锁

#### Scenario: guard 读投影执法

- **WHEN** guard 判断某 change 处于 awaiting 态且未确认
- **THEN** 写操作（Write/Edit 与 write-intent Bash）SHALL exit 2（awaiting 执法不弱化，不可经 Bash 绕过）
- **AND** guard SHALL 以事件日志 replay 结果判定 awaiting（事件是唯一真相）：投影缺失/损坏/stale 不影响判定——awaiting 仍 exit 2（不因投影问题放行）、非 awaiting 放行（不额外误拦）
- **AND** guard SHALL 只读，不写盘（hook 无副作用）
- **AND** 仅事件不完整（缺 seq / JSON 语法坏 / 末尾截断）导致无法 replay 时，guard SHALL fail-closed（exit 2，报「事件不完整，检查 seq N」）；`flow status` 同口径报错，不猜测不跳过

### Requirement: flow 命令与受保护路径

系统 SHALL 提供 `flow status` / `flow confirm` / `flow approve` / `flow block` / `flow advance` 命令，作为投影查询、等待态确认与阶段推进的 CLI 通道；`workflow-state.json` 与 `workflow-events.jsonl` SHALL 纳入受保护路径（governance=cli_written），只允许 CLI 写入。

#### Scenario: flow status 展示投影

- **WHEN** 运行 `flow status [--change <id>|--all]`
- **THEN** 系统 SHALL 输出各 change 的投影状态（state / milestones / source_event_seq），唯一/默认格式为 JSON
- **AND** 事件文件不一致时 SHALL 提示 stale
- **AND** 投影缺失/损坏/stale 时 SHALL 先用事件 replay 自动重建，重建成功即输出；仅事件不完整导致重建失败时 SHALL 报「事件不完整，检查 seq N」

#### Scenario: flow block / flow advance

- **WHEN** 运行 `flow block --change <id> --awaiting <type>`
- **THEN** 系统 SHALL 追加 `blocked_entered` 事件并进入对应 `blocked.awaiting_*` 态
- **WHEN** 运行 `flow advance --change <id> --to <sub_state>`
- **THEN** 系统 SHALL 追加 `transition_applied` 事件推进 sub_state

#### Scenario: 受保护路径只准 CLI 写

- **WHEN** agent 直接 Write/Edit `workflow-state.json` 或 `workflow-events.jsonl`
- **THEN** guard SHALL 拦截（exit 2）
- **AND** `flow` / `policy-*` CLI 作为合法写通道 SHALL 被 guard 豁免

### Requirement: 开发流程精简为 OpenSpec 主干 + 强制审阅闭环

开发流程 SHALL 精简为「OpenSpec 主干」（proposal → batch-grill-me → worktree → TDD → spec sync → PR）加「实现完成后强制独立 subagent 审阅闭环」。原四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）SHALL 停用，不再作为开发流程的强制要求。审阅证据 SHALL 存放于 `openspec/changes/<id>/reviews/`（随 change 进 PR，CI 可机械校验），非 docs + 有 spec delta + tasks 全部勾选的 change SHALL 有 building-review.md + manifest 且 verdict 为 PASS。

#### Scenario: 实现完成的新 change 提交 PR

- **GIVEN** 一个非 docs change 已实现且 tasks.md 全部勾选
- **WHEN** 提交 PR 前运行 artifact checker
- **THEN** 检查器 SHALL 验证 `openspec/changes/<id>/reviews/building-review.md` 存在
- **AND** 对应 manifest 存在且 verdict 为 PASS
- **AND** 缺审阅证据 SHALL 报错并阻止合入

#### Scenario: 部分实现的 change 不受拦截

- **GIVEN** 一个 change 处于提案或部分实现阶段（tasks.md 有未勾选项）
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 不要求审阅证据（避免误伤在途 change）

#### Scenario: 状态机仪式停用

- **GIVEN** 开发流程精简已生效
- **WHEN** agent 开始新 change 开发
- **THEN** 无需 phase/sub_state 推进、handoff.json 或 gate 停止
- **AND** 开发流程遵循 OpenSpec 主干 + 实现完成后 `/review-loop` 审阅闭环

### Requirement: 开发流程策略单一源

受保护路径治理规则 SHALL 收敛到单一策略文件 `scripts/flow-policy.json`，作为 guard（PreToolUse hook）与 CI artifact checker 的共同规则来源。该文件 SHALL 以 JSON 承载受保护路径规则表，每条规则 SHALL 声明 `match_type(exact|prefix|contains)`、`governance(guard_only|event_explained|manifest_verified|cli_written)` 与可空 `event_types`。系统 SHALL 禁止 agent 直接改写该策略文件（governance=cli_written），仅允许人类直改或 `policy-*` CLI 子命令更新。

#### Scenario: guard 与 checker 同源加载受保护路径规则

- **WHEN** guard 或 checker 需要判断某路径是否受保护
- **THEN** 系统 SHALL 从 `scripts/flow-policy.json` 读取规则表，而不再使用各自硬编码的独立清单
- **AND** guard 与 checker 对同一路径 SHALL 得出一致的受保护判定

#### Scenario: 策略文件缺失或损坏时 guard fail-closed

- **GIVEN** `scripts/flow-policy.json` 缺失、损坏或非法
- **WHEN** guard 拦截代码写操作
- **THEN** guard SHALL fail-closed（exit 2），不得静默放行
- **AND** guard SHALL 在错误信息中指明策略文件问题与恢复方向

#### Scenario: 策略文件规则与 guard 内嵌默认表保持一致

- **WHEN** 运行 parity 测试
- **THEN** 磁盘上的 `flow-policy.json` 规则表 SHALL 与 guard 源码内嵌的默认规则表一致
- **AND** checker 的受保护路径规则集 SHALL 是策略表 `event_explained` 子集

### Requirement: guard 写操作门禁顺序与路径归一化

guard 对 Bash 命令 SHALL 在 is_write 判定之前先扫描受保护路径；对 Write/Edit 的 `file_path` SHALL 先做路径归一化（normpath / 剥离 `./`、解析 `..`）再匹配。已知绕过形态（`echo > file`、`cat <<EOF`、`pathlib.write_text`、`docs/./` 变体）SHALL 被拦截。`workflow_state.py (artifact-event|review-manifest|policy-*|flow (status|confirm|approve|block|advance))` 作为合法写通道 SHALL 被豁免，但豁免 SHALL 仅限独立调用（无 `&&`/`;`/`|` 链式、无重定向、无命令替换、无换行）。

#### Scenario: Bash 命令绕过受保护路径被拦截

- **GIVEN** Bash 命令尝试改写受保护 artifact 但未命中既有写模式（如 `cat <<EOF`、`python3 -c "Path(...).write_text(...)"`）
- **WHEN** 命令具有写意图且包含受保护路径
- **THEN** guard SHALL 拦截（exit 2），不受 is_write 判定前置影响

#### Scenario: 归一化变体写入受保护路径被拦截

- **GIVEN** Write/Edit 或 Bash 使用 `docs/./known-debt.md` 等归一化变体路径
- **WHEN** 目标指向受保护 artifact
- **THEN** guard SHALL 在路径归一化后拦截（exit 2）

#### Scenario: 特权 CLI 链式调用不被豁免

- **GIVEN** Bash 命令以 `workflow_state.py` 合法子命令开头但通过 `&&`、`;`、`|` 或换行链式拼接写命令
- **WHEN** 该命令尝试改写受保护 artifact
- **THEN** guard SHALL 拒绝豁免并拦截（exit 2）

### Requirement: 内容门槛阶段感知

CI artifact checker 对 `Reference Implementation Research` 字段的检查 SHALL 区分结构门槛与内容门槛：change 处于 proposal 阶段时 SHALL 只要求 section 存在且非空；tasks 全部勾选（实现完成）时 SHALL 额外检查「自认未完成」短语级模式，命中 SHALL 报错（exit 2）并指明命中短语与字段。

#### Scenario: 实现完成的 change 含自认未完成占位

- **GIVEN** 一个 change 的 tasks 全部勾选
- **WHEN** 其 Reference Implementation Research 字段包含「尚未完成」「待补充」等自认未完成短语
- **THEN** checker SHALL exit 2
- **AND** 错误信息 SHALL 指明命中短语与所在字段

#### Scenario: proposal 阶段含占位不触发内容门槛

- **GIVEN** 一个 change 处于 proposal 阶段（tasks 未全勾）
- **WHEN** 其 Reference Implementation Research 字段含占位文本
- **THEN** checker SHALL 只按结构门槛检查（section 存在 + 非空），不触发内容门槛报错

### Requirement: 阶段执行者 agent schema 定义

`scripts/flow-policy.json` SHALL 支持可选的 `phases.<phase>.agent = {provider, model}` 与顶层 `review.agent` 声明，用于表达每阶段与审阅节点的执行者选择。本 requirement 只定义 schema 并做结构校验，不实现按阶段 spawn 执行者（后续阶段实现）。

#### Scenario: 合法 agent schema 通过校验

- **GIVEN** `flow-policy.json` 声明 `phases.building.agent` 或 `review.agent`，字段为合法 provider/model 字符串
- **WHEN** 运行 artifact checker
- **THEN** checker SHALL 通过 schema 校验

#### Scenario: 非法 agent schema 被拒绝

- **GIVEN** `flow-policy.json` 声明未知 phase 键、非字符串 provider/model 或额外未知字段
- **WHEN** 运行 artifact checker
- **THEN** checker SHALL 报错并指明非法字段
