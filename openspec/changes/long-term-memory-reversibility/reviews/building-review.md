# Building Review: long-term-memory-reversibility

## Verdict

CHANGES_REQUESTED

核心功能（commit-before-write 可逆写入 / resolve_conflict / MemoryGitBackend / 14 个回归测试）已真实实现且测试通过，无阻塞性缺陷。存在 **1 个中等严重度问题**（resolve_conflict 文档化的"默认归档 name_b"契约未实现，task 2.1 未完全满足），另加若干低严重度健壮性/测试覆盖缺口，需修复后重审。

## Reviewer

- run id: subagent-review-ltm-reversibility-20260803
- 时间: 2026-08-03
- base: 3d87bfcd4d5381778032806b7cd82ad6ecb5dee5 (origin/master)
- head: bfcb055cf68bb4c17304946f29a54eb040e81b70

## Tasks Verification

- [x] **1.1 `_ensure_git()` 懒初始化** — `agent/memory/persistent.py:407-431` 实现；`__init__`（168-193 行）无副作用，`test_persistent.py::test_save_rejects_invalid_name`（invalid name 后 memory_dir 不存在）仍通过；`_ensure_git` 在 memory_dir 不存在时返回 False、不建目录。**确认**
- [x] **1.2 `_git_commit` helper** — `persistent.py:433-465`：`_run_git`（26-33 行）内联 `-c user.name="Asterwynd Memory" -c user.email="memory@asterwynd.local"`；`git add -A`（452 行）全目录快照；`git diff --cached --quiet`（456-458 行）区分 nothing-to-commit（安全返回）与 git 真坏（add/commit 失败 raise RuntimeError，462-464 行）。**确认**
- [x] **1.3 `save()` 覆盖分支写入前 commit** — `persistent.py:521-523`：`existing is not None` 时先 `_git_commit("update", name, "save-overwrite")` 再改字段、`_write_entry`。**确认**
- [x] **1.4 `apply_judgment()` 三分支写入前 commit** — supplement `persistent.py:575-576`、update `589-590`、conflict `604` 均先 commit 当前状态；conflict 打标后（609-614 行）不立即 commit，交由下一次破坏性写兜底（符合 grill Q4）。**确认**
- [x] **2.1 `resolve_conflict` API** — `persistent.py:620-672`：清除双方 conflict_with（649-650）、changelog resolve 事件（671）、可选归档 loser（652-665）。**⚠️ 部分未满足**：task 2.1 / design.md:44 / 工具描述均声明"默认 loser=name_b"，但 `if archive and loser:`（652 行）要求 loser 必须显式传入，`archive=True` 且 `loser=None` 时不做任何归档（见 Issue 1）。**
- [x] **2.2 `ResolveMemoryConflict` 工具** — `agent/tools/builtin/memory.py:206-268`：PascalCase 命名、`@tool_parameters`、`permission = AGENT_STATE_PERMISSION`、参数 name_a/name_b/loser/archive/reason。**确认**
- [x] **3.1 `MemoryGitBackend` 单工具 + action** — `agent/memory/git_backend.py:14-87`：history/diff/revert 三 action，PascalCase 类名；`MemoryGitBackendTool` 在 memory.py:270-342。**确认**
- [x] **3.2 config 开关 + factory 注册** — `agent/config.py:220`（`git_backend_enabled: bool = True` 字段）、`1265-1270`（`_parse_bool` 解析）；`agent/tools/factory.py:100-101`（KNOWN_BUILTIN_TOOL_NAMES 加入两工具）、`349-354` / `451-456`（构造列表，MemoryGitBackend 受开关控制）。已实证：`git_backend_enabled=False` 时工具不注册、`True`（默认）时注册。**确认**（开关路径无回归测试，见 Issue 3）
- [x] **3.3 revert 两步 commit** — `git_backend.py:60-85`：step 1 `_git_commit("revert", ...)` 先落盘当前态（73 行），`git checkout <commit> -- <name>.md` 回退正文（72 行），`_update_index` 重建索引（77-79 行），`_append_changelog` 记 revert（81 行），step 2 `_git_commit` 再 commit revert 产物（84 行）。`git log -- <name>.md` 即时可见 revert。**确认**
- [x] **4.1-4.9 回归测试** — `tests/agent/memory/test_reversibility.py` 共 14 个测试，覆盖 4.1（update/supplement pre-image）、4.2（revert 还原 + 两步 commit 即时可见）、4.3（resolve 清标记 + 归档 loser）、4.4（git 失败 abort 写保护）、4.5（fresh repo 首次写）、4.6（load_entries 不受 git init 影响）、4.7（revert 索引跟随）、4.8（内联 identity）、4.9（两工具注册 + 调用）。**确认**
- [x] **5.1 benchmark smoke** — 已勾选，但本环境无外网 LLM API，无法用真实 LLM 复现 `uv run asterwynd run`；`run` 命令无 `--agent fake` 选项，无法在本环境跑 fake 冒烟。**间接证据**：全量 pytest 1793 通过（含 AgentLoop / factory / 工具层测试），工具注册未回归。该条无法在本环境独立复核，建议主 agent 提供运行记录。
- [x] **5.2 全量 pytest 无新增失败** — 1793 passed, 2 failed, 7 skipped。两个失败均为环境问题（tree-sitter Java grammar 缺失、docker sandbox 不可用），与本 change 无关（见 Test Results）。**确认**

