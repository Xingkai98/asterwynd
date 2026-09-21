# Building Review: fix-issue-232-archive-write

## Verdict

PASS

## Reviewer

- run id: `89e2eb23-7af9-4cd2-b9ac-c0655f115e53`（独立零记忆 subagent，未参与开发）

  > 说明：该 id 与 Round 1 相同——paseo 复用了同一 agent 会话，Round 2 是其上的新一轮**零记忆上下文**（不继承 Round 1 的开发或审阅记忆），所有结论均由本轮独立实跑得出。

- 时间: 2026-09-22
- 审阅基线: base `b54a50a3b132afbade150e175e9f40fdf8b8f24d` → head `a28f752b9584fdb4510fa5828ecc2aee68b457e4`
- 复核方式（**全部实跑**，非只读代码）:
  1. `uv run pytest tests/test_workflow_archive_write_channel.py tests/test_workflow_protected_write_channel.py tests/test_workflow_state_cli.py -q` → **43 passed**（14 + 11 + 18，与各文件 `grep -c '^def test_'` 一致）。
  2. `uv run pytest -q` 全量 → **3038 passed / 2 failed**（失败为 `tests/agent/memory/test_persistent.py::TestFindScopeRoot`，环境性，见 Test Results）。
  3. **O1 等价性三重核验**：① 解析式论证；② 差分矩阵实跑（7 种仓库状态 × 模拟旧「分支置位」/ 新「路径前缀」双判据 → MISMATCH=0）；③ 真实并存场景实跑（active + archive 同名）。
  4. **6 组独立变异**（每次改后从 `/tmp/ws_r2_backup.py` 还原，最终 `md5sum` 一致且 `git status --porcelain` 无 `scripts/` 改动）。
  5. **独立冷状态复现**：`/tmp` 自建仓库实跑 `artifact-event` / `review-manifest`，核验 exit code、落点、投影污染、active 幽灵目录。**未在真实仓库 `openspec/changes/archive/` 下执行任何写命令**（结束 `git status --porcelain` 为空）。
  6. `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed / 0 failed**；`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 见 Issues O6。
  7. 逐 Scenario 集合比对 delta（13）与正式 spec（11）。

## 审阅历史

- **Round 1**（head `4e22abc`）: **PASS**。发现问题均为低 severity 观察项：O1（`is_archived` 由分支置位、与 design D3「路径前缀」措辞不一致）、O2（3 条测试覆盖缺口）、O3（`docs/known-debt.md` 待更新 + 悬空注释）、O4（`--change ..` 先于本 change 存在的安全缺口）、O5（Scenario 计数漂移 + backlog 措辞）。报告见同目录 git 历史版本（该文件在 `a28f752` 中被提交）。
- **Round 2**（head `a28f752`）: **本报告**。开发者自述落实 O1、O2、O5；本报告逐项独立核验其**属实且正确**，并复核加固未引入新缺陷、判别力保持。O3/O4 按计划分别留收尾/另案（见 Issues）。

## Tasks Verification

`tasks.md` 当前 **3 条已勾选 / 其余未勾选**（`- [x]`：Round 1 审阅、审阅后加固、变异验证）。按仓库门禁口径，tasks 未全勾时不强制 building-review + manifest；下面同时核对已实现条目的代码落点。

