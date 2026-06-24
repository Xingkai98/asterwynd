## ADDED Requirements

### Requirement: plan mode 产出 Plan Document 和结构化 planning state

plan mode SHALL 支持产出人读 Markdown Plan Document，并使用 PlanningManager 保存其中可跟踪的高层步骤。Plan Document 可以是讨论中的草案，也可以是定稿版本；定稿 Plan Document SHALL 包含目标理解、实施步骤、风险和建议验证方式。Planning State SHALL 作为机器可读索引，不得被视为执行期 todo list。

#### Scenario: 计划产物可读取

- **GIVEN** plan mode 已生成草案或定稿 Plan Document
- **WHEN** 调用方读取计划产物
- **THEN** 系统 SHALL 返回最近一次 Plan Document
- **AND** 调用方读取 planning state 时 SHALL 返回本轮生成的计划步骤和状态

#### Scenario: 更新 Plan Document 草案

- **GIVEN** 模型正在和用户讨论计划
- **WHEN** 模型调用 `UpdatePlan`
- **THEN** 系统 SHALL 记录草案 Plan Document
- **AND** SHALL 将 `steps` 写入 PlanningManager
- **AND** SHALL 发布 `plan_document_updated` 和 `planning_state_updated` 事件

#### Scenario: 定稿 Plan Document

- **GIVEN** 模型和用户已经收敛计划
- **WHEN** 模型调用 `ExitPlanMode`
- **THEN** 系统 SHALL 记录最终 Plan Document
- **AND** SHALL 将 `steps` 写入 PlanningManager
- **AND** SHALL 发布 `plan_document_submitted` 和 `planning_state_updated` 事件
