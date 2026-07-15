# dev-workflow-state-machine 规格

## Purpose

定义开发流程状态机，包括 change 生命周期 phase/sub_state 模型、`handoff.json` 全局状态文件 schema、合法流转规则、human review gate 和回退机制。

## Requirements

### Requirement: 事件驱动 Workflow 状态

每个受管理开发事项 SHALL 在独立 Workflow Control Plane 中具有 workflow id、append-only event history 和派生 snapshot。Agent SHALL NOT 直接编辑当前 state 或 transition history。`handoff.json` MAY 作为迁移期兼容导出，但 SHALL NOT 与 event store 同时作为实时 source of truth。

#### Scenario: 创建需求事项

- **WHEN** 探索性对话被提升为正式 requirements workflow
- **THEN** 控制面 SHALL 创建 `workflow_started` 事件
- **AND** 初始受管理状态 SHALL 为 `requirements.defining_goal` 或模板定义的 requirements 起始状态

#### Scenario: Agent 报告当前工作

- **WHEN** agent 完成当前 WorkItem
- **THEN** agent SHALL 提交 WorkResult 和证据
- **AND** Orchestrator SHALL 验证并追加合法事件
- **AND** agent SHALL NOT 直接修改 snapshot 或兼容 `handoff.json`

#### Scenario: 导出兼容 handoff.json

- **WHEN** 迁移期工具需要读取 `handoff.json`
- **THEN** 系统 MAY 从 workflow events 生成只读兼容文件
- **AND** 对该文件的直接编辑 SHALL NOT 改变控制面状态

### Requirement: 端到端开发生命周期

开发 workflow SHALL 建模为 `exploring`、`requirements`、`design`、`building`、`code-review`、`closing`、`blocked` 和 `done`。`requirements`、`design`、`building`、`code-review` 和 `closing` 的末端 SHALL 设置 `ready_for_review` gate。

#### Scenario: 正常生命周期

- **GIVEN** 一个事项从 exploring 开始
- **WHEN** 需求、设计、实现、代码审查和 closing 依次完成并通过 gate
- **THEN** workflow SHALL 到达 done

#### Scenario: 跳过阶段

- **GIVEN** 项目模板允许跳过特定 phase
- **WHEN** 人在当前 gate 提交显式 skip decision 和 reason
- **THEN** Orchestrator MAY 进入模板声明的合法目标 phase
- **AND** SHALL 记录可信 approval 和 skip reason
- **AND** agent 自行请求 skip SHALL 被拒绝

### Requirement: Phase 内部 sub_state 定义

每个 phase SHALL 由版本化项目模板定义明确 sub-state 图，而不是由 agent 自由填写字符串。Asterwynd 默认模板 SHALL 至少包含：requirements 的目标、范围、验收和测试策略收敛；design 的参考调研、方案、设计追问和任务拆解；building 的测试先行、实现和验证；code-review 的 diff/测试/实现审查；closing 的 spec、归档、backlog、CI 和 PR 收尾。

每个 phase MAY 配置 executor lane，包括 `self`、runner、subagent、command 或 ask 模式。每个可审阅 phase MAY 在 human gate 前配置 canonical `review_lane.reviewers[]`，包括 reviewer adapter、fresh context policy、输入 artifact/evidence、通过策略和失败回退 sub-state。Runner 的具体 command、args、prompt_mode、permissions 和 timeout_seconds SHALL 由 `runner_profiles` 定义；review runner 默认 SHALL 为 read-only 且 `approval_policy: never`。Review lane SHALL NOT 允许 `self` reviewer；agent reviewer SHALL 使用 fresh context。Automated review SHALL 由 Orchestrator 派发 WorkItem，并 SHALL NOT 替代 human gate approval。会修改 Git 工作区的 phase 默认 SHALL 配置 commit_policy，要求进入 human gate 前有 clean worktree 和绑定 HEAD commit。

#### Scenario: 非法 Sub-state

