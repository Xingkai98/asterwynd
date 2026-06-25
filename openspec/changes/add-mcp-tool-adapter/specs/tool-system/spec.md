## ADDED Requirements

### Requirement: ToolRegistry 支持 MCP-backed tools

ToolRegistry SHALL 能注册由 MCP adapter 包装的工具，并按普通 Tool 一样暴露 schema、执行调用和返回字符串结果。

#### Scenario: 执行 MCP-backed tool

- **GIVEN** registry 中存在 MCP-backed tool
- **WHEN** 调用 `execute(tool_call)`
- **THEN** registry SHALL 通过 MCP adapter 执行远端工具
- **AND** 返回字符串结果

#### Scenario: 暴露 MCP-backed tool schema

- **GIVEN** MCP adapter 已将 MCP tool 包装为本地 Tool
- **WHEN** ToolRegistry 暴露 schema
- **THEN** schema 的 function name SHALL 是 provider-safe 注册名
- **AND** schema 的 parameters SHALL 来自 MCP tool 的 `inputSchema`

### Requirement: MCP-backed tools 携带来源元数据

MCP-backed Tool SHALL 携带来源元数据，例如 `origin=mcp` 和配置的 server name。来源元数据 SHALL 用于 trace、audit、display、默认权限推导和排查；当前 ModePolicy SHALL NOT 直接用来源元数据替代 `read_only` / `dangerous` 判权。

#### Scenario: 记录 MCP-backed tool 来源

- **GIVEN** MCP adapter 注册了一个 MCP-backed tool
- **WHEN** 系统记录或展示该 tool 的元数据
- **THEN** 元数据 SHALL 能区分该 tool 来源于 MCP server
- **AND** SHALL 保留配置的 server name
