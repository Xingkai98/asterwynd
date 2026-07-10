## Why

当前 `MemoryManager` 只做 session 内的 AutoCompact，没有跨 session 的持久记忆。每次新 session 开始，agent 对用户偏好、项目约定、历史决策一无所知。

Claude Code 有 `MEMORY.md` 自动记忆系统（`user/feedback/project/reference` 四类），Codex 有 `CODEBUDDY.md`，Cursor 有 `.cursorrules`。这些机制让 agent 在多次交互中逐步了解用户和项目，是 coding agent "越来越懂你的项目" 叙事的基础。

Asterwynd 的 AgentLoop 已经在系统消息中注入技能上下文（`_messages_with_run_context`），可复用同一条注入路径接入持久记忆。

## What Changes

- 新增 `agent/memory/persistent.py`：`PersistentMemory` 类，管理 `user/feedback/project/reference` 四类记忆文件。
- 记忆存储：`~/.claude/projects/<project-hash>/memory/MEMORY.md`（索引）+ 各类型 `.md` 文件（与 Claude Code 兼容格式）。
- 内置工具：
  - `SaveMemory`：写入一条记忆到对应类型文件。参数：`type`（user/feedback/project/reference）、`name`（kebab-case slug）、`description`（一行摘要）、`body`（内容）。
  - `RecallMemory`：读取并展示当前所有记忆的索引和内容。参数：可选的 `type` 过滤。
- AgentLoop 在每次 run 开始时通过 `PersistentMemory.load_context()` 读取所有记忆文件内容，注入系统消息（在技能上下文之前）。
- 记忆文件格式与 Claude Code 兼容（YAML frontmatter + 正文），方便未来迁移和对比。

## Capabilities

### Modified Capabilities

- `memory-context`: 从 "session 内 compaction" 扩展到 "session 内 compaction + 跨 session 持久记忆"。
- `tool-system`: 新增 `SaveMemory`、`RecallMemory` 工具。

## Impact

- 影响代码：
  - `agent/memory/persistent.py`（新增）
  - `agent/tools/builtin/memory.py`（新增）
  - `agent/tools/factory.py`
  - `agent/loop.py`（`_messages_with_run_context` 注入记忆上下文）
- 影响测试：
  - `tests/agent/memory/test_persistent.py`
  - `tests/agent/tools/test_memory_tools.py`
  - `tests/agent/test_loop.py`
- 不影响：session 内 compaction（`MemoryManager` 不变）、workspace safety、benchmark runner。

## Change Type

- primary: feature
