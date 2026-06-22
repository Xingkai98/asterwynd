## ADDED Requirements

### Requirement: LSP server 受 workspace safety 约束

LSP server 启动、文件打开、诊断读取和结果返回 SHALL 遵守 workspace policy、agent mode 和工具权限边界。

#### Scenario: 拒绝 workspace 外路径

- **GIVEN** agent 请求对 workspace 外文件执行 LSP 操作
- **WHEN** 系统校验 LSP 请求
- **THEN** 系统 SHALL 拒绝该请求
- **AND** SHALL NOT 向 LSP server 打开该文件

#### Scenario: 跳过 denied path

- **GIVEN** agent 请求对 `.env` 或其他 denied path 执行 LSP 操作
- **WHEN** 系统校验 LSP 请求
- **THEN** 系统 SHALL 拒绝该请求
- **AND** SHALL NOT 返回 denied path 内容

### Requirement: LSP server 配置显式可审计

系统 SHALL 通过显式配置启用 LSP server，并记录 server 状态、启动错误和请求超时。

#### Scenario: LSP server 启动失败

- **GIVEN** 配置的 LSP server 无法启动
- **WHEN** agent 请求 LSP 状态或操作
- **THEN** 系统 SHALL 返回可读状态或错误
- **AND** SHALL NOT 影响非 LSP 工具执行
