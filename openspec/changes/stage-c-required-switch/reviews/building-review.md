# Building Review: stage-c-required-switch（Round 2，最终版）

## Reviewer
- run id: paseo-building-review-stage-c-required-switch-r2
- 被审 revision: `60813b03d09a26f80a889f79c5e231420baaceb3`（HEAD）
- base: `4b5cc7d1a49d06caa94fe2c35aae2ccfce778e23`（`git merge-base HEAD origin/master`）
- 时间: 2026-10-17
- 零记忆: 是（未继承任何开发上下文；所有结论来自本次实跑与仓库原文）
- 工作区状态: 复核开始与结束时 `git status --porcelain` 均为空。**说明一处审阅者副作用**：为验证事件日志可投影，跑过一次 `flow status --change stage-c-required-switch`，它按设计自愈写了一份 gitignore 的 `openspec/changes/stage-c-required-switch/workflow-state.json`（`.gitignore:27` 命中）；已在收尾时删除，树恢复原状。

## Verdict

**CHANGES_REQUESTED**

理由：**本 change 的实质改动（规格同步）本轮逐字节复核为完全正确**——delta 的每一条 MODIFIED/ADDED 与当前规格**逐字节相同**（platform-gate 3 条、dev-workflow-gate 4 条）、REMOVED 那条确已消失、两份规格的 Requirement 计数为 **4 / 12**、被声明保留的 8 条**逐字节未变**（R1 的 I-9 空白噪声已由 `614db93`→`60813b0` 的重建彻底消除），事件日志、backlog、任务勾选与仓库事实逐条对得上，归档点四道门在模拟中**全过**。**没有发现规格与实况不符、也没有会让归档点门判红的问题。**

但发现 **1 条记录准确性缺陷（low 级，但按本仓判据属阻塞类）**：`design.md:208` 的 R3 收敛行声明「6 条非阻塞观察：**2 条处置**…**4 条如实登记为「接受、不处置」**」，而它的 4 条清单里**第 1 条描述的对象在同一次提交 `60813b0` 里已经被修掉了**（`design.md:191` 的「共 **6 处**」已删）——即「登记为未处置」与「实际已处置」相反；同时该 6=2+4 的划分**把 R3 的第 3 条观察算了两遍、把第 6 条观察整条漏掉**。这正是 R1 的 I-1 要求「如实登记」的那张表，也是本 change 三轮对抗反复追打的同一形态（记录 vs 产物不一致；R3 的 B-1 正是「修法自己引入新不一致」）。鉴于本 change 的全部价值就是记录准确，且修法是清单级的一处编辑，判 **CHANGES_REQUESTED**。

## Tasks Verification

逐条核对 `tasks.md` 里每一个 `[x]`（读产物 / 跑命令，不只看任务行写了什么）：

