# Building Review — retire-4phase-state-machine（第 3 轮 / 封顶轮）

- **Reviewer**: 独立零记忆 subagent（`/review-loop`，issue #90）
- **审阅对象**: `git diff ac0ccd7...HEAD`
- **base / head**: `ac0ccd7` / `987cb1ffb3bda60261e99f6a61758aafadbf3479`
- **审阅时间**: 2026-09-22
- **前置轮次**: R1 CHANGES_REQUESTED（3 条：2 中 1 低）→ R2 CHANGES_REQUESTED（1 条中残留）

## Verdict

**PASS**

R2 的唯一 Issue（`walkthrough.md:3666` 残留「74 个 task.json」）**已修复且与全仓完全一致**：`:3666` 现为「**73 个 task.json**（33 本地 + 38 Verified + 2 gate-smoke）」，与同文件 `:3900`、`:3670` 表格（33 / 38 / 2）、`:3674`（coding 合计 71）逐项自洽，并与文件系统实测（顶层 71 + gate-smoke 2 = 73；track 聚合 A=22 / B=11 / verified=38）完全吻合。R2 修复仅动 1 行（`git diff --stat cd9e645..HEAD` = 1 file changed, 1 insertion(+), 1 deletion(-)），未引入任何新问题——相反它顺手订正了 R2 提到的「glob 口径注记错位」（旧注记指向单层 glob 与实际递归计数不符，现改为明确的分项口径）。

本轮全仓脚本化交叉比对（`docs/` + `README.md` + `README_EN.md` + `AGENTS.md` + `CONTEXT.md`，排除 `openspec/changes/archive/**` 与 `docs/research/**`）**未再发现任何本 change 事实冲突的残留数字**：`74 个 task.json` / `72` / `34 本地` / `B 轨 12` 均已归零，`73 个 task.json` 全仓仅 2 处且互相一致。协议升级目标区间（A 轨 20–24 / B 轨 12–16 / Verified 50 / 合计 82–90 / ~90）原样保留，未被误改成现状数字。历史归档与既有漂移文件零改动。

第 3 轮为封顶轮：R1 三条 Issue 全部收敛，R2 一条 Issue 已收敛，本轮仅记录 **2 条「低」级既有漂移**（不在本 change 事实差量内、base 即已存在且被本 change 逐字保留），按裁定规则不阻塞，作为已知边界记录在案。

## 全部 Issue 收敛总览（R1–R3）

| # | 轮次 | 严重程度 | 描述 | 状态 |
|---|---|---|---|---|
| R1-1 | R1 | 中 | `walkthrough.md` B 轨表头仍写「（12）」且明细表仍列已删除的 `asterwynd-b03-awaiting-grill-state` | **已修复**（R2 已核销；本轮复验：表头（11）、明细 11 行、与 FS ID 集合逐字一致） |
| R1-2 | R1 | 中 | 数字同步漏改（`walkthrough.md:3676/:3817`、`FINAL-master-script.md:118`、`interview-prep.md:557`）造成同文件内自相矛盾 | **已修复**（R2 已核销四处具名位置；本轮全仓重扫无残留） |
| R1-2' | R2 | 中 | 同类残留：`walkthrough.md:3666` 仍写「74 个 task.json」 | **已修复**（`987cb1f`；本轮脚本实测，见「本轮独立复核」①） |
| R1-3 | R1 | 低 | `Q13-benchmark.md:7` 的「B 轨 12–16」属协议目标口径 | **处置正确**（协议目标原文保留，仅现状 72→71） |
| R3-1 | R3 | 低 | `README.md:178` / `README_EN.md:178`「44 个编码任务」为陈旧计数 | **已知边界（非本 change 造成）**，见「Issues」 |
| R3-2 | R3 | 低 | `README.md:36` / `README_EN.md:36`「10 fixture」为陈旧计数 | **已知边界（非本 change 造成）**，见「Issues」 |

## 本轮独立复核

### ① R2 Issue #1 是否真修好（脚本抽取 + 文件系统交叉，非目测）

`git diff cd9e645..HEAD` 为单行改动：

