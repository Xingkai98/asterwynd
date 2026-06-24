## ADDED Requirements

### Requirement: CLI 交互模式支持切换 mode

CLI 交互模式 SHALL 提供 `/mode <build|read_only|plan>` 用户命令切换当前 session mode，并展示切换结果。CLI 单次运行 SHALL 继续通过 `--mode` 指定初始 mode，不要求提供运行中的人工切换入口。

#### Scenario: CLI 切换 mode

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户请求切换到 `read_only`、`plan` 或 `build`
- **THEN** CLI SHALL 更新当前 session mode
- **AND** 输出当前实际 mode
- **AND** 后续 run SHALL 使用更新后的 mode

#### Scenario: CLI 拒绝切换到 bypass

- **GIVEN** 用户处于 CLI 交互模式
- **WHEN** 用户请求切换到 `bypass`
- **THEN** CLI SHALL 输出可读错误
- **AND** 当前 mode SHALL 保持不变
