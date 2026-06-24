## MODIFIED Requirements

### Requirement: 工具权限元数据

工具 SHALL 能声明 `read_only`、`dangerous` 和可选 `allowed_modes` 元数据；registry SHALL 能暴露指定工具是否 dangerous。`allowed_modes` 用于 mode-specific 工具，例如只允许在 `plan` mode 暴露和执行的 `UpdatePlan` / `ExitPlanMode`。

#### Scenario: 检查 Bash 权限

- **GIVEN** BashTool 被注册
- **WHEN** 调用 `get_sandbox("Bash")`
- **THEN** 系统 SHALL 返回该工具的 dangerous 标记

#### Scenario: mode-specific 工具

- **GIVEN** 工具声明 `allowed_modes`
- **WHEN** 当前 mode 不在该列表中
- **THEN** 系统 SHALL 不暴露该工具 schema
- **AND** 执行该工具时 SHALL 返回权限拒绝结果
