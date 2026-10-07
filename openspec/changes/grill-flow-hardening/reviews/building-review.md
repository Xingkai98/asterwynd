# 实现审阅（building-review）：grill 环节加固（grill-flow-hardening）

- **审阅者**: 独立零记忆实现审阅 subagent（`/review-loop`，不继承开发上下文）
- **时间**: 2026-10-07
- **对象**: `openspec/changes/grill-flow-hardening/` 全量 + `git diff origin/master`（checker / 测试 / 文档 / 3 个 current spec）
- **方法**: 逐个读被改文件 + `git diff origin/master` + `comm` 对比 master/worktree 的 spec 内容 + **真跑**两道门（checker、`openspec validate --all --strict`）+ **变异验证**（改坏 4 处，确认对应测试变红）。凡标「证据」者均为本机真实命令结果。

## Verdict

**CHANGES_REQUESTED**

实现主体**正确且完整**：两处改名、checker 新名匹配 + 兼容旧名（4 条回归）、归档点 `grill-adversarial.md` 存在性门（含 bugfix 豁免）、`## Code-Resolved Questions` 不计确认，均逐项验真；两道机械门全绿；4 处变异全部按预期变红；4 个 file 目标全部核对为真。**不通过的唯一原因是本 change 自己的 spec/design 正文与它刚落地的 checker 判据不一致**（见 Issue 1，severity low，2 行可修）。

### 已复核并确认修好的前轮发现（resolved）

本 change 在 grill 设计闭环后、开发过程中暴露/修好的两个问题，均已由我**独立复现确认修净**（非采信自述）：

- **R1（spec 内容损失）→ resolved**：`openspec/specs/dev-workflow-state-machine/spec.md` 的 `开发流程精简为 OpenSpec 主干 + 强制审阅闭环` Requirement 曾被 delta 重建时**误删 8 个 scenario + 2 段 SHALL**。现已基于 master 全文重建。
  - 证据（我本机 `comm` 复核）：`comm -23 <(master scenarios) <(worktree scenarios)` → **空**（无丢失）；新增恰为 2 个（`归档 change 需设计阶段审阅证据`、`grill 环节含设计阶段审阅闭环`）；scenario 计数 master 51 → worktree 53。
  - 两段 SHALL 已回归：`spec.md:266`（未勾选任务 SHALL 显式分类 / `(post-merge)`）、`spec.md:268`（完成度证据 SHALL 存在且可证明完成）。
  - `batch-grill-me` 于该 spec 计数 **0**；Requirement heading 出现 **1** 次（无 splice 重复）。
  - delta↔current spec 归一化 `diff` → **IDENTICAL**（delta 正文与 current spec 该 Requirement 段逐字一致）。
  - 同法复核另两个同步 spec（`change-documentation` / `subagents`）：**无丢失**；`change-documentation` 唯一「丢失」项为**改名**（`batch-grill-me is unavailable` → `grilling skill is unavailable`，`spec.md:115`），符合本 change 意图。

- **R2（bugfix 过宽）→ resolved**：新 `grill-adversarial.md` 门原对 **bugfix** 也触发，而 bugfix 不走 grill → 会「要求一个输入不存在的产物」。现已在门上加 `DESIGN_TYPES` 前置。
  - 证据：`scripts/check_openspec_artifacts.py:1634`（`and (change_type.all_types & DESIGN_TYPES)`）；`_check_design_review_task`（`:741`）对非 DESIGN_TYPES 本就 `return []`，二者口径一致。
  - 回归测试 `tests/test_openspec_artifact_checker.py:1009`（`test_archived_gate_grill_adversarial_exempt_for_bugfix`）**实跑通过**；我构造一个「primary=bugfix + 有 spec delta + 无 reviews/」的归档目录，`_check_archived_completion_gate` 现只报 `building-review.md missing`、**不再**报 `grill-adversarial.md missing`（变异 4 反向佐证）。