- **0.1**: 成立。`reviews/grill-design.md` 存在（22950 B），`## Confirmed Decisions`（`:8`）下有 **10** 条决策块（门槛 `MIN_CONFIRMED_DECISIONS = 3`），每条均为**同行裸** `来源: <run-id>`。用 witnessloop v1.7.0 自己的谓词实测 `grill_evidence_findings(text)` = **`[]`**（0 findings）。证据: `reviews/grill-design.md:9-18`。
- **0.2**: 成立。`reviews/grill-design.md:13` 用 `.witnessloop/policy.json:11-15` 的 `require_change_for = ["agent/**","scripts/**","web/**"]` 判定本 change 不触达它。本轮另实测本 change 的 diff 面（`git diff --name-only origin/master...HEAD` 共 19 个文件，**全部**在 `openspec/**` 与 `docs/**` 内）⇒ 该前提成立。
- **0.3**: 成立。`reviews/grill-adversarial.md` 含 `## Round 2`（`:102`）与 `## Round 3`（`:172`）两节 + Round 1 主体；三轮的 `被审 revision`（`798973e` / `647e349a4921…` / `5a074c784c4f…`）**逐个 `git log -1` 实测均在本分支存在**。
- **0.4**: 成立。停轮队列为空：`grill-design.md` 的 `## Open Questions`（`:46-47`）明写没有需要人类拍板的问题；本轮直接调 `_extract_open_question_indexes` = `[]`、`_unconfirmed_open_questions` = `[]` ⇒ 停轮门与用户确认门都不会被激活。
- **0.5**: 成立。`design.md:163` 有 `## Pre-Implementation Review`，含 D1–D8 处置表、三轮对抗收敛表（`:205-208`）与停轮结论。
- **0.6**: 成立。四条格式契约齐备且实测 0 findings；`## User Confirmation` 小节**无条件存在**（`grill-design.md:49`）并写明了 v1.7.0 的判据来源；候选 Open Questions 小节存在（`:46`）。
- **1.1**: 成立。`specs/platform-gate/spec.md` 的 delta 结构实测 = `## MODIFIED Requirements` **2** 条（合入平台闸门 / 平台闸门复用 GitHub branch protection 语义）+ `## ADDED Requirements` **1** 条（降级为非必过的检查仍须运行），无 REMOVED；顶部有「待施加的输入」显式声明（`:3`）。
- **1.2**: 成立。`specs/dev-workflow-gate/spec.md` 的 delta 实测 = `## REMOVED` **1** 条（带 Reason + Migration）+ `## MODIFIED` **2** 条 + `## ADDED` **2** 条（含 Decision 9 那条「翻开关这一动作自身必须具备 change 记录」）。
- **1.3**: 成立，且**本轮逐字节复核通过**。同步确已完成：脚本把 delta 的每个 MODIFIED/ADDED 块与当前规格逐字节比对 → **全部 EXACT**；REMOVED 的那条在现状里**确已消失**。计数：`platform-gate` **3 → 4**、`dev-workflow-gate` **11 → 12**。任务行「其余 10 条逐条保留且逐字节不变」——实测保留 10 条中，8 条（`双 PreToolUse` 那条仅差**块尾分隔空行**：它在 base 里是文件末块故无该空行，内容逐字节相同）内容未变，另 2 条正是 delta 声明要改的 MODIFIED。**已无空白噪声**（详见 R1-I-9 复核对）。任务行提到的计数已如实落在 `workflow-events.jsonl` 的 seq 3 / seq 4 两条 `current_spec_synced` 的 `reason` 里。
- **1.4**: 成立。`docs/development-guide.md` 的两条阶段 A 遗留 bullet 已按阶段 C 实况改写（`:354` 改为指向**已归档**的 `witnessloop-adoption`；`:355` 不再出现「本 change 自己」，改为「阶段 A 实测，仍然适用」）。证据: `git diff origin/master...HEAD -- docs/development-guide.md`。
- **1.5**: 成立。两份规格的 `## Purpose` 段与 `dev-workflow-gate` 的「阶段划分」段（`:10`，Purpose 段内的加粗段，**无 delta 载体**）均已按阶段 C 实况改写；段内死链已修（`:10` 现指 `openspec/changes/archive/2026-10-13-witnessloop-adoption/reviews/acceptance-stage-a.md`，**该文件实测存在**，26456 B）。1.3 / 1.5 现已在任务行里显式区分成两条轴（`:22` 只讲 Requirement，`:24` 只讲无 delta 载体的段落），R1 的 I-4 已闭环。
- **1.6**: 成立。`README.md:149` 与 `README_EN.md:149` 两条**同改同向**（中英各一行，语义逐字对应）。
- **1.7**: 成立。任务行点名的位置逐个读过，均为「判失败 / 报警，阶段 C 之后不再拦合并」口径：`Q13:13/:15/:51/:63`、`Q09:15/:61`、`walkthrough:3895`（现写「三个 job（阶段 C 后都不再拦合并）」）、`Q12-ci-testing.md:5`（「有三个 job」+ 树图三 job + required 段）。全仓 `grep -rn "自动拦截" docs/` = **0 命中**。任务行「不写「共 N 处」总数口径」的告诫**已被遵守**（见 I-1）。
- **2.1**（T1）: 成立。实跑 `Totals: 30 passed, 0 failed (30 items)`，exit 0，含 `✓ change/stage-c-required-switch`。
- **2.2**（T2）: **记录的 exit 0 在本次 revision 上不再复现**——本轮实跑 **exit 1**。原因不是同步出错，而是 `reviews/building-review.md`（R1 报告，已在 `60813b0` 落盘）触发了 checker 的 manifest 门：`ERROR: stage-c-required-switch: review manifest missing: …/reviews/building-review-manifest.json`。该 manifest 属未勾的 3.1/5.5 ⇒ **计划内未完成**，不是假绿；但任务行记的原始输出需在 3.1 之后刷新（见 I-2）。
- **2.3**（T3）: 同上，**本轮实测 exit 1**，同一原因（stderr 仍有一行 `[archived manifest check] tasks_hash 已按归档语境跳过（76 个 change；其余 hash 与字段仍校验）`）。
- **2.4**（T4）: 成立。`uv run python scripts/platform_gate.py --verify` 逐字段 `match: true`、输出 `全部一致`、**exit 0**；`target.contexts = ['gate / check']` 与 `scripts/platform-gate.json` 声明一致。任务行「不跑 `--apply`」（R7）**被遵守**：`scripts/platform-gate.json` 不在本 change 的 19 个变更文件里。
- **2.4b**（benchmark smoke）: 成立且**可复现**。用任务行**逐字**的命令（仅把 runs-dir 换成审阅者专属目录）重跑，得到**同样的输出与同样的 exit 0**：`success_rate: baseline=1.0000 current=1.0000 delta=+0.0000` / `p95_latency_s: SKIPPED (deterministic task set)` / `result: PASS`。任务行声称的产出目录 `/tmp/benchmark-gate-runs-sc/2026-10-16T19-05-06/` **确实存在**。
- **2.5**: 成立。规格里每一条涉及 required 集合 / job 是否运行 / `--apply` 是否已执行的断言，逐条与本轮 `gh api repos/Xingkai98/asterwynd/branches/master/protection` 的原始 JSON 对上：`{"admins":true,"approvals":0,"contexts":["gate / check"],"conv":true,"strict":true}`（见「Spec 对齐」）。

