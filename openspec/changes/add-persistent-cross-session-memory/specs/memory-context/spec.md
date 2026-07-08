## ADDED Requirements

### Requirement: 跨 session 持久记忆

系统 SHALL 支持通过 `PersistentMemory` 在 `~/.claude/projects/<project-hash>/memory/` 目录下维护跨 session 的持久记忆。记忆 SHALL 分为 `user`、`feedback`、`project`、`reference` 四类，每类记忆存储为一个独立 `.md` 文件，`MEMORY.md` SHALL 作为索引文件。

#### Scenario: 记忆写入

- **GIVEN** 当前项目 memory 目录不存在或为空
- **WHEN** agent 调用 SaveMemory 写入一条 type=user 的记忆
- **THEN** 系统 SHALL 创建 `<name>.md` 文件，内容包含 YAML frontmatter 和正文
- **AND** 系统 SHALL 在 MEMORY.md 中追加索引行

#### Scenario: 记忆更新

- **GIVEN** 已存在一条 name 为 `user_role` 的记忆
- **WHEN** agent 调用 SaveMemory 且 name 为 `user_role`
- **THEN** 系统 SHALL 更新 `<name>.md` 文件内容
- **AND** 系统 SHALL 更新 MEMORY.md 中对应的索引行

#### Scenario: 记忆读取

- **GIVEN** MEMORY.md 包含 3 条索引，对应 3 个有效记忆文件
- **WHEN** AgentLoop 启动
- **THEN** PersistentMemory SHALL 读取全部 3 条记忆的全文
- **AND** 内容 SHALL 注入到系统消息中

#### Scenario: 无记忆时不注入

- **GIVEN** 当前项目 memory 目录不存在或 MEMORY.md 为空
- **WHEN** AgentLoop 启动
- **THEN** 系统消息 SHALL NOT 包含 `## Project Memory` 段

#### Scenario: 索引指向已删除文件

- **GIVEN** MEMORY.md 索引行指向的 `.md` 文件已被手动删除
- **WHEN** PersistentMemory 尝试读取该文件
- **THEN** 系统 SHALL 跳过该条目
- **AND** 不阻止其他有效记忆的加载

### Requirement: SaveMemory 工具

系统 SHALL 提供 `SaveMemory` 工具。参数 SHALL 包含 `type`（user/feedback/project/reference）、`name`（kebab-case slug）、`description`（一行摘要）、`body`（Markdown 正文）。

#### Scenario: 写入记忆更新 MEMORY.md 索引

- **GIVEN** 当前 memory 目录存在且 MEMORY.md 已有其他条目
- **WHEN** agent 调用 SaveMemory 写入一条 type=user 的记忆
- **THEN** MEMORY.md SHALL 新增一行索引
- **AND** 对应 `.md` 文件 SHALL 包含合法的 YAML frontmatter 和正文

### Requirement: RecallMemory 工具

系统 SHALL 提供 `RecallMemory` 工具。参数 SHALL 包含可选的 `type` 过滤。不传 `type` 时 SHALL 返回全部记忆的完整内容。

#### Scenario: 按类型读取记忆

- **GIVEN** 存在 user 类型记忆 2 条、project 类型记忆 1 条
- **WHEN** agent 调用 RecallMemory(type="user")
- **THEN** 系统 SHALL 返回 2 条 user 记忆的完整内容
- **AND** 不返回 project 类型记忆
