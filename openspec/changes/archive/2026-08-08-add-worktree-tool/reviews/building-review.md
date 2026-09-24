# Building Review: add-worktree-tool（Round 6）

**Verdict**: PASS

**审阅基线**: base_sha=1e16ee14e8103b06786eb5407a50be36dd466f57（origin/master） head_sha=5a26adc3a42e9030eaec8107a619a4073564332d
**审阅时间**: 2026-09-24

> 本轮为 R5（CHANGES_REQUESTED）修复后的**独立复核**。逐一复核 R5 的 6 项 issue，并在临时
> 仓库中独立复现数据丢失场景、做变异验证证明新回归测试不是假保护。
> **结论：R5 的 6 项全部确认修复，未发现中等及以上新问题。** 唯一遗留是归档 manifest 需在
> 本报告写入后重新生成（`/review-loop` 的收尾步骤，非代码缺陷），另有 2 条低危观察项。

## R5 Issue 复核

| # | 上一轮问题 | 结论 | 实测证据 |
| --- | --- | --- | --- |
| 1 | [高] `EnterWorktree` 失败兜底删除已存在的 worktree（数据丢失） | ✅ 已修复 | 见「独立复现」：clean / dirty 两种场景下 worktree 与文件**均完好保留**，main 只剩 2 条注册未被改动；文案改为「已被占用（分支或目录已存在），未改动它」 |
| 2 | [中] 失败文案与事实相反（dirty 场景谎称「清理未完成/可能残留」） | ✅ 已修复 | dirty 场景实测文案为 `...已被占用（分支或目录已存在），未改动它；请换一个 name，或先 ExitWorktree 退出该 worktree`，**不含**「清理未完成」；回归测试断言 `assert "清理未完成" not in result.text` 且变异后变红 |
| 3 | [低] `base_branch` 参数注入（`--force` 被当选项吞掉、base 静默失效） | ✅ 已修复 | `worktree.py:184` 已加 `--`：`add -b <name> -- <path> <base>`。实测 `base_branch="--force"` → `fatal: invalid reference: --force`、`error_type=worktree_create_failed`、无 worktree 建成（修复前会静默成功建在 HEAD）；`base_branch="basebr"` 仍被正确采纳（新 worktree 含 base 分支独有文件） |
| 4 | [低] 测试缺口：无「同名 worktree 已存在」回归 | ✅ 已修复 | 新增 `test_enter_worktree_existing_worktree_not_deleted:196`、`test_enter_worktree_dirty_existing_worktree_not_deleted:225`，另有 `test_enter_worktree_base_branch_option_injection_rejected:247`；三条均经变异验证确实变红（见「变异验证」） |
| 5 | [低] spec 滞后：越权边界无 Scenario | ✅ 已修复 | 主规格与归档 delta **同步**补 `#### Scenario: 拒绝退出非本工具创建的 worktree`；两侧 Requirement 块各 60 行、`diff` **IDENTICAL**、Scenario 数 8；实现侧 `worktree.py:283-287` 与测试 `test_exit_worktree_rejects_non_tool_created:321` 支撑该 Scenario 全部 4 条断言 |
| 6 | [低] benchmark `gold.patch` 固化破坏性 remove | ✅ 已修复 | 现 `gold.patch` 与 `git diff 454bebe HEAD -- agent/tools/builtin/worktree.py` **IDENTICAL**；已不含无条件 remove，改为 `before/after` 差集清理（`gold.patch:114-127`）。base→gold 红绿闭环独立复现成立（见下） |

补充核验（R5 未列但同批需确认）：

- **残留分支是否可达**：R5 曾质疑「D2 里非 branch 冲突残留」是否存在。实测**存在**——`git worktree
  add` 在 `post-checkout` hook 失败时会留下注册（见「独立复现」C 节）。因此保留 `residue` 清理分支
  是**正确取舍**，而非死代码；`test_enter_worktree_add_failure_cleanup_checked` 用注入方式覆盖它同样合理。