- [x] **`_require_change_target` active 优先 + archive 回退** — 已验证: `scripts/workflow_state.py:914-935`；委托 `change_dir_for(CHANGES_ROOT.parent.parent, change_id, archived=True)`（`:918`），`repo_root` 用 `CHANGES_ROOT.parent.parent` 而非 `_PROJECT_ROOT`（`:918`）。实跑：归档 change `artifact-event` exit 0，事件落归档目录。
- [x] **解析结果位于 `CHANGES_ROOT/archive/` 之下时标记归档目标（路径前缀判定）** — 已验证且**本轮已与实现对齐**: `:854-860` 新增 `_is_archived_change_dir`，`:938` 以解析结果判定。Round 1 的「措辞与实现不一致」观察项已消除，实现即路径前缀判定。
- [x] **解析结果目录名必须裸 `<id>` 或 `<date>-<id>`，否则 fail-closed exit 1** — 已验证: `:862-875`（`re.fullmatch` + `re.escape`，含裸 `<id>` 分支）、`:915-922`（fail-closed）。实跑：查询 `alpha` 而 archive 仅存 `2026-09-22-alpha-beta` → exit 1，兄弟目录事件日志保持 1 行。
- [x] **`--change` 带日期前缀 id 显式拒绝** — 已验证: `:904-910`。实跑 `--change 2026-09-21-coldarch` → exit 1，未写任何文件。
- [x] **`cmd_review_manifest` 对归档目标传 `archived=True`** — 已验证: `:1101`（`archived=is_archived`）；`is_archived` 即 `_require_change_target` 的返回值，单一事实源。实跑 manifest 落 `archive/<date>-<id>/reviews/building-review-manifest.json`。
- [x] **归档目标跳过 `_flow_refresh_after_event`** — 已验证: `_after_protected_write` `:941-965`，`:951-953` 分流；实跑归档目录写入后无 `handoff.json` / `workflow-state.json`。
- [x] **归档目标只读 `verify_projection`，不一致 stderr 告警、exit 0、绝不落盘** — 已验证: `:954-965`；实跑预置陈旧 `workflow-state.json` → stderr 有告警、exit 0、投影内容 unchanged。
- [x] **保留 #199 全部行为** — 已验证: `:869-910` 既有校验分支未改（仅新增日期前缀拒绝 + archive 回退）；`tests/test_workflow_protected_write_channel.py` 11 条全绿；active 目标仍走 `_flow_refresh_after_event`（`:951-952`）。
- [x] **测试条目** — 已验证: `tests/test_workflow_archive_write_channel.py` 14 条，覆盖落点/污染/幽灵目录/裸 id 归档目录/老世代归档/不存在 id/路径型 id/日期前缀 id/前缀碰撞/只读告警/非法目录。
- [ ] **文档条目** — 部分待收尾: `diagnosis.md` 6 章、spec delta（13 条 Scenario）、backlog 登记均在；`docs/known-debt.md` 更新（tasks.md:38）与 spec 同步（tasks.md:37）尚未落，见 Issues O3/O6。

## Round-2 Delta Verification

### O1 等价性（关键）: 结论 —— **在全部可达路径上精确等价，行为不变** ✓

新判据 `_is_archived_change_dir`（`scripts/workflow_state.py:854-860`）为
`CHANGES_ROOT / "archive" in change_dir.parents`；旧判据为「active 目录不存在 → 走 archive 回退分支 → 置位 True」。

解析式论证（两条互斥路径，穷尽 `_require_change_target` 的出口）:

1. **active 分支**（`change_dir = CHANGES_ROOT / change_id` 存在，`:914-915`）: `change_id` 已被 `:899-903` 拒绝含 `/`、`\`、绝对路径，故 `change_dir` 是 `CHANGES_ROOT` 的**单段子目录**，其 `parents` 不含 `CHANGES_ROOT/archive`（`Path.parents` 不含自身，且 `change_id` 不可能为多段）；旧分支此处置 False。→ 两者均 False。
2. **archive 回退分支**（`:916-936`）: `change_dir_for(..., archived=True)`（`agent/workflow/review_manifest.py:37-46`）的两个返回语句分别为 `archive_root / <命中目录名>` 与 `archive_root / change_id`，`archive_root = base/"archive"`、`base = Path(repo_root)/"openspec"/"changes"`，而传入的 `repo_root = CHANGES_ROOT.parent.parent`，故返回值**恒**位于 `CHANGES_ROOT/archive/` 之下；旧分支此处置 True。→ 两者均 True。

差分矩阵实跑（7 种可达状态，含 `active + archive 同名并存`、`archive 下裸 id 与日期前缀 id 并存`）:

```
act dat bar  resolved_path                                   old   new   pfx  EQ
  0   0   1  openspec/changes/archive/alpha                 True  True  True True
  0   1   0  openspec/changes/archive/2026-09-21-alpha      True  True  True True
  0   1   1  openspec/changes/archive/alpha                 True  True  True True
  1   0   0  openspec/changes/alpha                        False False False True
  1   0   1  openspec/changes/alpha                        False False False True
  1   1   0  openspec/changes/alpha                        False False False True
  1   1   1  openspec/changes/alpha                        False False False True
