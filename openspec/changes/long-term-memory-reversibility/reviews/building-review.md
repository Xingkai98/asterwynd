# Building Review: long-term-memory-reversibility

## Verdict

PASS (Round 3，封顶轮)

三轮审阅闭环完成：Round 1 的 5 项修复 + Round 2 的安全漏洞修复全部正确落地并有回归测试。无未解决的中等以上问题；唯一剩余项（task 5.1 真实 LLM benchmark smoke）为本环境无法独立复核的环境限制，有全量 pytest 作为间接证据。核心功能真实存在、测试全绿（1800 passed，唯一失败为 tree-sitter Java grammar 环境问题，与本 change 无关）、无安全漏洞、无 CI 弱化。**批准合入**。

## Reviewer

- run id: subagent-review-ltm-reversibility-20260803
- 时间: 2026-08-03
- base: 3d87bfcd4d5381778032806b7cd82ad6ecb5dee5 (origin/master)
- head: 1f49cc03686584bce3c75be64a7b9080b7e68ff6 (Round 2 修复 commit)
- Round 1 审阅 head: bfcb055cf68bb4c17304946f29a54eb040e81b70
- Round 1 修复 head: 69dbe007da9f3e671feefc6838ea3166e5ec41b0

## Round 1 修复复核（git diff bfcb055..69dbe00，全部确认）

- [x] **1. resolve_conflict 默认 loser=name_b** — `persistent.py:654-656` `loser = loser or name_b`，与 task 2.1 / design.md:44 / 工具描述契约一致；`test_4_3_resolve_default_loser_archives_name_b` 通过。**确认**
- [x] **2. MemoryGitBackend name 校验** — `git_backend.py:38-42` `_check_name`（复用 `_validate_name`），history/diff/revert 三入口校验；`test_4_9_git_backend_rejects_invalid_name` 通过。**确认**
- [x] **3. `git_backend_enabled=False` factory 开关回归测试** — `TestGitBackendConfig::test_3_2_git_backend_disabled_skips_tool` 通过。**确认**
- [x] **4. resolve_conflict 同名自解防护** — `persistent.py:638-639`；`test_4_3_resolve_same_name_rejected` 通过。**确认**
- [x] **5. commit/changelog 分隔符统一** — `persistent.py:649/675` 均带空格。**确认**

## Round 2 修复复核（git diff 69dbe00..1f49cc0，全部确认）

- [x] **6. [中/安全] resolve_conflict 的 loser 路径穿越漏洞修复** — `persistent.py:654-662`：`loser = loser or name_b` 后紧跟校验 `if _validate_name(loser) is not None or loser not in (name_a, name_b): return Error`。loser 必须是合法 kebab-case 名且为矛盾双方之一。工具 schema（`memory.py:227-231`）同步约束 "Must be one of name_a or name_b."。**确认**

## Tasks Verification（现状全量）

- [x] **1.1 `_ensure_git()` 懒初始化** — `agent/memory/persistent.py:407-431`；`__init__` 无副作用；invalid name 后 memory_dir 不创建（test_persistent.py 回归通过）。**确认**
- [x] **1.2 `_git_commit` helper** — `persistent.py:433-465`：内联 `-c` identity（26-33 行）、`git add -A` 全目录快照（452 行）、`git diff --cached --quiet` 区分 nothing-to-commit 与 git 真坏（456-464 行）。**确认**
- [x] **1.3 `save()` 覆盖分支写入前 commit** — `persistent.py:521-523`。**确认**
- [x] **1.4 `apply_judgment()` supplement/update/conflict 写入前 commit** — `persistent.py:575-576/589-590/604`；conflict 打标后不立即 commit（交下次破坏性写兜底）。**确认**
- [x] **2.1 `resolve_conflict` API** — `persistent.py:620-676`：清标记 + changelog resolve 事件 + 可选归档 loser（默认 name_b，已校验）。**确认**
- [x] **2.2 `ResolveMemoryConflict` 工具** — `agent/tools/builtin/memory.py:206-268`：PascalCase、AGENT_STATE_PERMISSION、参数齐全。**确认**
- [x] **3.1 `MemoryGitBackend` 单工具 + action** — `agent/memory/git_backend.py:14-87`：history/diff/revert + `_check_name` 校验 + 两步 commit revert。**确认**
- [x] **3.2 config 开关 + factory 注册** — `agent/config.py:220/1265-1270`；`factory.py:100-101/349-354/451-456`；开关路径有回归测试。**确认**
- [x] **3.3 revert 两步 commit** — `git_backend.py:60-85`：step1 快照当前态 → checkout 回退 → `_update_index` 重建 → changelog revert 事件 → step2 再 commit。**确认**
- [x] **4.1-4.9 回归测试** — `tests/agent/memory/test_reversibility.py` 现 20 个测试，覆盖 4.x 全部 + Round 1 新增 5 项 + Round 2 新增 2 项安全回归。**确认**
- [x] **5.1 benchmark smoke** — 本环境无外网 LLM、`run` 无 fake agent 选项，无法独立复核（环境限制，非实现缺失）。间接证据：全量 pytest 1800 通过（含 AgentLoop/factory/工具层）。建议主 agent 保留该条的运行记录。
- [x] **5.2 全量 pytest** — 1800 passed, 1 failed（tree-sitter Java grammar 环境缺失，与本 change 无关）。**确认**

