# 对抗验证：witnessloop-adoption（R3 · 最终版）

## Reviewer

- **run id**: `grill-adversarial-witnessloop-adoption-r3-2026-10-13`（独立零记忆对抗验证 subagent；默认上游结论有错，逐条证伪；能实测的必须实测，不许以推理代替）
- **被审 revision**: `85bd816`（分支 `witnessloop-adoption/2026-10-13`，`origin/master` = `da3fd4f`）
- **上游**: R1/R2 记录 `reviews/grill-adversarial-v1.md`（R1 判 CHANGES_REQUESTED，7 条阻塞 B1–B7；R2 判 CHANGES_REQUESTED（窄口径），5 条陈述性残留 N1–N5 + 记录注记 N6）+ 作者的收口 commit `85bd816`
- **约束遵守**: 被审 worktree 只读（本轮 `git status --porcelain` 全程为空）；唯一写入 = 本文件（+ 仓外 `/tmp`）。实验全部在 **`git archive HEAD | tar -x` 重建的隔离副本**里做（无 `.git` 文件共享）；**不在被审 worktree 上跑任何会改状态的命令**。
- **方法**: ① `git show 85bd816` 逐文件读 diff，对照提交信息里 N1–N6 每条声明在文件里找**实质改动**（不是「提到了」）；② 反向找茬（逐字比定案值 / U7 口径 / 状态行）；③ 独立重跑三处机械自查（不引用作者数字），并**直接调用** `_unconfirmed_open_questions` / `_untagged_unchecked_tasks`；④ 在隔离副本里用 witnessloop 本尊实跑 `check`（A 现状 / B +测试执行点 / C +grill manifest 三态），证伪 N5 的事实口径。

---

## Verdict

**PASS**

- R1 的 7 条阻塞（B1–B7）**功能性关闭**，R2 的 5 条残留（N1–N5）**全部实质收口**——逐条独立复核见下表，证据均为本轮实读的 `文件:行号`。
- 三处反向找茬（四项定案值字面 / spec delta 对 U7 / README + backlog 状态行）**全部通过**。
- 三处机械自查**独立复跑全绿**（原始输出见 §四）。
- N5 的事实口径（U7 对、Q7 原文错）**由本轮隔离副本实测独立复现**（§三）。
- 收口 commit **未引入新矛盾**。
- 残留 3 条**不阻塞**的观察（R3-O1/O2/O3，§五）：均为「指向已改名小节 / 时态陈旧」的引用问题或良性死配置，**不改变任何生效裁定、不影响阶段 A 的任何产物与判据**，可在后续任意一次触及这些文件时顺手清掉。

⇒ **具备开工阶段 A 的条件**（tasks 0.4 可勾，`tasks.md:12` 所述「最后一道前置门」已过）。

---

## 一、R1 七条（B1–B7）逐条复核

