## Context

当前 MemoryManager 在每次 compact 时用 LLM 生成对话摘要并插入 system 消息，但摘要仅在当前 session 有效。Session 结束后对话历史、LLM 摘要全部丢弃。为了让 agent 在后续 session 中了解用户偏好和历史决策，需要覆盖跨 session 的持久层。

## Decisions

### 1. 存储格式与位置

与 Claude Code 的 memory 格式兼容：

```markdown
---
name: user-role
description: 用户的角色和偏好
metadata:
  type: user
---

用户是后端工程师，偏好 Go 和 Python。在解释代码时希望从调用链角度理解。
```

存储位置：`~/.claude/projects/<project-hash>/memory/`（复用 Claude Code 的路径结构，方便互操作）。

四类记忆：
- `user`：用户角色、偏好、知识背景
- `feedback`：用户给出的反馈和规则（"不要 mock 数据库"、"测试要覆盖 X"）
- `project`：项目相关的非代码信息（"下周五上线"、"legal 要求改 auth"）
- `reference`：外部资源指针（"bug 在 Linear INGEST 项目"、"Grafana 面板在 XX URL"）

### 2. 记忆索引 MEMORY.md

`MEMORY.md` 是索引文件，每行一条：
```markdown
- [用户角色](user_role.md) — 后端工程师，偏好 Go/Python，希望从调用链角度理解代码
- [测试规范](feedback_testing.md) — 集成测试必须连真实数据库，不要 mock
```

AgentLoop 启动时读取 `MEMORY.md` 索引注入系统消息（不超过 200 行 / 25KB），不读取记忆文件全文。Agent 需要详情时通过 RecallMemory 或 Read 工具按需获取。

### 3. SaveMemory 工具设计

```
SaveMemory(type, name, description, body)
```

- `type`: user | feedback | project | reference
- `name`: kebab-case slug，作为文件名（如 `user_role.md`）
- `description`: 一行摘要，写入 MEMORY.md 索引行
- `body`: 记忆正文（含 YAML frontmatter 外的 Markdown 内容）

工具写入两个文件：
1. `<name>.md` — 完整的记忆文件
2. 更新 `MEMORY.md` — 追加或更新索引行

如果 name 已存在，更新而不是重复创建。

### 4. RecallMemory 工具设计

```
RecallMemory(type=None)
```

- 读取 `MEMORY.md` 索引和对应记忆文件
- 可选按 type 过滤
- 返回每条记忆的完整正文，格式：`### name (type)` + 正文内容，多条以 `---` 分隔
- 不传 type 时返回全部记忆全文
- 当前阶段不做截断上限（记忆量级不大），后续必要时再加

### 5. 记忆注入策略

两层注入，参考 Claude Code 的 index-first 模式：

**AgentLoop 启动时**：注入 `MEMORY.md` 索引内容（截断为 200 行 / 25KB），不注入记忆文件全文。让 agent 知道有哪些记忆存在。

```
## Project Memory
The following persistent memories from prior sessions are available. Use RecallMemory to retrieve specific entries.
---
[Memories — MEMORY.md content]
---
```

**运行时**：agent 按需调用 RecallMemory 获取具体记忆内容。

注入位置：在所有系统消息之后、技能上下文之前。

注入时机：仅在 `MEMORY.md` 存在且非空时注入。如果不存在或为空，不注入。

### 6. 与 session 内 compact 的关系

两层记忆独立：
- `MemoryManager`（compact）：session 内短期内存，会被 compact 压缩/裁剪，session 结束后丢弃。
- `PersistentMemory`：跨 session 长期记忆，由用户或 agent 显式写入文件，保持不变直到被更新或删除。

两者不直接通信。AgentLoop 在构建系统消息时同时注入两者的产物。

### 7. 自动记忆

Agent 可以根据对话内容自主判断何时调用 `SaveMemory`。AGENTS.md / CLAUDE.md 中的 instructions 会引导 agent 在何时保存记忆（类似 Claude Code 的 auto-memory 机制）。

## Goals / Non-Goals

- 不支持向量化/语义检索记忆（当前阶段使用全文读取）。
- 不支持记忆的版本历史或 diff。
- 不支持记忆冲突检测或多用户协作。
- 不支持 `SaveMemory` 自动合并相似记忆。
- 不替代 `MemoryManager` 的 session 内 compact。

## Reference Implementation Research

- status: enabled
- reason: 与主流 coding agent 对比后识别的基础能力差距，需调研行业参考实现以指导设计方案。

- research questions:

1. Claude Code 的 memory 系统如何工作（文件格式、类型、读写机制）？
2. Codex 的 CODEBUDDY.md 机制如何运作？
3. 跨 session 记忆的注入时机和上下文 window 管理？

- findings:

