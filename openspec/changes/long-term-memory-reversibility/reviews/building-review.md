# Building Review: long-term-memory-reversibility

## Verdict

CHANGES_REQUESTED (Round 2)

Round 1 的 5 项修复全部正确落地且测试通过（见 Round 1 修复复核）。但本轮回审在 `resolve_conflict` 的 `loser` 归档路径上发现 **1 个新的中等安全漏洞**：`loser` 参数未做 `_validate_name` 校验（`name_a`/`name_b` 都校验了，`loser` 没有），导致**路径穿越——可在 memory_dir 之外任意写 `.md` 文件 + 删除任意 `.md` 文件**（已实证）。需修复后重审。

## Reviewer

- run id: subagent-review-ltm-reversibility-20260803
- 时间: 2026-08-03
- base: 3d87bfcd4d5381778032806b7cd82ad6ecb5dee5 (origin/master)
- head: 69dbe007da9f3e671feefc6838ea3166e5ec41b0 (Round 1 修复 commit)
- Round 1 审阅 head: bfcb055cf68bb4c17304946f29a54eb040e81b70

## Round 1 修复复核（git diff bfcb055..HEAD）

- [x] **1. resolve_conflict 默认 loser=name_b** — `persistent.py:654-656` 改为 `if archive: loser = loser or name_b`，与 task 2.1 / design.md:44 / 工具描述契约一致。新增 `test_4_3_resolve_default_loser_archives_name_b`（未传 loser 时归档 name_b、a 保留）通过。**确认**
- [x] **2. MemoryGitBackend name 校验** — `git_backend.py:38-42` 新增 `_check_name`（复用 `_validate_name`），history/diff/revert 三入口均校验。新增 `test_4_9_git_backend_rejects_invalid_name` 通过。**确认**
- [x] **3. `git_backend_enabled=False` factory 开关回归测试** — 新增 `TestGitBackendConfig::test_3_2_git_backend_disabled_skips_tool`（False 时无 MemoryGitBackend、仍有 ResolveMemoryConflict；默认时两者都有）。**确认**
- [x] **4. resolve_conflict 同名自解防护** — `persistent.py:638-639` 新增 `if name_a == name_b: return Error`。新增 `test_4_3_resolve_same_name_rejected` 通过。**确认**
- [x] **5. commit/changelog 分隔符统一** — `persistent.py:649`（commit message）与 `:675`（changelog）均为 `f"{name_a} <-> {name_b}"`（带空格）。**确认**

## Tasks Verification（现状全量）

- [x] **1.1 `_ensure_git()` 懒初始化** — `agent/memory/persistent.py:407-431`；`__init__` 无副作用；invalid name 后 memory_dir 不创建（test_persistent.py 回归通过）。**确认**
- [x] **1.2 `_git_commit` helper** — `persistent.py:433-465`：内联 `-c` identity（26-33 行）、`git add -A` 全目录快照（452 行）、`git diff --cached --quiet` 区分 nothing-to-commit 与 git 真坏（456-464 行）。**确认**
- [x] **1.3 `save()` 覆盖分支写入前 commit** — `persistent.py:521-523`。**确认**
- [x] **1.4 `apply_judgment()` supplement/update/conflict 写入前 commit** — `persistent.py:575-576/589-590/604`；conflict 打标后不立即 commit（交下次破坏性写兜底）。**确认**
- [x] **2.1 `resolve_conflict` API** — `persistent.py:620-676`：清标记 + changelog resolve 事件 + 可选归档 loser（默认 name_b）。**⚠️ 新发现安全漏洞**：`loser` 参数未 `_validate_name` 校验，可路径穿越（见 Issue 6）。**
- [x] **2.2 `ResolveMemoryConflict` 工具** — `agent/tools/builtin/memory.py:206-268`：PascalCase、AGENT_STATE_PERMISSION、参数齐全。**确认**
- [x] **3.1 `MemoryGitBackend` 单工具 + action** — `agent/memory/git_backend.py:14-87`：history/diff/revert + `_check_name` 校验 + 两步 commit revert。**确认**
- [x] **3.2 config 开关 + factory 注册** — `agent/config.py:220/1265-1270`；`factory.py:100-101/349-354/451-456`；开关路径已有回归测试（Round 1 修复项 3）。**确认**
- [x] **3.3 revert 两步 commit** — `git_backend.py:60-85`：step1 快照当前态 → checkout 回退 → `_update_index` 重建 → changelog revert 事件 → step2 再 commit。**确认**
- [x] **4.1-4.9 回归测试** — `tests/agent/memory/test_reversibility.py` 现 18 个测试，覆盖全部 4.x + Round 1 新增 5 项。**确认**
- [x] **5.1 benchmark smoke** — 本环境无外网 LLM、`run` 无 fake agent 选项，无法独立复核；间接证据：全量 pytest 1798 通过（含 AgentLoop/factory/工具层）。建议主 agent 提供运行记录。
- [x] **5.2 全量 pytest** — 1798 passed, 1 failed（tree-sitter Java grammar 环境缺失，与本 change 无关）。**确认**

## Issues

