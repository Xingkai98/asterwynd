## ADDED Requirements

### Requirement: Tool permissions SHALL separate capability, risk, and origin

工具权限模型 SHALL 区分工具能力、风险等级和来源元数据。工具能力描述 tool 能做什么，风险等级描述默认安全风险，来源元数据描述 tool 从哪里来；三者 SHALL NOT 互相替代。

#### Scenario: 外部来源不直接等同高风险

- **GIVEN** 一个 tool 的 origin 是 `mcp`
- **AND** 该 tool 被明确标注为 low risk read-only capability
- **WHEN** ModePolicy 判定该 tool 是否允许
- **THEN** 系统 SHALL NOT 仅因为 origin 是 `mcp` 而拒绝该 tool

#### Scenario: 高风险不直接等同外部来源

- **GIVEN** 一个内置 tool 具有 high risk capability
- **WHEN** ModePolicy 判定该 tool 是否允许
- **THEN** 系统 SHALL 按 risk/capability 处理该 tool
- **AND** SHALL NOT 因其 origin 是 `builtin` 而自动放行

### Requirement: Tool legacy permission metadata SHALL remain compatible during migration

系统 SHALL 在迁移期保留现有 `read_only`、`dangerous` 和 `allowed_modes` 行为，并能从旧字段推导新权限元数据，直到内置工具完成显式标注。

#### Scenario: legacy read-only tool

- **GIVEN** 一个旧工具只声明 `read_only=True` 且 `dangerous=False`
- **WHEN** 系统读取该工具权限元数据
- **THEN** 系统 SHALL 将其视为 low risk read capability 的兼容工具

#### Scenario: legacy dangerous tool

- **GIVEN** 一个旧工具声明 `dangerous=True`
- **WHEN** 系统读取该工具权限元数据
- **THEN** 系统 SHALL 将其视为 high risk 工具
