## MODIFIED Requirements

### Requirement: Handoff state file artifact

老世代 OpenSpec change（事件日志首事件为 `initialized`）SHALL include a `handoff.json`
artifact that records the current state machine state and transition history of the change
lifecycle。当代 change（事件日志首事件为 `change_created`，或异构派生且无 `handoff.json`）
SHALL NOT 被要求包含 `handoff.json`：其开发流程状态由 `workflow-events.jsonl` replay
生成的 `workflow-state.json` 投影承载（见 `dev-workflow-state-machine` 规格）。停用的
四阶段状态机不再作为开发流程的强制要求。

#### Scenario: handoff.json is created with the change

- **WHEN** a new 老世代 OpenSpec change（首事件 `initialized`）is created
- **THEN** `handoff.json` is initialized alongside the change
- **AND** the initial state is `planning.exploring`

#### Scenario: handoff.json is updated on state change

- **WHEN** any agent completes a sub-state or phase transition（老世代流程）
- **THEN** `handoff.json` state and transitions are updated accordingly

#### Scenario: handoff.json is submitted with the change

- **WHEN** a 老世代 change is ready for PR
- **THEN** `handoff.json` reflects the final state of the change
- **AND** it is committed as part of the change directory

#### Scenario: 当代 change 不要求 handoff.json

- **WHEN** a 当代 change（首事件 `change_created`，无 `handoff.json`）is created or 推进到归档
- **THEN** 系统 SHALL NOT 要求该 change 存在 `handoff.json`
- **AND** 其状态 SHALL 由 `workflow-state.json` 投影承载
- **AND** 受保护 artifact 写入（`artifact-event` / `review-manifest`）SHALL 对该 change 可用，SHALL NOT 因缺少 `handoff.json` 而被拒绝