### 中 Issue 6（新，Round 2）: `resolve_conflict` 的 `loser` 参数未校验 → 路径穿越（任意 `.md` 文件写 + 删）
- 文件:行号 证据：
  - `agent/memory/persistent.py:654-668` — `if archive:` 分支直接用 `loser` 构造路径：`:657` `self._entry_path(loser, archived=True)`、`:661` `_write_entry_to(loser_entry, ...)`、`:662-666` `loser_path.unlink()`；`loser` 全程无 `_validate_name` 校验
  - 对比 `:635-637` — `name_a`/`name_b` 都做了 `_validate_name` 校验，唯独 `loser` 漏掉
  - `agent/tools/builtin/memory.py:218-231` — 工具 schema 对 `loser` 无校验（只描述 "default name_b"），`execute` 直传
- 描述：`loser` 可含 `..` 路径穿越。已实证（临时脚本）：
  - **任意写**：`resolve_conflict("a","b", loser="../../../victim", archive=True)` → 在 `<tmp>/projects/victim.md`（memory_dir 之外）写入条目 b 的 frontmatter+body。
  - **任意删**：`loser="../secret"` → `_entry_path(loser)` = `memory_dir/../secret.md` = `<hash>/secret.md`，`loser_path.unlink()` 删除该文件（已实证 victim 被删）。
  - **误删无关记忆**：`loser="c"`（存在但非 a/b）→ 删除 `c.md`、把 b 内容写成 `archive/c.md`（内容错位 + 数据丢失）。
- 影响：`ResolveMemoryConflict` 是 agent 可用工具（AGENT_STATE_PERMISSION）。恶意/被注入的 agent 或用户传入构造的 `loser`，可在 `~/.asterwynd` 下任意 `.md` 文件写 + 删——正中本 change 要防的"内容丢失"。
- 建议：`resolve_conflict` 入口对 `loser` 做 `_validate_name` 校验，且限定 `loser in (None, name_a, name_b)`（语义上 loser 必须是矛盾双方之一）；工具 schema 同步约束。补路径穿越回归测试（`loser="../../x"` 必须返回 Error、不写不删）。

### 中 Issue 1（Round 1，已修复）: `resolve_conflict` 默认归档 name_b
- `persistent.py:654-656` 已实现 `loser = loser or name_b`；`test_4_3_resolve_default_loser_archives_name_b` 通过。**已关闭**

### 低 Issue 2（Round 1，已修复）: MemoryGitBackend name 校验
- `git_backend.py:38-42` `_check_name` 已加；history/diff/revert 校验；`test_4_9_git_backend_rejects_invalid_name` 通过。**已关闭**

### 低 Issue 3（Round 1，已修复）: factory 开关回归测试
- `test_3_2_git_backend_disabled_skips_tool` 已加。**已关闭**

### 低 Issue 4（Round 1，已修复）: `resolve_conflict("x","x")` 自解防护
- `persistent.py:638-639` 已加；`test_4_3_resolve_same_name_rejected` 通过。**已关闭**

### 低 Issue 5（Round 1，已修复）: commit/changelog 分隔符统一
- `persistent.py:649/675` 均带空格。**已关闭**

## Test Results

```
$ uv run pytest tests/agent/memory/test_reversibility.py tests/agent/memory/test_persistent.py tests/agent/tools/test_memory_tools.py -q
71 passed in 2.69s        （Round 2，含 Round 1 修复后）

$ uv run pytest tests/agent/memory/test_reversibility.py -q
18 passed in 1.99s

$ uv run pytest tests/agent/memory/ tests/agent/tools/ -q
519 passed in 15.18s

$ uv run pytest -q
1798 passed, 1 failed, 7 skipped in 102.83s
```

- 唯一失败 `tests/agent/code_intelligence/test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols` 为环境问题（tree-sitter Java grammar 缺失），与本 change 无关。
- 额外实证（临时脚本）：
  - Round 1 默认 loser 修复：`resolve_conflict("a","b", archive=True)` 归档 name_b、a 保留、archive/b.md 存在。
  - **新安全漏洞复现**：`loser="../../../victim"` → 在 memory_dir 外写 `projects/victim.md`；`loser="../secret"` → 删除 `<hash>/secret.md`；`loser="c"` → 删除无关 `c.md` 并把 b 内容写成 `archive/c.md`。
  - `git init` 在父仓库子目录建立独立仓库根，grill"commit 写进父仓库"风险不成立。

## 结论

Round 1 的 5 项修复**全部正确落地**，均有对应回归测试并通过；全量 pytest 1798 通过（唯一失败为环境问题）。commit-before-write / resolve / revert 核心机制经复验仍符合 grill 决策与 spec。

但回审发现 **1 个新的中等安全漏洞**：`resolve_conflict` 的 `loser` 参数未校验，路径穿越可在 memory_dir 外任意写/删 `.md` 文件（已实证含任意删）。该漏洞经 `ResolveMemoryConflict` 工具对 agent 可达，且与本 change 防内容丢失的目标直接冲突，**必须修复后才能合入**。修复很小（`loser` 加 `_validate_name` + 限定 `loser in (None, name_a, name_b)` + 回归测试）。

修复清单：
1. [中/安全] `resolve_conflict` 校验 `loser`：`_validate_name(loser)` + `loser in (None, name_a, name_b)`；工具 schema 同步；补路径穿越回归测试（`loser="../../x"` 返回 Error、不写不删）。