| R1 条目 | R3 判定 | 本轮核对证据（实读） |
|---|---|---|
| **B1** 样板 ≠ 绿（落 manifest 反而 2→14/16） | **已关闭** | `design.md:183-188`（Decision 7 第 3/4 条：原「样板=绿的一侧」被实测证伪并撤销，默认改「一份 manifest 都不落」，K2 保持 2 条红；若落须同时满足三条件）；`design.md:325`（R4 Mitigation 同口径）；`design.md:356`（Impact Analysis）；`design.md:231`（Pre-Implementation Review「已定」清单）；`tasks.md:56-59`（A.5.6 / A.5.6.1–3，含执行者＝人在本地跑）；spec delta `:143-148`（含「只落一部分的中间态 SHALL 被拒绝」）。本轮隔离副本复现了机理（§三 Run C：孤儿 + 正文判据一起被激活） |
| **B2** `来源:` 谓词不兼容 | **已关闭** | `design.md:25`（Context 第六条，已按 U7 加「阶段 A 不会遇到这条」限定）；`design.md:113`（含 `evidence.py:33` 逐字引用 + 7/7 实测）；`design.md:302-318`（U7）；`design.md:333-334`（R11 改写：补了 manifest 也拿不到绿 + 替代进步指标）；`proposal.md:80`（见 O1 观察）；spec delta `:157-176`（新增 Requirement + 3 个 Scenario）；witnessloop #20 已立。本轮 Run C 实测复现 7/7 条 `缺 来源:` |
| **B3** 证据 stale 顺序约束 | **已关闭** | `tasks.md:90`（Z.7 顺序写死：内容提交（含 Z.1/Z.2）→ 证据 → 归档 move 单独提交）；`design.md:336`（R13，含 `_check_git_span` 豁免集与「manifest 后再提交 `agent/probe.py` 即报旧 revision」实测）；`tasks.md:57`（A.5.6.1 ②）、`:68`（B.2）、`:83`（收尾三条硬约束 ③）同口径 |
| **B4** Q4 推荐值不可执行 | **已关闭（本轮独立复跑）** | `design.md:280-286`（U4 = `uv run --extra dev pytest -q`，含 `pyproject.toml:48-55` 依据）；`tasks.md:32`（A.3.1）；`proposal.md:15`；spec delta `:31`；backlog `:124`。本轮在干净 runner 模拟下**独立复现**：裸 `uv run pytest` ⇒ `Failed to spawn: pytest` exit=2；`uv run --extra dev pytest` ⇒ 4342 tests collected exit=0（原始输出见 §四.4） |
| **B5** B/C/N 未勾未标会红归档点门 | **已关闭（本轮实测）** | 直接调用 `_untagged_unchecked_tasks` ⇒ **34 条**，全部落在 `0.4` / `A.1.1–A.5.6.3` / `Z.1,Z.2,Z.3,Z.4,Z.5,Z.7`（**都是本 PR 内要做的**）；`B.1–B.8` / `C.1–C.2` / `N.1–N.7` / `Z.6` **一条都不在返回集里**（即全部被 `POST_MERGE_TAG_RE` 认出）；`_tasks_missing_evidence` = `None` |
| **B6** Decision 8 定性 + 实测点 | **已关闭** | `design.md:205`（「同一维度、不同判据…不是新增的面」+ 本仓守卫实测 `exit 2` 原文）；`design.md:330-331`（R9 收窄为两项 + 新增 R9b：`guard.sh` 调 PATH 裸命令、退出码映射 ⇒ 旧版 CLI **静默空转**）；`tasks.md:43-47`（A.4.5.1 前置核验 / A.4.5.2 两项未实测 / A.4.5.3 两棵树各一次 / A.4.5.4 命名空间静态判定）；spec delta `:178-194`（含「不夸大不缩小行为变化」Scenario）。本轮旁证 A.4.5.1 的必要性：`command -v witnessloop` ⇒ `/home/happy/.local/bin/witnessloop`、`--version` ⇒ `0.1.0`、`--help` 命中 `guard` 的行数 = **0**（§四.5） |
| **B7** Q5 未停轮会红归档点门 | **已关闭（本轮实测）** | `tasks.md:10`（0.2 七条清单含 Q5）、`:11`（0.3 明写「Q5 不能漏」）；直接调用实测：`reviews/grill-design.md` 的 `_extract_open_question_indexes` = `['Q4','Q5','Q6']`、`_extract_user_confirmation_indexes` = `['Q1'…'Q7']`、`_unconfirmed_open_questions` = `[]`；`design.md:288-292`（U5） |

**另有 R1 §三「其余新发现」5 条**（`phase`/`stage` 非一一对应、孤儿迁移成本、本报告自身成孤儿、谁在何时跑 `manifest build`、命名空间可静态判定）：均已落进 `design.md:102`（本仓 75 份 manifest 的 `phase` 只有 `building`(74)/`design`(1)）、`tasks.md:59`（A.5.6.3 收敛后清理中间轮产物）、`tasks.md:58`（A.5.6.2 执行者写死）、`design.md:216`（命名空间静态判定）、`tasks.md:100`（N.6 归档非规范 `.md` 的孤儿化）。

---

## 二、R2 五条（N1–N5）+ 注记（N6）逐条复核

