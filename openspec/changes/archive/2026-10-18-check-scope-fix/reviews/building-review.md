# Building Review: check-scope-fix

## Reviewer
- run id: f64ce274-5765-4824-8dc2-af2684f91045
- 时间: 2026-10-18
- 审阅基线: base origin/master=`b0469cba7b3248e6c9d483ed9dc5a6f6de5f8d45`；head=`c13bec59f80ebd5b7aa134f384773416d1d50fe6`
- 场景说明: 本工作区本地 `master=3c7196b`（落后 origin/master 103 个提交），即 issue #319 的复现场景；以下验证均在该真实落后状态下运行

## 本轮判定
- 第 1 轮：**PASS**

### 第 1 轮 · 批次（只列 blocker/high/medium）
- 无

### 第 1 轮 · 下一批（deferred）
- 无

### low/nit 登记

| id | severity | 问题 | 处置理由 |
|---|---|---|---|
| L1 | low | `tasks.md:20`（1.3）的变异计数仍是 6 条测试时代的旧值（写成 4 failed/2 passed、3 failed/3 passed；7 条实测为 4/3、3/4），补丁位置写 `:1538`，实际显式分支在 `scripts/check_openspec_artifacts.py:1540` | 失败集合（T1/T2/T4/T5、T1/T5/T6）与修复前 4 红 3 绿均与实测一致，判别力不受影响；纯记录性误差，grill-adversarial L2 已登记但未修 |
| L2 | low | `docs/adr/ADR-0007-default-base-resolution-for-archive-gate.md:9` 链接到当前树不存在的 ADR-0006（TUI 退役，由后续 PR B 提供） | 文件内已注明「由后续 PR B 提供」，属预期悬空引用；不阻塞本 PR，PR B 落地后自然消解 |
| L3 | nit | `_resolve_base_ref` 对非空显式值原样返回，不 strip：`--base-ref " origin/master "` 会被透传并在下游以两点 diff 失败 | 纯空白已按未提供处理（`explicit.strip()` 判空），带包围空白的 ref 属极低概率误用，且失败是响亮的（WARNING / `--require-base` 报错），不是静默跳过 |
| L4 | low | shallow clone 下 `git merge-base` 失败会退回候选 ref 名（两点语义），`--require-base` 不介入 | 设计/ADR 明确接受的退化；INFO 行会显示 `-> origin/master`，可定位；CI 用显式 PR base sha，不经过该路径 |
| L5 | nit | AGENTS.md 速查表的标准命令仍是显式 `--base-ref origin/master --require-base`；分支落后时该两点命令仍可能把上游受保护路径改动反向列出并误红 | 文档已同句披露「显式参数保留两点 diff」；保留显式命令是为 CI 式确定性，裸跑现在已无此问题 |

### 任务逐项验证

