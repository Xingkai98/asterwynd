## ADDED Requirements

### Requirement: TodoWrite 工具

系统 SHALL 提供 `TodoWrite` 工具，用于在任意 Agent Mode 下维护结构化的执行期任务列表。TodoWrite SHALL 支持 `create`、`update` 和 `list` 操作。每个 todo item SHALL 包含 id、content、status 和可选的 notes 字段。

#### Scenario: 创建新任务

- **GIVEN** 当前 todo 列表为空
- **WHEN** agent 调用 TodoWrite `create` 且 content 为 "实现 Edit 工具"
- **THEN** 系统 SHALL 返回新创建的 todo item
- **AND** item SHALL 有唯一 id
- **AND** item.status SHALL 为 `pending`

#### Scenario: 更新任务状态

- **GIVEN** 存在一个 status 为 `pending` 的 todo item
- **WHEN** agent 调用 TodoWrite `update` 且 status 为 `in_progress`
- **THEN** 该 item 的 status SHALL 变为 `in_progress`

#### Scenario: 列出所有任务

- **GIVEN** 存在 3 个 todo item
- **WHEN** agent 调用 TodoWrite `list` 且不传 status 过滤
- **THEN** 系统 SHALL 返回全部 3 个 item

#### Scenario: 按状态过滤

- **GIVEN** 存在 2 个 `pending` 和 1 个 `completed` item
- **WHEN** agent 调用 TodoWrite `list` 且 status 为 `pending`
- **THEN** 系统 SHALL 仅返回 2 个 `pending` item

#### Scenario: 无效 status 被拒绝

- **GIVEN** 任意状态
- **WHEN** agent 调用 TodoWrite `update` 且 status 为 `unknown`
- **THEN** 系统 SHALL 返回错误，item 保持不变