- **branch / dir / 非法 base / 非法 rev 冲突**：`worktree list --porcelain` 前后对比**均无新增注册**
  （git 2.43.0），证实「只清本次新增注册」的差集在常规失败路径上恒为空集 → 不触发任何删除，回到 base 安全语义。

## 独立复现

**A. Issue 1 原始 bug 场景（本轮必须做）** — 临时 git 仓库，直接调用工具类，`policy.workspace_root=repo`：

```
===== SCENARIO A (clean existing worktree) =====
after first enter error_type: None
exit(keep=True): {"workspace": "/tmp/r6-w83ky4m1", "removed": false}
porcelain after exit: ['/tmp/r6-...', '/tmp/r6-....asterwynd/worktrees/keepme']
re-enter error_type: worktree_create_failed
re-enter text: Error: worktree 创建失败：/tmp/....asterwynd/worktrees/keepme 已被占用
              （分支或目录已存在），未改动它；请换一个 name，或先 ExitWorktree 退出该 worktree:
              Preparing worktree (new branch 'keepme') / fatal: a branch named 'keepme' already exists
wt exists AFTER: True
precious AFTER: True
porcelain AFTER: ['/tmp/r6-...', '/tmp/r6-....asterwynd/worktrees/keepme']
-> RESULT: worktree_preserved=True file_preserved=True

===== SCENARIO B (dirty existing worktree) =====
re-enter error_type: worktree_create_failed
re-enter text: Error: worktree 创建失败：... 已被占用（分支或目录已存在），未改动它；...
wt exists AFTER: True
precious AFTER: True
dirty AFTER: True
-> RESULT: worktree_preserved=True file_preserved=True
```

对照 R5 报告的同场景记录（`wt exists AFTER: False` / `file AFTER: False` / 只剩主工作区）：
**破坏性删除已彻底消失，两条回归路径均安全**。另查 `.git/worktrees/` 目录条目：重入前后均为
`['keepme']`，未被误删；worktree 目录内容 `['.git','R','f.txt']` 完整。

**B. 残留探测（决定 `residue` 分支可达性）**：

```
branch-conflict  rc: 255   new registrations: set()
dir-conflict     rc: 128   new registrations: set()
invalid base     rc: 128   new registrations: set()      (fatal: invalid reference: --force)
bad rev          rc: 128   new registrations: set()
```

即：常规冲突路径 **无残留注册** → 差集为空 → **不执行任何 remove**（正是 base 的安全语义）。

**C. 真正可达的残留分支（post-checkout hook 失败）**：

```
porcelain before: ['/tmp/r6h-...']
error_type: worktree_create_failed
text: Error: worktree 创建失败（本次残留已清理）: Preparing worktree (new branch 'hookfail')
porcelain AFTER: ['/tmp/r6h-...']      path exists: False
```

证明「本次 add 确实留下注册 → 清理 → 精确文案」这条正路径**真实存在且工作正常**（R5 曾怀疑它是死代码）。

**D. 新逻辑边界探测**：

- 分支被**另一路径**的 worktree 占用：`error_type=worktree_create_failed`，文案退化为裸
  「创建失败」（`wt_path` 不存在故不走「被占用」分支）；两个 worktree 均未被触碰。文案**未撒谎**，只是引导性弱 → 记为观察项 O1。
- 合法 `base_branch`：新 worktree 同时含 base 分支独有文件与主分支文件，`--` 未破坏正常语义。

## 变异验证

在**一次性 detached worktree** `/tmp/r2-mut`（`git worktree add --detach /tmp/r2-mut HEAD`）中做「改坏 → 变红 → 还原」，**被审检出从未被写入**。

**变异 A：把失败兜底改回「无条件 remove」**（还原 R5 Issue 1 的原始缺陷）

```
$ .venv/bin/python -m pytest tests/agent/tools/test_worktree_tools.py -q
FAILED tests/agent/tools/test_worktree_tools.py::test_enter_worktree_existing_worktree_not_deleted
FAILED tests/agent/tools/test_worktree_tools.py::test_enter_worktree_dirty_existing_worktree_not_deleted
2 failed, 22 passed in 2.16s        EXIT=1
```

