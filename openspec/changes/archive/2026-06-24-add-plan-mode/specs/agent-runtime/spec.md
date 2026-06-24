## MODIFIED Requirements

### Requirement: AgentLoop 可发出 planning state 事件

AgentLoop SHALL 支持在计划创建或状态更新时发出 `planning_state_updated` 事件，并支持在 plan mode 更新或提交 Plan Document 时发出 `plan_document_updated` / `plan_document_submitted` 事件，同时保持原有 tool-call 协议不变量。`planning_state_updated` payload SHALL 包含完整 planning state snapshot，至少包含 `items` 列表和可选 `summary`。

#### Scenario: 计划状态更新

- **GIVEN** AgentLoop 运行中产生 planning state 更新
- **WHEN** 更新被应用
- **THEN** 系统 SHALL 通过事件或 hook 暴露更新后的 planning state
- **AND** SHALL NOT 插入破坏 provider tool-call 链的消息

#### Scenario: LLM 调用包含只读 planning context

- **GIVEN** AgentLoop 持有非空 planning state
- **WHEN** AgentLoop 调用 LLM
- **THEN** 系统 SHALL 将当前 planning state 作为临时只读上下文提供给 LLM
- **AND** SHALL NOT 将该上下文持久 append 到 messages

#### Scenario: Plan Document 更新或提交

- **GIVEN** AgentLoop 以 plan mode 运行
- **WHEN** 模型通过 `UpdatePlan` 更新草案或通过 `ExitPlanMode` 提交 Plan Document
- **THEN** 系统 SHALL 发出对应的 `plan_document_updated` 或 `plan_document_submitted` 事件
- **AND** SHALL 在 trace 中记录该 Plan Document
