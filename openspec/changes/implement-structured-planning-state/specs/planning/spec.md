## MODIFIED Requirements

### Requirement: planning 当前为预留能力域

系统 SHALL 在本 change 实现后提供结构化 planning state；在实现前不得声称已具备持久化 todo 或跨端展示能力。

#### Scenario: 当前代码运行

- **GIVEN** 用户通过 CLI 或 Web 运行 AgentLoop
- **WHEN** agent 需要拆解任务
- **THEN** 系统 MAY 通过普通 assistant 文本表达计划
- **AND** 只有在本 change 实现后才 SHALL 提供结构化 planning API

## ADDED Requirements

### Requirement: PlanningManager 维护结构化计划

PlanningManager SHALL 维护有序 plan items，每个 item 至少包含 id、content、status 和可选 note。status SHALL 支持 pending、in_progress、completed、failed 和 skipped。

#### Scenario: 创建计划

- **GIVEN** agent 生成一组计划步骤
- **WHEN** PlanningManager 接收这些步骤
- **THEN** 系统 SHALL 保存有序 plan items
- **AND** 每个 item SHALL 有稳定 id 和初始状态

#### Scenario: 更新计划状态

- **GIVEN** 某个 plan item 已存在
- **WHEN** agent 或运行时更新该 item 状态
- **THEN** PlanningManager SHALL 保存新状态
- **AND** 生成可观察的 planning state 事件

### Requirement: planning state 不替代自然语言回复

结构化 planning state SHALL 作为机器可读运行状态存在，不得要求 LLM 最终回复只输出 JSON 或放弃自然语言总结。

#### Scenario: 最终回复包含计划结果

- **GIVEN** AgentLoop 已完成任务
- **WHEN** 系统返回最终 assistant 回复
- **THEN** 最终回复 MAY 总结计划执行结果
- **AND** planning state SHALL 仍作为独立状态可读取