## Issues

### 中 Issue 6（Round 2，已修复）: `resolve_conflict` 的 `loser` 参数路径穿越
- `persistent.py:654-662` 已加 `_validate_name(loser)` + `loser not in (name_a, name_b)` 校验，返回 Error 且不写不删；工具 schema（`memory.py:227-231`）同步约束。新增 `test_4_3_resolve_rejects_path_traversal_loser`、`test_4_3_resolve_rejects_third_party_loser` 通过。**已关闭**
- 本 reviewer 独立复现验证：`loser="../../../victim"`（穿越写）、`loser="../secret"`（穿越删）、`loser="c"`（误删无关记忆）三个向量全部返回 Error，`victim.md`/`secret.md`/`c.md` 均未受损；合法默认 `archive=True` 未传 loser 仍正确归档 name_b。

### 中 Issue 1（Round 1，已修复）: `resolve_conflict` 默认归档 name_b
- `persistent.py:654-656` 已实现；`test_4_3_resolve_default_loser_archives_name_b` 通过。**已关闭**

### 低 Issue 2（Round 1，已修复）: MemoryGitBackend name 校验
- `git_backend.py:38-42` `_check_name` 已加；`test_4_9_git_backend_rejects_invalid_name` 通过。**已关闭**

### 低 Issue 3（Round 1，已修复）: factory 开关回归测试
- `test_3_2_git_backend_disabled_skips_tool` 已加。**已关闭**

### 低 Issue 4（Round 1，已修复）: `resolve_conflict("x","x")` 自解防护
- `persistent.py:638-639` 已加；`test_4_3_resolve_same_name_rejected` 通过。**已关闭**

### 低 Issue 5（Round 1，已修复）: commit/changelog 分隔符统一
- `persistent.py:649/675` 均带空格。**已关闭**

## Test Results

```
$ uv run pytest tests/agent/memory/test_reversibility.py -q
20 passed in 4.73s        （Round 2 修复后，含 2 个新增安全回归测试）

$ uv run pytest tests/agent/memory/ tests/agent/tools/ -q
521 passed in 28.26s

$ uv run pytest -q
1800 passed, 1 failed, 7 skipped in 107.73s
```

- 唯一失败 `tests/agent/code_intelligence/test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols` 为环境问题（tree-sitter Java grammar 缺失），与本 change 无关。
- 额外实证（临时脚本，Round 2 修复后）：
  - `resolve_conflict("a","b", loser="../../../victim", archive=True)` → Error，memory_dir 外无 `victim.md` 写出，a/b 完好。
  - `resolve_conflict("a","b", loser="../secret", archive=True)` → Error，`<hash>/secret.md` 未被删除。
  - `resolve_conflict("a","b", loser="c", archive=True)` → Error，无关 `c.md` 未被删除。
  - `resolve_conflict("a","b", archive=True)` → 默认归档 name_b，a 保留，`archive/b.md` 存在。
  - `git init` 在父仓库子目录建立独立仓库根，grill"commit 写进父仓库"风险不成立。

## 结论

三轮审阅闭环完成，最终 **PASS**。

- **正确性**：commit-before-write（save 覆盖 / supplement / update / conflict / resolve / revert）、nothing-to-commit 区分、abort 写保护、内联 identity、懒初始化、conflict 打标后不立即 commit、revert 两步 commit + 索引重建均严格符合 grill 决策与 spec。
- **安全性**：命令参数以列表传递无 shell 注入；git pathspec 约束路径穿越；`load_entries` 非递归 glob 排除 `.git`/`archive`；Round 2 修复后 `loser` 路径穿越（任意写/删 `.md`）已被 `_validate_name` + 白名单拦截。三轮共发现并修复 1 个中等问题（默认 loser 契约）+ 1 个中等安全漏洞（loser 路径穿越）+ 4 个低严重度项，全部有关回归测试。
- **测试覆盖**：20 个 reversibility 回归测试 + memory/tools 521 passed + 全量 1800 passed（唯一失败为环境问题）。CI 配置未被弱化。
- **收尾依赖**：tasks 6.1-6.4（spec sync / 文档影响 / known-debt / 归档）尚未勾选，属于 close-out 阶段，不在本次 building 审阅范围；归档时需按 AGENTS.md 为受保护路径补 workflow-events 事件并跑 artifact checker + openspec validate。

无剩余阻塞项。本报告为 PASS，可作为 review manifest 的基础。