## Issues

### 中 Issue 1: `resolve_conflict` 文档化的"默认归档 name_b"契约未实现（task 2.1 未完全满足）
- 文件:行号 证据：
  - `agent/memory/persistent.py:652` — `if archive and loser:`，loser 为 falsy（None）时走 else 分支，**不归档任何一方**
  - `openspec/changes/long-term-memory-reversibility/tasks.md:8` — task 2.1 写明"可选归档 loser（**默认 name_b**）"
  - `openspec/changes/long-term-memory-reversibility/design.md:44` — "`archive=True` 时归档 `loser`（**默认 `loser=name_b`**）"
  - `agent/tools/builtin/memory.py:230` — 工具参数描述 "Which memory to archive when archive=True (**default name_b**)"
- 描述：三处文档（task / design / 工具 schema）声明 `archive=True` 且未传 loser 时默认归档 name_b，但实现只在 `loser` 为 truthy 时归档。已实证：`resolve_conflict("a","b", archive=True)` 返回 "Memory 'a' and 'b' conflict resolved."，`b.md` 仍存在、`archive/b.md` 不存在——调用方（agent 或用户）依据工具描述预期 name_b 被归档，实际静默未归档。spec delta 写的是 "loser SHALL be identified by an explicit loser parameter"，与实现一致，但与 design/task/工具描述矛盾。
- 建议：二选一，且必须保持三处一致：(a) 实现默认——`loser = loser or name_b`（在 `archive=True` 时）；或 (b) 修正文档——把 task 2.1 / design.md:44 / 工具描述改为 "archive=True 时归档 loser（必须显式指定，默认不归档）"。推荐 (a)，与 task 2.1 原文契约一致。补一条默认归档的回归测试。

### 低 Issue 2: MemoryGitBackend history/diff/revert 未校验 name（`_validate_name`）
- 文件:行号 证据：`agent/memory/git_backend.py:40`（`f"{name}.md"`）、`:50`、`:72`；对比 `agent/memory/persistent.py:112-116` `_validate_name` 在 save/apply_judgment/resolve_conflict 均校验
- 描述：MemoryGitBackend 三个方法及 MemoryGitBackendTool 均不校验 name。已实证路径穿越名 `"../x"` 会被 git 自身拒绝（"outside repository"），`revert("../escape")` 因 `_load_entry_by_name` 找不到而返回错误——**无任意文件写/读漏洞**。但错误信息是晦涩的 git 原文，且与库内其余工具（非法名返回统一中文错误）行为不一致。属于健壮性/一致性缺口。
- 建议：在 `history`/`diff`/`revert` 入口用 `_validate_name(name)` 校验，返回统一错误。

### 低 Issue 3: `git_backend_enabled=False` 开关路径无回归测试
- 文件:行号 证据：`agent/tools/factory.py:350-354`、`451-456`（开关 gating）；测试仅 `tests/agent/memory/test_reversibility.py` 引用新工具
- 描述：开关功能实现正确（已实证），但无测试锁定 `git_backend_enabled=False` 时 MemoryGitBackend 工具不注册、且不影响 ResolveMemoryConflict 注册；config 解析新字段也无测试。task 3.2 实现未测。
- 建议：补一个 factory 层测试（True/False 两种配置下工具集合断言），锁定开关契约。

