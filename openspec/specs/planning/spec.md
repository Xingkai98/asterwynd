# planning 规格

## Purpose

定义计划拆分、todo list、状态推进和多端展示语义。当前仓库尚未实现独立 planning 子系统，本能力域用于约束未来需求。

## Requirements

### Requirement: planning 当前为预留能力域

系统 SHALL NOT 声称已经具备持久化 todo、计划状态机或跨 CLI/Web/TUI 的统一计划展示能力。

#### Scenario: 当前代码运行

- **GIVEN** 用户通过 CLI 或 Web 运行 AgentLoop
- **WHEN** agent 需要拆解任务
- **THEN** 当前系统 MAY 通过普通 assistant 文本表达计划
- **AND** SHALL NOT 提供结构化 planning API 或持久化计划状态

### Requirement: 新增 planning 必须走变更流程

系统 SHALL 在新增 planning 行为前创建 OpenSpec change，明确计划数据模型、状态、展示入口和测试策略。

#### Scenario: 准备实现 todo list

- **GIVEN** 需求提出结构化 todo list
- **WHEN** 需求尚未确认
- **THEN** 不得修改业务实现
- **AND** SHALL 先在 `openspec/changes/` 中描述 delta spec

