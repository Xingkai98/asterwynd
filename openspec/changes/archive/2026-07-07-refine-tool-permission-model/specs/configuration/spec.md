## ADDED Requirements

### Requirement: Permission profile configuration SHALL support bounded customization

系统 SHALL 支持在统一配置中为既有 Agent Mode 选择内置 permission profile，或定义自定义 permission profile。自定义 profile SHALL 只扩展权限判定参数，不得新增 Agent Mode 或改变 AgentLoop mode 语义。系统 SHALL fail fast 校验未知 capability、risk level、permission profile、tool name 和互相矛盾的 profile 配置。

#### Scenario: 使用内置 permission profile

- **GIVEN** 配置为某个 mode 选择内置 permission profile
- **WHEN** 系统构造 ModePolicy
- **THEN** ModePolicy SHALL 使用该 profile 判定工具权限

#### Scenario: 未知 permission profile

- **GIVEN** 配置引用未知 permission profile
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL fail fast 并返回可读配置错误

#### Scenario: 自定义 permission profile

- **GIVEN** 配置定义一个 permission profile
- **AND** 该 profile 声明 allowed capabilities、auto-approve risk threshold、approval-required risk threshold 和 denied tools
- **WHEN** 系统构造 ModePolicy
- **THEN** ModePolicy SHALL 使用该自定义 profile 判定工具权限

#### Scenario: 自定义 Agent Mode 不在本 change 范围

- **GIVEN** 配置尝试新增未知 Agent Mode
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL fail fast
- **AND** 错误信息 SHALL 说明本 change 只支持自定义 permission profile，不支持自定义 Agent Mode