未勾任务（3.1、3.2、4.1–4.3、5.1–5.6、6.1–6.2）经核对**均为计划内**，其中 6.1 / 6.2 已正确标注 `(post-merge)`。**保守方向的两处**：5.1（backlog 结算）与 5.2（写事件日志）的实际产物**已存在**（见下），却仍是 `- [ ]`——少勾只会拦自己，但 5.3 结算时必须勾掉，否则归档点门会报「未勾且未标 `(post-merge)`」。

## Spec 对齐（内容真实性）

| 规格断言 | 实况（本轮实跑） | 结论 |
|---|---|---|
| `required_status_checks.contexts` = `["gate / check"]` 且只有它 | `["gate / check"]` | ✅ |
| `required_status_checks.strict` = true | `true` | ✅ |
| `required_conversation_resolution` 开启 | `true` | ✅ |
| `required_approving_review_count` = 0 | `0` | ✅ |
| `enforce_admins` 开启 | `true` | ✅ |
| 该值由 `scripts/platform-gate.json` 声明 | `--verify` 逐字段 `match: true`，exit 0 | ✅ |
| `validate` / `benchmark-gate` / `windows-platform` 三 job 仍运行（降级不关闭） | `.github/workflows/ci.yml` 三 job 齐备；本 change **未动** `.github/`（`git diff --name-only origin/master...HEAD -- .github/` 无输出） | ✅ |
| 本 change 不改平台实况（R7） | `--verify` 全部一致；`platform-gate.json` 不在 diff 内 | ✅ |
| Purpose 段死链已改指归档路径 | `dev-workflow-gate/spec.md:10`，目标文件存在（26456 B） | ✅ |
| 「已知红性质迁移」已被记录 | `dev-workflow-gate/spec.md` MODIFIED 条目 + 新 Scenario 实测存在 | ✅ |

