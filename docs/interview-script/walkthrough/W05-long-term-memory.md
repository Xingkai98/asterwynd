# W05 · 长期记忆系统

**对应简历 bullet 5**：*"构建长期记忆系统，LLM 写时执行 exact、near-duplicate、contradiction 三路去重，importance × recency 联合时效衰减（30 天半衰期）、超期未访问自动归档且可恢复，git commit-before-write + revert 机制保障数据可逆，对比 mem0 路线后自主设计并沉淀 ADR"*

## 代码入口

```
agent/memory/
├── persistent.py   ← PersistentMemory（存储/衰减/归档/git 可逆）
├── dedup.py        ← MemoryDedupJudge（LLM 写时三路去重判定）
├── git_backend.py  ← MemoryGitBackend（history / diff / revert 工具）
├── manager.py      ← MemoryManager（会话内上下文压缩，见 W04）
├── model.py        ← MemoryEntry / MemoryHit
└── summary.py      ← ~50 token 全局摘要

工具面（tools/builtin/memory.py）：SaveMemory / RecallMemory / SearchMemory /
  ResolveMemoryConflict / MemoryGitBackend（可选）
```

## 核心逻辑

### 三路去重（dedup.py + persistent.py:548 apply_judgment）

```
SaveMemory 工具调用
  → recall_similar() 召回 top-K 相似记忆（NGramEmbedding，recall_threshold=0.5）
  → MemoryDedupJudge.judge() → LLM 判定四选一：
      new        → 直接 save
      supplement → 并进旧记忆 body（追加）
      update     → 整体替换旧记忆
      conflict   → 两条都保留，互打 conflict_with 标记（可后续 resolve）
  → apply_judgment() 执行
```

（简历"exact/near-duplicate/contradiction 三路"对应代码 supplement/update/conflict 三分支 + new 兜底。）

关键设计：
- **recall_threshold 短路**（dedup.py:93-95）：候选相似度低于 0.5 直接 new，零 LLM 成本。
- **LLM 判错不阻塞写**（dedup.py:115-117）：调用失败降级 new。
- **target_name 校验**（persistent.py:568）：写前校验 kebab-case，防 LLM 编造 target 路径穿越。
- **判定是建议不是事实**：supplement/update/conflict 由代码执行，LLM 只给 action+target+reason。

### importance × recency 联合衰减（persistent.py:212-261）

```
decay_score = importance × 0.5^(days_since_last_access / recency_halflife_days)

归档条件（AND）：
  1. 超过 archive_after_days（30 天）未访问
  2. decay_score < decay_threshold（1.5）
```

- **30 天半衰期**（RECENCY_HALFLIFE_DAYS=30）。
- **importance 1-5 默认 3**，重要记忆即使不访问也能撑更久（score ≥ threshold → 跳过归档）。
- **`_touch` 更新 last_accessed_at**（persistent.py:840）：recall/search 都 touch，衰减反映真实访问。
- **节流**（_run_decay_if_due）：每 3600 秒最多扫一次存储。
- **可恢复**（persistent.py:797）：restore() 从 archive/ 移回 active。

### git commit-before-write 可逆（persistent.py:407-466 + git_backend.py）

```
每次破坏性写之前：
  git add -A → git diff --cached --quiet（无变化安全返回）
  → git commit -m "<action> <name> → <reason>"   ← 记录旧状态
  → 才执行实际写入
  → 提交失败 → raise RuntimeError（写保护 abort）——宁可写失败，不丢旧内容
```

- **懒初始化**（_ensure_git）：只在首次破坏性写前 git init，__init__ 无副作用。
- **内联 identity**（_GIT_USER_NAME）：CI 无全局 git config 也能 commit。
- **两段式 revert**（git_backend.py:69-102）：先 snapshot 当前态 → checkout 旧 body + 重建索引行 + 追加 changelog → 再 commit revert 结果。
- **审计**：commit message 与 changelog 行对齐，`git log -- <name>.md` 即单记忆版本史。

### 为什么不用 mem0 ADD-only（ADR-0002）

- **mem0 V3 的转向**：因"写时 reconciliation 判错会静默删记忆"，删了第二遍 LLM diff，改 ADD-only（只做 MD5 精确去重，矛盾记忆并列存储，读时用多信号 ranker 挑当前事实）。
- **Asterwynd 的选择**：保留写时三分支 + **用 git 对冲误判**（commit-before-write）。因为当前 read 路径只有 NGramEmbedding，没有时间/BM25/实体多信号 ranker——直接抄 ADD-only 会让矛盾记忆无序浮出、recall() 分不清新旧。
- **拒绝侧车 revisions**："自己发明的残缺版 git"——无 diff/log/restore/backup；git 现成 + Letta Context Repositories 背书。

**面试金句**：*"我们没跟 mem0 走 ADD-only，因为那条路线的前提是读路径有强 ranker，我们没有。我们把可逆性做在写路径上——误判了也能 git checkout 回来。这是基于自己系统能力边界做的取舍，不是跟风。"*

## 简历核实

| 简历 | 核实 | 结论 |
|------|------|------|
| "三路去重"（exact/near-duplicate/contradiction） | supplement/update/conflict 三分支 | ✅（代码是三路+new） |
| "importance × recency 联合时效衰减（30 天半衰期）" | 0.5^(days/30) + importance 加权 | ✅ |
| "超期未访问自动归档且可恢复" | run_decay + restore() | ✅ |
| "git commit-before-write + revert" | _git_commit + MemoryGitBackend.revert | ✅ |
| "对比 mem0 路线后自主设计并沉淀 ADR" | ADR-0002 完整论证 | ✅ |

## 面试加分点

1. **ADR-0002 决策叙事**（mem0 对比 + 为什么选 git）——最有故事性的素材。
2. **importance 让"重要记忆活得久"** 的代码支撑（decay_score + threshold 跳过）。
3. **target_name 写前校验防路径穿越**——安全细节。