```
-`benchmarks/tasks/` 下共有 **74 个 task.json**（`benchmarks/tasks/*/task.json` glob 结果）：
+`benchmarks/tasks/` 下共有 **73 个 task.json**（33 本地 + 38 Verified + 2 gate-smoke）：
```

同文件四处数字实测（awk 逐行抽取）：

| 行 | 内容 | 一致性 |
|---|---|---|
| `:3662` | `### 11. 任务数据集 — 71 个 coding 任务` | ✅ 与 :3674 合计 71 自洽 |
| `:3666` | `共有 **73 个 task.json**（33 本地 + 38 Verified + 2 gate-smoke）` | ✅ **本轮修复点** |
| `:3670` | 表格：本地 **33**（22 A + 11 B）/ Verified **38** / gate-smoke **2** | ✅ 33+38+2 = 73 |
| `:3674` | `coding 任务合计 = 71（33 本地 + 38 Verified）` | ✅ 73 − 2 gate-smoke = 71 |
| `:3900` | `73 个 task.json — 33 本地 + 38 Verified + 2 gate-smoke` | ✅ 与 :3666 逐字同口径 |

文件系统实测（`ls -d` + Python 聚合）：

```
ls -d benchmarks/tasks/*/task.json | wc -l          → 71   (顶层)
ls -d benchmarks/tasks/gate-smoke/*/task.json | wc -l → 2
find benchmarks/tasks -name task.json | wc -l        → 73   (递归)
track 聚合(全部 task.json): {'verified': 38, 'A': 22, 'B': 11}  total 71
```

**结论：73 在本文件所有出现点、以及两种口径（递归 / 顶层+gate-smoke）下均成立。R2 Issue #1 已正确修复。**

### ② 全仓最终交叉比对（脚本跨文件，非逐条 grep）

写脚本对 `docs/**/*.md` + `README.md` + `README_EN.md` + `AGENTS.md` + `CONTEXT.md`（排除 `openspec/changes/archive/**`、`docs/research/**`）抽取所有候选陈旧计数：

```
--- 74个task.json ---   (none)
--- 73个task.json ---   docs/interview-bullets/walkthrough.md:3666
                        docs/interview-bullets/walkthrough.md:3900
--- 34个本地/本地任务34 --- docs/openspec-change-backlog.md:88  (历史归档 change 的既有记述)
--- 72(非区间) ---       (none)
--- B轨12(非区间) ---    (none)
```

- **`74 个 task.json` 全仓归零** ✅
- `73 个 task.json` 仅 2 处，互为同口径 ✅
- 唯一命中的 `34 本地` 位于 `docs/openspec-change-backlog.md:88`，是**历史已归档 change `evaluation-btrack-expansion` 当时的交付口径**（原文「面试叙事数字校准 37→44（34 本地 = 22 A + 12 B）」），属历史记录、不应回改；且该行**不在本 change 的 diff 内**（`git diff ac0ccd7...HEAD -- docs/openspec-change-backlog.md | grep btrack-expansion` 零命中）✅

补充枚举式校验（正则）：「本地 33」「A 轨 22」「B 轨 11」「总数 71」「Verified 38」「task.json 73」在不同文档间的出现点全部互相兼容，无自相矛盾。

### ③ 协议升级目标区间未被误改（重点）

| 位置 | 协议目标（应原样保留） | 实测 |
|---|---|---|
| `docs/benchmark-run-protocol.md:21-24` | 「A 轨 20–24 / B 轨 12–16 / Verified 50 / 合计 82–90」 | `git diff ac0ccd7...HEAD -- docs/benchmark-run-protocol.md` **零输出**（整文件未动）✅ |
| `docs/interview-script/questions/Q13-benchmark.md:7` | 「~90 = A 轨 20–24 + B 轨 12–16 + Verified 50」**原文保留** | 仅现状「72 = 34 本地」→「71 = 33 本地」✅ |
| `docs/interview-script/FINAL-master-script.md:118` | 「~90（A 轨 20–24 + B 轨 12–16 + Verified 50）」**原文保留** | 仅现状「当前已落 72」→「71」✅ |
| `docs/interview-bullets/walkthrough.md:3676/:3816` | 「82–90（A 轨 20–24 + B 轨 12–16 + Verified 50）」**原文保留** | 仅现状改 ✅ |

**无任何协议目标区间被改写成现状数字。** R1 Issue 3 的处置在本轮仍然正确。

### ④ 历史归档 / 既有漂移未被动

```
$ git diff --name-only ac0ccd7...HEAD -- openspec/changes/archive/     # 零输出 ✅
$ git diff --name-only ac0ccd7...HEAD -- docs/benchmark-plan.md        # 零输出 ✅
$ git diff --name-only ac0ccd7...HEAD -- docs/benchmark-run-protocol.md # 零输出 ✅
```

`benchmark-plan.md:22/:76` 的既有漂移「27 个本地任务」保持未动，与本 change 无关 ✅

### ⑤ 任务 ID 明细表 ↔ 文件系统（脚本集合比对）

| 轨道 | 文档明细表 ID 数 | FS `track` 聚合数 | 集合精确相等 |
|---|---|---|---|
| A 轨（`walkthrough.md:3684-3694`，双列表） | 22 | 22 | **True**（`doc-only=∅`、`fs-only=∅`） |
| B 轨（`walkthrough.md:3700-3710`） | 11 | 11 | **True**（`doc-only=∅`、`fs-only=∅`） |

`asterwynd-b03-awaiting-grill-state` 在 B 轨明细表中已不存在 ✅

### ⑥ 抽样独立复核 R1/R2 声明的已排除高危（本任务要求 #6）

**抽样项：`.gitignore` glob 双向验证**（`git check-ignore -v`）：

| 路径 | 结果 |
|---|---|
| `openspec/changes/retire-4phase-state-machine/handoff.json` | 命中 `.gitignore:26:openspec/changes/*/handoff.json`，**exit 0**（被忽略）✅ |
| `openspec/changes/archive/2026-08-15-flow-event-projection/handoff.json` | **exit 1**（不忽略）✅ |
| `openspec/changes/archive/2026-08-15-flow-event-projection/workflow-state.json` | **exit 1**（不忽略）✅ |

单层 `*` 正确地只覆盖 active `changes/<id>/`、不误伤嵌套两层的 `changes/archive/<date>-<id>/`——双向验证通过，R1/R2 结论独立复现。

**附加抽样（顺带，因成本低）：spec delta 与正式 spec 的 Requirement 名逐字匹配 + 活 Scenario 存在性**：

```
dev-workflow-state-machine: delta=16 official=22 ; delta - official = ∅  (0 处名字不匹配)
change-documentation:       delta=2  official=15 ; delta - official = ∅
活 Scenario: 受保护写通道拒绝非法目标 / 受保护写通道拒绝归档语境下的非法 change id /
             checker 派生物一致性 / guard 读投影执法 / flow status 展示投影  → 全部 PRESENT ✅
