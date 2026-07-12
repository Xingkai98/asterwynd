## ADDED Requirements

### Requirement: CLI 使用统一 system prompt

CLI SHALL 通过统一 prompt builder 构造默认 system prompt，不得维护独立漂移的硬编码 prompt。

#### Scenario: CLI 启动 AgentLoop

- **GIVEN** 用户通过 CLI 启动任务
- **WHEN** CLI 创建 AgentLoop
- **THEN** CLI SHALL 使用统一 prompt builder 的输出作为默认 system prompt
