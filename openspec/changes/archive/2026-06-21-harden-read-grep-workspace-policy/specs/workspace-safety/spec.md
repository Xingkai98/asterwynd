## MODIFIED Requirements

### Requirement: WorkspacePolicy 路径必须限制在 workspace 内

WorkspacePolicy SHALL 解析路径并阻止越过 workspace root 的读写访问。读权限和写权限校验 SHALL 都执行 workspace root 边界检查。

#### Scenario: 读路径逃逸

- **GIVEN** 工具请求读取 workspace 外路径
- **WHEN** policy 校验读取权限
- **THEN** 系统 SHALL 拒绝访问
- **AND** 返回权限错误

#### Scenario: 写路径逃逸

- **GIVEN** 工具请求写入 workspace 外路径
- **WHEN** policy 校验写入权限
- **THEN** 系统 SHALL 拒绝访问
- **AND** 返回权限错误

### Requirement: 敏感文件写入默认拒绝

WorkspacePolicy SHALL 在面向 agent tool 的读写校验中拒绝匹配 denied patterns 的路径，例如本地环境变量、私密配置、版本控制内部目录、虚拟环境、依赖目录和生成目录。

#### Scenario: 写入 `.env`

- **GIVEN** 工具请求写入被 denied pattern 命中的路径
- **WHEN** policy 校验写入权限
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: 读取 `.env`

- **GIVEN** 工具请求读取被 denied pattern 命中的路径
- **WHEN** policy 校验读取权限
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: 普通 agent tool 不绕过 read policy

- **GIVEN** 普通 agent tool 请求读取 read policy 拒绝的路径
- **WHEN** policy 校验读取权限
- **THEN** 系统 SHALL 拒绝该操作
- **AND** SHALL NOT 为普通 agent tool 提供隐式绕过
