# Design: 长期记忆可逆写入 — git 管理的 commit-before-write 快照 + resolve_conflict

## Context

#75 长期记忆做深已实现写时去重三分支。LLM 误判时内容永久丢失（update 无 pre-image、supplement 污染无 undo、conflict_with 只增不减），`memory_dir` 在项目 git 仓库外、无 VCS 兜底。本 change 让记忆写入可逆、冲突可解除。

完整方案对比见 [ADR-0002-long-term-memory-reversibility](../adr/ADR-0002-long-term-memory-reversibility.md)。本 design 聚焦实现。

## Goals / Non-Goals

Goals:
- 破坏性写（update/supplement/save 覆盖）前，旧状态先落盘为可恢复快照。
- 提供 resolve_conflict：清除矛盾双方 conflict_with 标记 + changelog 记录 resolve 事件。
- changelog 审计从 action 级提升到内容级（旧内容可从 git 历史还原）。
- 复用 git 原生能力（log/diff/checkout）做恢复，不自造版本格式。

Non-Goals:
- 不改变 LLM 三分支去重语义（dedup.py 不动）。
- 不做 mem0 ADD-only（ADR-0002 拒绝，需重写 read 路径）。
- 不把 `~/.asterwynd/` 纳入项目 git 仓库。

## Decisions

### Decision 1: memory_dir 独立 git init + commit-before-write（写保护）

- **懒初始化**：`PersistentMemory.__init__` 不做任何副作用。首次破坏性写（save 覆盖 / supplement / update / conflict / resolve_conflict）实际落盘前，`git init` memory_dir（幂等，已 init 则跳过）。保护现有测试 test_persistent.py:209-212（invalid name 后 memory_dir 必须不存在）。
- **commit-before-write**：所有破坏性写路径在写入**前**先 commit 当前状态，把 target 旧状态（+ incoming 不存在 / 待清标记态）一起快照：
  - `save()` 当 `existing is not None`（覆盖更新）→ 先 commit。
  - `apply_judgment()` supplement / update 分支 → 先 commit target 旧状态。
  - `apply_judgment()` conflict 分支 → 先 commit 当前状态（快照 target 旧状态 + incoming 不存在），**打标后不立即 commit**，交给下一次破坏性写的 commit-before-write 兜底。
  - `resolve_conflict()` 清标记前 → 先 commit（被解除的 conflict 标记态必须进历史）。
  - `MemoryGitBackend.revert()` → 两步 commit（先 commit 当前态作为撤销凭据，revert 产物再 commit 落盘，见 Decision 3）。
- **commit 失败 = 写保护（abort）**：commit 失败（permission / git 损坏 / identity 缺失）则**中止写入**，宁可写失败不丢旧内容。区分"nothing to commit"（fresh repo 无旧状态可快照，**安全继续**）与"git 真坏"（abort）。
- **内联 git identity**：`git -c user.name="Asterwynd Memory" -c user.email="memory@asterwynd.local" commit`，永不依赖全局/仓库配置（CI validate job 无 user.name/email）。
- **commit message 与 changelog 对齐**：`<action> <name> → <reason>`。审计叙事为"checkout commit N 撤销写 N"（commit N 内容 = 写 N 前状态，revert 语义正确）。
- **git add 范围**：`git add -A -- <memory_dir>/`，全目录快照（条目 + MEMORY.md + changelog + archive 都有历史）。接受 touch 元数据 / 索引变更夹带进同一 commit 的噪声（#75 每次检索重写文件的设计所致，非本 change 引入）。

为什么 commit-before-write 而非 write 后 commit：写入后崩溃则新旧都没了，无法恢复。必须先提交旧状态，再写。

### Decision 2: resolve_conflict API + 工具（含 loser 参数）

- `PersistentMemory.resolve_conflict(name_a, name_b, loser=None, archive=False, reason="")`：
  - 从双方 `conflict_with` 移除对方。
  - changelog 记录 `- [时间] resolve <name_a> <-> <name_b> → reason`。
  - `archive=True` 时归档 `loser`（默认 `loser=name_b`），append-only 历史保留。
  - 清标记前先 commit-before-write（Decision 1）。
  - 返回确认消息。
- `agent/tools/builtin/memory.py` 暴露 `ResolveMemoryConflict` 工具（PascalCase，符合 #75 R1-Q8 库内约定），参数 `name_a` / `name_b` / `loser` / `archive` / `reason`。权限走 `AGENT_STATE_PERMISSION`（与 SaveMemory 同级）。

### Decision 3: MemoryGitBackend（单工具 + action 参数）

- `agent/memory/git_backend.py` 封装 git 操作，**单个工具 + action 参数**：`MemoryGitBackend(action="history"|"diff"|"revert", name, commit_a, commit_b)`。
  - `history(name)`：`git log -- <name>.md`。
  - `diff(commit_a, commit_b, name)`：`git diff <a> <b> -- <name>.md`。
  - `revert(name, commit)`：**两步 commit**——
    1. **第一步**：revert 是破坏性写，先 commit 当前态（快照被覆盖的当前版本，作为撤销 revert 的凭据）。
    2. `git checkout <commit> -- <name>.md` 回退正文，读取回退后 frontmatter，`_update_index` 重建 MEMORY.md 索引行，changelog 记录 `- [时间] revert <name> → <commit>`。
    3. **第二步**：revert 产物（正文回退 + 索引重建 + changelog）再 commit 一次，使 revert 历史即时可见、`git log -- <name>.md` 干净（v1→v2→v1 一条线），且下一次破坏性写快照的是 revert 后干净状态、不夹带 revert 产物。
