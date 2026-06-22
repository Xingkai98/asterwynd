## ADDED Requirements

### Requirement: mode transition 可观察

Agent runtime SHALL 在 mode 切换时发布可观察事件，并记录切换前 mode、切换后 mode、触发来源和可选原因。

#### Scenario: 记录 mode_changed 事件

- **GIVEN** session 当前 mode 为 `read_only`
- **WHEN** 用户将 mode 切换为 `build`
- **THEN** runtime SHALL 发布 `mode_changed` 事件
- **AND** 事件 SHALL 包含 old_mode、new_mode 和 source

#### Scenario: 已开始执行工具不被中途取消

- **GIVEN** 某个工具调用已经开始执行
- **WHEN** 用户在工具执行期间切换 mode
- **THEN** 系统 SHALL NOT 因 mode 切换强制取消已开始执行的工具
- **AND** 后续尚未开始的 tool call SHALL 使用最新 mode 判断权限