## Issue（按 severity 排列）

### Issue 1 — 新增 spec scenario / design D3 口径与 checker 判据不一致（low，须修）

- **现象**：本 change 自己新增的 scenario 与其 design 正文，把 `grill-adversarial.md` 门的触发口径写成「非 docs + 有 spec delta」，但 R2 修复后实现**多了一道 `DESIGN_TYPES` 前置**——bugfix/research（非 DESIGN_TYPES）即使有 spec delta 也**不**触发该门。三处正文未随 R2 同步。
  - spec scenario：`openspec/specs/dev-workflow-state-machine/spec.md:338`（`- **GIVEN** 一个本 PR 新归档的、非 docs + 有 spec delta 的 change`）
  - 同 delta：`openspec/changes/grill-flow-hardening/specs/dev-workflow-state-machine/spec.md`（同一 scenario）
  - design：`openspec/changes/grill-flow-hardening/design.md:66`（`- **口径**：对**本 PR 新归档**的、非 docs + 有 spec delta 的 change，要求 …存在`）
  - 实现（真值）：`scripts/check_openspec_artifacts.py:1633-1637`（`change_type.primary != "docs" and (change_type.all_types & DESIGN_TYPES) and _changed_capabilities(...) and not (...).exists()`）
- **为何须修**：该 scenario 的 GIVEN 对「bugfix + 有 spec delta」这一类输入**不成立**——checker 对这类输入并不要求该文件，与 scenario 的 THEN 矛盾。本 change 的核心自标就是「把流程判据写精确并机械化」，其自身 spec 陈述与自身实现发生漂移，属 self-consistency 缺口。**方向是安全的**（spec 比代码更严，不产生绕开面），故 severity low、非功能缺陷、CI 全绿——但一行 GIVEN 即可对齐。
- **建议修法**（2 行）：把该 scenario 的 GIVEN 与 `design.md:66` 的口径改为「非 docs + **属 DESIGN_TYPES（feature/refactor/process）** + 有 spec delta」，或补一行说明「bugfix/research 不走 grill，故豁免」。注意 `:260` 的 Requirement 正文那句「非 docs + 有 spec delta」是 building-review 与 grill-adversarial **共用**的概括句，对 building-review 成立（其归档点门确无 DESIGN_TYPES 前置，`:1623`），故**不必**改；只改这个只描述 grill-adversarial 的新 scenario 与 design 口径即可。

> 无其他 blocker / 无 correctness 缺陷 / 无安全或 CI 完整性问题。

## 任务逐项验证