- **WHEN** report 或导入历史引用模板中不存在的 sub-state
- **THEN** 系统 SHALL 拒绝该事件

#### Scenario: 模板允许循环

- **GIVEN** 模板声明 design review 可回到 design revision
- **WHEN** 人拒绝 design gate 并提供修改意见
- **THEN** Orchestrator SHALL 回到模板指定的 design sub-state
- **AND** SHALL 创建新状态版本

### Requirement: Human review gate

每个配置为人工审阅的 gate SHALL 在到达后停止 agent 自动推进并撤销可写 lease。只有持有 approval capability 的可信用户客户端 SHALL 能提交批准、拒绝、回退或允许的 skip decision。

#### Scenario: 到达 Gate 自动停止

- **WHEN** Orchestrator 接受完成 phase 最后一个执行 sub-state 的 report
- **AND** 配置的 automated review lane 已通过或未配置
- **AND** 配置的 commit_policy 已满足或声明为 none
- **THEN** 状态 SHALL 进入 `ready_for_review`
- **AND** 后续 agent `enter` SHALL 返回 waiting_for_human
- **AND** workspace write SHALL 被拒绝

#### Scenario: Automated Review 阻止进入 Gate

- **GIVEN** 当前 phase 配置了 automated review lane
- **WHEN** reviewer 返回 `changes_requested`
- **THEN** 状态 SHALL 返回模板定义的修复 sub-state
- **AND** SHALL NOT 进入 `ready_for_review`
- **AND** SHALL 记录 reviewer findings 作为 evidence

#### Scenario: Agent 尝试批准

- **WHEN** agent 使用 report payload 或自由身份字符串声明 human approval
- **THEN** 系统 SHALL 拒绝该声明

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
- **THEN** `state` SHALL 包含 `phase`（枚举值: `planning` / `reviewing` / `building` / `code-review` / `closing` / `blocked` / `done`）
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
- **AND** `type` 枚举值为 `planner` / `reviewer` / `builder` / `code-reviewer` / `closer`

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

系统 SHALL 根据 workflow 绑定的模板版本验证每个 event 是否来自当前派生状态、是否满足合法邻接、actor capability、state version、lease、evidence 和 gate approval。CI SHALL 对完整 history 使用相同规则重放验证。

#### Scenario: 非相邻跳步

- **WHEN** 当前状态与请求结果之间不存在模板声明的边
- **THEN** Orchestrator SHALL 拒绝流转
- **AND** SHALL NOT 写入 accepted transition event

#### Scenario: History 前后不连续

- **WHEN** 某事件的 expected version 或 from state 与前一事件派生结果不一致
- **THEN** history validation SHALL 失败

#### Scenario: Blocked 恢复

- **GIVEN** workflow 因外部条件进入 blocked
- **WHEN** blocker 被可信 actor 标记解决
- **THEN** workflow SHALL 恢复到 blocker 记录的合法恢复点
- **AND** SHALL 创建新 version 而非改写旧事件

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

系统 SHALL 允许同一个 agent 连续完成全部五个 phase，不强制切换 agent。

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

系统 SHALL 允许项目模板和 per-workflow 配置选择 executor adapter 与 session mode。路由结果 SHALL 生成 WorkItem，而不是让 executor 自行决定 phase。非 inline executor 的启动、失败和结果 SHALL 通过统一 adapter contract 表达。

#### Scenario: 不同 Phase 使用不同 Executor

- **GIVEN** design 配置为 Codex，building 配置为 Asterwynd
- **WHEN** design gate 获得批准
- **THEN** 下一个 WorkItem SHALL 指定 Asterwynd executor adapter
- **AND** SHALL 继续使用同一 workflow state 和 worktree binding

#### Scenario: Executor 不可用

- **WHEN** 配置的 executor 无法启动
- **THEN** workflow SHALL 进入 blocked 或保持当前状态
- **AND** SHALL NOT 假定该 sub-state 已完成

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