```

`openspec archive` 靠 Requirement 名做匹配，0 处不匹配意味着 delta 不会静默失效。

## Issues（本轮新发现）

两条**「低」**，性质相同：**base 提交即已存在的陈旧计数，本 change 逐字未动、且不在本 change 的事实差量内**（本 change 删除的是本地任务 `b03`，不改变 Verified 子集计数，也不改变历史快照口径）。按 R1/R2 对既有漂移（`benchmark-plan.md:22` 的「27 个本地任务」）的既定裁量口径，判定为**非阻塞的已知边界**。

| # | 严重程度 | 位置（文件:行号） | 描述 | 证据 |
|---|---|---|---|---|
| 1 | 低 | `README.md:178` / `README_EN.md:178` | 项目结构树「`tasks/` # **44 个编码任务**（asterwynd-* 本地 + swebench-* Verified 子集）」为陈旧计数（44 ≈ 旧口径 34 本地 + 10 Verified）；与本文件 `:36`/`:374` 已同步的「33 本地 + Verified 38」不符。 | 该行 base==HEAD **逐字节相同**（`diff <(git show ac0ccd7:README.md \| sed -n 178p) <(sed -n 178p README.md)` 无差异），本 change 未触碰；44 在 base 即不成立（base 顶层 34+38=72 ≠ 44），**非本 change 造成** |
| 2 | 低 | `README.md:36` / `README_EN.md:36` | 「SWE-bench Verified 精选子集（**10 fixture**，目标 50）」为陈旧计数（现为 38）；同行本 change 仅把「34 个本地」改为「33 个本地」/「12 B 轨」改为「11 B 轨」。 | 「10 fixture」在 diff 中**无独立 +/- 行**（仅作为被改行的上下文保留）；base Verified 实为 38，10 在 base 即不成立，**非本 change 造成** |

**说明**：这两条的修复面都不在本 change 的交付范围内——`b03` 是本地任务，其删除不改变 Verified 子集数量（38 前后一致），也不改变 `44` 所记的历史快照口径。二者的根因是更早的 Verified 子集扩容（10 → 38）与本地任务扩容（26 → 34）时的 README 同步遗漏，属**独立债务**，建议另记 `docs/known-debt.md` 或单独 issue 处理，不阻塞本 change 合入。

> 另注：本 change **修正了** README_EN 内部的一处既有矛盾——`README_EN.md:375` base 写「27 local tasks」，与同文件 `:36` 的「34 local」冲突；本 change 已将其同步为「33 local tasks」，与 `:36` 一致。即本 change 在 README 数字同步上是**净改善**。

## 命令输出

```
$ uv run pytest -q
4 failed, 2916 passed, 10 skipped, 76 warnings in 292.79s (0:04:52)
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
FAILED tests/agent/tools/test_factory_sandbox_wiring.py::TestBuildSandboxFromConfig::test_docker_backend
FAILED tests/agent/tools/test_sandbox_backends.py::TestBackendSelection::test_docker_backend_available
# 与 R1 / R2 / base ac0ccd7 完全相同的 4 条既有失败（memory 2 + docker 2，环境相关），非本 change 引入。
# passed 数与 R2 相同（2916），说明 R2 修复为零回归的纯文档单行改动。

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)

