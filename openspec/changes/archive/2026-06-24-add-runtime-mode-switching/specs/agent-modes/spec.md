## ADDED Requirements

### Requirement: 支持运行时实时切换 agent mode

系统 SHALL 支持在一个 session 运行期间切换当前 agent mode。mode 切换完成后 SHALL 更新该 session 的当前 mode，并立即影响后续工具 schema 暴露和工具执行权限。当前 CLI 交互和 Web 入口 SHALL 至少保证 mode 切换影响同一 session 的后续 run；runtime transition API SHALL 保持可由未来控制面在 run 中调用的立即生效语义。

#### Scenario: 切换后 schema 立即变化

- **GIVEN** session 当前 mode 为 `build`
- **WHEN** runtime transition API 将 mode 切换为 `read_only`
- **THEN** 下一次获取工具 schema 时 SHALL 使用 `read_only` mode
- **AND** schema SHALL 不包含当前 mode 禁止的工具

#### Scenario: 切换后执行权限立即变化

- **GIVEN** session 当前 mode 已从 `build` 切换为 `read_only`
- **WHEN** 尚未执行的 tool call 请求调用 Edit 或 Bash
- **THEN** 系统 SHALL 按 `read_only` mode 拒绝该 tool call
- **AND** 返回可读权限错误作为 tool result

#### Scenario: 切换到 plan mode 后暴露 plan-only 工具

- **GIVEN** session 当前 mode 为 `build`
- **WHEN** runtime transition API 将 mode 切换为 `plan`
- **THEN** 下一次获取工具 schema 时 SHALL 包含 plan mode 允许的 `UpdatePlan` 和 `ExitPlanMode`
- **AND** 切出 `plan` 后这些工具 SHALL 不再暴露且不可执行

#### Scenario: bypass 不能通过实时切换启用

- **GIVEN** bypass 授权流程尚未实现
- **WHEN** 用户请求将 mode 切换为 `bypass`
- **THEN** 系统 SHALL 拒绝该切换
- **AND** 当前 mode SHALL 保持不变
