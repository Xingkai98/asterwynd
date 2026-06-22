## ADDED Requirements

### Requirement: plan mode 使用结构化 planning state

plan mode SHALL 使用 PlanningManager 保存计划步骤，并在最终回复中总结计划、风险和建议验证方式。

#### Scenario: 计划产物可读取

- **GIVEN** plan mode 完成运行
- **WHEN** 调用方读取 planning state
- **THEN** 系统 SHALL 返回本轮生成的计划步骤和状态
