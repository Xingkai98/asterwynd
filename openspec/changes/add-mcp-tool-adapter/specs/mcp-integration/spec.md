## MODIFIED Requirements

### Requirement: MCP 当前为预留能力域

系统 SHALL 在本 change 实现后支持配置 MCP server、发现 MCP tools 并通过 ToolRegistry 调用；在实现前不得声称已支持 MCP 集成。

#### Scenario: 当前运行 MyAgent

- **GIVEN** 用户通过 CLI、Web 或 benchmark 运行当前系统
- **WHEN** 系统构造工具 registry
- **THEN** registry SHALL 只包含当前代码显式注册的本地工具
- **AND** 只有在本 change 实现后才 MAY 注册配置的 MCP tools

## ADDED Requirements

### Requirement: 发现并注册 MCP tools

系统 SHALL 能从配置的 MCP server 发现工具，并将其映射为 ToolRegistry 可暴露的 tool schema。

#### Scenario: MCP server 暴露工具

- **GIVEN** 配置的 MCP server 返回工具列表
- **WHEN** AgentLoop run 开始且首次 LLM 调用尚未发生
- **THEN** ToolRegistry SHALL 注册对应 MCP-backed tools
- **AND** 首次 LLM 调用 SHALL 能看到当前 mode 允许的 MCP-backed tool schema

### Requirement: MCP transport 首版范围明确

系统 SHALL 支持 stdio 和 Streamable HTTP MCP transport；首版 SHALL NOT 支持 legacy HTTP+SSE transport。

#### Scenario: 连接 stdio server

- **GIVEN** 配置的 MCP server 使用 `stdio` transport
- **WHEN** MCP adapter 初始化该 server
- **THEN** adapter SHALL 使用 SDK stdio client 完成 initialize 和 tools/list

#### Scenario: 连接 Streamable HTTP server

- **GIVEN** 配置的 MCP server 使用 `streamable_http` transport
- **WHEN** MCP adapter 初始化该 server
- **THEN** adapter SHALL 使用 SDK Streamable HTTP client 完成 initialize 和 tools/list

### Requirement: MCP tool 名称必须 provider-safe

系统 SHALL 将 MCP 原始 tool name 映射为 provider-safe 的 ToolRegistry 名称，并保留原始名称用于实际 MCP 调用。

#### Scenario: MCP tool name 包含非法字符

- **GIVEN** MCP server 暴露名称包含空格或非 provider-safe 字符的 tool
- **WHEN** adapter 注册该 tool
- **THEN** ToolRegistry 中的名称 SHALL 使用清洗后的 `{server_name}__{tool_name}` 格式
- **AND** adapter 调用 MCP server 时 SHALL 使用原始 tool name

### Requirement: MCP tool 执行错误可恢复

MCP tool 执行失败、超时或 server 不可用时，系统 SHALL 返回可读错误字符串，不得破坏 tool-call 消息链。

#### Scenario: MCP tool 超时

- **GIVEN** MCP tool 调用超过超时限制
- **WHEN** adapter 捕获超时
- **THEN** 工具结果 SHALL 是可读错误文本

### Requirement: MCP tool result 转换为字符串

系统 SHALL 将 MCP `tools/call` 返回的 content blocks 转换为本地 Tool 协议需要的字符串结果。

#### Scenario: MCP tool 返回多个 text content blocks

- **GIVEN** MCP tool 返回多个 text content block
- **WHEN** MCP-backed Tool 返回结果
- **THEN** 结果 SHALL 是按顺序拼接后的字符串

#### Scenario: MCP tool 返回 isError

- **GIVEN** MCP tool call result 标记 `isError=true`
- **WHEN** MCP-backed Tool 返回结果
- **THEN** 结果 SHALL 是以 `[MCP error:` 开头的可读错误文本