失败的**正是两条新增回归**，且 dirty 用例的失败断言为 `assert '清理未完成' not in result.text`
（说明 Issue 2 的文案断言同样是真保护，非摆设）。

**变异 B：去掉 `--` 分隔符**（还原 R5 Issue 3）

```
FAILED tests/agent/tools/test_worktree_tools.py::test_enter_worktree_base_branch_option_injection_rejected
1 failed, 23 passed in 1.98s        EXIT=1
```

失败证据：`assert None == 'worktree_create_failed'` where `error_type=None`、
`text='{"worktree": ".../test-wt", "branch": "test-wt"}'` —— 即去掉 `--` 后 `--force` 被吞、
**静默按 HEAD 建成功**，与 R5 描述完全一致 → 回归测试有效。

**还原确认**：`git checkout -- agent/tools/builtin/worktree.py` 后 `git status --porcelain` **空**；
`git worktree remove --force /tmp/r2-mut` 已执行，`git worktree list` 中无 `/tmp/r2-mut`。
被审检出 `git status --porcelain` 与 `git diff --stat` **均为空**，无任何未还原改动（唯一写入是本报告）。

**benchmark 红→绿闭环（独立复现，未采信历史报告）**：在 `454bebe` 检出上

```
base + test.patch                → 1 failed, 2 passed   EXIT=1
  （失败：test_rejected_in_orchestration_worktree，text 显示 removed:true / error_type=None）
base + test.patch + gold.patch   → 3 passed            EXIT=0
```

`git apply --check --reverse gold.patch` 于 HEAD → rc=0；`test.patch` 同样 reverse-apply 干净。

## 新引入问题检查

逐项核对 E 节关注点，**未发现中等及以上新问题**。以下为低危观察：

- **O1 [低] 失败文案覆盖不全（分支被异路径 worktree 占用）**：`worktree.py:206` 用
  `wt_path.exists()` 判定「被占用」，只覆盖「路径被占」；若分支被**另一个路径**的 worktree 占用，
  文案退化为裸「创建失败」，不提示「换 name / 先 ExitWorktree」。行为安全（未删任何东西），仅引导性弱。
  另外 `wt_path` 是陈旧非空目录时文案会顺带建议「先 ExitWorktree 退出该 worktree」，而那种情况下
  并无注册 worktree——措辞轻微不精确。两者均不影响正确性。
- **O2 [低] `before` 快照取不到时是 fail-open 方向**：`residue = after - before`，若
  `_registered_worktree_paths` 在**第一次（before）**调用失败（函数在 `git worktree list` 非 0 时
  `return set()`，含 30s 超时映射），则已有 worktree 会被算进 `residue` → 破坏性 remove 回归。
  实测用故障注入复现可触发（`before` 返回空集时 `wt exists AFTER: False / precious AFTER: False`）。
  触发条件苛刻（同一条 git 命令在 before 调用上瞬时失败、在 after 调用上成功，且 add 恰好因
  分支冲突失败），故判低危；建议改为 **fail-closed**：before 快照不可得时直接跳过清理，只回文案。
- **O3 [提示] 归档 manifest 在本次修复后已失去绑定**：修复改动了 `specs/`（manifest 的 `spec_hash`
  源）与本报告（`report_hash`），故 `--check-archived` 现在报两条错：

  ```
  ERROR: review report hash mismatch
  ERROR: spec hash mismatch
  ```

  R5 时只有 `report_hash` 一条；新增的 `spec_hash` 失配是本次（合法、必要）修改 specs 所致。
  这属于 `/review-loop` 收尾「重生成 manifest 绑定新报告」的预期中间态，**不是缺陷**；但**必须**
  在开出/更新 PR 前重生成 manifest（绑定新的 report/spec/tasks/diff hash），否则 CI 第二步
  （`.github/workflows/ci.yml:70-71`）会红。
