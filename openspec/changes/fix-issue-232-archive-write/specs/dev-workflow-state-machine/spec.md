## MODIFIED Requirements

### Requirement: 工作流事件日志与 handoff.json projection

每个 change 目录下 SHALL 存在一个 `workflow-events.jsonl` 文件，作为该 change 开发流程的权威事实来源。投影分为两代：老世代（归档 change）SHALL 由事件日志 replay 生成 `handoff.json` projection；当代（新 change）SHALL 由事件日志 replay 生成 `workflow-state.json` projection。Agent 不 SHALL 直接编辑投影文件来声明状态变化；所有状态变化 SHALL 通过 CLI 追加事件并重新生成投影。

受保护 artifact 的写入通道（`workflow_state.py` 的 `artifact-event` 与 `review-manifest`）SHALL 以 change 的合法性（change 目录存在且含 `proposal.md`）为前置，SHALL NOT 要求 `handoff.json` 存在——`handoff.json` 是停用的四阶段状态机产物，当代 change 不产生它。为兼容老世代目标（例如 `spawn` 生成的子 change，只有 `handoff.json` 而无 `proposal.md`），前置 SHALL 接受 `proposal.md` **或** `handoff.json` 任一存在。

目标解析 SHALL 与 `flow status` 的既有口径一致：**active 目录优先，已归档 change 回退到 `openspec/changes/archive/<date>-<id>/`**。对已归档目标，写入 SHALL 落在归档目录内（manifest 落在 `archive/<date>-<id>/reviews/`，事件追加到归档目录的 `workflow-events.jsonl`），SHALL NOT 在 active 路径新建目录。已归档 change 的投影为**只读历史**：对归档目标的写入 SHALL NOT 触发投影刷新，SHALL NOT 在归档目录中产出 `handoff.json` / `workflow-state.json` 等投影文件。对 active 目标，两条命令成功写入后 SHALL 重新生成投影，使写入结果可立即被校验。

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

#### Scenario: 新建 change 时初始化 workflow event log

- **WHEN** 创建新的 OpenSpec change
- **THEN** 系统 SHALL 自动生成 `workflow-events.jsonl`
- **AND** 当代 change 的初始状态 SHALL 为 `planning.exploring`
- **AND** 当代 change SHALL NOT 被要求生成 `handoff.json`（其状态由 `workflow-state.json` 投影承载）
- **AND** 老世代 change 的 `handoff.json` 生成行为 SHALL 与修复前保持一致

#### Scenario: agent 读取当前状态

- **WHEN** 任一角色 agent 开始处理 change
- **THEN** agent SHALL 首先读取该 change 的投影状态（老世代读 `handoff.json`，当代读 `workflow-state.json`）获取当前 state
- **AND** agent SHALL 根据 `state.phase` 和 `state.sub_state` 确定自己的工作起点

#### Scenario: WorkflowEngine 更新状态

- **WHEN** agent 完成一个 sub_state 内的任务并准备转移到下一个 sub_state 或 phase
- **THEN** agent SHALL 请求 WorkflowEngine/CLI 执行状态推进
- **AND** WorkflowEngine SHALL 追加一条 `workflow-events.jsonl` 事件
- **AND** WorkflowEngine SHALL 重新生成该 change 世代的投影（老世代 `handoff.json`，当代 `workflow-state.json`）
- **AND** 校验器 SHALL 验证磁盘投影与 `workflow-events.jsonl` replay 结果一致

#### Scenario: 投影被手动篡改

- **GIVEN** `workflow-events.jsonl` replay 的当前状态与磁盘投影不一致（老世代为 `handoff.json`，当代为 `workflow-state.json`）
- **WHEN** 运行 gate 或 CI 校验
- **THEN** 系统 SHALL 拒绝通过
- **AND** SHALL 报告该投影与事件日志不一致

#### Scenario: 非状态 artifact 事件

- **WHEN** `workflow-events.jsonl` 包含不改变 workflow state 的 artifact 事件
- **THEN** replay 投影时 SHALL 保留事件日志顺序校验
- **AND** SHALL 忽略这些事件对投影的影响
- **AND** 支持的 artifact event type SHALL 至少包含 `protected_artifact_explained`、`current_spec_synced`、`backlog_updated`、`change_archived`

#### Scenario: 受保护写通道不要求 handoff.json

- **WHEN** 对一个无 `handoff.json` 的当代 change 运行 `workflow_state.py artifact-event` 或 `workflow_state.py review-manifest`
- **THEN** 系统 SHALL 成功写入对应事件 / manifest（exit 0）
- **AND** SHALL NOT 因缺少 `handoff.json` 而拒绝
- **AND** 写入后该 change 的投影 SHALL 被重新生成，无需额外运行 `flow status` 即可通过投影一致性校验

#### Scenario: 受保护写通道拒绝非法目标

- **WHEN** 对一个不存在的 change、一个既无 `proposal.md` 也无 `handoff.json` 的目录，或一个路径型 `--change`（绝对路径或含 `/`，非单段 change id）运行 `artifact-event` 或 `review-manifest`
- **THEN** 系统 SHALL 以明确错误退出（exit 1）
- **AND** SHALL NOT 写入任何事件或 manifest
- **AND** SHALL NOT 抛出未捕获的 traceback，也 SHALL NOT 写入仓库外路径

#### Scenario: 老世代 change 的受保护写通道保持可用

- **WHEN** 对一个有 `handoff.json` 的老世代 change（含无 `proposal.md` 的 `spawn` 子 change）运行 `artifact-event` 或 `review-manifest`
- **THEN** 系统 SHALL 成功写入（exit 0）
- **AND** 行为 SHALL 与修复前保持一致

#### Scenario: 受保护写通道支持已归档 change

- **GIVEN** 一个已归档 change（存在于 `openspec/changes/archive/<date>-<id>/`，active 目录不存在）
- **WHEN** 以该 change id 运行 `workflow_state.py artifact-event` 或 `workflow_state.py review-manifest`
- **THEN** 系统 SHALL 成功写入（exit 0），SHALL NOT 报「change 不存在」
- **AND** review manifest SHALL 落在 `archive/<date>-<id>/reviews/`，事件 SHALL 追加到归档目录的 `workflow-events.jsonl`
- **AND** SHALL NOT 在 active 路径 `openspec/changes/<id>/` 新建任何目录或文件
- **AND** 归档目录 SHALL NOT 新增 `handoff.json` / `workflow-state.json` 等投影文件（归档投影为只读历史）
