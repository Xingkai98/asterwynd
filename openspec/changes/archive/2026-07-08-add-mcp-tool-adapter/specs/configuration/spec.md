## ADDED Requirements

### Requirement: 配置支持 MCP servers

系统 SHALL 支持在 `asterwynd.yaml` 顶层 `mcp.servers` 下声明 MCP server。MCP 配置 SHALL 与 `tools` 配置分离。非法 transport、缺失必需字段、非法 timeout、非法权限 capability 或 risk level SHALL fail fast 并返回可读配置错误。

#### Scenario: 配置 stdio MCP server

- **GIVEN** `asterwynd.yaml` 声明 `mcp.servers.local_math.type: stdio`
- **AND** 声明 `command`、可选 `args`、`cwd` 和 `env`
- **WHEN** 系统加载配置
- **THEN** 配置对象 SHALL 包含该 stdio server
- **AND** 相对 `cwd` SHALL 以配置文件所在目录为基准解析

#### Scenario: 配置 Streamable HTTP MCP server

- **GIVEN** `asterwynd.yaml` 声明 `mcp.servers.docs.type: streamable_http`
- **AND** 声明 `url` 和可选 headers
- **WHEN** 系统加载配置
- **THEN** 配置对象 SHALL 包含该 Streamable HTTP server

#### Scenario: 配置 MCP action 权限

- **GIVEN** `asterwynd.yaml` 为 MCP server 或单个 tool/prompt/resource 声明 capability 和 risk level
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 校验这些权限字段
- **AND** 在构造 MCP action 权限时使用本地配置覆盖默认保守权限

#### Scenario: MCP 配置不在 tools 下

- **GIVEN** `asterwynd.yaml` 将 MCP server 配置写入 `tools.mcp`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL fail fast
- **AND** 错误信息 SHALL 指向顶层 `mcp.servers`