| R2 条目 | 声称的收口 | R3 判定 | 本轮核对证据（实读） |
|---|---|---|---|
| **N1** 三处仍把「`reviews/` 下 witnessloop 形态 manifest」列为阶段 A 新增产物 | 三处统一改「阶段 A 默认一份都不落」 | **已关闭** | ① `design.md:356`（Impact Analysis）：现为「…**注意：阶段 A 默认 `reviews/` 下一份 witnessloop 形态 manifest 都不落**（Decision 7 / tasks A.5.6）——落它会让孤儿规则被激活、红数从 2 条涨到 14/16 条。仅在满足 Decision 7 第 4 条的三条件…时才落，见 tasks **Z.7**」；② `design.md:325`（R4 Mitigation）：「…**默认一份 witnessloop 形态 manifest 都不落**（Decision 7；样板方案已撤销，若确要落见 Z.7 的条件式）」；③ `design.md:231`（Pre-Implementation Review 已定清单）：「…阶段 A 默认一份 witnessloop 形态 manifest 都不落（Decision 7；**原「补一份 grill manifest 当样板」的处置已被对抗轮实测证伪并撤销**…）」。**反向全量计数**：`grep -n manifest design.md` = 51 行，逐行读完，**无任何一处**再把 witnessloop 形态 manifest 写成阶段 A 的默认产物（其余命中均为：描述 K2 的**缺失**、Decision 2/7 的机制说明、阶段 B 的动作、或 policy 字段） |
| **N2** `proposal.md` 未随裁定更新 | 改为七条已裁定 + 写入四项定案值 + 失引改 `## User Rulings` | **已关闭（一处时态残留见 O1）** | `proposal.md:15`（需求第 4 条）现为「**七条 Open Question 已于 2026-10-13 由用户停轮拍板、全部按推荐值裁定**（生效口径见 `design.md` 的 `## User Rulings`（U1–U7），逐条答复见 `reviews/grill-design.md` 的 `## User Confirmation`）。**四项 policy 定案值**：…」；`proposal.md:108`（RIR design impact）现为「policy 的可配字段**已全部裁定**（U1/U2/U3/U6，见「需求」第 4 条的四项定案值）」。**逐字比对**：`require_change_for = ["agent/**", "scripts/**", "web/**"]` ≡ `design.md:264`（U2）≡ `design.md:68`（Decision 1 JSON）✓；`protected_paths` 五项字面 ≡ `design.md:296`（U6）≡ JSON `:65-67` ✓；测试执行点 `uv run --extra dev pytest -q` ≡ `design.md:282`（U4）✓；事件类型名见 O1′ |
| **N3** backlog 同条目自相矛盾 | 删旧尾段 + 订正 Q4/Q7 描述与已知红口径 | **已关闭** | `docs/openspec-change-backlog.md:124` 读全文：「七条 Open Question 已全部拍板…可开工」+「（配置决策已全部裁定，要点见本条目开头；生效口径见 `design.md` 的 `## User Rulings`。）」——**旧「三条待拍板决策（都写进 `## Open Questions`…）①…②…③」尾段已不存在**；R2 点名 Q4 处现为「当时的推荐已被 U4 取代为 `uv run --extra dev pytest -q`」、Q7 处现为「处置已由用户拍板为 **U7：等 witnessloop issue #20 修谓词、本仓零改动**」；已知红口径现为「属「**缺 manifest**」这一类（隔离副本实测本 change 自身：`缺少 review manifest` + `无 stage=grill 的 manifest`，另加阶段 A 落地前的「测试执行点缺失」）；**不是**「`来源:` 谓词判红」」——**与本轮 Run A/B 实测逐字一致**（§三）。计数口径：`grep -rn "三条待拍板\|三条项目配置决策\|待拍板" <change dir> docs/openspec-change-backlog.md` 的活跃文档命中 = **0**（仅剩两处**追加型历史记录**：`workflow-events.jsonl` 的 seq 1/3 与 `grill-adversarial-v1.md` 的 R1/R2 原文——前者是 append-only 事件日志、后者是必须保持原样的原始记录，均不构成活跃口径矛盾） |
| **N4** `README.md` 状态行陈旧 | 与 N2/N3 统一 | **已关闭** | `README.md:8` 现为「状态：立项文档，未开始实现；**七条 Open Question 已于 2026-10-13 由用户停轮拍板、全部按推荐值裁定**（见 `design.md` 的 `## User Rulings`），待 tasks 0.4「设计阶段审阅闭环复跑确认」后开工」 |
| **N5** Q7 答复与 U7 矛盾 | 改准口径（阶段 A 的已知红 = 「缺 manifest」类） | **已关闭，且本轮实测独立复现 U7 对** | `reviews/grill-design.md:141-142`（Q7 行 + 「事实描述订正（R2 / N5，裁定不变）」注记）、`design.md:308-318`（U7 块）、`design.md:248`（Remaining risks）、`design.md:25`、`proposal.md:79-80`、spec delta `:172-176`、`tasks.md:74`（B.8）**六处同口径**。事实判定见 §三：**无 witnessloop 形态 manifest 时正文判据根本不会被触发**，`来源:` 那组红只在其**之后**才出现——**design 的 U7 口径与实测相符**（不构成阻塞） |
| **N6**（记录注记）Q4 正文推荐已被 B4 推翻 | 加注指向生效口径 | **已关闭** | `reviews/grill-design.md:139` 新增一行注（R2 / N6）：「本节 Q4 正文里的原推荐是 `uv run pytest -q`…该推荐已被对抗轮 B4 实测推翻…**生效口径是上面 `## User Confirmation` 的 (a′)**（见 `design.md` U4）。正文保留原样以存真」 |

