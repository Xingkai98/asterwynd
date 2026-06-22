## ADDED Requirements

### Requirement: ToolRegistry 支持 MCP-backed tools

ToolRegistry SHALL 能注册由 MCP adapter 包装的工具，并按普通 Tool 一样暴露 schema、执行调用和返回字符串结果。

#### Scenario: 执行 MCP-backed tool

- **GIVEN** registry 中存在 MCP-backed tool
- **WHEN** 调用 `execute(tool_call)`
- **THEN** registry SHALL 通过 MCP adapter 执行远端工具
- **AND** 返回字符串结果
