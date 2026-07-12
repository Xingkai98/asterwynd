## ADDED Requirements

### Requirement: Web session 使用统一 system prompt

Web session SHALL 通过统一 prompt builder 构造默认 system prompt，与 CLI 保持同一基础行为边界。

#### Scenario: Web 创建新会话

- **GIVEN** 用户在 Web UI 创建新会话
- **WHEN** server 初始化 session runtime
- **THEN** Web session SHALL 使用统一 prompt builder 的输出作为默认 system prompt
