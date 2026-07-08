## ADDED Requirements

### Requirement: ToolRegistry 支持 MCP-backed tools

ToolRegistry SHALL 能注册由 MCP adapter 包装的工具，并按普通 Tool 一样暴露 schema、执行调用、执行 mode policy 判定和返回字符串结果。

#### Scenario: 执行 MCP-backed tool

- **GIVEN** registry 中存在 MCP-backed tool
- **WHEN** 调用 `execute(tool_call)`
- **THEN** registry SHALL 通过 MCP adapter 执行远端工具
- **AND** 返回字符串结果

#### Scenario: MCP-backed tool 需要审批

- **GIVEN** registry 中存在 high risk MCP-backed tool
- **AND** 当前 mode policy 要求审批
- **WHEN** 调用 `execute(tool_call)` 且未传入 approval
- **THEN** registry SHALL 返回 approval required 文本
- **AND** SHALL NOT 调用远端 MCP server
