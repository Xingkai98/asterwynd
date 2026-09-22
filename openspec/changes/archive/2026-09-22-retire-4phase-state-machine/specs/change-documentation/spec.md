## REMOVED Requirements

### Requirement: Handoff notes directory

**Reason**: agent-to-agent handoff note 机制随四阶段状态机退役——其唯一实现 `agent/workflow/handoff_note.py`（含 `FALLBACK_HANDOFF_PROMPT` 与 `.handoff/<change-id>/` 目录约定）实测全仓 0 处 import，属四阶段子系统。本 change 删除该模块后，`.handoff/` 目录不再有任何生产者（原写入者 `check_phase_done.py` / `doc_artifact_protocol*` 亦已删除），requirement 已无对象。

**Migration**: 跨 session / 跨 agent 的上下文交接改由 change 自身的 OpenSpec 文档（proposal / design / tasks）与 `reviews/` 审阅记录承载——这些随 change 进 PR、CI 可机械校验，优于本地不提交的 `.handoff/`。`.gitignore` 中的 `.handoff/` 条目保留（防止本地残留被误提交），但不再有生成流程。

## MODIFIED Requirements

### Requirement: Handoff state file artifact

老世代 OpenSpec change（事件日志首事件为 `initialized`）的 `handoff.json` SHALL 作为**只读历史投影**保留：它记录该 change 生命周期在退役前的 state 与 transition 历史。当代 change（事件日志首事件为 `change_created`，或异构派生且无 `handoff.json`）SHALL NOT 被要求包含 `handoff.json`：其开发流程状态由 `workflow-events.jsonl` replay 生成的 `workflow-state.json` 投影承载（见 `dev-workflow-state-machine` 规格）。

自本 change 起，四阶段状态机实现已退役，**不再有任何流程产出新的老世代 change**（原生产者 `cmd_spawn` 已删除）：`handoff.json` 的**创建与推进通道不复存在**，既存归档目录中的 `handoff.json` 仅作历史保留，不再被更新。当代 change 的投影刷新 SHALL NOT 产出 `handoff.json`。停用的四阶段状态机不再作为开发流程的强制要求。

#### Scenario: 当代 change 不要求 handoff.json

- **WHEN** a 当代 change（首事件 `change_created`，无 `handoff.json`）is created or 推进到归档
- **THEN** 系统 SHALL NOT 要求该 change 存在 `handoff.json`
- **AND** 其状态 SHALL 由 `workflow-state.json` 投影承载
- **AND** 受保护 artifact 写入（`artifact-event` / `review-manifest`）SHALL 对该 change 可用，SHALL NOT 因缺少 `handoff.json` 而被拒绝
- **AND** 对其运行 `flow status` SHALL NOT 产出 `handoff.json`

#### Scenario: 老世代 handoff.json 作为只读历史保留

- **GIVEN** 一个既存的老世代 change（事件日志首事件为 `initialized`，含 `handoff.json`）
- **WHEN** 运行 `flow status` 或校验投影
- **THEN** 系统 SHALL 沿用既有 handoff.json projection 路径读取它，不抛错
- **AND** 系统 SHALL NOT 把它改写成当代投影，也 SHALL NOT 为其产出 `workflow-state.json` 于 active 路径之外
- **AND** 系统 SHALL NOT 要求为它补建 `proposal.md`

#### Scenario: 没有流程再产出老世代 change

- **WHEN** 一个新 change 被创建
- **THEN** 其事件日志首事件 SHALL 为 `change_created`（当代）
- **AND** 系统 SHALL NOT 为其生成 `handoff.json`
- **AND** 唯一可能产出 `handoff.json` 的旧命令（`spawn`）SHALL 已不存在