---

## 三、N5 事实口径的独立实测（隔离副本，witnessloop 本尊）

**装置**：`git archive origin/master | tar -x -C /tmp/wl-r3git` → `git init` → base commit（`07e815b…`）→ `git apply` 本分支 `origin/master..85bd816` 的全量 diff → head commit（`148eefd…`，10 个变更文件、1 个 change 目录）；`.witnessloop/policy.json` 逐字用 `design.md:61-77` 的 Decision 1 定稿 JSON。CLI 一律 `uv run witnessloop`（witnessloop 仓工作树版本，非 PATH 上的 0.1.0）。

三态实测（原始输出见 §四.6）：

| 状态 | `witnessloop check` 结果 | 与文档口径比对 |
|---|---|---|
| **A** 只有 policy（无 `reviews/` manifest、无测试执行点） | **3 项**：`缺少 review manifest` + `无 stage=grill 的 manifest（现有 stage：（无））` + `测试执行点缺失` | 与 `design.md:308`「实测本 change 自身…两条；**阶段 A 落地前还会多一条「测试执行点缺失」**」**逐字一致** ✓ |
| **B** A + `.github/witnessloop-tests.txt`（`uv run --extra dev pytest -q`） | **2 项**：`缺少 review manifest` + `无 stage=grill 的 manifest` | 与 `design.md:308`、backlog `:124`「K2 保持 2 条红」一致 ✓ |
| **C** B + `manifest build --stage grill --report reviews/grill-design.md` | **9 项**：1 条 stale + 1 条孤儿（`grill-adversarial-v1.md`）+ **7 条 `缺 来源:`**（7/7 条 Confirmed Decision） | **证伪 N5 的旧口径、证实 U7**：`来源:` 那组判据在无 manifest 时**一条都不出现**，落了 witnessloop 形态 manifest 才被触发；`stage_manifest_findings_in_change` 在无匹配 stage 时**先返回「无 stage=… 的 manifest」并 early-return**（`evidence.py:203-208`，读码确认） |

**两个附带确认**：① 三态下**都没有** `无 stage=building` / `无 stage=grill-adversarial` —— 因为本 change 的 diff 不触达 `agent/**` / `scripts/**` / `web/**` ⇒ `code_hits` 为空 ⇒ 这两条 stage 判定不触发，正是 `design.md:177`（K2 行）的断言 ✓；② 红数**不是常量**（C 态相对 B 态涨了 4.5 倍），印证 `design.md:100` 的「要么每份都建、要么一份别落」操作约束与 Decision 7 的默认处置方向正确 ✓。（本轮 A/B/C 的绝对条数 3/2/9 与文档记的 2/14/16 不完全同值，是因为文件集不同——文档那组是在 `reviews/` 还含 `building-review.md` / `grill-adversarial.md` 的 PR 末态测的；**机理与单调性一致**，且被审口径（A/B 两态）逐字复现。）

---

## 四、三处机械自查（本轮原始输出，不引用作者数字）

### 1. 项目 artifact checker（带 base）

```
$ export PATH=/home/happy/.local/bin:$PATH; cd /home/happy/ax-wt/witnessloop-adoption
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base
OpenSpec artifact checks passed
exit=0
```

### 2. OpenSpec strict validate

```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
…
✓ change/witnessloop-adoption
✓ spec/dev-workflow-gate
…
Totals: 30 passed, 0 failed (30 items)
exit=0
```

### 3. 两个判定函数直接调用

