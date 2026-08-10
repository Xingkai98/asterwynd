# Bullet 5: 长期记忆系统 — 代码走读

> 简历原文：构建长期记忆系统，LLM 写时四分支去重（supplement/update/conflict + new 兜底），importance × recency 联合时效衰减（30 天半衰期）、超期未访问自动归档且可恢复，git commit-before-write + revert 机制保障数据可逆，对比 mem0 路线后自主设计并沉淀 ADR

---

## 整体架构

长期记忆系统由 4 个核心模块组成，存储在 `agent/memory/` 目录下：

```
用户记忆文件 → ~/.asterwynd/projects/<sha256[:16]>/memory/
               ├── MEMORY.md         ← 人类可读索引
               ├── <name>.md         ← 每条记忆一个 Markdown 文件（YAML frontmatter）
               ├── changelog.md      ← 审计日志
               ├── archive/          ← 归档目录（超期/手动）
               └── .git/             ← 独立 git 仓库（懒初始化，不在项目仓库内）
```

数据模型（`agent/memory/model.py`）：

```python
@dataclass
class MemoryEntry:
    name: str
    description: str
    body: str
    type: str = "project"           # user / feedback / project / reference
    importance: int = 3             # 1-5
    created_at: datetime | None
    last_accessed_at: datetime | None  # decay 的时间锚点
    scope: str                       # 项目 root path，隔离不同项目
    archived: bool = False
    conflict_with: list[str]         # 写时去重标记的矛盾记忆名列表
```

4 种记忆类型（`persistent.py:37`）：`_VALID_TYPES = frozenset({"user", "feedback", "project", "reference"})`。

工具暴露（`agent/tools/builtin/memory.py`）：`SaveMemory`、`RecallMemory`、`SearchMemory`、`ResolveMemoryConflict`、`MemoryGitBackend`，共 5 个（`factory.py:97-101`，`KNOWN_BUILTIN_TOOL_NAMES` 中确认）。

---

## 1. LLM 写时四分支去重（supplement / update / conflict + new 兜底）

### 1.1 四分支定义

**文件**：`agent/memory/dedup.py:24`

```python
_ACTIONS = frozenset({"new", "supplement", "update", "conflict"})
```

恰好 4 个分支，语义由 LLM 判决系统提示词定义（`:41-54`）：

| 分支 | 语义 | 写入行为 |
|------|------|---------|
| `new` | 与任何已有记忆都不重叠 | 新建文件 |
| `supplement` | 对已有记忆补充细节，不矛盾 | 追加 body（`旧body \n\n 新body`） |
| `update` | 新内容取代旧内容 | 替换 body |
| `conflict` | 内容矛盾，两方都应保留 | 新建文件 + 双向标记 `conflict_with` |

### 1.2 去重流水线

**调用入口**：`agent/tools/builtin/memory.py:74-102`（`SaveMemoryTool.execute()`）

```
① 构造 incoming_text = "name: description\nbody"                          (:85)
② persistent.recall_similar(incoming_text, top_k=5) — 向量召回 Top-K     (:86)
③ MemoryDedupJudge.judge(incoming, candidates) — LLM 判决                 (:87)
④ persistent.apply_judgment(...) — 按判决结果执行写入                      (:88-95)
```

**步骤 2 向量召回**（`persistent.py:763-770`）：

```python
def recall_similar(self, query, top_k=5, embedder=None):
    """Write-dedup candidate recall: top-k similar active memories."""
    return self.search(query, top_k=top_k, embedder=embedder)
```

使用 `NGramEmbedding`（字符 n-gram MD5 哈希，2048 维，零外部依赖）做余弦相似度检索。

**步骤 3 LLM 判决**（`dedup.py:84-119`）：

```python
class MemoryDedupJudge:
    def __init__(self, llm=None, model=None, recall_threshold=0.5):
```