**全仓旧口径扫描（本轮专做）**：`grep -rn "required" --include=*.md docs/ README.md README_EN.md AGENTS.md CONTEXT.md | grep -E "validate|benchmark-gate"` 的命中里，**没有一处**仍把 `validate` / `benchmark-gate` 当作 required；`docs/testing-guide.md:43` 的「原本两个 job」是讲 locale 历史教训（对象是「原本」），不是被本次证伪的 CI 口径。⇒ 事实漂移面已清干净。

**引用溯源（本轮抽查 8 处，全部成立）**：`AGENTS.md:226` ✅ 逐字；`docs/development-guide.md:350` / `:354` / `:355` ✅；`tasks.md:31` 关于「本地 `master` ≠ `origin/master` 故 T2 必须显式绑 `origin/master`」的告诫 ✅（实测 `3c7196b2…` vs `4b5cc7d1…`）；`design.md:263` 关于 witnessloop revision（PATH 0.1.0 / `v1` / CI `v1.7.0`）✅；`.witnessloop/policy.json:11-15` 的 `require_change_for` ✅；`design.md:152` 的「仓内仅 1 份归档 delta 含 `## Purpose`」✅（实测 219 份归档 delta 中恰好 1 份）；`design.md:160` 的「阶段 B 实测 63 份归档 `grill-design.md` 中 39 份零 finding」✅ **复算成立**（排除 `2026-10-14-guard-write-allowlist` 后恰好 63 / 39——见 R1-I-6）；`proposal.md:83` 的 CI 日志 `##[notice]` 原文 ✅ 逐字（本轮未再发现 R3 的 B-1 那种假出处：`docs/development-guide.md` 的引文已从该句中删除）。

## Issues

- **I-1（low；按本仓判据「断言了仓库里查不到的事实」属阻塞类）: `design.md` 的 R3 处置登记与产物相反，且 6=2+4 的划分漏掉 R3 的一条观察。**
  证据（逐条实测）：
  - `design.md:208`（R3 收敛行的处置格）写「6 条非阻塞观察：**2 条处置**（Decision 4 的「只写一处」规则**对称**适用到 `dev-workflow-gate` 的 ADDED 条目；tasks 0.3 的 `exempt` 字样改为 `light`），**4 条如实登记为「接受、不处置」**（见下）」。
  - `reviews/grill-adversarial.md` 的 R3「非阻塞观察」节实测有 **6 条**（编号 1–6）：1 = Decision 4 规则范围；2 = `tasks.md:13` 的 `exempt`；**3 = 讲稿面处数/清单口径两处残留（① `design.md:191` 的「共 **6 处**」；② `proposal.md:64` 漏 `Q13:15`）**；4 = 收尾节未点名 5.1/5.2/5.3；5 = Decision 5 假阳性的耐久落点；6 = `grill-design.md` 的 `## Open Questions` 说明句。
  - `design.md:213-217` 登记为「接受、不处置」的 4 条 = {R3-3①, R3-4, R3-5, R3-3②}。连同「2 条处置」= {R3-1, R3-2}，这 6 个名额里 **R3-3 被拆成 ①②各占一格、R3-6 整条没有落点**。
  - 清单第 1 条（`design.md:214`）写「**`design.md` 的历史行仍写「6 处」**…改写它会让「当时发现了什么」的叙述失真」，但 **`60813b0` 已把 `design.md:191` 的「共 **6 处**一次性订正」删掉**、改为按位置列举：`git show 614db93:…design.md | grep "共 6 处"` 有命中，HEAD 实测 **0 命中**（`grep -rn "共 6 处\|共 9 处" design.md` 无输出；`design.md` 里唯一含「6 处」字样的就是这条登记本身）。⇒ **该条登记的对象在同一次提交里已处置**，登记与产物相反，且它给的不处置理由（「改写会让叙述失真」）随之失效。
  - 同一清单第 4 条（`design.md:217`）也已被 I-2 的修法部分推翻：`proposal.md:64` 现为 `Q13-benchmark.md:13/:15/:51/:63`（`614db93` 时是 `:13/:51/:63`），R3-3② 点名的缺口已补。
  ⇒ 后果：后人按这张表读「R3 留了哪 4 条不处置」，会得到**两个已被修掉的条目**，并因此低估实际处置数（实际至少 4 条：Decision 4 指针、`tasks.md` 的 `exempt`、`design.md:191` 的总数、`proposal.md:64` 的 `:15`）。这正是 R1 的 I-1 要求「如实登记」的那张表，也是本 change 三轮对抗反复追打的同一形态。
  建议: 把 R3-3① 从「接受、不处置」清单移出（它已处置），改成如实口径，例如：R3 的 6 条中 **4 条已处置**（Decision 4 指针、`tasks.md:13` 的 `exempt`、`design.md:191` 的总数口径、`proposal.md:64` 的 `:15`）、**2 条接受不处置**（收尾节未点名 5.1/5.2/5.3；Decision 5 假阳性无耐久落点）、**1 条已满足**（R3-6：`grill-design.md:47` 的说明文字即其要求的落点）；或至少把 `design.md:214` 的「仍写「6 处」」改为过去式并说明它已随本轮修掉。
