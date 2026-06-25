## ADDED Requirements

### Requirement: Permission profile configuration SHALL be conservative

系统 MAY 支持在统一配置中选择或扩展 mode permission profile，但初始实现 SHALL 优先提供内置 profiles 和 deny override。完整自定义 capability/risk matrix 如果开放，必须 fail fast 校验未知 capability、risk level、origin 和 tool name。

#### Scenario: 使用内置 permission profile

- **GIVEN** 配置为某个 mode 选择内置 permission profile
- **WHEN** 系统构造 ModePolicy
- **THEN** ModePolicy SHALL 使用该 profile 判定工具权限

#### Scenario: 未知 permission profile

- **GIVEN** 配置引用未知 permission profile
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL fail fast 并返回可读配置错误