- `recall_threshold = 0.5`（`dedup.py:78`）：候选相似度 < 0.5 的直接短路为 `new`，零 LLM 成本（`:93-95`）
- `llm=None` 时（无 LLM 可调）→ 全部返回 `new`，不阻塞写入（`:90-91`）
- LLM 调用失败 → fallback `new`，记录 `llm_call_failed`（`:115-117`）
- JSON 解析失败 → fallback `new`，记录 `parse_failed`（`:141-150`）
- 未知 action → fallback `new`，记录 `invalid_action`（`:148-150`）

**new 的多层兜底**：无 LLM / 无候选 / 相似度低于阈值 / LLM 报错 / 解析失败 / 未知 action / 目标不存在 / 目标已归档 — 所有路径最终 fallback 到 `self.save()`（`persistent.py:618`）。

### 1.3 四分支写入实现

**文件**：`agent/memory/persistent.py:548-618`（`apply_judgment()`）

```python
def apply_judgment(self, type, name, description, body, judgment, importance=None):
    action = getattr(judgment, "action", "new")
    target = getattr(judgment, "target_name", None)
```

| 分支 | 实现位置 | 写入逻辑 |
|------|---------|---------|
| `supplement` | `:571-583` | `entry.body = f"{entry.body}\n\n{body.strip()}"` — 尾部追加 |
| `update` | `:585-598` | `entry.body = body.strip()` — 整体替换 |
| `conflict` | `:600-616` | 新建 `name` 条目 + 双向 `conflict_with` 列表追加 |
| `new`（兜底） | `:618` | 直接 `self.save()` — 新建文件 |

**LLM 提供的 target 名前验证**（`:567-569`）：

```python
if target is not None and _validate_name(str(target)) is not None:
    return self.save(type, name, description, body, importance=importance)
```

防止 LLM 幻觉出非法文件名（如 `../etc/passwd`）→ 直接 fallback 到 `new`。

**target 不存在或已归档时的兜底**（`:573-574, :587-588`）：supplement/update 的目标如果已消失或归档 → 退化为 `new`。

### 1.4 去重判断默认可关闭

**文件**：`agent/tools/builtin/memory.py:84`

```python
if self._judge is not None:
    # 有 judge → 走四分支
else:
    # 无 judge → 直接 save，无去重
    return memory.save(type, name, description, body, importance=importance)
```

`MemoryDedupJudge` 由 `SaveMemoryTool` 构造函数的 `judge` 参数传入（`:62`）。不传 `judge` 时，所有写入跳过 LLM 判决，直接覆盖保存。工具注册在 `factory.py` 中，`judge` 是否传入取决于配置。

---

## 2. importance × recency 联合时效衰减（30 天半衰期）

### 2.1 参数定义

**文件**：`agent/memory/persistent.py:40-54`

```python
DEFAULT_IMPORTANCE = 3      # line 40
IMPORTANCE_MIN = 1          # line 41
IMPORTANCE_MAX = 5          # line 42
ARCHIVE_AFTER_DAYS = 30     # line 43
RECENCY_HALFLIFE_DAYS = 30  # line 44  ← 半衰期 30 天
MAX_SUMMARY_TOKENS = 50     # line 45
DEDUP_RECALL_THRESHOLD = 0.5 # line 46
DECAY_THRESHOLD: float | None = 1.5      # line 51 — 衰减分数门限
DECAY_INTERVAL_SECONDS = 3600            # line 54 — 衰减检查节流间隔（1 小时）
```

所有参数均可通过 `PersistentMemory.__init__` 的构造参数覆盖（`:168-178`），实现按实例定制。

### 2.2 衰减公式

**文件**：`agent/memory/persistent.py:212-223`（`decay_score()`）

