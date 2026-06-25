## ADDED Requirements

### Requirement: MCP tools 必须声明现有权限元数据

MCP-backed tools SHALL 复用现有 Tool 权限元数据：`read_only`、`dangerous` 和可选 `allowed_modes`，并受 agent mode policy 约束。系统 SHALL NOT 在本 change 中新增独立 `read_write` 字段或三态权限 enum。

`dangerous` SHALL 表示高风险或副作用不可控，不表示工具来源。MCP-backed tool 默认 dangerous 是保守默认值，用户显式配置后 MAY 将已审阅的 read-only MCP tool 标记为 non-dangerous。

#### Scenario: MCP tool 被 mode 禁止

- **GIVEN** 当前 mode 不允许 dangerous tool
- **WHEN** MCP server 暴露 dangerous tool
- **THEN** 系统 SHALL 不向 LLM 暴露该工具
- **AND** 直接执行该工具 SHALL 返回权限错误

#### Scenario: MCP tool 配置为 read-only

- **GIVEN** MCP server 的某个 tool 在配置中覆盖为 `read_only: true` 且 `dangerous: false`
- **WHEN** 当前 mode 是 `read_only` 或 `plan`
- **THEN** 系统 MAY 向 LLM 暴露该 tool

#### Scenario: MCP 来源不等同 dangerous

- **GIVEN** MCP-backed tool 来源元数据为 `origin=mcp`
- **AND** 该 tool 被配置为 `read_only: true` 且 `dangerous: false`
- **WHEN** 当前 mode 允许 read-only non-dangerous tools
- **THEN** 系统 SHALL NOT 仅因为该 tool 来源于 MCP 而拒绝它