```
$ PYTHONPATH=. python3 - <<'PY'   # 对 change 目录下每一份 .md 读文本后调用
openspec/changes/witnessloop-adoption/reviews/grill-design.md:
    open=['Q4', 'Q5', 'Q6'] confirmed=['Q1','Q2','Q3','Q4','Q5','Q6','Q7'] unconfirmed=[]
TOTAL unconfirmed across change dir: 0
_untagged_unchecked_tasks count: 34
    （全部命中 0.4 / A.1.1–A.5.6.3 / Z.1,Z.2,Z.3,Z.4,Z.5,Z.7；B/C/N/Z.6 一条不在集内）
_tasks_missing_evidence: None
```

### 4. Q4 执行点命令（干净 runner 模拟，B4 的独立复跑）

```
$ env -u VIRTUAL_ENV PATH=/usr/bin:/bin UV_PROJECT_ENVIRONMENT=/tmp/wl-r3-venv2 uv run pytest -q --collect-only
Installed 77 packages in 111ms
error: Failed to spawn: `pytest`   Caused by: No such file or directory (os error 2)
exit=2
$ env -u VIRTUAL_ENV PATH=/usr/bin:/bin UV_PROJECT_ENVIRONMENT=/tmp/wl-r3-venv3 uv run --extra dev pytest --collect-only -q
4342 tests collected in 12.87s
exit=0
```
（⇒ 文档现写的 `uv run --extra dev pytest -q` **是干净环境里唯一能跑的形式**，U4 的取值与其理由成立。）

### 5. 阶段 A 前置核验的旁证（A.4.5.1）

```
$ command -v witnessloop ; witnessloop --version ; witnessloop --help | grep -c guard
/home/happy/.local/bin/witnessloop
witnessloop 0.1.0
0          ← PATH 上这份 CLI 没有 guard 子命令 ⇒ guard.sh 会静默空转，A.4.5.1 的前置核验不可省
```

### 6. witnessloop check 三态原始输出（隔离副本）

```
--- Run A: policy only ---
check：基线 07e815b4...HEAD，10 个变更文件，1 个 change 目录
  change：witnessloop-adoption
check：未通过 ✗（3 项）
  1. …：缺少 review manifest（审阅证据必须「报告 + manifest」成对，glob=reviews/*.manifest.json）
  2. …：无 stage=grill 的 manifest（现有 stage：（无））——grill 决策记录必须有对应的审阅证据
  3. .github/witnessloop-tests.txt：策略声明了测试执行点，但该文件不存在（执行点缺失）。…
exit=1
--- Run B: + tests execution point ---
check：未通过 ✗（2 项）
  1. …：缺少 review manifest（…glob=reviews/*.manifest.json）
  2. …：无 stage=grill 的 manifest（现有 stage：（无））——…
exit=1
--- Run C: + manifest build --stage grill --report reviews/grill-design.md ---
check：未通过 ✗（9 项）
  1. …/reviews/grill.manifest.json：审阅的是旧 revision：head_sha=148eefd… 之后又改动了非证据文件：.github/witnessloop-tests.txt
  2. …/reviews/grill-adversarial-v1.md：孤儿报告：reviews/grill-adversarial-v1.md 未被任何 manifest 绑定
  3-9. …/reviews/grill-design.md：第 1..7 条 Confirmed Decision 缺 `来源:`
exit=1
```

---

## 五、R3 新发现（全部**非阻塞**；无阻塞项）

**R3-O1（时态陈旧，1 处）— `proposal.md:80`**：Impact Analysis 的「已知阻塞」条目仍写「处置作为 **Open Question Q7** 交用户拍板，并已去 witnessloop 立 issue #20」——而同一文件 `:15` 已写「七条…已全部裁定」，`design.md:302-318` 的 U7 也已裁定。**为何不阻塞**：该句没有陈述**另一个**处置（未与 U7 冲突），只是时态停在裁定前；它不进入任何产物清单、不被任何 checker 读取、也不改变阶段 A 的任何动作（阶段 A 两侧都不产 grill 证据）。**建议**：后续任意一次触及 `proposal.md` 时把该半句改为「处置已拍板为 **U7**（等上游修谓词、本仓零改动）」，与 `:15` 同口径。

**R3-O2（引用已改名小节，4 处）— `design.md:113` / `:226` / `:233` / `:334`**：分别写「见 **Open Question Q7**」「其推荐值保留在 **Open Question Q5**」「B2（`来源:` 谓词不兼容）→ **Open Question Q7**」「阻塞在 **Open Question Q7**」。`## Open Questions` 已改名为 `## User Rulings`（`design.md:250` 标题已标注「原 Open Questions…无遗留」），故这些是历史 id 交叉引用。**为何不阻塞**：R2 已对同类（`design.md:243`/`:252`）明确判定「可接受且更利于溯源」；四处所指的生效口径都在同文档的 U5/U7 里可查，且 `design.md:334` 的「或本仓改写法」与 U7 的「后续」段、`tasks.md:101`（N.7 两选项）**一致**，不是被否决分支的复活。**建议**：清 O1 时顺手把这四处的「Open Question Qn」改为「U5 / U7」。