```python
def decay_score(self, entry: MemoryEntry, now=None) -> float:
    """Importance × recency joint score (Decision 3).

    recency = 0.5 ^ (days_since_last_access / recency_halflife_days).
    """
    now = now or self._now()
    last = entry.last_accessed_at or entry.created_at or now
    days = max(0.0, (now - last).total_seconds() / 86400.0)
    recency = 0.5 ** (days / self._recency_halflife_days)
    return entry.importance * recency
```

**公式解读**：

```
decay_score = importance × 0.5^(days / 30)
```

- `importance` 范围 1-5，默认 3
- `days` = 距上次访问的天数（**小数天**，`:221` 用 `total_seconds() / 86400.0`，不是整天数）
- `recency` 在 30 天时恰好 = 0.5（半衰期），60 天时 = 0.25，以此类推

**时间锚点**：`last_accessed_at or created_at or now`（`:220`）——优先用最后访问时间，其次创建时间，最后当前时间。

**访问即刷新**：`persistent.py:840-846`（`_touch()`）

```python
def _touch(self, name):
    """Update last_accessed_at on retrieval so decay reflects real access."""
    entry = self._load_entry_by_name(name)
    if entry is None or entry.archived:
        return
    entry.last_accessed_at = self._now()
    self._write_entry(entry)
```

每次 `recall()` / `search()` 命中某条记忆，`_touch()` 更新其 `last_accessed_at`，实时刷新衰减时钟。

### 2.3 衰减分数计算举例

| importance | 距上次访问 | days/30 | recency (0.5^(d/30)) | decay_score |
|:---|:---|:---|:---|:---|
| 5 | 30 天 | 1.0 | 0.5 | 2.5 |
| 3 | 30 天 | 1.0 | 0.5 | 1.5 |
| 1 | 30 天 | 1.0 | 0.5 | 0.5 |
| 5 | 60 天 | 2.0 | 0.25 | 1.25 |
| 3 | 60 天 | 2.0 | 0.25 | 0.75 |
| 1 | 60 天 | 2.0 | 0.25 | 0.25 |

可见：高 importance（5）的记忆 60 天不访问后 score=1.25 仍高于默认门限 1.5？不对，1.25 < 1.5，所以会被归档。而 importance=5 在 30 天时 score=2.5 远高于 1.5，不会被归档。这就是 `importance × recency` 联合衰减的效果——**重要记忆即使不访问也能存活更久**。

---

## 3. 超期未访问自动归档且可恢复

### 3.1 归档条件（双门 AND 逻辑）

**文件**：`agent/memory/persistent.py:225-246`（`run_decay()`）

```python
def run_decay(self, now=None) -> int:
    """Archive active memories that have aged out.
    ...
    """
    now = now or self._now()
    archived = 0
    for entry in self.load_entries():
        last = entry.last_accessed_at or entry.created_at or now
        days = (now - last).total_seconds() / 86400.0
        if days <= self._archive_after_days:       # Gate 1: 30 天
            continue
        if self._decay_threshold is not None and self.decay_score(entry, now) >= self._decay_threshold:
            continue                                # Gate 2: score >= 1.5 则保护
        self.archive(entry.name, reason="decay: not retrieved within archive_after_days")
        archived += 1
    return archived
```

归档条件 = **超期（> 30 天未访问）AND 衰减分数低于门限（< 1.5）**。两个条件同时满足才归档。

**门限可关闭**：`decay_threshold=None` 时（构造参数可设为 None），Gate 2 失效 → 纯时间归档（> 30 天即归档）。

### 3.2 归档节流

**文件**：`agent/memory/persistent.py:248-261`（`_run_decay_if_due()`）

```python
def _run_decay_if_due(self, now=None) -> int:
    """Throttled decay trigger, called from every read entry point."""
    now = now or self._now()
    if self._last_decay_run is not None:
        elapsed = (now - self._last_decay_run).total_seconds()
        if elapsed < self._decay_interval_seconds:
            return 0
    self._last_decay_run = now
    return self.run_decay(now)
```