- **0.1** ✅ `reviews/grill-design.md` 存在，6 条 Confirmed Decisions 每条含同行裸 `来源:`；`## Open Questions`（无）与 `## User Confirmation`（无待拍板项）无条件存在。
- **0.2** ✅ 确认项在 `design.md`（Decision 1–5、Risks、Testing Strategy）与 `proposal.md` 中逐项落地；TUI 退役明确列为 Non-Goal 并注明另立 PR。
- **0.3** ✅ `reviews/grill-adversarial.md` 存在，第 1 轮 A1/A2 两条 medium 全修、修复验证 PASS、出口 PASS、`本批 medium+ 数量：0`。
- **0.4** ✅ 无 Open Question，设计环出口 PASS（`grill-adversarial.md:72-77`）。
- **0.5** ✅ `design.md:148-159` 的 `## Pre-Implementation Review` 已回填 grill 与对抗环的 run id、批次与出口。
- **1.1** ✅ 7 条测试全部存在于 `tests/test_openspec_artifact_checker.py:2772-2966`；`-k` 过滤器实测选中 7 条（125 deselected）。
- **1.2** ✅ 在 `/tmp` 副本用 origin/master 版 checker 跑 7 条测试，实测 **4 failed / 3 passed**，红集恰为 T1/T2/T5/T7，绿集为 T3/T4/T6，与记录一致；helper 单元在基线版因 `_resolve_base_ref` 不存在而红，非假保护。
- **1.3** ✅ 变异实测（仅改 `/tmp` 副本）：① 恒返回 `"master"` → **4 failed / 3 passed**（T1/T2/T4/T5）；② 隐式分支返回候选 ref（两点）→ **3 failed / 4 passed**（T1/T5/T6）。失败集合与记录一致；计数/行号陈旧见 L1。
- **2.1** ✅ `--base-ref` 默认 `None`（`:1816-1824`）；`_resolve_base_ref`（`:1525-1564`）实现显式优先、空/纯空白视为未提供、origin/master → master 的 merge-base 顺序、merge-base 失败退回候选 ref、两个都不可解析返回 `"master"`、隐式命中向 stderr 打 INFO。
- **2.2** ✅ `main()` 只解析一次（`:1888-1897`），同一 `base_ref` 传给归档点门（`:1899-1907`）与受保护路径 diff（`:1909-1912`）；仅在 `archive_gate_enabled or protected_paths_enabled` 时解析。归档点门过滤（`--diff-filter=AR` + base 树不存在）与 `_review_exit_*` / `_check_archived_completion_gate` 经 `git diff` 确认逐行未动。help 文案已含空/纯空白例外。
- **2.3** ✅ `uv run pytest -q tests/test_openspec_artifact_checker.py tests/test_retire_manifest_check.py` → **173 passed in 7.92s**。
- **3.1** ✅ delta `specs/dev-workflow-state-machine/spec.md` 以 `## MODIFIED Requirements` 修改归档点 Requirement，正文首行含 SHALL。
- **3.2** ✅ 脚本抽取 delta 与 current 的同名 Requirement 块比较：**逐字一致**（均 5681 字符）；Requirement 计数 current 12、base 12，与记录 12 → 12 一致；strict validate 通过。
- **3.3** ✅ `AGENTS.md:131`、`docs/development-guide.md:322-328`、`docs/requirements-process.md:261,290`、`docs/known-debt.md:218-221`、`.github/workflows/ci.yml:96` 均为 merge-base 口径；`workflow-events.jsonl` seq 3 `current_spec_synced`（spec）、seq 4 `protected_artifact_explained`（known-debt）与本 change 的受保护路径改动对应；裸跑 checker 通过（说明事件门满足）。
- **3.4** ✅ ADR-0007 存在，含 Decision、8 个 Alternatives（远超 ≥2 备选要求）、Consequences、Revisit Conditions；ADR-0006 悬空链接见 L2。
- **3.5** ✅ 全仓 grep 旧口径（「缺省是 master」「默认 --base-ref master 会误判」等），除 `openspec/changes/archive/**` 历史记录（应保留）外无命中。
- **4.1** ✅ 裸跑：`INFO: using implicit base ref 'origin/master' -> b0469cba...` → `OpenSpec artifact checks passed`，EXIT=0。
- **4.2** ✅ `--base-ref origin/master --require-base` → EXIT=0（无 INFO，显式路径未被覆盖）。
- **4.3** ✅ `--check-archived` → EXIT=0（因受保护路径检查仍启用，打印一行 INFO，属设计预期）。
- **4.4** ✅ 新建归档缺 `## 闭环出口` 的守卫用例在 HEAD 版 7 条中通过；基线版实跑为红（T2/T7 依赖同一锚点，T3 独立守卫），证明收窄未放宽判据。
- **4.5** ✅ `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**。
- **4.6** ✅ 记录在案（2 failed / 4530 passed / 9 skipped，2 条为既有 `TestFindScopeRoot` 本机 `/tmp` 环境失败，与基线同因）。本次审阅未重跑全量（不在指定验证集内）；本 PR 除 checker 默认 base 外无运行时代码改动，定向 173 passed 已独立复跑。
- **4.7 / 4.8** ✅ 未勾口径正确：二者是「归档 move 之后、PR 发起之前」的本地复验/事件步骤，不是 `(post-merge)` 动作，因此不应在本阶段勾选；按 tasks 文件头次序在归档 commit 前必须结算为已勾，归档点门会机械强制。
- **5.1 / 5.2** ✅ 未勾正确：本报告即 5.1 的产出，当前处于审阅闭环进行中；medium+ 批次为空，5.2 的「全修」条件天然满足。
- **6.1 / 6.2** ✅ 均标注 `(post-merge)`，属合入后动作，归档点门豁免。

### 验证命令实跑记录

```text
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
INFO: using implicit base ref 'origin/master' -> b0469cba7b3248e6c9d483ed9dc5a6f6de5f8d45
OpenSpec artifact checks passed
EXIT=0

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base
OpenSpec artifact checks passed
EXIT=0

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived
INFO: using implicit base ref 'origin/master' -> b0469cba7b3248e6c9d483ed9dc5a6f6de5f8d45
OpenSpec artifact checks passed
EXIT=0

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref "" --skip-protected-paths --skip-backlog
INFO: using implicit base ref 'origin/master' -> b0469cba7b3248e6c9d483ed9dc5a6f6de5f8d45
OpenSpec artifact checks passed
EXIT=0        # 未被静默跳过：INFO 证明 base 解析生效；归档点门仍在跑

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog
OpenSpec artifact checks passed
EXIT=0        # CI 第二步：两个消费者都关闭，无 INFO 噪音（与 ci.yml 注释一致）

$ uv run pytest -q tests/test_openspec_artifact_checker.py tests/test_retire_manifest_check.py
173 passed in 7.92s

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)

# /tmp 副本：origin/master 版 checker + HEAD 版测试（7 条过滤器）
4 failed, 3 passed, 125 deselected
# 红：test_resolve_base_ref_prefers_origin_master_and_honors_explicit /
#     test_bare_check_does_not_trace_historical_archives /
#     test_empty_base_ref_does_not_skip_checks /
#     test_resolve_base_ref_is_used_for_protected_path_diff

# /tmp 副本变异①：_resolve_base_ref 恒返回 "master"
4 failed, 3 passed   # T1/T2/T4/T5

# /tmp 副本变异②：隐式分支返回候选 ref（两点）
3 failed, 4 passed   # T1/T5/T6
```

其它独立核对：`INFO` 仅写 stderr（stdout 重定向后只剩 `passed`）；delta/current Requirement 块逐字一致；`git status --short` 收尾仍为空（未改工作树）；ci.yml 仅注释变更，witnessloop / platform-gate 未动。

## 收口确认
- 第 1 轮 medium+ 批次为空（0 条），deferred 为空；low/nit 5 条已登记、均不阻塞合入。
- 任务逐项验证未发现虚报完成（4.6 为记录证据未重跑，已注明）；4.7/4.8/5.x 未勾口径正确，归档前须结算。

## 闭环出口
PASS

本批 medium+ 数量：0