TOTAL=7  MISMATCH=0     # old=模拟旧分支置位, new=实现返回值, pfx=_is_archived_change_dir
```

**并存场景实跑**（`openspec/changes/dual/` 与 `openspec/changes/archive/2026-09-21-dual/` 同时存在）:

```
$ artifact-event --change dual ...            exit=0
active dir  : handoff.json, proposal.md, workflow-events.jsonl, workflow-state.json   # 走 active，刷新投影
archive dir : proposal.md, workflow-events.jsonl                                      # 未被触碰
active 事件日志 seq=2 = protected_artifact_explained；archive 日志仍为 seq=1
```

→ 解析走 **active**、`is_archived=False`、manifest/事件**均落 active**、archive 零写入；与旧实现一致。

**其余分支实跑**（直接调 `_require_change_target`）:

```
A 并存      'dual'     -> openspec/changes/dual                          is_archived=False  (pfx=False)
B 日期前缀  'dateone'  -> openspec/changes/archive/2026-09-21-dateone    is_archived=True   (pfx=True)
C 裸 id     'bareone'  -> openspec/changes/archive/bareone               is_archived=True   (pfx=True)
D 均不存在  'ghostone' -> None（错误：change 'ghostone' 不存在）
E 仅 active 'activeone'-> openspec/changes/activeone                     is_archived=False  (pfx=False)
```

**新判据更优的一点（非缺陷，记录备查）**: 旧写法把 `is_archived` 与「走了哪条分支」耦合，将来新增解析路径漏置位即静默降级为 False（会把归档当 active 刷新，污染归档）。新写法由解析结果推导，且 `is_archived` 是 `cmd_artifact_event:1078` 与 `cmd_review_manifest:1101,1116` 的**单一事实源**（同时决定 manifest 落点与是否跳过刷新），消除了两处漂移的可能性。

### O2 新用例判别力（关键）: 结论 —— **3 条新用例均有真实判别力，无「恒绿摆设」** ✓

用例数确认 `11 → 14`（`grep -c '^def test_'` = 14）。逐条变异（每次单独改、单独跑、跑完还原）:

| 变异 | 目标新用例 | 实测结果 |
|---|---|---|
| 删 `_archive_dir_matches_change_id` 的 `name == change_id` 裸 id 分支（`:872-873`） | `test_archived_write_supports_bare_id_archive_dir` | **1 failed, 13 passed**（仅该条红，stderr=`解析到归档目录 'bare-dir'，目录名与 change id 不匹配`） |
| 删前置条件的 `handoff.json` 兼容分支（`:936`） | `test_archived_write_supports_gen1_change_with_only_handoff` | **1 failed, 13 passed**（stderr=`不是合法 change（缺 proposal.md 且无 handoff.json）`） |
| 删 `archived_dir.exists()` 存在性检查（`:917-919`） | `test_archived_write_rejects_unknown_change` | **1 failed, 13 passed**（stderr 由 `不存在` 退化为 `不是合法 change`） |

→ 裸 `<id>` 用例**不是摆设**：它是唯一执行 `_archive_dir_matches_change_id` 裸 id 分支的用例，去掉实现即红。

### 判别力保持（6 组独立变异，全部变红）

```
M1  _is_archived_change_dir 恒返回 False            -> 7 failed, 36 passed
M2  _after_protected_write 改回无条件刷新            -> 5 failed, 38 passed   （与开发者自述「5 红」一致）
M3  删 _archive_dir_matches_change_id 裸 id 分支     -> 1 failed, 13 passed   （O2-① 判别性）
M4  删前置条件 handoff.json 兼容分支                 -> 1 failed, 13 passed   （O2-② 判别性）
M5  删 archived_dir 存在性检查                       -> 1 failed, 13 passed   （O2-③ 判别性）
M6  禁用 archive 回退                                -> 9 failed, 5 passed
还原后：md5sum scripts/workflow_state.py == /tmp/ws_r2_backup.py == 4291a817715cc45f5eef560c47eb9450
        git status --porcelain 为空（无 scripts/ 改动）