- `DECAY_INTERVAL_SECONDS = 3600`（`:54`）：最多每 1 小时运行一次衰减扫描
- 触发点：每次 `load_index()` / `load_summary()` / `recall()` / `search()` 调用都会检查（`:273, 312, 702, 738`），但节流保证不会在繁忙 session 中每个读路径都全量扫描

### 3.3 归档实现

**文件**：`agent/memory/persistent.py:776-795`（`archive()`）

```python
def archive(self, name, reason=None):
    entry = self._load_entry_by_name(name)
    if entry is None:
        return f"Error: memory '{name}' not found."
    if entry.archived:
        return f"Memory '{name}' already archived."
    archive_dir = self.memory_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    src = self._entry_path(name)
    dst = archive_dir / f"{name}.md"
    entry.archived = True
    self._write_entry_to(entry, dst)    # 写入 archive/ 目录
    src.unlink()                         # 删除原位置文件
    self._remove_from_index(name)        # 从 MEMORY.md 移除索引行
    self._append_changelog("archive", name, reason or "archived")
    return f"Memory '{name}' archived."
```

归档 = 移动文件到 `archive/` 子目录 + 更新 frontmatter 中 `archived: true` + 从 MEMORY.md 索引移除 + 记录 changelog。**内容不删除，只是换位置**。

### 3.4 恢复

**文件**：`agent/memory/persistent.py:797-812`（`restore()`）

```python
def restore(self, name):
    """Move an archived memory back into the active store."""
    entry = self._load_entry_by_name(name, include_archived=True)
    if entry is None or not entry.archived:
        return f"Error: memory '{name}' not found in archive."
    src = self._entry_path(name, archived=True)
    dst = self._entry_path(name)
    entry.archived = False
    self._write_entry_to(entry, dst)     # 写回 memory/ 目录
    src.unlink()                          # 删除 archive/ 中文件
    self._update_index(name, entry.description, existed=False)
    self._append_changelog("restore", name, "restored from archive")
    return f"Memory '{name}' restored."
```

恢复是归档的逆操作：`archived` 标记改回 `false`，文件从 `archive/` 移回上级目录，索引行重建，changelog 追加。**注意**：`restore()` 目前**没有暴露为独立工具**（`memory.py` 中无 `RestoreMemoryTool`），仅内部 API 可用。agent 可通过 `MemoryGitBackendTool` 的 `revert` action 间接恢复被归档之前的内容，但无法直接将 `archive/` 中的条目移回 active。

**归档触发机制**（`persistent.py` 中的三个归档入口）：

| 入口 | 触发者 | 位置 |
|------|--------|------|
| 自动衰减 | `_run_decay_if_due()`（每次读路径节流触发） | `:273, 312, 702, 738` |
| 手动归档 | 直接调用 `archive()` | `:776` |
| 冲突解决归档 | `resolve_conflict(archive=True)` — 归档败者 | `:654` |

---

## 4. git commit-before-write + revert 机制保障数据可逆

### 4.1 核心设计：懒初始化 + 内联 identity

**文件**：`agent/memory/persistent.py:407-431`（`_ensure_git()`）

```python
def _ensure_git(self) -> bool:
    """Lazily initialize the memory git repo.
    No side effect in __init__: the repo is created only on the first
    destructive write, so invalid-name paths never create a memory dir.
    """
    if shutil.which("git") is None:
        return False
    if not self.memory_dir.exists():
        return False
    # git init -q
```

关键点：
- **懒初始化**：不在 `PersistentMemory.__init__` 里 `git init`，只在首次破坏性写时触发（`:408-412` 注释说明）
- **内联 identity**（`:22-23`）：`_GIT_USER_NAME = "Asterwynd Memory"`、`_GIT_USER_EMAIL = "memory@asterwynd.local"` — 不依赖全局/仓库级 git config（CI 环境无 git config 也能 commit）
- **内联方式**（`:26-33`）：`_run_git()` 每次调用都带 `-c user.name=... -c user.email=...`