- **I-2（low）: 任务 2.2 / 2.3 记录的 `exit 0` 在本次 revision 上不再复现，而设计只预警了另一种失效方向。**
  证据: `tasks.md:31` / `:32` 各记「→ exit 0」并已勾 `[x]`；本轮实跑 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` 与 `… --check-archived --skip-protected-paths --skip-backlog` 均 **exit 1**，唯一错误是 `review manifest missing: …/reviews/building-review-manifest.json`——触发源是 R1 的报告 `reviews/building-review.md` 在 `60813b0` 落盘（checker 对 `reviews/*-review.md` 逐个要求配对 manifest，见 `scripts/check_openspec_artifacts.py:1143-1152`），而 manifest 属未勾的 3.1 / 5.5。`design.md` 的 Testing Strategy 只写死了「T2/T3/T5 只对**已提交**的内容有效（untracked 不进 `git diff`）」这一种失效方向，没有覆盖「审阅报告已提交、manifest 尚未生成」这一种。
  为什么算 issue：它属「记录与实况不符」（勾着的行断言一个当前为红的判据），且会让复核者/执行者在中途重跑 T2/T3 时误判本 change 坏了。**不阻塞归档**——3.1 产出 manifest 后 T2/T3 会自动恢复绿。
  建议: 在 3.1 生成 manifest 之后**重跑 T2/T3 并用新输出刷新这两行**（或在这两行标注「exit 0 的取值时点为 `614db93`；`reviews/building-review.md` 落盘后需待 3.1 的 manifest 配对才复现」），并在 Testing Strategy 的「前置」列补一句这个第三态。

## Test Results

逐条实跑，抄原始结论：

| # | 命令 | 原始结论 |
|---|---|---|
| T1 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 30 passed, 0 failed (30 items)`，**exit 0**（含 `✓ change/stage-c-required-switch`、`✓ spec/platform-gate`、`✓ spec/dev-workflow-gate`） |
| T2 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | **exit 1**：`ERROR: stage-c-required-switch: review manifest missing: openspec/changes/stage-c-required-switch/reviews/building-review-manifest.json`（见 I-2；计划内，3.1 后恢复） |
| T3 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` | **exit 1**，同一错误；stderr 一行 `[archived manifest check] tasks_hash 已按归档语境跳过（76 个 change；其余 hash 与字段仍校验）` |
| T4 | `uv run python scripts/platform_gate.py --verify` | 逐字段 `match: true`，输出 `全部一致`，**exit 0** |
| T5 | `/home/happy/wl170/bin/witnessloop check --root . --base origin/master --head HEAD` | **未通过 ✗（2 项）**，exit 1：① `缺少 review manifest`（= 3.1/4.1 未做）② `无 stage=grill 的 manifest（现有 stage：（无））`（= 4.1/4.2 未做）。**两项均为本 change 尚未产证据的计划内状态，不是缺陷**；自报 `requested_revision=v1.7.0，commit_id=c9b281167ad20b63e4832ad9ab8510964a2adc60`（锚定正确）；报「19 个变更文件，1 个 change 目录」 |

**附加实跑（本轮新做，非引用）**：

| 检查 | 结论 |
|---|---|
| delta ↔ 当前规格逐字节比对 | platform-gate：MODIFIED 2 / ADDED 1 **全 EXACT**；dev-workflow-gate：MODIFIED 2 / ADDED 2 **全 EXACT** |
| 保留的 Requirement 逐字节性 | 8 条内容逐字节未变（其中 7 条连块尾都相同，`双 PreToolUse…` 仅差块尾分隔空行——它在 base 里是文件末块）；差异只有 Purpose + 2 MODIFIED + 1 REMOVED + 2 ADDED。**R1 的 I-9 空白噪声已消除**（两份文件都只有单空行作块分隔：`\n\n### Requirement` 计数 = 12 / 11，`\n\n\n` = 0） |
| 事件日志字段与投影 | 5 条事件，`event_type`/`artifact_path`/`reason`/`approved_by`/`change_id`/`seq` **无空值**；`seq` = 1..5 **连续**；`project_workflow_state` 可投影（`flow status` 返回合法 JSON，`source_event_seq=5`，自愈后 `stale:false`，无 StateMachineError） |
| backlog 一致性 | 「## 未实现队列」（`:121`）与「## 已完成待归档」（`:175`）两节**均不含本 change**；唯一提及在「## 并行开发批次 / ### 第十七批」的已完成口径段落（`:115`），不在扫描范围 |
| 归档点完成度门模拟 | 把 change 目录复制到 `archive/2026-10-17-stage-c-required-switch/`、除两条 `(post-merge)` 外全勾后直接调 `_check_archived_completion_gate` → **0 条错误**；`_untagged_unchecked_tasks` = `[]`；RIR 门、停轮门、Open Question 确认门全部静默通过。另实测 5.3 行内的 `(post-merge)` 字样**不会**被误识别为标记（它被正确算作「未勾且未标」） |
| `reviews/` 孤儿面 | 只有 `grill-design.md` / `grill-adversarial.md` / `building-review.md` 三份 `.md`，**没有中间轮产物**（3.2 的清理要求已满足），暂无 `*.manifest.json` |
| `.github/` 逐字节性 | `git diff --name-only origin/master...HEAD -- .github/` **无输出** ⇒ 本 change 未弱化任何 CI 配置 |
| `grill_evidence_findings`（v1.7.0） | `[]`（0 findings） |

## Round 1 的 Issues 与处置

- **R1-I-1（medium，design 的 R3 行把 6 写成 2 且 4 条未登记）**: **部分处置**。数字已改对（`design.md:208` 现写「6 条非阻塞观察」）、4 条清单已建（`:213-217`）——这是 R1 要求的核心，做到了；但清单第 1 条（`:214`）**与产物相反**（`design.md:191` 的「共 6 处」已在本轮删除，见 I-1），且 6=2+4 的划分漏掉 R3 的第 6 条观察。⇒ 按 R1 的原要求（「其余 4 条如实登记为接受不处置」）复核，**登记不实**，故为部分处置。
- **R1-I-2（low，proposal 影响面清单漏 `Q13:15`）**: **已处置**。`proposal.md:64` 现为 `Q13-benchmark.md:13/:15/:51/:63`（`614db93` 时尚为 `:13/:51/:63`）；且 `Q13-benchmark.md:15` 实测已订正为阶段 C 口径。
- **R1-I-3（low，1.3 勾了但自称的 `current_spec_synced` 事件没有）**: **已处置**。`workflow-events.jsonl` 已存在，含 5 条事件（`change_created` / `backlog_updated` ×2 / `current_spec_synced` ×2），两份 `current_spec_synced` 的 `artifact_path` **分别指向 `openspec/specs/platform-gate/spec.md` 与 `openspec/specs/dev-workflow-gate/spec.md`**，`reason` 里如实带「3 → 4」与「11 → 12」的计数。`change_archived` 尚未写（属 5.4，计划内）。
- **R1-I-4（low，1.3 与 1.5 对 Purpose 段各写一遍且勾选相反）**: **已处置**。`tasks.md:22`（1.3）已删去 Purpose 子句、只讲 Requirement；`tasks.md:24`（1.5）现标 `[x]`、开头明写「**与 1.3 是两条不同的轴**」；1.5 声明的产物**全部实测存在**（Purpose 段与「阶段划分」段已改写、死链已修且目标文件存在）。
- **R1-I-5（low，required 取值同时断言在两份规格）**: **接受不处置**。`design.md:219` 已登记为「接受、不处置」并给了成立的理由（粒度不同：`platform-gate` 规定取值与不变量，`dev-workflow-gate` 只断言形态）。实测其理由**可核对**：`dev-workflow-gate` 的 ADDED 条目确有不变量指针 blockquote，且断言取值的 Scenario 带括注「（该取值与其不变量由 `platform-gate` 能力域规定）」。⇒ 处置方式合法。
- **R1-I-6（low，观察：63/39/3 ↔ 64/40/4 的测量口径）**: **未处置（可接受）**。实测数字**复算成立**：排除 `2026-10-14-guard-write-allowlist` 后恰好 grill-design.md **63** 份、零 finding **39** 份，且文本已标注「**阶段 B 实测**」⇒ 不是编造、是有测点的历史事实。**唯一残留**：同行「用加粗写法的只有 **3** 份」（`design.md:160`）测点当日成立、今日实测为 **4** 份，未标注测点，也未登记为接受不处置。R1 原判「不阻塞」，故不列 issue。
- **R1-I-7（low，观察：「76 份归档 delta」措辞）**: **未处置（可接受）**。`design.md:152` 仍写「仓内 76 份归档 delta 中仅 1 份含 `## Purpose`」。实测 76 是 checker 的另**一个**口径（带 `reviews/*-review.md` 的归档 change 数，T3 的 stderr 亦为「76 个 change」），归档 change 目录实为 **124**、归档 delta 文件实为 **219**；**实质结论成立**（219 份中确实只有 1 份含 `## Purpose`）。属措辞精度，R1 原判「不阻塞」。
- **R1-I-8（low，观察：`00192ab` 是 tag 对象 sha）**: **未处置（可接受）**。`proposal.md:83` 仍写「`00192abe…` 就是 `v1.7.0` tag 的 commit」。实测在 witnessloop 仓 `git cat-file -t 00192ab…` = **`tag`**、`git rev-parse 'v1.7.0^{commit}'` = `c9b2811…`；引用的合法性不受损（GitHub 与 witnessloop 自己的自报都把 `refs/tags/v1.7.0` 报成 `00192ab`）。R1 原判「不阻塞」。
- **R1-I-9（low，观察：同步在每个 Requirement 标题后插了空行）**: **已处置**。`614db93`→`60813b0` 的重建消除了空白噪声：两份规格的块分隔全为单空行（无 `\n\n\n### Requirement`），保留的 8 条 Requirement **内容逐字节未变**，diff 里只剩 Purpose 段 + 2 MODIFIED + 1 REMOVED + 2 ADDED，正是该出现的那几处。

## 非阻塞观察

- **T5 的 2 项红是计划内状态，不是缺陷**（对应未勾的 3.1 / 4.1 / 5.5）；如实记录即可，不必也不应为此改任何判据。
- **两份 delta 顶部的「待施加的输入」banner 现已过期**。`specs/*/spec.md:3` 仍写「本文件是「待施加的输入」，不是已同步的结果…在那一刻之前，当前规格里仍是阶段 A 的口径——**不要**据本文件的存在推断同步已完成」。同步**已经完成**（1.3 已勾、规格已是阶段 C 口径），故该 banner 的第一句与末句的告诫方向现在都是反的。它当初是为回应设计阶段 I-11（D2「待施加」未标记）而加，属措辞/时态问题；归档后读者若只看 delta，可能误以为同步仍待做。建议在 5.3 结算时顺手把它改成过去式或加一行「（同步已于 `614db93` 完成，当前规格已是阶段 C 口径）」。
- **R1 的 I-6 / I-7 / I-8 既未处置也未登记为「接受、不处置」**（R1 原判均为「不阻塞」，故可接受）。与 R3 的 4 条对照，本 change 为后者建了显式登记清单、为前者没有——同一类残留两种待遇，属体例不齐，非缺陷。
- **I-5 那份「接受、不处置」的措辞与相邻 Scenario 有轻微张力**：`dev-workflow-gate` 的 ADDED 条目 blockquote 写「required 集合与其「降级不关闭」不变量**不在本规格重复**」，而紧随其后的 Scenario 里仍有「本仓自建门禁 SHALL 全部退出 required（**降级，不是关闭**）」。取舍理由（形态 vs 取值/不变量）成立且有括注缓解，仅措辞面。
- **本 change 的实质改动面（规格同步）本轮未发现任何问题**：delta 与当前规格逐字节一致、计数正确、REMOVED 干净、保留条目未被动、全仓无残留旧口径、`.github/` 与 `scripts/**` 未动。I-1 / I-2 都是**记录层**的缺陷，不影响产物本身。

## 结论

本 change 的**实质交付是可信且精确的**：规格同步经逐字节比对为完全正确（delta 的 7 条 MODIFIED/ADDED 全部 EXACT、REMOVED 已消失、保留的 8 条内容逐字节未变、两份规格计数为 4 / 12），R1 指出的空白噪声（I-9）已被重建消除，规格里每一条涉及合入门禁实况的断言都与 `gh api` 的原始 JSON 和 `--verify` 的输出逐条对上，全仓已无残留的旧口径，`.github/` 逐字节未变，事件日志字段齐备且可投影、backlog 两节干净、归档点四道门在模拟中全过，benchmark smoke 可复现且其「假阳性」理由可复现，本轮抽查的 8 处引用（含前两轮各抓到一次假出处的那个位置）**全部真实**——R3 的 B-1 类缺陷未再出现。

问题集中在**记录层**，且只剩两处、均为一处编辑可修：`design.md:208-217` 的 R3 处置登记把两条**已处置**的项目写成「接受、不处置」（其中第 1 条断言 `design.md:191`「仍写「6 处」」，而该文本已在同一次提交 `60813b0` 被删），并把 R3 的第 6 条观察漏在 6=2+4 的划分之外（I-1）；以及任务 2.2/2.3 勾着记录的 `exit 0` 在 `60813b0` 起因 `reviews/building-review.md` 触发 manifest 门而不再复现（I-2）。鉴于本 change 的全部价值就是「把阶段 C 记录对账清楚」，而 I-1 让后人按收敛表读到的 R3 结论与产物不符，且它是**修复 R1 的 I-1 时自己引入**的（与 R3 的 B-1 同形），故判 **CHANGES_REQUESTED**，请求按 I-1（主要）与 I-2 修改后重审；两者均不影响归档点门，T5 的 2 项红属计划内、不是本轮判红的理由。