- **O4 [提示] 受保护路径事件文本已过时**：`workflow-events.jsonl` seq 2 的 reason 写「7 个 Scenario」，
  而本次 spec 已增至 8 个。事件门禁机械上仍通过（存在覆盖该路径的 `current_spec_synced` 事件，
  且第一条 checker 命令 exit 0），仅文字与现状不符，属历史记录口径，不阻断。

其余 E 节关注点核对结论：

- **`_rebind_workspace` 抛错的回滚路径未受影响**：回滚仍在 `add` 成功之后（`worktree.py:220-235`），
  此时路径必然是本次新建的注册，`worktree remove` 前后语义正确；`test_enter_worktree_rollback_on_post_add_failure:350` 通过。
- **是否可能误删**：仅当 `wt_path ∈ (after - before)` 才删，即 git 在本次调用中确实在该路径注册过，
  且此前未注册——语义上不可能指向用户既有 worktree。唯一例外即 O2 的 before 快照失效。
- **是否漏清真残留**：hook 失败场景实测被正确清理（C 节），未漏清。
- **文案自相矛盾**：三类文案（被占用未改动 / 真残留已清理 / 清理未完成残留）互斥且与实测一致，无矛盾。
- **`.git` 外副作用 / 路径归一化**：`before/after` 与 `wt_path` 均经 `Path(...).resolve()` 归一化，
  集合比较口径一致；`.git/worktrees/` 条目实测未被波及（前后均为 `['keepme']`）。

## 验证命令实跑结果

```bash
export PATH=/home/happy/.local/bin:$PATH
cd /home/happy/my-agent/.claude/worktrees/add-worktree-tool+2026-08-07
```

| # | 命令 | 真实输出 | exit |
| --- | --- | --- | --- |
| 1 | `uv run pytest tests/agent/tools/test_worktree_tools.py tests/agent/tools/test_worktree_benchmark_smoke.py -q` | `27 passed in 2.29s` | 0 |
| 2 | `uv run pytest tests/test_workflow_guard.py -q` | `26 passed in 10.87s` | 0 |
| 3 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 28 passed, 0 failed (28 items)`（含 `✓ spec/tool-system`） | 0 |
| 4 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref 1e16ee14e8103b06786eb5407a50be36dd466f57 --require-base` | `OpenSpec artifact checks passed` | 0 |
| 5 | `uv run pytest -q`（全量，可选） | `2 failed, 3053 passed, 9 skipped, 77 warnings in 341.45s (0:05:41)` | 1 |

第 5 项的两条失败为任务书声明的**已知无害项**，与本次 change 无关：
`tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir` 与
`...::test_malformed_git_file_falls_back_to_scan`（本机 `/tmp` 自身是 git 仓库；base 同样失败、CI 不复现）。

附带项（`--check-archived`，见 O3）：

```
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog
[archived manifest check] tasks_hash 已按归档语境跳过（49 个 change；其余 hash 与字段仍校验）
ERROR: review report hash mismatch
ERROR: spec hash mismatch
exit=1
```

同一命令在 `origin/master`（1e16ee1）为 `OpenSpec artifact checks passed`、在修复前的 `9ef7bfa`
同样 passed —— **该失配是本次合法修改 + 未重生成 manifest 共同造成，需在收尾步骤消除。**

## Spec 对齐检查

三层一致性：**主规格 ≡ 归档 delta ≡ 实现，且实现/测试覆盖全部 8 个 Scenario。无偏差。**

1. **主规格 vs 归档 delta**：`openspec/specs/tool-system/spec.md` 与
   `openspec/changes/archive/2026-08-08-add-worktree-tool/specs/tool-system/spec.md` 的
   Requirement「Worktree 隔离工具」块各 **60 行**，逐行 `diff` = **IDENTICAL**；Scenario 计数两侧均为 **8**。
   R5 指出的「第 8 个 Scenario 缺失」已在两侧同步补齐（主规格 `:274-281`）。
