# ADR-0002: 长期记忆可逆写入用 git 管理（commit-before-write），不做 mem0 ADD-only 或侧车 revisions

- **Status**: accepted
- **Date**: 2026-08-03
- **Deciders**: issue #99 长期记忆可逆性设计评审

## Context

Issue #75（长期记忆做深）已实现写时去重三分支（supplement / update / conflict）。该判断由 LLM 作出，**误判时内容永久丢失**，且当前无任何恢复手段：

- `apply_judgment()` update 分支（`agent/memory/persistent.py:500-511`）整体替换旧 body，无 pre-image。
- supplement 分支（`persistent.py:488-498`）把独立新记忆并进无关旧记忆（`旧body \n\n 新body`），污染后无法撤销。
- conflict_with 标记（`persistent.py:513-525`）只增不减，无解除/清除 API、无消费点。
- `memory_dir` 位于 `~/.asterwynd/projects/<project-hash>/memory/`，**在项目 git 仓库之外、无 VCS 兜底**——误判覆盖即无法找回。

需要决策：采用什么机制让记忆写入可逆、冲突可解除？

业界证据（2026-08-03 调研）：

- **mem0 V3**：因"写时 reconciliation 判错会静默删除/污染记忆"，**删除了第二遍 LLM diff 调用**，转向 single-pass ADD-only——写入只做 MD5 精确去重，矛盾/近重复并列存储，读时用语义 + BM25 + 实体 + 时间多信号排序挑当前事实（[Mem0 architecture](https://github.com/mem0ai/mem0/blob/main/skills/mem0/references/architecture.md)、[Field Guide: Updates and Conflicts](https://www.memoryplugin.com/wiki/updates-and-conflicts.html)）。
- **Letta / MemGPT**：memory block 写时增量 version + `block_edit_log` 保留完整改写历史；Letta Code 进一步用 **Context Repositories（git 管理记忆）**，每次改动自动版本化、子 agent 并发协作与回滚走标准 git 操作（[Letta: Context Repositories](https://www.letta.com/blog/context-repositories/)、[engram-core memory_blocks](https://docs.rs/engram-core/latest/engram/storage/memory_blocks/index.html)）。
- **Zep / Graphiti**：时序知识图谱，事实带 `valid_from`/`valid_to`，变更走"失效而非删除"（旧边打 `invalid_at`、新建边），支持点查历史事实（[Graph Overview](https://help.getzep.com/v3/graph-overview)）。

## Decision

**采用 git 管理的可逆写入**，不做 mem0 ADD-only、不做侧车 revisions：

1. `memory_dir` 初始化为独立 git 仓库（`git init`），`.git` 仅存在于用户主目录的 `~/.asterwynd/` 下，不影响项目仓库。**懒初始化**：仅首次破坏性写前 init，`PersistentMemory.__init__` 不做副作用。
2. **commit-before-write**：每次破坏性写（`save()` 覆盖、`apply_judgment()` supplement/update/conflict、`resolve_conflict` 清标记、`revert` 覆盖文件）前，先 `git add -A -- <memory_dir>/ && git commit` 记录旧状态，再执行写入。**提交失败则中止写入（写保护 abort）**——宁可写失败，不丢旧内容；区分 nothing-to-commit（fresh repo 无旧状态，安全继续）与 git 真坏（abort）。commit 内联 identity（`-c user.name/-c user.email`），不依赖全局配置。
3. **commit message 承载结构化审计**：`<action> <name> → <reason>` 与 changelog 行对齐，使 `git log -- <name>.md` 给出该文件版本历史。审计叙事为"checkout commit N 撤销写 N"。
4. **新增 `resolve_conflict` API + 工具**：清除矛盾双方 `conflict_with` 标记 + changelog 记录 resolve 事件 + 可选归档败者（`loser` 参数，append-only 历史保留）。
5. **恢复能力**：基于 git 原生能力——`git log` 查历史、`git diff` 看变化、`git checkout <commit> -- <name>.md` 还原旧内容。对外暴露 `MemoryGitBackend`（history / diff / revert）作为可选工具，由 agent 按需调用。**revert 后重建索引行**（`_update_index` 同步 MEMORY.md 描述），保证正文与索引一致；changelog 保留审计、不随正文回退。
6. **不做 mem0 ADD-only**：Asterwynd 当前 `search()`（`persistent.py:562`）只有 NGramEmbedding 向量相似度，无时间/BM25/实体多信号 ranker。直接不覆盖会让矛盾记忆按 query 相似度无序浮出，`recall()` 分不清新旧——这是比 #99 大得多的 read 路径重构。
7. **不做侧车 revisions 目录**：它是"自己发明的残缺版 git"——无 diff/log/restore/backup、版本清理与原子性要自己造；git 已提供全部能力且业界有 Letta Context Repositories 背书。

## Alternatives Considered

| 备选方案 | 描述 | 拒绝原因 |
|----------|------|---------|
| **mem0 V3：ADD-only + 读时 ranker** | 删除写时 LLM diff，只做 MD5 精确去重；矛盾/近重复并列存储，读时用语义+BM25+实体+时间多信号排序挑当前事实（mem0 已从写时 reconciliation 转此路线） | 需要重写 read 路径 + 引入时序打分/BM25/实体匹配引擎，远超 #99 范围；Asterwynd 当前只有 NGramEmbedding 向量相似度，弱 ranker 下 ADD-only 会让矛盾记忆无序浮出，`recall()` 分不清新旧。作为方向性备选记录，留待未来引入多信号 ranker 时重估 |
| **侧车 revisions 目录** | update/supplement 前把旧 body 写入 `memory_dir/revisions/<name>/<ts>.md` 侧车目录 | 自己发明残缺版 git：无 diff/log/restore/backup，版本清理、原子性、多 agent 并发写都要自己造；git 已提供全部能力且业界有 Letta Context Repositories 背书 |
| **单文件 .bak / changelog 内联** | 每个记忆一个 `.bak` 文件，或 changelog 内嵌旧内容 | 误判链覆盖中间版本；changelog 内联破坏 R1-Q5 行格式与 grep 性（#75 已拒，同因） |

## Consequences

- 正面影响：
  - 恢复语义成熟：`git checkout <commit> -- <name>.md` 即还原，无需自写恢复 API。
  - 免费 `git log` / `git diff` / `git blame`：内容 diff 与 dedup reason（commit message）天然对齐，changelog 审计从 action 级提升到内容级。
  - 可备份：`~/.asterwynd/` 下 memory 目录是独立 git 仓库，可 push 远端，机器丢失也能救回。
  - 对接 #79 多 Agent 协作：多 subagent 并发写记忆有 git 兜底（Letta Context Repositories 同款动机）。注意：git 解决误判恢复，**不解决并发丢更新**（#75 已知债，read-modify-write 无 flock），登记 known-debt。
  - 实现量最小：不重写 read 路径、不造版本格式，核心是"写前 commit + resolve_conflict API"。
- 负面影响：
  - `~/.asterwynd/` 下出现 `.git` 目录，需文档说明（属用户主目录，不入项目仓库）。
  - 依赖系统 `git` 可用；`git` 不可用/commit 失败时**中止写入**（abort 写保护），区分 nothing-to-commit（fresh repo 安全继续）与 git 真坏（abort）。
  - conflict_with 标记累积仍存在，需 resolve_conflict API 主动解除。
  - commit 频率需控制：写入频繁时会产生大量小 commit，可接受（每次破坏性写一条，与 changelog 行一一对应）。
- 需要的相关变更：
  - `docs/adr/ADR-0002-long-term-memory-reversibility.md` 本文件。
  - change 内实现：`agent/memory/persistent.py`（commit-before-write + resolve_conflict）、`agent/tools/builtin/memory.py`（resolve_conflict 工具 + 可选 MemoryGitBackend 工具）、回归测试。

## Revisit Conditions

在以下条件出现时重新审视本决策：
- [ ] 引入读时多信号 ranker（时间/BM25/实体打分）后，评估 mem0 ADD-only 是否更适合（可逆性从"写前留底"变为"从不覆盖"）。
- [ ] 记忆规模或并发写达到 git 管理瓶颈（如单条记忆毫秒级高频写入），需换 append-only log / DB。
- [ ] `git` 不可用的环境成为常态部署目标，需改为纯 Python 版本管理。
