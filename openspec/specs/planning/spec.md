# planning 规格

## Purpose

定义计划拆分、todo list、状态推进和多端展示语义。当前仓库已经具备 PlanningManager 和结构化 planning state 基础设施；真实 plan mode、持久化 todo 和跨端计划工作流仍由后续 change 定义。
## Requirements
### Requirement: planning state 当前提供运行期结构化状态

系统 SHALL 提供运行期结构化 planning state，但不得声称已经具备持久化 todo、真实 plan mode 或跨端计划工作流。

#### Scenario: 当前代码运行

- **GIVEN** 用户通过 CLI 或 Web 运行 AgentLoop
- **WHEN** agent 需要拆解任务
- **THEN** 系统 MAY 通过普通 assistant 文本表达计划
- **AND** MAY 通过 PlanningManager 暴露结构化 planning state
- **AND** SHALL NOT 声称该状态等同于真实 plan mode

### Requirement: 新增 planning 必须走变更流程

系统 SHALL 在新增 planning 行为前创建 OpenSpec change，明确计划数据模型、状态、展示入口和测试策略。

#### Scenario: 准备实现 todo list

- **GIVEN** 需求提出结构化 todo list
- **WHEN** 需求尚未确认
- **THEN** 不得修改业务实现
- **AND** SHALL 先在 `openspec/changes/` 中描述 delta spec

### Requirement: PlanningManager 维护结构化计划

PlanningManager SHALL 维护有序 plan items，每个 item 至少包含 id、content、status 和可选 note。status SHALL 支持 pending、in_progress、completed、failed 和 skipped。

#### Scenario: 创建计划

- **GIVEN** agent 生成一组计划步骤
- **WHEN** PlanningManager 接收这些步骤
- **THEN** 系统 SHALL 保存有序 plan items
- **AND** 每个 item SHALL 有稳定 id 和初始状态
- **AND** item id SHALL 由 PlanningManager 在当前生命周期内单调生成且不复用

#### Scenario: 更新计划状态

- **GIVEN** 某个 plan item 已存在
- **WHEN** agent 或运行时更新该 item 状态
- **THEN** PlanningManager SHALL 保存新状态
- **AND** 生成可观察的 planning state 事件
- **AND** 同一时刻 SHALL 至多存在一个 in_progress item

#### Scenario: 读取计划摘要

- **GIVEN** PlanningManager 已保存计划状态
- **WHEN** 调用方读取 summary
- **THEN** 系统 SHALL 返回总步骤数和各状态计数
- **AND** SHALL 返回当前 in_progress 步骤信息（如果存在）

#### Scenario: 替换计划

- **GIVEN** PlanningManager 已存在计划
- **WHEN** 调用方设置新的计划
- **THEN** 系统 SHALL 用新 plan items 替换当前计划
- **AND** SHALL 为新 plan items 分配未复用的稳定 id

### Requirement: planning state 不替代自然语言回复

结构化 planning state SHALL 作为机器可读运行状态存在，不得要求 LLM 最终回复只输出 JSON 或放弃自然语言总结。

#### Scenario: 最终回复包含计划结果

- **GIVEN** AgentLoop 已完成任务
- **WHEN** 系统返回最终 assistant 回复
- **THEN** 最终回复 MAY 总结计划执行结果
- **AND** planning state SHALL 仍作为独立状态可读取