- Claude Code 使用 `~/.claude/projects/<hash>/memory/` 目录结构，`MEMORY.md` 作为索引，每个记忆独立一个 `.md` 文件。四类记忆（user/feedback/project/reference）通过 frontmatter 的 `metadata.type` 字段区分。
- Claude Code 的记忆文件有 YAML frontmatter（name, description, metadata.type），正文是 Markdown。
- Claude Code 的 auto-memory 指令引导 agent 在特定触发条件下自动写入记忆（用户纠正、确认非平凡选择、项目决策等）。
- Codex 使用 `CODEBUDDY.md` 作为项目级持久记忆文件，与 Claude Code 的 MEMORY.md 类似但格式更简单。
- Cursor 的 `.cursorrules` 是项目级行为配置文件，偏向指令而非记忆。

- design impact:

- 文件格式直接对齐 Claude Code，确保记忆文件互操作。
- 存储路径复用 `~/.claude/projects/` 结构，避免另起一套。
- 记忆类型和触发条件参考 Claude Code 的 auto-memory 指令。
- 当前阶段不做向量检索是因为记忆量级不大（几十条），全文读取成本可控。
- **注入策略修正**: 参考 Claude Code 的两层读取设计——AgentLoop 启动时只注入 MEMORY.md 索引（截断 200行/25KB），agent 按需通过 RecallMemory 获取具体记忆内容。避免盲目全文注入消耗 token。
- Claude Code 的辅助查询（LLM 精选 5 条最相关记忆每轮注入）暂不实现，待记忆量增大后再评估。
- Aider/Cursor 无智能检索机制，均采用静态文件注入方式，不适合作为记忆系统参考。

## Impact Analysis

| 影响面 | 状态 |
|--------|------|
| Memory 模块 | 新增 PersistentMemory 类 |
| AgentLoop 系统消息构建 | 新增 MEMORY.md 索引注入段 |
| ToolRegistry | 新增 SaveMemory / RecallMemory |
| ToolPermissions | 新增 `AGENT_STATE_LOW_PERMISSION` 常量 |
| 项目标识 | 新增 project_hash 计算（git root / cwd） |
| AGENTS.md | 新增 Agent 持久记忆指令段 |
| Session 内 compact | 不影响 |
| MCP | 不影响 |
| Benchmark | 不影响（benchmark 使用临时 workspace，无记忆目录） |
| TUI/Web | 后续可选展示记忆面板 |


## Risks / Trade-offs

- [Risk] 记忆文件与 Claude Code 格式兼容但路径相同，两个工具可能互相覆盖。Mitigation: 使用相同的 MEMORY.md 索引文件，自然共享记忆。
- [Risk] 记忆文件手动编辑后 frontmatter 损坏导致解析失败。Mitigation: 解析失败时跳过该记忆并记录警告，不阻止其他记忆加载。
- [Risk] 全文读取所有记忆可能在记忆量大时增加 token 消耗。Mitigation: 当前阶段量小，后续可改为摘要注入或 RAG 检索。

## Grill Decisions (2026-07-09)

14 项关键决议，逐项确认后进入实现：

1. **project_hash 计算**: `hashlib.sha256(str(git_root)).hexdigest()[:16]`，无 git 时用 `Path.cwd().resolve()`
2. **工具注册范围**: `get_default_tools()` 和 `get_coding_tools()` 两边都注册
3. **name 格式校验**: 只允许 `[a-z0-9-]+`，不合法返回错误
4. **SaveMemory 返回值**: 简洁确认字符串，如 `"Memory 'user_role' saved."`
5. **RecallMemory 输出格式**: `### name (type)` + 正文，多条以 `---` 分隔，不做截断
6. **记忆注入策略**: 两层——AgentLoop 只注入 MEMORY.md 索引（200行/25KB），agent 按需调 RecallMemory
7. **YAML frontmatter**: 工具自动生成，agent 只传参数
8. **错误处理**: fail-open 策略——格式异常/文件丢失跳过不阻塞全局
9. **工具权限**: SaveMemory → `AGENT_STATE_PERMISSION`（复用）；RecallMemory → 新增 `AGENT_STATE` / `LOW` 常量
10. **PersistentMemory API**: `load_index()` / `save()` / `recall()` 三个方法
11. **MEMORY.md 解析**: 索引行只提取文件名，元信息从 frontmatter 读取
12. **依赖注入**: `PersistentMemory(project_root)` 在 `build_agent()` 创建，与 MemoryManager 并列传入 AgentLoop
13. **索引行更新**: 用 name 做 Title，按文件名匹配更新索引行
14. **AGENTS.md 指令**: 新增 `## Agent 持久记忆` 段，描述四类记忆保存时机和不保存内容

- PersistentMemory 单元测试：写入/更新/读取记忆、MEMORY.md 不存在时返回空。
- SaveMemory 工具测试：四类记忆创建、同名更新。
- RecallMemory 工具测试：全量和按 type 过滤。
- AgentLoop 集成：有记忆时注入 `## Project Memory`、无记忆时不注入。
- 文件兼容性测试：YAML frontmatter 合法性。