| 任务 | 结论 | 证据（file:line / 命令） |
|---|---|---|
| 1.1 proposal.md | ✅ | `proposal.md`（Change Type/Why/What/Capabilities/RIR `research_tier: light`/Impact Analysis 齐全） |
| 1.2 design.md | ✅ | `design.md`（D1–D5 + Risks + Testing + Pre-Implementation Review + Impact Analysis） |
| 1.3 grilling 设计追问 | ✅ | `reviews/grill-design.md`（5 条 Confirmed Decisions；对象/方法/证据齐全） |
| 1.4 设计阶段审阅闭环 | ✅ | `reviews/grill-adversarial.md`（R1 CHANGES_REQUESTED→R2→R3 **PASS**；含 Decision Challenge + Code-Resolved + Findings） |
| 1.5 停轮确认 | ✅ | `reviews/grill-design.md:63-64`（Q2=A 本轮上机械门 / Q3=B 不加形状校验，均含「用户答复：…确认时间」；Q1 已 code-resolved 移出停轮） |
| 2.1 change-documentation delta | ✅ | delta 增「设计阶段审阅闭环」+「code-resolved vs user-decision」+ `grilling` 名；补 2 个 scenario；已 splice 进 `openspec/specs/change-documentation/spec.md`（`:29-118`），Requirement heading 出现 1 次 |
| 2.2 dev-workflow delta | ✅（修后） | 见 R1：基于 master 全文重建，12 scenario（10 原 + 2 新），delta↔current IDENTICAL |
| 2.3 subagents delta | ✅ | `openspec/specs/subagents/spec.md:278`（`而非执行 \`grilling\``）；scenario 计数 master=worktree=40（无丢失） |
| 3.1 AGENTS.md | ✅ | 4 处旧名→新名（`:18` 两条 + `:72` 路由表 + `:77` fallback 句 + `:96` 阶段表）+ grill 段落补「设计阶段审阅闭环」段 |
| 3.2 requirements-process.md | ✅ | 8 处改名 + 流程步骤补「设计阶段审阅闭环」+「能代码定的用代码定」两条（`:185-186`） |
| 3.3 domain.md | ✅ | 2 处改名（`:11,:25`） |
| 3.4 project.md | ✅ | 2 处改名（`:56,:62`）+ 作答语义 |
| 3.5 templates/tasks.md | ✅ | `:5` 改名（`1.3` 设计审阅 task 与本文 1.3/1.4 对齐） |
| 3.6 在途 change 改名 | ✅ | `add-minimal-tui-runtime-view/design.md:53`、`tasks.md:7` 均已 → `grilling`（本机 `grep` 复核） |
| 4.1 `_has_design_review_task` 加 `grilling` | ✅ | `checker:672-679`（新名 `:675` + 旧名 `grill-with-docs`/`batch-grill` 保留 `:676-677` + `等价设计追问`）；文案 `:793` |
| 4.2 设计审阅证据门 | ✅（修后） | `checker:1633-1641`（归档点、存在性、DESIGN_TYPES 前置）；见 Issue 1（正文口径待对齐） |
| 4.3 `_unconfirmed_open_questions` 只读 Open Questions | ✅ | `checker:872`（`_extract_open_question_indexes` 读 `## Open Questions` `:814-820`）；`## Code-Resolved Questions` 不在其抽取面 |
| 5.1 新名匹配 | ✅ | 测试 `:940`；变异 2 见下 |
| 5.2 旧名兼容 | ✅ | 测试 `:949`（`batch-grill-me`/`grill-with-docs`/`等价设计追问`）；变异 3 见下 |
| 5.3 三者皆无仍报错 | ✅ | 测试 `:957` |
| 5.4 Code-Resolved 不计确认 | ✅ | 测试 `:963`（Open Questions 空 + 有 Code-Resolved 节 → 不报未确认） |
| 5.5 设计审阅门存在性（+ bugfix 豁免） | ✅ | 测试 `:985,:997,:1009,:1022`；变异 1、4 见下 |
| 6.1 grep 验收 | ✅ | 本机 `grep -rn "batch-grill-me" --include=*.md`（排除 `archive/` 与本 change 目录）→ **空** |
| 6.2 openspec strict validate | ✅ | `Totals: 29 passed, 0 failed`（EXIT=0） |
| 6.3 checker | ✅ | `OpenSpec artifact checks passed`（EXIT=0）；另 `--base-ref origin/master` 亦 EXIT=0 |
| 6.4 全量 pytest | ✅（环境数） | 相关面 `test_openspec_artifact_checker.py` **130 passed**（本机实跑）；全量由用户侧跑得 **4091 passed / 2 预存在 `/tmp`-is-git-repo 环境失败**（`test_persistent.py`，与本 change 无关，base 可复现）。**注**：本机全量跑超 2 分钟未等到结果，故 4091 数采信用户侧；已跑的相关子集与全量结论一致 |
| 6.5 benchmark smoke | ✅ | 本 change 零运行时改动（仅 spec/checker/文档）；`benchmark-gate` 无影响面，符合任务口径 |
| 7.1–7.6 收尾 | ⏳ 未做 | 归档 / backlog / manifest / PR / post-merge——属 closeout，非本审阅范围（预期） |

