## ADDED Requirements

### Requirement: MCP tools 必须声明权限边界

MCP-backed tools SHALL 声明 read_only、read_write 或 dangerous 等权限元数据，并受 agent mode policy 约束。

#### Scenario: MCP tool 被 mode 禁止

- **GIVEN** 当前 mode 不允许 dangerous tool
- **WHEN** MCP server 暴露 dangerous tool
- **THEN** 系统 SHALL 不向 LLM 暴露该工具
- **AND** 直接执行该工具 SHALL 返回权限错误
