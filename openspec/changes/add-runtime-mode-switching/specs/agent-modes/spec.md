## ADDED Requirements

### Requirement: 支持运行时实时切换 agent mode

系统 SHALL 支持在一个 session 运行期间实时切换当前 agent mode。mode 切换完成后 SHALL 立即影响后续工具 schema 暴露和工具执行权限。

#### Scenario: 切换后 schema 立即变化

- **GIVEN** session 当前 mode 为 `build`
- **WHEN** 用户将 mode 切换为 `read_only`
- **THEN** 下一次获取工具 schema 时 SHALL 使用 `read_only` mode
- **AND** schema SHALL 不包含当前 mode 禁止的工具

#### Scenario: 切换后执行权限立即变化

- **GIVEN** session 当前 mode 已从 `build` 切换为 `read_only`
- **WHEN** 尚未执行的 tool call 请求调用 Edit 或 Bash
- **THEN** 系统 SHALL 按 `read_only` mode 拒绝该 tool call
- **AND** 返回可读权限错误作为 tool result

#### Scenario: bypass 不能通过实时切换启用

- **GIVEN** bypass 授权流程尚未实现
- **WHEN** 用户请求将 mode 切换为 `bypass`
- **THEN** 系统 SHALL 拒绝该切换
- **AND** 当前 mode SHALL 保持不变
