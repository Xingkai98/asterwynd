## RENAMED Requirements

- FROM: `### Requirement: 全局状态文件 handoff.json`
- TO: `### Requirement: 事件驱动 Workflow 状态`
- FROM: `### Requirement: 五阶段生命周期`
- TO: `### Requirement: 端到端开发生命周期`

## MODIFIED Requirements

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

每个 phase MAY 配置 executor lane，包括 `self`、runner、subagent、command 或 ask 模式。每个可审阅 phase MAY 在 human gate 前配置 canonical `review_lane.reviewers[]`，包括 reviewer adapter、fresh context policy、输入 artifact/evidence、通过策略和失败回退 sub-state。Runner 的具体 command、args、prompt_mode、permissions 和 timeout_seconds SHALL 由 `runner_profiles` 定义；review runner 默认 SHALL 为 read-only 且 `approval_policy: never`。Review lane SHALL NOT 允许 `self` reviewer；agent reviewer SHALL 使用 fresh context。Automated review SHALL 由 Orchestrator 派发 WorkItem，并 SHALL NOT 替代 human gate approval。

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