```

### O5 文档计数: 结论 —— **已修正且与实测一致** ✓

逐 Scenario 集合比对（change delta vs 正式 spec 的 `工作流事件日志与 handoff.json projection` Requirement）:

```
formal = 11, delta = 13
LOST  (formal 有、delta 无): []                                        ← 零丢失
ADDED (delta 有、formal 无): ['受保护写通道支持已归档 change',
                              '受保护写通道拒绝归档语境下的非法 change id']
```

- `design.md:67,69`：已改为「delta 起初 12 条…补入第 2 条 Scenario…**delta 最终为 13 条（既有 11 + 新增 2）**」——与实测一致 ✓
- `tasks.md:36`：已改为「新增 **2** 条（归档写通道、归档语境下拒绝非法 id）」——与实测一致 ✓

## Spec Alignment（逐条 SHALL 对照 spec delta）

| spec delta SHALL | 实现 | 实跑证据 |
|---|---|---|
| 目标解析 active 优先，否则回退 `archive/<date>-<id>/` | `scripts/workflow_state.py:914-935` | 归档写入 exit 0；并存场景落 active |
| 回退 SHALL NOT 依赖 `flow status` 解析 | 委托 `change_dir_for`（`:918`），未用 `_flow_resolve_change_dir` | `_flow_resolve_change_dir('fix-issue-199-handoff-prereq')` → `None`（既有回退是死代码） |
| 解析结果 SHALL 与查询 id 一致，否则 exit 1 | `:862-875` + `:915-922` | `alpha` vs `2026-09-22-alpha-beta` → exit 1，未写任何文件 |
| `--change` SHALL 只接受裸 id | `:904-910` | `--change 2026-09-21-coldarch` → exit 1，事件日志保持 1 行 |
| 写入落归档目录、SHALL NOT 新建 active 目录 | `:935` + `:1101` | `/tmp` 冷复现：事件/manifest 均落 archive，`openspec/changes/coldarch` 不存在 |
| 归档 SHALL NOT 产出投影文件 / SHALL NOT 刷新投影 | `_after_protected_write` `:941-965` | 冷复现归档目录无 `handoff.json` / `workflow-state.json` |
| 不一致 SHALL 告警但 SHALL NOT 落盘、SHALL NOT 失败 | `:954-965` | 陈旧投影 → stderr 告警 + exit 0 + 内容 unchanged |
| 对 active 目标写入后 SHALL 重新生成投影 | `:951-952` | 并存场景生成 `workflow-state.json` + `handoff.json`；#199 11 条全绿 |
| 归档语境下非法 id SHALL 被拒绝 | `:862-875,904-910` | 路径型/日期前缀/不存在 三类 id 实跑均 exit 1 |

## Issues

**无中等及以上问题。** 以下 6 条均为低 severity 观察/收尾项，不阻塞（O4 先于本 change 存在，明确非目标）。

- **O6**（Low，**对本仓库门禁事实的更正**，非代码缺陷）: Round 1 结论中「artifact checker 只在 tasks 全勾选时才强制 building-review + manifest，若收尾时漏勾 `[x]`，该门禁会静默失效」**不准确**。实读 `scripts/check_openspec_artifacts.py:1044-1051`：`requires_building_review`（`:1027-1032`，含 `_tasks_all_complete`）只控制「`building-review.md` **是否存在**」这一条；而只要 `reviews/` 下存在任一 `*-review.md`，就会进入 `for report_path in review_dir.glob("*-review.md")` 循环并调用 `verify_review_manifest(...)`——**与 tasks 勾选状态无关**。实测当前 head：
  ```
  $ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
  ERROR: fix-issue-232-archive-write: review manifest missing: .../reviews/building-review-manifest.json
  checker exit=1
  ```
  结论方向是**更安全**的（fail-closed，不会静默放过），但必须据此行动：**本报告落盘后（报告 hash 参与 manifest 绑定）立即生成 `building-review-manifest.json`**，否则 baseline CI 恒红。该条已列在 tasks.md:44-45。
- **O3**（Low，收尾项 + 悬空引用，Round 1 遗留）: `scripts/workflow_state.py:867-869` 注释称「修复该正则属独立决策，记在 `docs/known-debt.md`」，但 `docs/known-debt.md` 仍未更新（`grep -n "change_dir_for" docs/known-debt.md` 无命中），且其「归档 change 的 review manifest 写入/校验双盲区」一节仍写着「写入盲区…`_require_change_target` 只看 active 目录」——本 change 合入后该表述失真。tasks.md:38 已排期，收尾必须完成。
- **O5-①**（Info，Round 1 遗留未修）: `docs/openspec-change-backlog.md:115-116` 仍保留两处本 change **已自证失实**的表述——「不传 `archived=` 会写进 active 幽灵目录」（实为先抛 `FileNotFoundError` → exit 1，目录不新建；见 `workflow-events.jsonl` seq 2 更正）与「复用既有 `_flow_resolve_change_dir` 口径」（实为委托 `change_dir_for`）。Round 2 delta 未触碰 `docs/`（`git diff --stat 4e22abc...HEAD -- docs/` 为空）。该条目在收尾时整条删除，不会进入 master。
- **O5-②**（Info，tasks.md 计数残留漂移）: `tasks.md:25` 写 `tests/test_workflow_protected_write_channel.py`「10 条」，实测 **11** 条（14+11+18=43 与 pytest 输出一致）；`tasks.md:27` 写「去 archive 回退 → 8 条」，实测 **9 条**；`tasks.md:28` 写「（归档跳过刷新）3 条红」，加固后实测 **5 条**（tasks.md:49 的加固述条已正确写 5，与 :28 自相矛盾）。均为文档数字，建议收尾一并校正。
- **O4**（Low，安全，**先于本 change 存在，明确非目标**）: `--change ..` 仍被当作合法单段 id——`:899` 的校验只拦绝对路径与 `/`、`\`，`:904` 的日期前缀正则不命中 `..`。实测 HEAD：若仓库内存在 `openspec/proposal.md`，`artifact-event --change ..` 会 exit 0 并把 `workflow-events.jsonl` / `workflow-state.json` / `handoff.json` 写到 `openspec/`（changes 根之上）。该缺口在 base `b54a50a` **完全一致**（`git show b54a50a:scripts/workflow_state.py` 第 **869** 行即同一校验，与 HEAD `:899` 逐字相同）；且最远只能上一级（`/` 被拒），**无法写到仓库外**，spec「SHALL NOT 写入仓库外路径」未被违反。Round 2 未使其恶化（该场景下新旧判据均返回 `is_archived=False`）。建议另案收紧。
- **Info**（潜在解析歧义，先于本 change 存在）: 若 `archive/<id>/` 与 `archive/<date>-<id>/` **同时**存在，`change_dir_for`（`agent/workflow/review_manifest.py:37-46`）按 `iterdir()` 顺序返回先命中者。因两者都在 archive 下，`is_archived` 判定与 O1 等价性均不受影响（差分矩阵 `dat=1,bar=1` 用例已验证），仅记录备查。

## Test Results

```
$ uv run pytest tests/test_workflow_archive_write_channel.py tests/test_workflow_protected_write_channel.py tests/test_workflow_state_cli.py -q
...........................................                              [100%]
43 passed in 50.51s
# 14 + 11 + 18 = 43，与 grep -c '^def test_' 各文件计数一致

