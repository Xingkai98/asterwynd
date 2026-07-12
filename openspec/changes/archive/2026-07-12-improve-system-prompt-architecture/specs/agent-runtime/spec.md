## ADDED Requirements

### Requirement: 统一 system prompt 构造

系统 SHALL 使用统一 prompt builder 构造 coding-agent system prompt，并在 AgentLoop 中作为最高优先级上下文使用。

#### Scenario: AgentLoop 创建默认运行

- **GIVEN** 用户未提供自定义 system prompt
- **WHEN** AgentLoop 初始化运行消息
- **THEN** 系统 SHALL 使用统一 prompt builder 生成 system prompt

### Requirement: System prompt 表达 coding-agent 行为边界

system prompt SHALL 明确定义 coding-agent 身份、工具调用协议、工作区安全、编辑约束和验证责任。

#### Scenario: 检查默认 system prompt

- **GIVEN** 系统生成默认 system prompt
- **WHEN** 测试读取 prompt 段落
- **THEN** prompt SHALL 包含工具调用、代码编辑和验证责任相关约束
