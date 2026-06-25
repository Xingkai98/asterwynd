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

### Requirement: LSP server 限写不限读

LSP server SHALL 禁止任何 write 操作（不实现 `workspace/applyEdit`、`codeAction` 等 write 类方法），但读取不限于 workspace 内，允许读 stdlib、依赖目录等 server 正常工作所需路径。

#### Scenario: write 类方法不实现

- **GIVEN** LSP server 协议层收到 `workspace/applyEdit` 或 `codeAction` 请求
- **WHEN** 系统处理请求
- **THEN** 系统 SHALL NOT 执行写操作
- **AND** SHALL 返回 method not supported 或忽略

### Requirement: project root 强制在 workspace 内

`root_markers` 发现 project root 时，若命中的 marker 在 workspace 外，系统 SHALL 回退到 workspace root 本身并 warn，不越界扫描 workspace 外兄弟目录。

#### Scenario: root_markers 命中 workspace 外

- **GIVEN** workspace 是 `/repo/subdir`，`root_markers` 是 `pyproject.toml`
- **WHEN** 系统向上找 root_markers 并在 `/repo/pyproject.toml` 命中
- **THEN** 系统 SHALL 回退到 workspace root `/repo/subdir`
- **AND** SHALL 记录 warn
- **AND** SHALL NOT 把 `/repo` 作为 LSP server root

### Requirement: LSP server 进程清理可审计

系统 SHALL 通过 `atexit` 注册和进程组 spawn 确保 LSP server 子进程随父进程退出。请求超时 SHALL 标记 server unhealthy，下次请求仍超时则 shutdown 重启。系统 SHALL 通过显式配置启用 LSP server，并记录 server 状态、启动错误和请求超时。

#### Scenario: LSP server 启动失败

- **GIVEN** 配置的 LSP server 无法启动
- **WHEN** agent 请求 LSP 状态或操作
- **THEN** 系统 SHALL 返回可读状态或错误
- **AND** SHALL NOT 影响非 LSP 工具执行
- **AND** SHALL NOT 留下僵尸进程

#### Scenario: 父进程退出时子进程清理

- **GIVEN** LSP server 子进程正在运行
- **WHEN** 父进程（agent）退出
- **THEN** 系统 SHALL 通过 atexit 和进程组机制终止子进程
- **AND** SHALL NOT 留下孤儿 server 进程