### 4.2 commit-before-write 流程

**文件**：`agent/memory/persistent.py:433-465`（`_git_commit()`）

```python
def _git_commit(self, action, name, reason):
    """commit-before-write: snapshot current memory dir before a destructive write.
    - git 不可用 → RuntimeError（中止写入）
    - git init 失败 → RuntimeError（中止写入）
    - git add 失败 → RuntimeError（中止写入）
    - nothing-to-commit（fresh repo / 无旧状态）→ 安全返回，继续写入
    - git commit 失败 → RuntimeError（中止写入）
    """
    if shutil.which("git") is None:
        raise RuntimeError("Memory reversibility: git is not available; aborting write...")
    if not self._ensure_git():
        raise RuntimeError("Memory reversibility: failed to initialize git repo; aborting write.")
    add = _run_git(self.memory_dir, "add", "-A")
    if add.returncode != 0:
        raise RuntimeError(f"Memory reversibility: git add failed: {add.stderr}")
    # No staged changes → nothing to commit (fresh repo / no prior state).
    quiet = _run_git(self.memory_dir, "diff", "--cached", "--quiet")
    if quiet.returncode == 0:
        return
    msg = f"{action} {name} → {reason}"
    commit = _run_git(self.memory_dir, "commit", "-q", "-m", msg)
    if commit.returncode != 0:
        raise RuntimeError(f"Memory reversibility: git commit failed, aborting write...")
```

**写保护语义**：commit 失败 → `RuntimeError` → 调用方不执行写入。宁可写失败，不丢旧内容。

**nothing-to-commit 特殊处理**（`:456-458`）：fresh repo（第一次写入前）无旧状态需要快照，直接安全通过。

### 4.3 所有触发 commit-before-write 的写入路径

| 操作 | 触发位置 | commit message |
|------|---------|---------------|
| `save()` 覆盖已有条目 | `persistent.py:523` | `update <name> → save-overwrite` |
| `apply_judgment()` supplement | `persistent.py:576` | `supplement <target> → <reason>` |
| `apply_judgment()` update | `persistent.py:590` | `update <target> → <reason>` |
| `apply_judgment()` conflict | `persistent.py:604` | `conflict <name> → <reason>` |
| `resolve_conflict()` | `persistent.py:649` | `resolve <name_a> <-> <name_b> → <reason>` |

**注意**：新建条目（`new` 分支）不触发 commit-before-write —— 因为没有旧内容需要快照。

### 4.4 Revert 机制（两阶段 commit）

**文件**：`agent/memory/git_backend.py:69-102`（`MemoryGitBackend.revert()`）

```python
def revert(self, name, commit):
    """Two-step commit (design Decision 3):
      1. snapshot current state (undo credential)
      2. checkout old body + rebuild index + append changelog,
         then commit the revert result.
    """
    # Step 1: snapshot the current (to-be-overwritten) state.
    self._memory._git_commit("revert", name, f"before revert to {commit}")

    # Apply the revert: checkout old body.
    proc = self._git("checkout", commit, "--", f"{name}.md")

    # Rebuild the index line from the reverted frontmatter
    entry = self._memory._load_entry_by_name(name)
    if entry is not None:
        self._memory._update_index(name, entry.description, existed=True)
    # Append change log entry (audit history is preserved, not rolled back).
    self._memory._append_changelog("revert", name, commit)

    # Step 2: commit the revert result
    self._memory._git_commit("revert", name, f"revert to {commit}")
```

**两阶段 commit 的设计意图**（ADR 对应 grill Q9 / design Decision 3）：
- **Step 1**（`:84`）：先 commit 当前状态作为 undo 凭证（"被覆盖前的最后状态"）
- **Step 2**（`:100`）：checkout 旧内容 + 重建 MEMORY.md 索引行（保证正文与索引一致）+ changelog 保留审计（不随正文回退），再 commit

