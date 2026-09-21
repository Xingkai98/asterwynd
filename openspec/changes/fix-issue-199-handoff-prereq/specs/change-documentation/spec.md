## MODIFIED Requirements

### Requirement: Handoff state file artifact

老世代 OpenSpec change（事件日志首事件为 `initialized`）SHALL 包含 `handoff.json` 记录状态机 state 与 transition history。当代 change（事件日志首事件为 `change_created`，或异构派生且无 `handoff.json`）SHALL NOT 被要求包含 `handoff.json`：其开发流程状态由 `workflow-events.jsonl` replay 生成的 `workflow-state.json` 投影承载（见 `dev-workflow-state-machine` 规格）。停用的四阶段状态机不再作为开发流程的强制要求。

#### Scenario: handoff.json 随老世代 change 创建

- **WHEN** 一个老世代 change（首事件 `initialized`）被创建
- **THEN** `handoff.json` SHALL 随该 change 初始化
- **AND** 初始 state SHALL 为 `planning.exploring`

#### Scenario: handoff.json 随状态变化更新

- **WHEN** agent 完成一个 sub-state 或 phase transition（老世代流程）
- **THEN** `handoff.json` 的 state 与 transitions SHALL 相应更新

#### Scenario: handoff.json 随 change 提交

- **WHEN** 老世代 change 准备进入 PR
- **THEN** `handoff.json` SHALL 反映该 change 的最终 state
- **AND** SHALL 作为 change 目录的一部分提交

#### Scenario: 当代 change 不要求 handoff.json

- **WHEN** 一个当代 change（首事件 `change_created`，无 `handoff.json`）被创建或推进到归档
- **THEN** 系统 SHALL NOT 要求该 change 存在 `handoff.json`
- **AND** 其状态 SHALL 由 `workflow-state.json` 投影承载
- **AND** 受保护 artifact 写入（`artifact-event` / `review-manifest`）SHALL 对该 change 可用，SHALL NOT 因缺少 `handoff.json` 而被拒绝
