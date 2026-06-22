## ADDED Requirements

### Requirement: CLI 支持选择 agent mode

CLI SHALL 支持为 AgentLoop 选择 `build`、`read_only` 或 `plan` agent mode，并在运行输出或日志中记录实际 mode。CLI SHALL 接受 `read_only` 和 `read-only` 两种用户输入，并在内部规范化为 `read_only`。未指定 mode 时 SHALL 默认使用 `build`。CLI SHALL NOT 接受 `bypass` 作为用户可选 mode。

#### Scenario: CLI 传入 mode

- **GIVEN** 用户执行 CLI 并指定 mode
- **WHEN** CLI 构造 AgentLoop
- **THEN** 系统 SHALL 使用对应 mode 配置工具集合
- **AND** 输出或日志 SHALL 记录实际 mode

#### Scenario: CLI 规范化 read-only

- **GIVEN** 用户执行 CLI 并指定 `read-only`
- **WHEN** CLI 解析 mode
- **THEN** 系统 SHALL 将其规范化为 `read_only`
- **AND** 使用 `read_only` mode 构造 AgentLoop

#### Scenario: CLI 默认 build mode

- **GIVEN** 用户执行 CLI 且未指定 mode
- **WHEN** CLI 构造 AgentLoop
- **THEN** 系统 SHALL 使用 `build` mode

#### Scenario: CLI 日志记录 mode

- **GIVEN** CLI 启动 AgentLoop
- **WHEN** run 开始
- **THEN** CLI 日志 SHALL 记录实际 mode

#### Scenario: CLI 拒绝 bypass mode

- **GIVEN** 用户执行 CLI 并指定 `bypass` mode
- **WHEN** CLI 解析参数
- **THEN** 系统 SHALL 返回可读错误
- **AND** SHALL NOT 构造 bypass AgentLoop
