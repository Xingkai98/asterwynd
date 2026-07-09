## ADDED Requirements

### Requirement: SaveMemory 工具

SaveMemory SHALL 支持 `create` 和 `update` 语义（name 不存在时创建，已存在时更新）。SaveMemory SHALL 写入对应的 `.md` 记忆文件和 `MEMORY.md` 索引行。工具能力 SHALL 标记为 `AGENT_STATE` / `MEDIUM` risk。

#### Scenario: 创建新记忆

- **GIVEN** name 为 `user-role` 的记忆不存在
- **WHEN** agent 调用 SaveMemory(type="user", name="user-role", description="用户角色", body="...")
- **THEN** 系统 SHALL 创建 `user-role.md`
- **AND** MEMORY.md SHALL 新增一行索引

#### Scenario: 更新已有记忆

- **GIVEN** name 为 `user-role` 的记忆已存在
- **WHEN** agent 调用 SaveMemory 使用相同 name
- **THEN** 系统 SHALL 覆盖原有内容
- **AND** MEMORY.md SHALL 更新对应索引行

### Requirement: RecallMemory 工具

RecallMemory SHALL 读取 MEMORY.md 索引和对应记忆文件。可选 type 过滤。返回每条记忆的完整正文，格式为 `### name (type)` + 正文，多条以 `---` 分隔。工具能力 SHALL 标记为 `AGENT_STATE` / `LOW` risk。

#### Scenario: 读取全部记忆

- **GIVEN** 存在 user、project 各 1 条记忆
- **WHEN** agent 调用 RecallMemory() 不传 type
- **THEN** 系统 SHALL 返回 2 条记忆的完整内容

#### Scenario: 按类型过滤

- **GIVEN** 存在 user 记忆 1 条、project 记忆 2 条
- **WHEN** agent 调用 RecallMemory(type="project")
- **THEN** 系统 SHALL 返回 2 条 project 记忆
