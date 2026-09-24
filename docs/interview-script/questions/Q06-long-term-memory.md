# Q06: 长期记忆——存储、去重、衰减、可逆

## 讲稿

长期记忆解决"跨 session 记住东西"。Asterwynd 的长期记忆有四块能力：**存储、去重、衰减、可逆**。

**存储**（#75）。记忆是 Markdown 文件 + MEMORY.md 索引，存在 `~/.asterwynd/projects/<hash>/memory/`，按项目 scope 隔离。每条记忆带 frontmatter（type/importance/created_at/conflict_with），支持语义检索（embedding 召回）。三层存储（Postgres + 向量库）经 ADR-0001 论证后作为后置演进，当前本地文件形态足够且零依赖。

**去重**。写时用 LLM 做三分支判断：新记忆 vs 召回 top5 相似记忆 → `supplement`（补充）/`update`（更新）/`conflict`（矛盾）/`new`。`MemoryDedupJudge` 把 incoming + 候选发给 LLM，返回 JSON 判断。低于相似度阈值短路为 `new`（零 LLM 成本）。

**衰减**。importance × recency 联合评分，超 30 天未检索且评分低于阈值自动归档（可恢复）。高 importance 记忆豁免归档。

**可逆**（#99，面试亮点）。LLM 三分支会**误判**，误判覆盖 = 内容永久丢失。于是用 git 管理可逆写入：每次破坏性写前 `commit-before-write` 快照旧状态，`resolve_conflict` 解除矛盾标记，`MemoryGitBackend` 提供 history/diff/revert。这比 mem0 的 ADD-only 路线多考虑了可恢复性（Q15 展开）。

## 代码走读

### 入口与调用链

```
SaveMemoryTool (agent/tools/builtin/memory.py) → PersistentMemory.apply_judgment/save
  → MemoryDedupJudge.judge (agent/memory/dedup.py:84) → LLM → 三分支写
RecallMemory/SearchMemory → PersistentMemory.recall/search
```

### 关键文件逐段

**`agent/memory/persistent.py` `class PersistentMemory`**
- `save`（502 行）：新增或覆盖记忆。覆盖前 `_git_commit` 快照旧状态（#99）。
- `apply_judgment`（548 行）：应用 LLM 三分支判断。
  - supplement（补充）：`entry.body = f"{旧}\n\n{新增}"` 合并，写前 commit。
  - update（更新）：整体替换 description + body，写前 commit。
  - conflict（矛盾）：保存新记忆 + 双方互打 `conflict_with` 标记，写前 commit（打标后不立即 commit，下次写兜底）。
  - 无效 target / unknown action 回退 `save`。
- `resolve_conflict`（620 行）：清除双方 conflict_with + changelog resolve 事件 + 可选归档 loser（#99）。写前 commit 快照"被解除的标记态"。
- `decay_score`（212 行）：importance × recency = `0.5^(days_since_access/halflife)`。
- `run_decay`（225 行）：超 30 天未检索 + 评分低于阈值 → 归档。
- `load_index`（267 行）/`load_summary`（303 行）：MEMORY.md 索引 / ~50 token 全局摘要（注入上下文用）。
- `_ensure_git`（407 行）/`_git_commit`（433 行）：git 懒初始化 + commit-before-write（内联 identity、abort 写保护、nothing-to-commit 区分）。

**`agent/memory/dedup.py`**
- `Judgment`（28 行）：action + target_name + reason。
- `MemoryDedupJudge.judge`（84 行）：LLM 判断三分支。
  - 无 LLM 或无候选 → `new`。
  - 全部低于 `recall_threshold`（默认 0.5）→ `new`（**零 LLM 成本短路**）。
  - 否则发 LLM，解析 JSON（容错 markdown fence + 尾部文本）。
  - LLM 调用失败 → `new`（降级不阻塞写）。

**`agent/memory/git_backend.py` `class MemoryGitBackend`**（#99）
- `history(name)`：`git log -- <name>.md`。
- `diff(name, a, b)`：`git diff <a> <b> -- <name>.md`。
- `revert(name, commit)`：**两步 commit**——先快照当前态（撤销凭据）→ checkout 旧 body → 重建索引行 → changelog → 再 commit revert 产物（历史即时可见）。

**`agent/tools/builtin/memory.py`** — `SaveMemoryTool` / `RecallMemoryTool` / `SearchMemoryTool` / `ResolveMemoryConflictTool` / `MemoryGitBackendTool`。

**`agent/memory/model.py`** — `MemoryEntry`（name/type/importance/created_at/conflict_with/scope 等）、`MemoryHit`（entry + score）。

### 设计理由

- **文件存储而非 DB**：local/lightweight 定位（ADR-0001），零常驻服务；embedding 通过 `agent/embedding/` 可插拔（NGramEmbedding 零依赖默认，可换 pgvector）。
- **写时去重 vs 读时排序**：#75 选写时 LLM 三分支（保留，能讲出设计取舍），#99 用 git 可逆性对冲其误判代价——mem0 因"判错静默污染"转向 ADD-only，我们用"写前留底"达到可恢复（Q15 完整展开）。
- **衰减保护高 importance**：不只是时间驱逐，`importance × recency` 让重要记忆即使老也不被归档。
- **scope 隔离**：记忆按项目 git root 隔离，worktree 共享 scope（`_find_scope_root`），跨项目不串数据。
