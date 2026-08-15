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

#### Scenario: guard 读投影执法

- **WHEN** guard 判断某 change 处于 awaiting 态且未确认
- **THEN** 写操作（Write/Edit 与 write-intent Bash）SHALL exit 2（awaiting 执法不弱化，不可经 Bash 绕过）
- **AND** guard SHALL 以事件日志 replay 结果判定 awaiting（事件是唯一真相）：投影缺失/损坏/stale 不影响判定——awaiting 仍 exit 2（不因投影问题放行）、非 awaiting 放行（不额外误拦）
- **AND** guard SHALL 只读，不写盘（hook 无副作用）
- **AND** 仅事件不完整（缺 seq / JSON 语法坏 / 末尾截断）导致无法 replay 时，guard SHALL fail-closed（exit 2，报「事件不完整，检查 seq N」）；`flow status` 同口径报错，不猜测不跳过

#### Scenario: checker 派生物一致性

- **WHEN** 项目 artifact checker 校验 tasks 全勾的 change
- **THEN** 它 SHALL 校验磁盘投影与从事件 replay 重建的投影一致（投影 == replay）
- **AND** 不一致时 SHALL 失败（exit 2），防止自锁

## ADDED Requirements

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