**R3-O3（良性死配置，1 项）— `change_archived` 在 witnessloop policy 里没有消费方**：`design.md:73-74` / U1 的事件类型表含 `change_archived`，而本仓 `scripts/flow-policy.json` 把该类型绑在 `openspec/changes/archive/` 上——而 Decision 3 明确**不把归档目录列进 `protected_paths`** ⇒ 该类型名在 witnessloop 侧是死配置。**为何不阻塞**：`protected_write_event_types` 是**白名单**语义，多余项不会产生假红/漏报，也不影响本仓 checker（该文件本 change 一行不改）；U6 的否决理由只点名 `backlog_updated` / `protected_artifact_explained` 两条，而这两条现均有消费方（`docs/openspec-change-backlog.md` / `docs/known-debt.md` / `docs/known-issues.md`），**U6 的论证本身成立**。**建议**：留作阶段 B 报告的一行注记即可，不必改。

**另一处「提交信息 vs 文件内容」的偏差（不是文档缺陷，仅记录以求存真）**：`85bd816` 的提交信息称「写入**四项定案值字面**（require_change_for / protected_paths / **事件类型名** / 执行点命令）」，但 `proposal.md:15` 对事件类型名写的是**指称**（「`evidence.protected_write_event_types` 沿用本仓现有类型名（U1）」）而非四项类型名列表；该列表在 `design.md:256`（U1）、`design.md:73-74`（Decision 1 JSON）、spec delta `:27` 三处均为字面且互相逐字一致 ✓。⇒ **实质不受影响**，仅是收口范围的自我描述略宽。

---

## 六、结论

1. **R1 的 7 条阻塞全部功能性关闭**（逐条带 `文件:行号` 证据，见 §一）；**R2 的 5 条陈述性残留全部实质收口**（见 §二），N6 注记亦已补。
2. **反向找茬通过**：四项定案值字面与 `## User Rulings`（U1/U2/U3+U6/U4）**逐字一致**；spec delta 与 U7 **同口径**；`README.md:8` / backlog `:113` + `:124` 状态行与二者一致，且 backlog 条目内的旧口径矛盾已消除（活跃文档中「待拍板」类命中 = **0**）。
3. **三处机械自查独立全绿**：artifact checker `passed`/exit=0；openspec strict validate `30 passed, 0 failed`/exit=0；`_unconfirmed_open_questions` 全目录 = `[]`、`_untagged_unchecked_tasks` = 34（全为本 PR 内任务）、`_tasks_missing_evidence` = `None`。
4. **N5 的事实口径由实测独立复现**：阶段 A 的已知红是「缺 manifest」类（Run A/B），`来源:` 那组红只在落了 witnessloop 形态 manifest 之后才出现（Run C）⇒ **U7 对**，`design.md:308-318` 的订正准确。
5. 新发现 3 条**非阻塞**观察（O1 时态陈旧 1 处、O2 历史 id 交叉引用 4 处、O3 良性死配置 1 项）+ 1 条提交信息自述偏差；**均不改变任何生效裁定、不影响阶段 A 的产物与判据**。
6. **Verdict = PASS；具备开工阶段 A 的条件。** 0.4 可勾；建议在阶段 A 的文档提交里顺手清掉 O1/O2（成本一行）。

---

## 附：本轮复跑判据（供下一轮/归档引用）

- 被审 revision `85bd816`；隔离副本由 `git archive origin/master` + `git apply origin/master..85bd816` 重建（`/tmp/wl-r3git`，base `07e815b4…`，head `148eefd…`）。
- 复跑命令：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`；`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`；`scripts.check_openspec_artifacts._unconfirmed_open_questions` / `_untagged_unchecked_tasks` / `_tasks_missing_evidence` 直接调用；`uv run witnessloop check --root /tmp/wl-r3git --base <base_sha>`（A/B/C 三态）。
- 被审 worktree 在本轮全程 `git status --porcelain` 为空（唯一写入 = 本文件）。
