## ADDED Requirements

### Requirement: build mode 执行进度展示

系统 SHALL 支持在 build mode 和 read_only mode 下通过 `TodoWrite` 工具维护执行期 todo 列表。TodoWrite 维护的 todo list SHALL 与 Plan Mode 的 Planning State 共享相同的 item 数据模型（id, content, status, notes），但 SHALL 存储为独立的扁平列表，不按 plan document 章节组织。

#### Scenario: build mode 下创建 todo

- **GIVEN** AgentMode 为 BUILD
- **AND** Plan Mode 未产出 Planning State
- **WHEN** agent 通过 TodoWrite 创建 todo item
- **THEN** item SHALL 正常创建
- **AND** TUI/Web UI SHALL 可展示当前 todo 列表

#### Scenario: TodoWrite 与 Planning State 隔离

- **GIVEN** Plan Mode 产出了 2 个 plan items
- **WHEN** agent 切换到 build mode 后通过 TodoWrite 创建 1 个 execution todo
- **THEN** plan items SHALL 保持不变
- **AND** execution todo SHALL 独立维护
- **AND** 两者不影响对方的展示