$ uv run pytest -q
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
2 failed, 3038 passed, 9 skipped, 76 warnings in 319.11s (0:05:19)
# 与本 change 零交集：git diff --stat base...HEAD 未触碰 tests/agent/memory/** 或 agent/memory/**
# 失败用例 monkeypatch Path.exists 使 .git 恒为 False，属环境性（Round 1 同样观测到同 2 条）

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
ERROR: fix-issue-232-archive-write: review manifest missing: .../reviews/building-review-manifest.json
checker exit=1        # 唯一错误；见 Issues O6（收尾生成 manifest 即消除）
```

独立冷状态复现（`T=/tmp/ws_r2_cold`，归档目录 `archive/2026-09-21-coldarch/`）:

```
===== 1) artifact-event =====
已记录 artifact 事件: protected_artifact_explained (docs/known-debt.md)     exit=0
===== 2) review-manifest =====
已写入 review manifest: .../archive/2026-09-21-coldarch/reviews/building-review-manifest.json   exit=0
--- 归档目录文件 ---
proposal.md  reviews/building-review-manifest.json  reviews/building-review.md
tasks.md     workflow-events.jsonl                       # 无 handoff.json / workflow-state.json
--- active 幽灵目录 ---  openspec/changes/coldarch: No such file or directory
===== 3) 不存在 id =====
错误：change 'nope' 不存在                                                      exit=1