结果：`git log -- <name>.md` 显示完整版本历史，包括 revert 前后的每一个快照。

### 4.5 Git 三件套：history / diff / revert

**文件**：`agent/memory/git_backend.py:27-102`

| 操作 | 方法 | 底层命令 | 位置 |
|------|------|---------|------|
| 查看版本历史 | `history(name)` | `git log --format=%h %s -- <name>.md` | `:44-55` |
| 比较两个版本 | `diff(name, commit_a, commit_b)` | `git diff commit_a commit_b -- <name>.md` | `:57-67` |
| 回退到指定版本 | `revert(name, commit)` | `git checkout commit -- <name>.md` + index rebuild + commit | `:69-102` |

工具暴露：`MemoryGitBackendTool`（`memory.py:275-342`），支持 `action` 参数取值 `"history"` / `"diff"` / `"revert"`。

---

## 5. 对比 mem0 路线 + ADR 沉淀

### 5.1 ADR 概览

**文件**：`docs/adr/ADR-0002-long-term-memory-reversibility.md`

- **Status**: accepted
- **Date**: 2026-08-03
- **Deciders**: issue #99 长期记忆可逆性设计评审

### 5.2 三条备选方案对比

| 方案 | 描述 | 拒绝原因 |
|------|------|---------|
| **mem0 V3：ADD-only + 读时 ranker** | 删除写时 LLM diff，只做 MD5 精确去重；矛盾/近重复并列存储，读时用语义+BM25+实体+时间多信号排序 | 需要重写 read 路径 + 引入多信号打分引擎，远超 #99 范围；Asterwynd 当前只有 NGramEmbedding，弱 ranker 下 ADD-only 会让矛盾记忆无序浮出（ADR:33, Alternative 1） |
| **侧车 revisions 目录** | update/supplement 前把旧 body 写入 `memory_dir/revisions/<name>/<ts>.md` | "自己发明的残缺版 git"：无 diff/log/restore、版本清理与原子性要自己造；git 已提供全部能力且业界有 Letta Context Repositories 背书（ADR:41, Alternative 2） |
| **单文件 .bak / changelog 内联** | 每个记忆一个 `.bak` 文件，或 changelog 内嵌旧内容 | 误判链覆盖中间版本；changelog 内联破坏行格式与 grep 可审计性（ADR:42, Alternative 3） |

### 5.3 最终决策（7 条）

**ADR Decision 1-7**（`:28-34`）：

1. `memory_dir` 初始化为独立 git 仓库，懒初始化（仅首次破坏性写前 `git init`）
2. **commit-before-write**：每次破坏性写前 `git add -A` + `git commit`，失败则中止写入
3. **commit message 承载结构化审计**：`<action> <name> -> <reason>` 与 changelog 行对齐
4. **新增 `resolve_conflict` API + 工具**：清除 `conflict_with` 标记 + 可选归档败者
5. **恢复能力**：基于 git 原生 `log`/`diff`/`checkout`，对外暴露 `MemoryGitBackend`
6. **不做 mem0 ADD-only**：Asterwynd read 路径只有 NGramEmbedding，无多信号 ranker（ADR 将此列为 revisit condition）

### 5.4 业界调研引证

ADR 引用了三个业界参考（`:18-22`）：

- **mem0 V3**：因"写时 reconciliation 判错会静默删除/污染记忆"，**删除了第二遍 LLM diff 调用**，转向 single-pass ADD-only
- **Letta / MemGPT**：Context Repositories 用 git 管理记忆，每次改动自动版本化
- **Zep / Graphiti**：时序知识图谱，事实带 `valid_from`/`valid_to`，变更走"失效而非删除"

### 5.5 已知债务（ADR Consequences）

- **并发丢更新**：git 解决误判恢复，但不解决并发写（read-modify-write 无 flock），登记为已知债（`:49`）
- **git 依赖**：依赖系统 `git` 可用，不可用时中止写入（`:54`）
- **commit 频率**：每次破坏性写一条 commit，可接受（`:56`）
- **conflict_with 累积**：需 `resolve_conflict` 主动解除（`:55`）

