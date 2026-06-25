## ADDED Requirements

### Requirement: 支持 MCP server 配置

系统 SHALL 支持在 `myagent.yaml` 的 `tools.mcp` 下配置 MCP server 列表、默认超时和权限默认值。配置解析 SHALL fail fast 处理非法 transport、非法 server name、缺失 command/url、非法超时和非法权限覆盖。

#### Scenario: 配置 stdio MCP server

- **GIVEN** `myagent.yaml` 配置了 `tools.mcp.servers[].transport: stdio`
- **AND** 该 server 提供 `command`
- **WHEN** 系统加载配置
- **THEN** 配置对象 SHALL 保留该 server 的 command、args、env、timeout 和权限默认值
- **AND** command SHALL 支持 string 或 list 形式

#### Scenario: 配置 Streamable HTTP MCP server

- **GIVEN** `myagent.yaml` 配置了 `tools.mcp.servers[].transport: streamable_http`
- **AND** 该 server 提供 `url`
- **WHEN** 系统加载配置
- **THEN** 配置对象 SHALL 保留该 server 的 url、headers、timeout 和权限默认值

#### Scenario: 拒绝 legacy HTTP+SSE transport

- **GIVEN** `myagent.yaml` 配置了 `tools.mcp.servers[].transport: sse` 或模糊的 `http`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 返回可读配置错误

#### Scenario: MCP headers/env 展开环境变量

- **GIVEN** `tools.mcp.servers[].headers` 或 stdio `env` 中包含 `${ENV_VAR}`
- **WHEN** 系统加载 MCP 配置
- **THEN** 系统 SHALL 使用进程环境变量替换该占位符
- **AND** 如果引用的环境变量不存在，系统 SHALL fail fast 并返回可读配置错误
