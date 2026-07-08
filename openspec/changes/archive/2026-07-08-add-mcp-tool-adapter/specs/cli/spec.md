## ADDED Requirements

### Requirement: CLI interactive exposes MCP slash commands

CLI 交互模式 SHALL 通过 central slash command registry 暴露 `/mcp`、`/mcp-prompt` 和 `/mcp-resource`。这些命令 SHALL 保留来源 metadata，不得伪造 user/assistant 历史消息。

#### Scenario: List MCP status

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/mcp`
- **THEN** CLI SHALL 输出 MCP server ready/failed 状态
- **AND** SHOULD 输出每个 server 的 tools/prompts/resources 数量

#### Scenario: MCP prompt command injects context

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/mcp-prompt docs review_pr {"repo":"asterwynd"}`
- **THEN** CLI SHALL 按 mode policy 请求或校验权限
- **AND** 读取 MCP prompt
- **AND** 将带来源标记的 system context 注入当前会话
- **AND** SHALL NOT 将原始 slash command 作为普通用户消息发送给 AgentLoop

#### Scenario: MCP resource command injects context

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户输入 `/mcp-resource docs docs://architecture/agent-loop`
- **THEN** CLI SHALL 按 mode policy 请求或校验权限
- **AND** 读取 MCP resource
- **AND** 将带来源标记的 system context 注入当前会话
- **AND** SHALL NOT 将原始 slash command 作为普通用户消息发送给 AgentLoop
