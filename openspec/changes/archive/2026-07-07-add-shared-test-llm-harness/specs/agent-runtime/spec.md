## ADDED Requirements

### Requirement: Agent runtime 入口回归使用共享测试 LLM harness

项目 SHALL 提供共享测试 LLM harness，用于在测试中以确定性 fake LLM 或显式 opt-in real LLM 驱动真实 AgentLoop 和入口层 smoke。默认 fake LLM SHALL 兼容现有 `LLM` protocol，并支持普通文本、streaming、tool call、错误路径和调用记录。

#### Scenario: Fake LLM 驱动真实 AgentLoop

- **GIVEN** 测试使用共享 fake LLM harness
- **WHEN** 入口 smoke 构造 AgentLoop
- **THEN** 系统 SHALL 使用真实 AgentLoop、ToolRegistry、Memory 和 runtime event 路径
- **AND** SHALL 只替换 LLM provider 行为

#### Scenario: Harness 记录 LLM 调用

- **GIVEN** AgentLoop 通过共享 fake LLM harness 执行一次 run
- **WHEN** 测试检查 harness 状态
- **THEN** harness SHALL 暴露调用次数、messages、tools 和 model 等断言信息

#### Scenario: Real LLM smoke 显式开启

- **GIVEN** 测试 harness 支持真实 provider profile
- **WHEN** 未显式传入 real API flag 或对应环境变量
- **THEN** 默认回归 SHALL 使用 fake LLM
- **AND** SHALL NOT 要求真实 API key、外部网络或真实模型输出
