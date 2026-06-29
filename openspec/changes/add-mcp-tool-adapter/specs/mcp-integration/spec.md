## MODIFIED Requirements

### Requirement: MCP 当前为预留能力域

系统 SHALL 在本 change 实现后支持配置 MCP server、发现 MCP tools 并通过 ToolRegistry 调用；在实现前不得声称已支持 MCP 集成。

#### Scenario: 当前运行 Asterwynd

- **GIVEN** 用户通过 CLI、Web 或 benchmark 运行当前系统
- **WHEN** 系统构造工具 registry
- **THEN** registry SHALL 只包含当前代码显式注册的本地工具
- **AND** 只有在本 change 实现后才 MAY 注册配置的 MCP tools

## ADDED Requirements

### Requirement: 发现并注册 MCP tools

系统 SHALL 能从配置的 MCP server 发现工具，并将其映射为 ToolRegistry 可暴露的 tool schema。

#### Scenario: MCP server 暴露工具

- **GIVEN** 配置的 MCP server 返回工具列表
- **WHEN** 系统初始化 MCP adapter
- **THEN** ToolRegistry SHALL 注册对应 MCP-backed tools

### Requirement: MCP tool 执行错误可恢复

MCP tool 执行失败、超时或 server 不可用时，系统 SHALL 返回可读错误字符串，不得破坏 tool-call 消息链。

#### Scenario: MCP tool 超时

- **GIVEN** MCP tool 调用超过超时限制
- **WHEN** adapter 捕获超时
- **THEN** 工具结果 SHALL 是可读错误文本
