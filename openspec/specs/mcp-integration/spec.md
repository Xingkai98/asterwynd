# mcp-integration 规格

## Purpose

定义 MCP server/tool 发现、注册、隔离和权限的未来能力边界。当前仓库尚未实现 MCP 集成。

## Requirements

### Requirement: MCP 当前为预留能力域

系统 SHALL NOT 声称已经支持 MCP server 连接、MCP tool discovery、MCP tool 注册或 MCP 权限隔离。

#### Scenario: 当前运行 MyAgent

- **GIVEN** 用户通过 CLI、Web 或 benchmark 运行当前系统
- **WHEN** 系统构造工具 registry
- **THEN** registry SHALL 只包含当前代码显式注册的本地工具
- **AND** 不会自动发现 MCP server

### Requirement: 新增 MCP 必须定义协议边界

新增 MCP 能力前 SHALL 通过 OpenSpec change 明确 server 配置、tool schema 映射、权限模型、错误处理和测试策略。

#### Scenario: 准备接入 MCP 工具

- **GIVEN** 需求提出接入 MCP
- **WHEN** 尚未完成需求规格
- **THEN** 不得直接修改 ToolRegistry 或 AgentLoop 实现

