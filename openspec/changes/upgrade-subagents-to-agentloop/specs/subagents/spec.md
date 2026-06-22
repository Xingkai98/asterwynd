## MODIFIED Requirements

### Requirement: 当前子 agent 不继承完整 AgentLoop

在本 change 实现前，当前子 agent SHALL 被视为轻量 LLM 委托。实现后，系统 SHALL 支持受限 AgentLoop 子 agent，但仍需明确其工具权限、消息历史和取消边界。

#### Scenario: 文档描述 subagent 能力

- **GIVEN** 当前实现只直接调用 llm.chat
- **WHEN** 编写能力说明
- **THEN** 文档 SHALL 避免声称子 agent 已具备完整工具循环

## ADDED Requirements

### Requirement: 支持受限 AgentLoop 子 agent

SubAgentManager SHALL 能为子任务创建受限 AgentLoop。子 AgentLoop SHALL 拥有独立消息历史、工具集合、mode 和 trace。

#### Scenario: 委托受限 AgentLoop 子任务

- **GIVEN** 调用方提供 task、tools、model、llm 和 mode
- **WHEN** 调用 `delegate`
- **THEN** 系统 SHALL 创建后台子 AgentLoop
- **AND** 返回 subagent id

### Requirement: 子 agent trace 独立记录

子 agent SHALL 记录独立 trace，并在完成时通过 ParentChannel 回传摘要和 artifact 引用。

#### Scenario: 子 agent 完成

- **GIVEN** 子 AgentLoop 完成运行
- **WHEN** manager 写入结果
- **THEN** ParentChannel SHALL 保存子任务结果、状态和 trace 摘要
