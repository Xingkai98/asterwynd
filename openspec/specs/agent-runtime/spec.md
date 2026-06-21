# agent-runtime 规格

## Purpose

定义 MyAgent 的核心运行循环、消息状态、工具调用协议和停止条件。当前实现以 `agent/loop.py` 的 `AgentLoop` 为核心。

## Requirements

### Requirement: AgentLoop 执行消息循环

系统 SHALL 以消息列表作为主要运行状态，在每轮中调用 LLM、解析 assistant 响应、执行工具调用并把工具结果追加回消息历史。

#### Scenario: assistant 返回最终文本

- **GIVEN** 输入消息列表和可用 LLM
- **WHEN** LLM 返回不包含工具调用的 assistant 消息
- **THEN** AgentLoop SHALL 将最终 assistant 回复加入消息历史
- **AND** 返回包含最终内容的运行结果

#### Scenario: assistant 返回工具调用

- **GIVEN** LLM 返回包含一个或多个 tool call 的 assistant 消息
- **WHEN** AgentLoop 解析工具名和参数
- **THEN** 系统 SHALL 通过 ToolRegistry 执行对应工具
- **AND** 为每个 tool call 追加匹配的 tool result 消息
- **AND** 继续下一轮 LLM 调用

### Requirement: tool-call 消息链合法

系统 SHALL 保持 assistant tool call 与 tool result 的匹配关系，不得生成缺失、错配或伪造的工具结果链。

#### Scenario: 达到 max_iterations

- **GIVEN** AgentLoop 已达到最大迭代次数
- **WHEN** 最后一轮仍然产生工具调用或未形成最终 assistant 文本
- **THEN** 系统 SHALL 返回受控的终止结果
- **AND** SHALL NOT 把最后一个工具结果伪造成 assistant 最终回复

### Requirement: 生命周期扩展点

系统 SHALL 支持 HookManager 在 AgentLoop 运行过程中接入日志、trace、debug 和 token budget 等通过 Hook protocol 表达的横切能力。

#### Scenario: 配置 hooks

- **GIVEN** AgentLoop 构造时传入 HookManager
- **WHEN** AgentLoop 执行 LLM 调用和工具调用
- **THEN** hooks MAY 观察或影响对应生命周期事件
- **AND** 核心 tool-call 协议不变量 SHALL 保持有效

### Requirement: 运行轨迹记录

系统 SHALL 支持通过 TraceRecorder 记录 LLM 迭代、工具调用、工具结果、编辑、diff、测试和完成状态。

#### Scenario: benchmark 注入 trace_recorder

- **GIVEN** benchmark runner 为一次任务提供 TraceRecorder
- **WHEN** AgentLoop 执行任务
- **THEN** 系统 SHALL 记录可序列化 trace
- **AND** trace 可写入 benchmark artifact
