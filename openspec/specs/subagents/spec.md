# subagents 规格

## Purpose

定义子 agent 委托、后台任务、ParentChannel、结果回传和取消。当前实现位于 `agent/subagent/`。

## Requirements

### Requirement: 支持委托后台子 agent

SubAgentManager SHALL 为每次委托生成 subagent id，创建 ParentChannel，并启动后台 asyncio task。

#### Scenario: 委托任务

- **GIVEN** 调用方提供 task、tools、model 和 llm
- **WHEN** 调用 `delegate`
- **THEN** 系统 SHALL 返回 subagent id
- **AND** 在内部记录后台 task 和 channel

### Requirement: 子 agent 结果通过 ParentChannel 回传

ParentChannel SHALL 使用 asyncio queue 保存 SubAgentResult。

#### Scenario: 子 agent 完成

- **GIVEN** 子 agent 获得 LLM 响应或错误
- **WHEN** manager 写入结果
- **THEN** ParentChannel SHALL 保存 task、tool_call_id、result 和 subagent_id

### Requirement: 支持查询和取消子 agent

SubAgentManager SHALL 支持列出运行中 subagent、获取 channel 和取消后台任务。

#### Scenario: 取消存在的 subagent

- **GIVEN** subagent id 对应运行中的 task
- **WHEN** 调用 `cancel(subagent_id)`
- **THEN** 系统 SHALL 取消 task
- **AND** 返回成功状态

### Requirement: 当前子 agent 不继承完整 AgentLoop

当前子 agent 实现 SHALL 被视为轻量 LLM 委托，不得描述为完整独立 Coding AgentLoop，除非后续 change 明确扩展。

#### Scenario: 文档描述 subagent 能力

- **GIVEN** 当前实现只直接调用 llm.chat
- **WHEN** 编写能力说明
- **THEN** 文档 SHALL 避免声称子 agent 已具备完整工具循环