- 作为独立工具注册（PascalCase），默认开启；`agent/config.py` 提供开关。revert 走 `AGENT_STATE_PERMISSION`。

### Decision 4: load_entries 不污染

- memory_dir 顶层 `glob("*.md")` 非递归（现状已是），`.git/`、`archive/` 都在子目录，天然不进加载。changelog.md 虽匹配 `*.md` 但无 frontmatter 被 `_parse_file` 跳过。
- 新增测试断言：git init 后 `load_entries()` 结果与 init 前一致。

## Pre-Implementation Review

本 change 为 #99，源自 #75 grill Round 2 Decision 2 / R1-Q4。已通过 ADR-0002 记录三方案对比（mem0 ADD-only / 侧车 / git），用户确认 git 方案。

2026-08-03 独立 subagent grill（run `subagent-grill-ltm-reversibility-20260803`，见 `reviews/grill-design.md`）逐项挑战全部 4 条 Decision，产出 5 条 Confirmed + 11 条 Open Questions。用户停轮拍板全部 11 条（记录于 grill-design.md `## User Confirmation`），核心结论：

- commit 失败 → **abort 写保护**（非降级仍写）。
- 内联 git identity（`-c user.name/-c user.email`），CI 无全局配置也可提交。
- git init **懒初始化**（保护 test_persistent.py:209-212）。
- conflict / resolve / revert 均纳入 commit-before-write 集。
- resolve_conflict 增加 `loser` 参数。
- MemoryGitBackend 单工具 + action 参数，PascalCase 命名。
- revert 后**重建索引行**保证正文与 MEMORY.md 一致；changelog 保留审计不跟随回退。
- `git add -A -- <memory_dir>/` 全目录快照，接受 touch/索引噪声。
- 并发丢更新登记 known-debt，本次不引入锁。

## Reference Implementation Research

- status: enabled
- 详见 proposal.md `## Reference Implementation Research`。要点：mem0 V3 ADD-only（拒绝原因见 ADR-0002）；Letta Context Repositories git 管理（本方案直接对齐）；Zep 时序失效（作"不删除"的另一形态参考）。
- design impact: git 管理是最小成本路径；conflict 解除仍需独立 API。

## Risks / Trade-offs

- **[git 不可用 / commit 失败]**: **abort 写保护**——commit 失败则中止写入，宁可写失败不丢旧内容。区分 nothing-to-commit（fresh repo 安全继续）与 git 真坏（abort）。
- **[git identity 缺失]**: 内联 `-c user.name/-c user.email`，CI validate 无全局配置也可提交。
- **[.git 目录出现于用户主目录]**: 文档说明；属 `~/.asterwynd/` 独立仓库，不入项目仓库。
- **[commit 碎片化 + touch/索引噪声]**: 每次破坏性写一条 commit，`git add -A` 全目录快照夹带 touch 元数据 / MEMORY.md / changelog 变更。可接受（#75 每次检索重写文件的设计所致，非本 change 引入）。
- **[conflict_with 标记累积仍存在]**: resolve_conflict API 主动解除；不解决的话标记仍只增不减（本 change 提供手段，不自动清理）。
- **[并发丢更新未被 git 兜底]**: git 可逆性解决误判恢复、不解决并发丢更新（#75 已知债，read-modify-write 无 flock）。登记 known-debt，本次不引入锁。

## Testing Strategy

- 单测（`tests/agent/memory/`）：
  - `test_save_update_creates_git_commit`：save 覆盖前先 commit，`git log` 有旧版本。
  - `test_apply_judgment_update_supplement_preimage`：update/supplement 前旧 body 在 git 历史可恢复。
  - `test_revert_restores_old_body`：revert 后 body 回到旧版本，changelog 有 revert 事件。
  - `test_revert_syncs_index`：revert 后 MEMORY.md 索引行与正文 description 一致。
  - `test_resolve_conflict_clears_flags`：resolve 后双方 conflict_with 清空 + changelog resolve 事件。
  - `test_git_unavailable_aborts_write`：git 失败时中止写入（abort 写保护），旧内容保留。
  - `test_nothing_to_commit_first_write`：fresh repo 首次写安全继续（nothing to commit 非失败）。
  - `test_load_entries_unaffected_by_git`：git init 后 load_entries 结果不变。
  - `test_commit_uses_inline_identity`：内联 -c identity，CI 无全局配置也可提交。
- 工具层（`tests/agent/tools/`）：ResolveMemoryConflict 工具注册 + 调用；MemoryGitBackend 工具 history/diff/revert 调用。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/memory/persistent.py` | commit-before-write + resolve_conflict + 懒初始化 git init |
| `agent/memory/git_backend.py` | MemoryGitBackend（history/diff/revert + 索引重建） |
| `agent/tools/builtin/memory.py` | ResolveMemoryConflict 工具 + MemoryGitBackend 工具 |
| `agent/tools/factory.py` | 新工具注册（KNOWN_BUILTIN_TOOL_NAMES + 构造列表） |
| `agent/config.py` | MemoryGitBackend 开关 |
| `~/.asterwynd/projects/<hash>/memory/` | git init + `.git` 目录（懒初始化） |
| `docs/adr/ADR-0002` | 新增 |
| `docs/known-debt.md` | 并发丢更新债务登记（受保护，需 workflow-events） |
| 测试 | `tests/agent/memory/`、`tests/agent/tools/` |