2. **规格 vs 实现**（8/8 逐条可回核）：创建并进入 → `worktree.py:184/236-238` + `test_enter_worktree_creates_and_rebinds:122`；
   非 git 拒绝 → `:162-166` + `test_enter_worktree_not_a_git_repo:156`；嵌套拒绝 → `:167-171` + `test_enter_worktree_nested_rejected:169`；
   退出保留 → `:302/318-322` + `test_exit_worktree_keep_true:371`；退出删除 → `:305-316` + `test_exit_worktree_keep_false_removes:390`；
   含未提交改动被拒 → `:291-300` + `test_exit_worktree_dirty_rejected_state_unchanged:408`；
   不在 worktree 中 → `:275-279` + `test_exit_worktree_not_in_worktree:441`；
   **拒绝退出非本工具创建** → `:283-287` + `test_exit_worktree_rejects_non_tool_created:321`（`keep=False` 但
   `error_type=not_in_worktree`，且断言 policy root 未变、任务 worktree 未被删 —— 与 Scenario 的
   `SHALL NOT 退出或删除` / `工作目录保持不变` 完全对应）。
3. **实现写了规格没写**：未发现。R1 追加的越权边界本轮已进规格（R5 Issue 5 闭合）。
4. 归档 change 目录含 `specs/` delta，`openspec validate --strict` 覆盖 28 项全通过。

## 结论

**Verdict: PASS。**

- R5 的 6 项 issue **逐条确认为真修复**，且都拿到了实测证据而非纸面声明：Issue 1 的原始数据丢失
  场景在 clean / dirty 两种形态下均复现为「worktree 与文件完好保留」；Issue 3 的 `--` 分隔符经
  故障注入证明有效；Issue 4/6 经变异验证与 base→gold 红绿闭环证实不是假保护。
- **未引入中等及以上新问题**：`before/after` 差集只可能指向本次新增注册，`_rebind_workspace`
  失败回滚路径未被波及，`residue` 分支经 hook 失败场景证明真实可达且工作正常，文案三类互斥自洽。
- 遗留 4 条均为低危/流程项：O1 文案覆盖不全（行为安全）、O2 before 快照 fail-open（触发条件苛刻，
  建议改 fail-closed）、O3 manifest 需重生成（收尾步骤，非缺陷）、O4 事件文本过时（门禁通过）。
  **O2/O3 建议在收尾时顺手处理**：O3 是硬要求（否则 CI 第二步红），O2 是两行防御性改动。
- 测试侧：worktree 27 例 + guard 26 例 + OpenSpec 28 项 + 第一条 artifact checker 全绿；
  全量 3053 passed，仅 2 条任务书声明的 `/tmp` 环境已知失败。

**放行条件（收尾必做）**：由 `/review-loop` 重新生成
`reviews/building-review-manifest.json`，绑定本轮 `report_hash` 与新的 `spec_hash`（以及
tasks/diff hash），使 `--check-archived` 恢复 exit 0。本报告写入后该 manifest 必然失配，属预期。

## Open Questions

1. **O2 是否本轮一并改为 fail-closed**（before 快照不可得则跳过清理、绝不 remove）？我判低危不阻断，
   但这是把「唯一的删除动作」从「依赖快照可靠」改为「默认不删」的一行防御性改动，成本极低。
2. **O1 是否补全「分支被异路径 worktree 占用」的文案**？可让所有 `add` 失败都带
   「换 name / 先 ExitWorktree」引导，而不只依赖 `wt_path.exists()`。
3. **O4 是否追加一条 `workflow-events.jsonl` 事件**记录本轮 spec 从 7 个 Scenario 增至 8 个？
   事件门禁当前已通过（机械合规），追加纯粹为可追溯性。
4. **R5 Open Question 3（3.7 文档口径）仍未拍板**：`docs/architecture.md` 内置工具表是否补
   EnterWorktree/ExitWorktree 两行？R5 提过、本轮未变（本分支相对 master 的 `docs/` 改动仍只有
   `docs/openspec-change-backlog.md`）。任务 3.7 带「如有新能力线」限定词，两种口径都讲得通，
   但既然已连续两轮挂起，建议明确拍板以免继续悬空。
