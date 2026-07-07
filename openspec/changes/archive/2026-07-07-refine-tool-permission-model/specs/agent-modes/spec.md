## MODIFIED Requirements

### Requirement: Agent mode 约束工具权限

系统 SHALL 使用当前 Agent Mode 约束工具 schema 暴露和工具执行权限。Agent Mode SHALL 绑定 permission profile；profile SHALL 基于 tool capability、risk level 和显式 deny override 判定工具 `allow`、`deny` 或 `require_approval`。origin 初始 SHALL NOT 直接决定 allow/deny，只用于审计、展示、默认推导和配置定位。`bypass` 为内部保留 mode，默认 fail closed。

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

### Requirement: Plan mode 产出可审阅计划

系统 SHALL 将 `plan` mode 作为计划讨论模式。AgentLoop 以 `plan` mode 运行时 SHALL 使用 plan permission profile：允许只读调研能力、计划文档/规划状态相关 agent_state 工具、`UpdatePlan` 和 `ExitPlanMode`，默认拒绝 workspace 写入、命令执行和 high risk 工具。模型 MAY 通过 `UpdatePlan` 更新 Markdown Plan Document 草案，并 SHALL 在计划定稿时通过 `ExitPlanMode` 提交最终 Markdown Plan Document，同时将高层步骤同步为结构化 planning state。

#### Scenario: plan mode 默认保守运行

- **GIVEN** AgentLoop 以 `plan` mode 运行
- **WHEN** 系统暴露工具 schema
- **THEN** schema SHALL 只包含 plan profile 允许的工具、`UpdatePlan` 和 `ExitPlanMode`
- **AND** 系统 SHALL 拒绝 workspace 写入、命令执行和 high risk 工具调用

#### Scenario: plan mode 不等同 read_only mode

- **GIVEN** 一个工具具有 plan profile 明确允许的 agent_state capability
- **WHEN** AgentLoop 以 `plan` mode 运行
- **THEN** 系统 MAY 暴露该工具
- **AND** read_only mode MAY 继续拒绝该工具