## 变异验证（改坏确认变红）

对每处改动做一次「破坏 → 跑测试 → 复原」，确认保护非假保护：

| # | 变异 | 结果 | 佐证 |
|---|---|---|---|
| 1 | 删掉归档点 `grill-adversarial.md` 存在性门整块 | 🔴 变红 | `test_archived_gate_flags_missing_grill_adversarial` FAIL |
| 2 | 把新名分支 `"grilling" in lowered` 改为 `False` | 🔴 变红 | `test_design_review_task_accepts_new_name_grilling` FAIL |
| 3 | 删掉旧名分支 `or "batch-grill" in lowered` | 🔴 变红 | `test_design_review_task_accepts_legacy_names` FAIL |
| 4 | 删掉门上 `(change_type.all_types & DESIGN_TYPES)` 前置 | 🔴 变红 | `test_archived_gate_grill_adversarial_exempt_for_bugfix` FAIL |

4/4 变异均被对应用例捕获（无假保护）。复原后 `git diff --stat` 确认无残留、无 `mutated` 痕迹。

## 其他维度结论

- **正确性**：`_has_design_review_task` 的 `"grilling" in lowered` 是**子串**匹配——理论上会命中任何含 `grilling` 的串。核查后**无误伤风险**：该分支仅在**缺 `grill-design.md` 结构化证据**时作字面兜底（`checker:775-795`），是兼容路径而非常规路径；且 `grilling` 并非通用英语词，仓内 3 个归档 tasks 命中（`multi-agent-collaboration`/`bypass-mode`/`grill-confirmation-gate`）**全部**是正当的 grill 语义引用，非误匹配。归档点门不会误伤 docs（`primary != "docs"` 前置）——已按 R2 修复补上 DESIGN_TYPES 前置，仅剩 Issue 1 的正文口径待对齐。
- **Spec 对齐**：3 个 current spec 与各自 delta 逐字一致（`diff` IDENTICAL）；无重复 Requirement / 无旧名残留（`grep -c batch-grill-me` = 0）；`grill-adversarial.md` 不以 `-review.md` 结尾，**不**触发 `*-review.md` manifest glob（测试 `:1022` 用 `fnmatch` 双重锁定）。
- **冗余/可维护性**：checker 改动最小（+22/-3），无死代码；`DESIGN_TYPES` 复用既有常量（`checker:32`），无新概念。
- **测试覆盖**：新增 8 条（`:940/:949/:957/:963/:985/:997/:1009/:1022`）+ 改 1 条旧断言文案 + fixture 加 `grill_adversarial` / `change_type` 参数；覆盖「新名 / 旧名兼容 / 皆无报错 / Code-Resolved 不计确认 / 归档门存在性 / bugfix 豁免 / glob 不撞」全部要求面。**无假保护**（变异 1–4 佐证）。
- **文档一致性**：AGENTS.md / requirements-process 的新措辞与 spec 一致、无自相矛盾；「grilling skill」与「/grill 命令」被明确区分为 skill vs harness（`AGENTS.md` grill 段），未见混淆。

## 结论（Round 1）

- 实现**功能面全部正确**、两道门全绿、变异 4/4 生效、两处前轮发现**独立复核确认修净**。
- **唯一须修**：Issue 1——把本 change 新增的 scenario（`spec.md:338` 及 delta）与 `design.md:66` 的触发口径补上 `DESIGN_TYPES` 限定（bugfix/research 豁免），使之与 `checker:1633-1637` 一致。修毕即可 PASS。

## Round 2

