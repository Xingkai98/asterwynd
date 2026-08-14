# dev-workflow-state-machine 规格 delta

## MODIFIED Requirements

### Modified: 工作流事件日志与 handoff.json projection

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

#### Scenario: 非状态 artifact 事件

- **WHEN** `workflow-events.jsonl` 包含不改变 workflow state 的 artifact 事件
- **THEN** replay projection 时 SHALL 保留事件日志顺序校验
- **AND** SHALL 忽略这些事件对 projection 的影响
- **AND** 支持的 artifact event type SHALL 至少包含 `protected_artifact_explained`、`current_spec_synced`、`backlog_updated`、`change_archived`

### Modified: 阻塞状态

系统 SHALL 支持任意 phase 进入 awaiting 态，用于等待外部依赖或决策。等待合法化不弱化执法：awaiting 期间写操作 SHALL 仍被 guard 拦截（exit 2），用户确认后才放行。awaiting 态集合 SHALL 包含 `awaiting_human_review` 与 `awaiting_user_confirmation`；`awaiting_proposal_confirmation` 保留槽位但暂不派生；`review_blocked` 不 SHALL 计入 awaiting 集。

#### Scenario: 进入等待态

- **WHEN** agent 完成某阶段并进入需要外部输入的状态
- **THEN** 完成命令 SHALL 追加 `blocked_entered` 事件（复用 v1 blocked 事件类型，不新增类型）
- **AND** 投影状态 SHALL 变为对应的 awaiting 态
- **AND** `blocked_entered` SHALL 只由进入 awaiting 的完成命令写入（写路径唯一化）

#### Scenario: 解除等待态

- **WHEN** 用户确认或批准解除等待
- **THEN** `flow confirm` / `flow approve` SHALL 追加 `blocked_resolved` 事件（复用 v1 blocked 事件类型）
- **AND** `blocked_resolved` SHALL 只由 `flow confirm` / `flow approve` 写入（写路径唯一化）
- **AND** 状态 SHALL 恢复到进入 awaiting 之前的阶段

#### Scenario: guard 读投影执法

- **WHEN** guard 判断某 change 处于 awaiting 态且未确认
- **THEN** 写操作 SHALL exit 2（awaiting 执法不弱化）
- **AND** 投影缺失、损坏或 `source_event_seq` 与事件文件不一致（stale）时，guard SHALL 回退现有正则兜底（fail-closed，不因投影问题放行）

#### Scenario: checker 派生物一致性

- **WHEN** 项目 artifact checker 校验 tasks 全勾的 change
- **THEN** 它 SHALL 校验磁盘投影与从事件 replay 重建的投影一致（投影 == replay）
- **AND** 不一致时 SHALL 失败（exit 2），防止自锁

## ADDED Requirements

### Requirement: flow 命令与受保护路径

系统 SHALL 提供 `flow status` / `flow confirm` / `flow approve` 命令，作为投影查询与等待态确认的 CLI 通道；`workflow-state.json` 与 `workflow-events.jsonl` SHALL 纳入受保护路径（governance=cli_written），只允许 CLI 写入。

#### Scenario: flow status 展示投影

- **WHEN** 运行 `flow status [--change <id>|--all]`
- **THEN** 系统 SHALL 输出各 change 的投影状态（state / milestones / source_event_seq）
- **AND** 事件文件不一致时 SHALL 提示 stale

#### Scenario: 受保护路径只准 CLI 写

- **WHEN** agent 直接 Write/Edit `workflow-state.json` 或 `workflow-events.jsonl`
- **THEN** guard SHALL 拦截（exit 2）
- **AND** `flow` / `policy-*` CLI 作为合法写通道 SHALL 被 guard 豁免
