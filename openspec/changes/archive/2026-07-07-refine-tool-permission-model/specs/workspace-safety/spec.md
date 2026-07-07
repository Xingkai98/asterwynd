## ADDED Requirements

### Requirement: WorkspacePolicy remains an execution boundary

工具 capability 和 mode profile SHALL 决定 tool 是否对 LLM 可见以及是否允许执行；WorkspacePolicy SHALL 继续作为路径、敏感文件、命令和 workspace 边界的执行前强制校验，不得被 capability metadata 绕过。

#### Scenario: capability 允许但 workspace policy 拒绝

- **GIVEN** 当前 mode profile 允许某个 workspace read tool
- **AND** 该 tool 请求读取 denied path
- **WHEN** WorkspacePolicy 校验该路径
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: capability 允许但命令 policy 拒绝

- **GIVEN** 当前 mode profile 允许某个命令执行工具
- **AND** 该 tool 请求执行命中 command denylist 的命令
- **WHEN** WorkspacePolicy 校验该命令
- **THEN** 系统 SHALL 拒绝该操作