===== 并存场景（active + archive 同名 dual）=====
artifact-event exit=0；事件落 active（seq=2）；active 生成投影；archive 保持 seq=1 未被触碰
```

还原自检:

```
$ md5sum scripts/workflow_state.py /tmp/ws_r2_backup.py
4291a817715cc45f5eef560c47eb9450  scripts/workflow_state.py
4291a817715cc45f5eef560c47eb9450  /tmp/ws_r2_backup.py
$ git status --porcelain          # 空（真实仓库 openspec/changes/archive/ 未被写入）
```

Lint（供参考，**ruff 不在 CI**）: `uv run ruff check scripts/workflow_state.py` → 2 条 F401（`PHASE_ORDER`、`WorkflowManager`），与 base 完全相同；base 的第 3 条（`verify_projection` unused）已被本 change 消除。新测试文件 `ruff check` **All checks passed**。全仓库 188 个文件会被 `ruff format` 重排，说明格式非门禁项。

## 结论

Round-2 加固**属实、正确、未引入新缺陷**，判别力保持：

1. **O1** 已在全部可达路径上证明与旧行为**精确等价**（解析式论证 + 7 状态差分矩阵 MISMATCH=0 + 并存/cold 实跑），实现与 design D3 措辞现已一致，且把 `is_archived` 收拢为解析结果的单一事实源，比旧分支置位更不易漂移。
2. **O2** 3 条新用例逐条经变异验证**均有真实判别力**，裸 `<id>` 归档用例不是恒绿摆设；测试文件 11 → 14。
3. **O5** 计数漂移已修正，与实测（formal 11 / delta 13 / LOST 0 / ADDED 2）一致。
4. 6 组独立变异全部变红，`#199` active 行为零回归（11 条全绿 + 全量 3038 passed，2 条失败为环境性且与本 change 零交集）。

未发现中等及以上缺陷，判 **PASS**。

收尾前必须处理（均已在 tasks.md 排期，非代码缺陷）:

1. **生成 `building-review-manifest.json`**（tasks.md:44-45）——按 Issues **O6**，checker 对存在 `*-review.md` 的 change **无条件**校验 manifest，当前 head `checker exit=1`；报告落盘后本文件 hash 会被 manifest 绑定，须在本报告定稿后生成。
2. `docs/known-debt.md` 更新与 spec 同步（tasks.md:37-38，见 O3）——否则 `scripts/workflow_state.py:867-869` 的注释成为悬空引用、known-debt 与代码事实相反。
3. tasks.md 计数残留（O5-②）与 backlog 条目（O5-①）随收尾一并校正/删除。