$ uv run python scripts/check_openspec_artifacts.py
ERROR: retire-4phase-state-machine: review manifest missing: .../reviews/building-review-manifest.json
exit=1
# 预期结果，非缺陷：manifest 在审阅 PASS 后的收尾阶段生成，且须在 tasks.md 最终化 / 归档后生成
# （D3 纪律）。本轮不生成、不计入 Issue。

$ git rev-parse HEAD
987cb1ffb3bda60261e99f6a61758aafadbf3479

$ git diff --stat cd9e645..HEAD            # R2 修复增量
 docs/interview-bullets/walkthrough.md | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)

$ git diff --name-only ac0ccd7...HEAD -- openspec/changes/archive/          # （零输出）✅
$ git diff --name-only ac0ccd7...HEAD -- docs/benchmark-plan.md             # （零输出）✅
$ git diff --name-only ac0ccd7...HEAD -- docs/benchmark-run-protocol.md     # （零输出）✅

# 文件系统口径
71   # ls -d benchmarks/tasks/*/task.json | wc -l
2    # ls -d benchmarks/tasks/gate-smoke/*/task.json | wc -l
73   # find benchmarks/tasks -name task.json | wc -l
{'verified': 38, 'A': 22, 'B': 11}  total 71   # track 聚合

# 任务 ID 集合比对
doc B count: 11 | FS B count: 11 | EXACT MATCH: True
doc A count: 22 | FS A count: 22 | EXACT MATCH: True

# .gitignore 双向（本轮独立抽样）
openspec/changes/retire-4phase-state-machine/handoff.json → .gitignore:26 命中, exit=0
openspec/changes/archive/<date>-<id>/handoff.json         → exit=1（不忽略）
openspec/changes/archive/<date>-<id>/workflow-state.json  → exit=1（不忽略）

# spec Requirement 名集合比对
dev-workflow-state-machine: delta=16 official=22 ; delta - official = ∅
change-documentation:       delta=2  official=15 ; delta - official = ∅
活性 Scenario 5/5 PRESENT

# 全仓残留扫描（脚本）
74个task.json → (none)        72 → (none)        B轨12(非区间) → (none)
73个task.json → walkthrough.md:3666, walkthrough.md:3900
「34 本地」唯一命中：docs/openspec-change-backlog.md:88（历史已归档 change 记述，未被本 change 改动）
```

## 抽样范围与未覆盖说明

本轮按任务要求做**针对性复核 + 抽样**。实际执行：R2 Issue #1 定点实测（4 处数字 + FS 双口径）、全仓脚本化残留扫描（含枚举正则）、任务 ID 集合比对、协议目标区间逐处确认、归档/漂移文件 diff 空验证、`.gitignore` 双向验证（抽样项）、spec Requirement 名集合比对 + 活 Scenario 存在性（附加抽样）。

**未重跑**：R1 的两处变异验证（恢复子命令 / 恢复 handoff 写）与 benchmark smoke、覆盖率矩阵、49 归档 change 投影扫描。理由：R2 相对 R1 的增量为**纯文档单行 diff**（`987cb1f` 仅改 1 个 `.md` 文件 1 行），不触及任何代码 / spec / 门禁路径；上述项目在 R1 实测有判别力，本轮的改动面不可能影响其结果。

## 结论

- **R2 Issue #1 已修复**：`walkthrough.md:3666` = 73，与同文件 `:3900`/`:3670`/`:3674` 及文件系统（71 + 2 = 73）全口径自洽，且顺手订正了旧 glob 口径注记的错位。
- **本轮全仓扫描零残留**：`74`/`72`/`34 本地`/`B 轨 12` 均已归零，无任何本 change 事实冲突的计数。
- **协议升级目标区间、历史归档、既有漂移文件均未被误改**；R1 关于架构级删除面「干净」的核心结论在本轮抽样复核下继续成立。
- 新增仅 2 条**「低」**级、**非本 change 造成**的既有 README 漂移（44 / 10 fixture），按既定裁量口径记为**已知边界**，不阻塞。
- 按判定规则（无「高」/「中」Issue → PASS），且本轮为第 3 轮封顶轮，**最终 Verdict：PASS**。建议收尾阶段生成 review manifest 时一并（可选）把上述 2 条 README 漂移记入 `docs/known-debt.md` 或单开 issue。
