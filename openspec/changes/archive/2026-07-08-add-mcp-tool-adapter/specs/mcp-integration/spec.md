## MODIFIED Requirements

### Requirement: MCP 当前为预留能力域

系统 SHALL 在本 change 实现后支持配置 MCP server、发现 MCP tools/prompts/resources、通过 ToolRegistry 调用 MCP tools，并通过显式 MCP 命令读取 prompts/resources；在实现前不得声称已支持 MCP 集成。

#### Scenario: 当前运行 Asterwynd

- **GIVEN** 用户通过 CLI、Web 或 benchmark 运行当前系统
- **WHEN** 系统构造工具 registry
- **THEN** registry SHALL 只包含当前代码显式注册的本地工具
- **AND** 只有在本 change 实现后才 MAY 注册配置的 MCP tools 或读取 MCP prompts/resources

### Requirement: 配置并连接 MCP servers

系统 SHALL 支持从顶层 `mcp.servers` 配置一个或多个 MCP server。Server SHALL 声明 `type`，首版 SHALL 支持 `stdio` 和 `streamable_http`。系统 SHALL 在启动 discovery 时连接 enabled server，并记录每个 server 的 ready/failed 状态。

#### Scenario: stdio server discovery

- **GIVEN** 配置包含 `type: stdio`、`command`、可选 `args`、`cwd` 和 `env`
- **WHEN** 系统初始化 MCP adapter
- **THEN** 系统 SHALL 通过 stdio transport 启动 server 并执行 discovery

#### Scenario: Streamable HTTP server discovery

- **GIVEN** 配置包含 `type: streamable_http`、`url` 和可选 headers
- **WHEN** 系统初始化 MCP adapter
- **THEN** 系统 SHALL 通过 Streamable HTTP transport 连接 server 并执行 discovery

#### Scenario: Optional server startup failure

- **GIVEN** 配置的 MCP server 未设置 `required: true`
- **AND** 该 server 启动失败或 discovery 超时
- **WHEN** 系统初始化 MCP adapter
- **THEN** 系统 SHALL 记录该 server 的 failed 状态
- **AND** SHALL 跳过该 server 暴露的 tools/prompts/resources
- **AND** SHALL NOT 中止整个 agent 启动

#### Scenario: Required server startup failure

- **GIVEN** 配置的 MCP server 设置了 `required: true`
- **AND** 该 server 启动失败或 discovery 超时
- **WHEN** 系统初始化 MCP adapter
- **THEN** 系统 SHALL fail fast 并返回可读错误

## ADDED Requirements

### Requirement: 发现并注册 MCP tools

系统 SHALL 能从配置的 MCP server 发现 tools，并将其映射为 ToolRegistry 可暴露的 tool schema。模型可见工具名 SHALL 使用安全化后的 `mcp__<server>__<tool>`；adapter 内部 SHALL 保留原始 `(server, tool)` 用于 MCP `tools/call`。

#### Scenario: MCP server 暴露工具

- **GIVEN** 配置的 MCP server 返回工具列表
- **WHEN** 系统初始化 MCP adapter
- **THEN** ToolRegistry SHALL 注册对应 MCP-backed tools
- **AND** 工具 schema SHALL 使用模型可见名

#### Scenario: MCP tool 名称冲突

- **GIVEN** 多个 MCP tools 安全化后名称冲突
- **WHEN** 系统注册 MCP-backed tools
- **THEN** 系统 SHALL 追加稳定短 hash 或等价后缀避免覆盖

### Requirement: MCP tool 执行错误可恢复

MCP tool 执行失败、超时或 server 不可用时，系统 SHALL 返回可读错误字符串，不得破坏 tool-call 消息链。

#### Scenario: MCP tool 超时

- **GIVEN** MCP tool 调用超过超时限制
- **WHEN** adapter 捕获超时
- **THEN** 工具结果 SHALL 是可读错误文本

### Requirement: 发现并读取 MCP prompts

系统 SHALL 能从配置的 MCP server 发现 prompts，并按显式请求读取 prompt 内容。Prompt 读取结果 SHALL 保留 server、prompt 名和参数来源。

#### Scenario: MCP prompt 读取成功

- **GIVEN** 配置的 MCP server 暴露 prompt `review_pr`
- **WHEN** 用户或命令处理器请求读取该 prompt 并传入 JSON 参数
- **THEN** 系统 SHALL 调用 MCP `prompts/get`
- **AND** 返回可注入当前会话的 prompt 内容

#### Scenario: MCP prompt 读取失败

- **GIVEN** MCP prompt 读取失败、超时或 server 不可用
- **WHEN** adapter 捕获错误
- **THEN** 系统 SHALL 返回可读错误
- **AND** SHALL NOT 伪造 user/assistant 历史消息

### Requirement: 发现并读取 MCP resources

系统 SHALL 能从配置的 MCP server 发现 resources，并按 URI 显式读取 resource 内容。Resource 读取结果 SHALL 保留 server 和 URI 来源。

#### Scenario: MCP resource 读取成功

- **GIVEN** 配置的 MCP server 暴露 URI `docs://architecture/agent-loop`
- **WHEN** 用户或命令处理器请求读取该 resource
- **THEN** 系统 SHALL 调用 MCP `resources/read`
- **AND** 返回可注入当前会话的 resource 内容

#### Scenario: MCP resource 读取失败

- **GIVEN** MCP resource 读取失败、超时或 server 不可用
- **WHEN** adapter 捕获错误
- **THEN** 系统 SHALL 返回可读错误
- **AND** SHALL NOT 伪造 user/assistant 历史消息