---

## 6. 其他支撑机制

### 6.1 MEMORY.md 索引

**文件**：`agent/memory/persistent.py:34-35, 266-301, 860-875, 904-938`

- 格式：`- [name](name.md) — description` 每一行对应一条记忆
- 大小限制：`MAX_INDEX_LINES = 200`，`MAX_INDEX_BYTES = 25_000`（`:34-35`）
- 超限截断 + 警告提示（`:295-300`）
- 作为 system message 注入到 Agent 上下文（`load_index()`, `:267-301`）

### 6.2 ~50 token 全局摘要

**文件**：`agent/memory/summary.py` + `persistent.py:303-315`

- `load_summary()` 调用 `build_summary()`（`summary.py:15`）
- 按 `importance` 降序 + `last_accessed_at` 升序排列（同 importance 下越早访问的越靠前）
- 截断到 `max_tokens=50`（`persistent.py:45`）
- 超出预算时追加 `... (use SearchMemory for details)` 提示

### 6.3 changelog 审计日志

**文件**：`agent/memory/persistent.py:848-854`（`_append_changelog()`）

```python
def _append_changelog(self, action, name, reason):
    changelog = self.memory_dir / "changelog.md"
    ts = self._now().isoformat(timespec="seconds")
    line = f"- [{ts}] {action} {name} → {reason}\n"
    with changelog.open("a", encoding="utf-8") as fh:
        fh.write(line)
```

格式：`- [<ISO timestamp>] <action> <name> -> <reason>`，与 git commit message 对齐，提供双重审计。

### 6.4 名称校验

**文件**：`agent/memory/persistent.py:36, 112-116`

```python
_VALID_NAME_RE = re.compile(r"^[a-z0-9-]+$")

def _validate_name(name):
    if not name or not _VALID_NAME_RE.match(name):
        return f"Invalid memory name '{name}': must be kebab-case ..."
```

所有公开 API（`save`/`archive`/`restore`/`resolve_conflict`/`revert`）在路径构造前都经过 `_validate_name()` 检查，防止路径遍历。

### 6.5 Git Worktree 感知的作用域

**文件**：`agent/memory/persistent.py:62-109`（`_find_scope_root()` + `_git_common_dir()`）

```python
def _find_scope_root(path):
    """Resolve the project scope root for a checkout.
    The scope root is the canonical repository root shared across git
    worktrees (Decision 5 / R1-Q10).
    """
    # walks up from path, resolves .git file → commondir → main worktree root
```

同一个 git 仓库的所有 worktree 共享一份 memory 存储（scope root = 主 worktree 的 repo root），不会因 worktree 切换而产生多份记忆。

---

## 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/memory/persistent.py` | PersistentMemory 主类：save、apply_judgment、decay_score、run_decay、archive、restore、_git_commit、resolve_conflict |
| `agent/memory/dedup.py` | MemoryDedupJudge：LLM 四分支判决（new/supplement/update/conflict） |
| `agent/memory/git_backend.py` | MemoryGitBackend：history / diff / revert（两阶段 commit） |
| `agent/memory/model.py` | MemoryEntry / MemoryHit 数据模型 |
| `agent/memory/summary.py` | build_summary：~50 token 重要性排序全局摘要 |
| `agent/tools/builtin/memory.py` | 5 个工具：SaveMemory / RecallMemory / SearchMemory / ResolveMemoryConflict / MemoryGitBackend |
| `docs/adr/ADR-0002-long-term-memory-reversibility.md` | ADR：mem0 对比、备选方案、最终决策、revisit conditions |
| `agent/tools/factory.py:71-110` | KNOWN_BUILTIN_TOOL_NAMES（确认 5 个 memory 工具在内置 38 中） |