- **审阅者**: 独立零记忆实现审阅 subagent（R2；不继承 R1 与开发上下文）
- **时间**: 2026-10-07
- **对象**: R1 唯一 issue（Issue 1）的修复复核——`归档 change 需设计阶段审阅证据` scenario（current spec + delta）与 `design.md:66` 的触发口径是否与实现 `DESIGN_TYPES` 前置一致；并复核是否引入新问题
- **方法**: 只读复核——逐字读三处修订 + 实现 guard（`scripts/check_openspec_artifacts.py`）；`DESIGN_TYPES` 常量核对；delta↔current spec 归一化 `diff`；`comm` 复核 scenario 增删；真跑 `openspec validate --all --strict` 与 `test_openspec_artifact_checker.py`。凡标「证据」者均为本机真实命令结果。

### R2 Verdict

**PASS**

Issue 1 已修净：三处正文的触发口径现与实现 guard 逐条对齐，delta↔current spec 仍逐字一致，无新问题。R1 的其余结论（功能面正确、两道门全绿、变异 4/4、前轮两处发现已修）保持不变。

### Issue 1 复核（口径 ↔ 实现）→ **已修净**

- **实现真值**（`scripts/check_openspec_artifacts.py:1633-1637`）：触发 `grill-adversarial.md` 存在性门的条件为
  `change_type.primary != "docs"` **∧** `(change_type.all_types & DESIGN_TYPES)` **∧** `_changed_capabilities(change_dir)`（= 有 spec delta）**∧** `not (...).exists()`。
- **三处修订后正文逐条对齐**：
  - current spec scenario（`openspec/specs/dev-workflow-state-machine/spec.md:338`）GIVEN = 「非 docs + 属 DESIGN_TYPES（feature/refactor/process）+ 有 spec delta」（+ 括注「bugfix/research 不走 grill，故豁免本门」）。
  - delta scenario（`openspec/changes/grill-flow-hardening/specs/dev-workflow-state-machine/spec.md`，同 scenario）GIVEN 逐字同 current spec。
  - `design.md:66` 口径 = 「非 docs + **属 DESIGN_TYPES（feature/refactor/process）** + 有 spec delta」，并补明「比 building-review 多一道 `DESIGN_TYPES` 前置」及理由（grill 只对 DESIGN_TYPES challenge；bugfix/research 不走 grill → 要求其产此文件是「要求一个输入不存在的产物」）。
- **常量核对**：`DESIGN_TYPES = {"feature", "refactor", "process"}`（`checker:32`），与正文括注的三类**完全一致**；`research` 确不在集合内 → 「bugfix/research 豁免」成立。
- **`_changed_capabilities` ↔ 「有 spec delta」**：该函数 glob `specs/*/spec.md`（`checker:700-712`），即「有 spec delta」，正文表述准确。
- **R1 的 Issue 1 精确消解**：R1 指出的矛盾是「scenario 的 GIVEN 对『bugfix + 有 spec delta』不成立，而实现不要求该文件」；现 GIVEN 已把该类输入排除在触发面外，与其 THEN 不再冲突。**判已修净。**

### 一致性/回归复核（无新问题）

- **delta↔current spec 逐字一致**：归一化 `diff`（剥空行，取该 Requirement 段）→ **IDENTICAL**（证据：`norm` 两文件后 `diff` 无输出）。
- **scenario 无丢失、仅 +2**：`comm` master↔worktree → 丢失面**空**；新增恰为 `归档 change 需设计阶段审阅证据` 与 `grill 环节含设计阶段审阅闭环`（evidence：`comm -23`/`comm -13`）。
- **两道门仍绿**：`npx @fission-ai/openspec validate --all --strict` → `Totals: 29 passed, 0 failed`；`test_openspec_artifact_checker.py` → **130 passed**（均本机实跑）。
- **无新问题**：本次修订仅改两处 spec 正文 + 一处 design 正文（措辞对齐），**不触** checker 代码与测试，不引入新的门禁面或假保护；R1 的变异验证（4/4 生效）结论不受影响。

### R2 结论

**PASS** — Issue 1 修复与实现一致、delta↔current spec 逐字一致、无新 issue。实现面可归档；后续按 `/review-loop` 常规生成 `building-review-manifest.json` 即可。
