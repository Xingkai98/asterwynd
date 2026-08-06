## MODIFIED Requirements

### Requirement: Agent mode 约束工具权限

系统 SHALL 使用当前 Agent Mode 约束工具 schema 暴露和工具执行权限。Agent Mode SHALL 绑定 permission profile；profile SHALL 基于 tool capability、risk level 和显式 deny override 判定工具 `allow`、`deny` 或 `require_approval`。origin 初始 SHALL NOT 直接决定 allow/deny，只用于审计、展示、默认推导和配置定位。默认 profile 映射为：`build` 使用 `build_default`，`read_only` 使用 `read_only_default`，`plan` 使用 `plan_default`，`bypass` 使用 `bypass_default`。`bypass` 为自动放行模式：所有风险等级工具默认 `allow`，不产生审批请求；显式 deny override 仍然生效。

#### Scenario: read_only mode 过滤工具 schema

- **GIVEN** ToolRegistry 注册了读写或 high risk 工具
- **WHEN** 系统以 `read_only` mode 获取工具 schema
- **THEN** 不符合 read-only profile 的工具 SHALL 不出现在 schema 中

#### Scenario: 被 mode 禁止的工具执行

- **GIVEN** 工具调用命中当前 mode profile 禁止的工具
- **WHEN** ToolRegistry 执行该调用
- **THEN** 系统 SHALL 返回可读权限错误作为 tool result

#### Scenario: mode profile 要求审批

- **GIVEN** 一个工具被当前 mode profile 判定为 `require_approval`
- **WHEN** 模型请求执行该工具
- **THEN** AgentLoop SHALL 在实际执行前请求用户审批
- **AND** ToolRegistry SHALL NOT 绕过该审批直接执行工具

#### Scenario: bypass mode 自动放行所有风险工具

- **GIVEN** AgentLoop 以 `bypass` mode 运行
- **WHEN** 模型请求执行任意已注册且未被显式 deny 且未被 `allowed_modes` 排除的工具
- **THEN** 系统 SHALL 判定该工具为 `allow`
- **AND** AgentLoop SHALL 自动执行该工具
- **AND** 系统 SHALL NOT 请求用户审批

### Requirement: session mode 支持运行时切换

系统 SHALL 支持在同一个交互式 session 内切换当前 Agent Mode。mode transition 完成后 SHALL 更新该 session 的当前 mode，并影响同一 session 后续 run 的工具 schema 暴露和工具执行权限。

#### Scenario: session 切换到 read_only

- **GIVEN** CLI 交互、Web 或未来 TUI session 当前 mode 为 `build`
- **WHEN** 用户将该 session 切换到 `read_only`
- **THEN** 该 session 后续 run SHALL 使用 `read_only` mode
- **AND** 工具 schema SHALL 不再暴露当前 mode 禁止的工具

#### Scenario: session 切换到 plan

- **GIVEN** session 当前 mode 为 `build`
- **WHEN** 用户将该 session 切换到 `plan`
- **THEN** 后续 run SHALL 使用 plan mode 工具策略
- **AND** SHALL 暴露 `UpdatePlan` 和 `ExitPlanMode`

#### Scenario: session 切换到 bypass

- **GIVEN** 用户处于交互式 session
- **WHEN** 用户请求将 mode 切换到 `bypass`
- **THEN** 系统 SHALL 将 session 切换到 `bypass`
- **AND** 后续 run SHALL 使用 bypass mode 工具策略
- **AND** 工具调用 SHALL 自动执行且不经过审批

## ADDED Requirements

### Requirement: Bypass mode 自动执行工具不审批

系统 SHALL 将 `bypass` mode 作为自动放行模式。AgentLoop 以 `bypass` mode 运行时 SHALL 使用 bypass permission profile：允许全部 capability，`auto_approve_max_risk` 覆盖 HIGH。已注册且未被显式 deny 的工具 SHALL 判定为 `allow` 并自动执行，不产生 `require_approval`。显式 `deny_tools` 配置和工具 `allowed_modes` 约束 SHALL 仍然生效。

#### Scenario: bypass 自动执行高危工具

- **GIVEN** 一个 HIGH 风险工具已注册且未被显式 deny
- **WHEN** AgentLoop 以 `bypass` mode 请求执行该工具
- **THEN** 系统 SHALL 判定为 `allow`
- **AND** AgentLoop SHALL 自动执行，不经过审批

#### Scenario: bypass 仍尊重显式 deny

- **GIVEN** 配置为 `bypass` mode deny 某个已注册工具
- **WHEN** AgentLoop 以 `bypass` mode 请求执行该工具
- **THEN** 系统 SHALL 判定为 `deny`
- **AND** 该工具 SHALL NOT 被执行

#### Scenario: bypass 作为用户可选 mode

- **GIVEN** 用户通过 CLI `--mode bypass`、交互 `/mode bypass`、Web mode 切换或 `default_mode: bypass` 配置请求 bypass
- **WHEN** 请求合法
- **THEN** 系统 SHALL 接受该 mode
- **AND** 后续 run SHALL 使用 bypass mode 工具策略
