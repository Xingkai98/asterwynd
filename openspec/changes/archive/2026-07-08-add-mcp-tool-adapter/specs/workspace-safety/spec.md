## ADDED Requirements

### Requirement: MCP actions 必须声明权限边界

MCP-backed tools、prompt 读取和 resource 读取 SHALL 声明 capability / risk / origin 权限元数据，并受 agent mode policy 约束。未显式配置的 MCP action SHALL 默认为 `origin=mcp`、`capabilities=[external_side_effect]`、`risk_level=high`；MCP server 自身 annotation SHALL NOT 作为最终权限判定依据。

#### Scenario: MCP tool 被 mode 禁止

- **GIVEN** 当前 mode 不允许 MCP action 所需 capability
- **WHEN** MCP server 暴露该 tool
- **THEN** 系统 SHALL 不向 LLM 暴露该工具
- **AND** 直接执行该工具 SHALL 返回权限错误

#### Scenario: MCP prompt/resource 读取需要审批

- **GIVEN** 当前 mode 对某个 MCP prompt/resource 读取要求审批
- **WHEN** 用户通过 slash command 读取该 prompt/resource 且未批准
- **THEN** 系统 SHALL 返回 approval required 文本
- **AND** SHALL NOT 调用远端 MCP server

#### Scenario: 本地配置降低 MCP 读取权限

- **GIVEN** 本地配置将某个 MCP server 的 resource 读取声明为 `network_read` + `low`
- **WHEN** 当前 mode 允许该 capability 和 risk
- **THEN** 系统 SHALL 允许读取该 resource