### 低 Issue 4: `resolve_conflict("x","x")` 自解无防护
- 文件:行号 证据：`agent/memory/persistent.py:620-672`
- 描述：当 `name_a == name_b` 时，a/b 为同一 entry；`archive=True` 时先写 archive/name.md、unlink 活动文件、移除索引，随后 `_write_entry(winner_entry)` 又把同一 name 写回活动目录——归档的同时复活同一条，语义混乱。实际调用方不会故意传同名，属边界健壮性缺口。
- 建议：入口校验 `name_a != name_b`，否则返回错误。

### 低 Issue 5: resolve commit message 与 changelog 分隔符不一致（cosmetic）
- 文件:行号 证据：`agent/memory/persistent.py:647` commit message 用 `f"{name_a}<->{name_b}"`（无空格）；`:671` changelog 用 `f"{name_a} <-> {name_b}"`（有空格）
- 描述：`apply_judgment` conflict 分支（615 行）commit 与 changelog 均无空格，resolve 分支 commit 无空格、changelog 有空格——与"commit message 与 changelog 行对齐"的验收口径略不一致。纯 cosmetic。
- 建议：统一格式（建议都带空格或都无空格）。

## Test Results

```
$ uv run pytest tests/agent/memory/test_reversibility.py tests/agent/memory/test_persistent.py tests/agent/tools/test_memory_tools.py -q
67 passed in 3.12s

$ uv run pytest tests/agent/memory/ tests/agent/tools/ -q
515 passed in 24.35s

$ uv run pytest -q
1793 passed, 2 failed, 7 skipped in 164.95s
```

- 2 个失败均为环境问题，与本 change 无关：
  - `tests/agent/code_intelligence/test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols` — tree-sitter Java grammar 在本环境缺失（解析返回空符号列表）。
  - `tests/agent/tools/test_sandbox_backends.py::test_contract[docker]` — docker sandbox 不可用。
- 额外实证（临时脚本）：
  - `git init` 在已存在父仓库的子目录中会建立独立仓库根（`git rev-parse --show-toplevel` 返回 memory_dir 自身），grill 风险项"commit 写进父仓库"不成立。
  - `resolve_conflict("a","b", archive=True)`（未传 loser）不归档 b（Issue 1 复现）。
  - `MemoryGitBackend.history("../x")` / `revert("../escape")` 均被 git 或 entry 加载挡回，无越界写。
  - `MemoryConfig(git_backend_enabled=False)` 使 factory 不注册 MemoryGitBackend、仍注册 ResolveMemoryConflict。

## 结论

实现整体高质量：commit-before-write 的 abort 写保护、nothing-to-commit 区分、内联 identity、懒初始化、conflict 打标后不立即 commit、revert 两步 commit + 索引重建均严格符合 grill 决策与 spec；14 个回归测试覆盖 4.1-4.9 且全部通过；安全检查（命令参数列表传递无注入、git pathspec 约束路径穿越、load_entries 非递归 glob 排除 `.git`）均确认无漏洞；CI 配置未被弱化。

唯一中等问题：**task 2.1 / design.md / 工具描述声明的"默认归档 name_b"契约未实现**（`persistent.py:652` 要求 loser 显式传入），属文档-代码契约违背，需修复后重审。其余为低严重度健壮性/测试覆盖项（MemoryGitBackend name 校验、开关路径测试、同名自解防护、commit/changelog 分隔符一致性），建议一并修复。

修复清单：
1. [中] resolve_conflict 实现"默认 loser=name_b"（或同步修正 task 2.1 / design.md:44 / 工具描述三处文档），并补默认归档回归测试。
2. [低] MemoryGitBackend history/diff/revert 入口加 `_validate_name` 校验。
3. [低] 补 `git_backend_enabled=False` 的 factory 开关回归测试。
4. [低] resolve_conflict 校验 `name_a != name_b`。
5. [低] 统一 resolve commit message 与 changelog 分隔符格式。
