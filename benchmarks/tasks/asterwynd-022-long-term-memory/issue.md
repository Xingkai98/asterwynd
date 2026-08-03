# 长期记忆做深：写入去重 + 冲突检测 + 时效性衰减 + 语义检索 + scope 隔离

Asterwynd 的跨 session 记忆当前是 Markdown 文件 + MEMORY.md 索引（`agent/memory/persistent.py` 的 `PersistentMemory`，YAML frontmatter + Markdown，类型 user/feedback/project/reference）。`SaveMemoryTool` 按 name 直接覆盖，无去重、无冲突检测、无衰减、无 scope 标签。`MemoryIndexSource`（`agent/context/sources.py`）注入完整 MEMORY.md 索引（200 行/25KB 截断）。

本任务把记忆系统升级到工业级形态，四个可量化目标：

## 1. 写入去重 + 冲突检测（三分支闭环）

新记忆写入时，用 embedding 召回 top-5 相似既有记忆，交给 LLM 判断"补充/更新/矛盾"三分支，矛盾标记保留双方并写 change log：

- 补充（supplement）= 合并追加到既有记忆 body；
- 更新（update）= 整体替换既有记忆的 description + body；
- 矛盾（conflict）= 双方保留，frontmatter `metadata.conflict_with` 互相标记，并记录 change log；
- 无相似候选或 LLM 不可用时回退为直接新建。

要求：schema 扩展 `metadata.importance/created_at/last_accessed_at/scope/conflict_with/archived`；change log 写入 `memory_dir/changelog.md`。

## 2. 时效性衰减 + 归档

`score = importance × recency`，`recency = 0.5 ^ (days_since_last_access / 30)`；超 30 天未检索自动归档（`run_decay()` 惰性执行），归档/恢复 API 可逆。

## 3. 按需语义检索 + 全局摘要

- 新增 `SearchMemory` 工具（`query` + `top_k`，可带 `type`/`scope` 过滤），对活跃记忆做 embedding 语义 top-k 检索并返回相似度；
- `MemoryIndexSource` 从注入完整索引改为注入 ~50 token 全局摘要（importance 降序的 `name: description` 行），全文按需用 `SearchMemory` 取。

## 4. Scope 隔离

frontmatter 增加 `metadata.scope`（git root 路径）；跨 scope 的检索/读取请求被拒绝，不串数据。

## 参考实现

复用 `agent/embedding/` 模块（`NGramEmbedding` + `InMemoryVectorStore`，由 #77 提供）。新文件建议：`agent/memory/model.py`（MemoryEntry/MemoryHit）、`agent/memory/dedup.py`（MemoryDedupJudge 三分支判断）、`agent/memory/summary.py`（~50 token 摘要）。

## 验收量化指标

- **注入 token 节省**：摘要注入 token 数 ≤ 50，相比原 MEMORY.md 索引（≥2K）节省 >90%。
- **三分支闭环**：update/supplement/conflict 三种判断各自产生正确存储结果，change log 可回溯。
- **衰减留存率**：30 天内访问过的记忆全部保留；超 30 天未访问的被归档，恢复 API 可还原。
