# Q15: 记忆可逆性坑——LLM 误判丢失内容，怎么对冲

## 讲稿

面试官问"讲一个踩过的坑"，这是我最喜欢讲的一个——它涉及记忆系统设计、业界对比、工程权衡，而且我们最终实现比 mem0 还多考虑了可恢复性。

**坑本身**。长期记忆的写时去重（#75）用 LLM 判断 incoming 记忆 vs 旧记忆的关系：`supplement`（补充）/`update`（更新）/`conflict`（矛盾）。但 LLM 会**误判**——而误判的后果是**内容永久丢失**：update 分支直接覆盖旧 body，supplement 把独立新记忆并进无关旧记忆，且 memory 目录在项目 git 仓库之外、无任何 VCS 兜底。

**业界调研**。我们发现 mem0 也踩过这个坑：它因为"写时 reconciliation 判错会静默污染"，**彻底转向 ADD-only**——写入只做精确 MD5 去重，矛盾/近重复并列存储，靠读时多信号 ranker 挑当前事实。这是业界最强数据点。

**我们的取舍**。没有直接抄 mem0，因为 Asterwynd 当前只有 NGramEmbedding 向量相似度，没有时序/BM25/实体多信号 ranker——直接 ADD-only 会让矛盾记忆无序浮出。于是我们选**保留写时去重 + git 可逆写入对冲**（ADR-0002）：每次破坏性写前 `commit-before-write` 快照旧状态，误判后可 revert；`resolve_conflict` 解除矛盾标记；`MemoryGitBackend` 提供 history/diff/revert。revert 用**两步 commit**——先快照当前态（撤销凭据），再提交 revert 产物，让 `git log -- <name>.md` 历史即时可见。

**最后结论**：mem0 用"从不覆盖"绕开误判，我们用"写前留底"做到可恢复。两者都解决数据丢失，我们保留写时去重（记忆库不无限膨胀），代价是 git 管理 + 版本清理。面试讲这个，能展示"我不是抄业界方案，而是理解取舍后做决策"。

## 代码走读

### 入口与调用链

```
SaveMemoryTool → PersistentMemory.apply_judgment → [写前 _git_commit 快照] → 三分支写
  → resolve_conflict（解除标记） / MemoryGitBackend.revert（回退） / history / diff
```

### 关键文件逐段

**`docs/adr/ADR-0002-long-term-memory-reversibility.md`** — 三方案对比（面试核心证据）。
- Context：写时去重误判丢失内容，memory 无 VCS 兜底。
- Decision：git 管理可逆写入，commit-before-write + resolve_conflict + MemoryGitBackend。
- **Alternatives Considered 第一行是 mem0 V3 ADD-only**：完整记录 mem0 为何转向 ADD-only（判错静默污染）、机制（single-pass + MD5 精确去重 + 读时多信号 ranker）、以及我们为何拒绝（当前无多信号 ranker，弱 ranker 下 ADD-only 让矛盾记忆无序浮出）。
- 备选还有侧车 revisions（残缺版 git）、单文件 .bak（覆盖中间版本，已被 #75 拒）。
- Consequences / Revisit Conditions（引入多信号 ranker 后重估 ADD-only）。

**`agent/memory/persistent.py`**
- `apply_judgment`（548 行）：三分支写。supplement/update/conflict 分支**写前** `_git_commit` 快照旧状态。
- `_git_commit`（433 行）：commit-before-write——内联 identity、abort 写保护（commit 失败中止写入，不丢旧内容）、nothing-to-commit 区分（fresh repo 安全继续）。
- `resolve_conflict`（620 行）：解除双方 conflict_with + changelog + 可选归档 loser；写前 commit 快照"被解除的标记态"。
- `_ensure_git`（407 行）：git 懒初始化（`__init__` 无副作用，保护 invalid-name 测试）。

**`agent/memory/git_backend.py` `class MemoryGitBackend`**
- `history(name)`：`git log -- <name>.md`。
- `diff(name, a, b)`：`git diff`。
- `revert(name, commit)`：**两步 commit**——先 `_git_commit` 快照当前态（撤销凭据）→ `git checkout <commit> -- <name>.md` 回退正文 → `_update_index` 重建索引行（正文与 MEMORY.md 一致）→ changelog 记 revert → 再 `_git_commit` 提交 revert 产物（历史即时可见，`git log` 上 v1→v2→v1 一条线）。

**`agent/memory/dedup.py`** — LLM 三分支判断（#75）。
- `MemoryDedupJudge.judge`（84 行）：incoming + top5 候选 → LLM → Judgment(action/target/reason)。
- 低于阈值短路 `new`（零 LLM 成本）；LLM 失败降级 `new`。

**测试**：`tests/agent/memory/test_reversibility.py`（20 个）——pre-image 可恢复、revert 两步 commit、索引跟随、resolve 清标记、abort 写保护、fresh repo、内联 identity、工具注册。

### 设计理由

- **为什么 commit-before-write 而非写后**：写后 commit 快照的是新状态，旧 body 已在写入时覆盖，无法提供可逆性。必须先提交旧状态再写。
- **为什么两步 commit revert**：revert 是"被覆盖当前态 + 回退产物"两段状态，一步 commit 会让 revert 历史滞后（要等下次写才可见）；两步让 `git log -- <name>.md` 即时干净。
- **为什么不用侧车 revisions**：侧车是"自己发明的残缺版 git"——无 diff/log/restore/backup、版本清理要自己造；git 全有 + 业界有 Letta Context Repositories 背书。
- **为什么不用 mem0 ADD-only**：当前无多信号 ranker，直接不覆盖会让矛盾记忆无序浮出；读时排序是比可逆性大得多的重构。
- **abort 写保护**：git 坏了就中止写入（宁可写失败不丢内容），而不是静默无保护写——降级写 = 虚假兜底，比没有更糟。
