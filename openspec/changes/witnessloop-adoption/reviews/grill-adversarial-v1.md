# 对抗验证：witnessloop-adoption（v1）

## Reviewer

- **run id**: `grill-adversarial-witnessloop-adoption-v1-2026-10-13`（独立零记忆对抗验证 subagent；默认上游结论有错，逐条证伪；能实测的必须实测）
- **被审 revision**: `3fa927e`（分支 `witnessloop-adoption/2026-10-13`）
- **上游**: `reviews/grill-design.md`（grill 决策记录）+ 作者的整合 commit（`dd421b6..3fa927e`，8 个文件）
- **约束遵守**: 本仓只读；唯一写入 = 本文件。全部实验在 `/tmp/wl-sim`（`git archive` 重建的隔离副本，不碰被审 worktree）与 `/tmp/uvtest-venv*`。
- **方法**: ① 在隔离副本里复现「本 change 自己的 PR」并实跑 `witnessloop check` / `manifest build` / `witnessloop guard` / `scripts/workflow_guard.py`；② 直接调用两侧判定函数（`witnessloop.evidence.grill_evidence_findings`、`scripts.check_openspec_artifacts._untagged_unchecked_tasks` 等）逐份核对；③ 在模拟 runner 的干净环境里实跑 Q4 候选命令；④ 读码核对整合件的每一处 `文件:行号` 引用。

---

## Verdict

**CHANGES_REQUESTED**

阻塞项 7 条（B1–B7）。其中 B1/B2 直接证伪 design 的核心验收安排（「样板 manifest = 阶段 A 验收里第一次出现绿的一侧」），B2 更使得**阶段 B 的 grill stage 按现在的报告写法结构性无法判绿**——而 R11 正是把「跑出绿的一侧」当作阶段 B 成立的前提。B4 使 Q4 的推荐值在 CI 里跑不起来。B5 使本 change 照现有 tasks.md 归档必红。

---

## 一、对抗上游逐条

### 对 grill `## Confirmed Decisions`（7 条）

| # | grill 结论 | 对抗结果 |
|---|---|---|
| 1 | 立项时把 `dev-workflow-gate` 落进 `openspec/specs/` 先例成立 | **成立**（未另测；`platform-gate` 先例与 `_check_current_spec_mapping` 读码一致） |
| 2 | 必须 `init --policy <seed>` 一次写成 | **成立且加强**：实测探针 diff 改 `agent/probe.py` ⇒ 确实**只在与 change 目录同时出现时**才追加 `building` / `grill-adversarial` 两条 stage 判定 |
| 3 | `protected_paths` 不列 `archive/**` | **成立**（读码 `contract.py:38-55` + 实测 12 条假红的机理一致） |
| 4 | 「归档天然安全」+ move 两端都排除 | **成立**，但 missing 的操作约束已在 design Decision 3 补齐 |
| 5 | 本地守卫能力退步（丢 Bash 面） | **成立**：`plugin/hooks/hooks.json` 的 matcher 确为 `Write\|Edit`，`scripts/workflow_guard.py:5` 含 `Bash` |
| 6 | 立项态机械门禁是绿的 | **成立**（本次复核期内 `openspec validate --all --strict` 与 `check_openspec_artifacts.py` 均绿） |
| 7 | 三条 OQ 确为「项目配置」 | **方向成立**，但**不完整**：见 B2/B7——还有一条**不是配置、而是报告格式**的硬不兼容被整轮遗漏 |

### 对 grill `## Code-Resolved Questions`（CQ1–CQ6）

- **CQ1（glob 不是问题、schema 才是）——成立。** 独立复现：隔离副本里放入本仓形态 `reviews/building-review-manifest.json`（`phase` 字段、无 `stage`），`check` **不**对它报「manifest 缺字段」，证明默认 glob 确实不匹配本仓命名。同时复现：只要 `reviews/` 下**任何一份** witnessloop 形态 manifest 存在，`contract.py:127-148` 就会对**逐份**校验并对全部未绑定 `.md` 报孤儿（CQ2 结论成立）。
- **CQ2（放宽 glob 有害）——成立。** `evidence.py:197-210` 的 `matching[0]` + `contract.py:139-148` 的逐份校验，两处读码与实测一致。
- **CQ3（归档 move 必须独立纯改名提交）——成立。** 读码 `contract.py:38-55` 的 `R100` 硬条件。
- **CQ4（`protected_paths` 与事件类型表自相矛盾）——已被整合修正**（design Q6 已补齐三条路径并写成决策面）。
- **CQ5（两处引用行号不准）——已被整合修正。** 复核：`design.md:51` 与 `proposal.md:38/96` 现引 `src/witnessloop/constants.py:43-52`，实测该区间正是 `DEFAULT_REQUIRE_CHANGE_FOR` 的 **8 条 glob 元组**（`constants.py:43-52`）✓；`REVIEW_MANIFEST_REQUIRED_FIELDS` 现引 `constants.py:95-105`，实测 9 个字段与 design Decision 2 表格**逐字对**（`constants.py:95-105`）✓；本仓侧 `agent/workflow/review_manifest.py:95` 确为 `"phase": phase`，路径 `reviews/<phase>-review-manifest.json` 确在 `:62-69` ✓。
- **CQ6（新建当前规格被本 change 自己证伪）——已被整合修正**：delta 有 `## REMOVED Requirements`（`specs/dev-workflow-gate/spec.md:3-9`）、`tasks.md:76` Z.2 改为「覆盖重写」、`openspec/specs/dev-workflow-gate/spec.md:11` 有退休预告 ✓。grill R5 指出的另一处过度断言（「master 的 PR SHALL 不运行该 job」）也已收敛为「既有 in-flight PR 不受影响」+「合入后新 PR 会跑但不拦」（delta `:41-52`）✓。

### 对 grill `## Open Questions`（Q4/Q5/Q6）与 `## 风险`

- **Q4 的推荐值不成立** → 见 **B4**（实测跑不起来）。
- **Q5 的「已定案，不停轮」定性不成立** → 见 **B7**（本仓自己的归档点门就要求 Q5 有确认记录，与 witnessloop 无关）。
- **Q6 成立**（补齐三条路径，与 Q3 同构）✓。
- **R1（阶段 B 结构性跑不绿）——grill 的缓解措施本身不成立** → 见 **B2**：即使按 Decision 2 补三份 witnessloop 形态 manifest，grill stage 仍会因报告正文判据判红。
- **R2（两个守卫并存）——实测位选错且定性有误** → 见 **B6**。
- **R3（归档 move 粒度）——已落进 tasks.md Z.5 ✓。**
- **R4（本 change 自身缺席 known-red）——已落进 Decision 7 K2 ✓**，但 K2 的**红数被低估** → 见 **B1**。
- **R5（无强制窗口 + spec 过度断言）——已修 ✓。**
- **R6（plugin 三处未核实）——其中「命令命名空间」可由文件判定，不必列为未实测** → 见 §二.5。
- **R7（checker 的 Open Questions 抽取只认列表项）——成立**，已登记为 tasks N.5 ✓；且本 change 的 grill-design.md 自己用了列表项写法，抽取正确（实测本仓侧得 `['Q4','Q5','Q6']`）。

---

## 二、新发现（上游完全没有的）

### B1（阻塞）— Decision 7 / A.5.6「样板 manifest = 验收里第一次出现绿的一侧」被实测证伪，实际把红从 2 条变成 14–16 条

**实测**（`/tmp/wl-sim`，Decision 1 基线 policy，复现「本 change 自己的 PR」）：

| 状态 | `witnessloop check` 结果 |
|---|---|
| 现状（`reviews/` 只有本仓形态报告） | **2 项红**：`缺少 review manifest` + `无 stage=grill 的 manifest` —— 与 `design.md:167` 的 K2 描述一致 ✓ |
| 按 A.5.6 跑一次 `manifest build --stage grill --report reviews/grill-design.md` 并提交 | **14 项红** |
| 再放入 `reviews/grill-adversarial.md`（issue #298 要求停轮前必须存在） | **16 项红** |

成因四条，逐条可复现：

1. **孤儿规则被「激活」**：`contract.py:127-148` 在 glob **匹配到 0 份**时于 `:129-135` 早退（所以现状**不**报孤儿——这回答了「本仓 manifest 不匹配 glob 时 `grill-design.md` / `building-review.md` 会不会被判孤儿」：**不会**）；但只要存在任意一份 witnessloop 形态 manifest，`_check_orphan_reports`（`contract.py:185-219`）就会把 `reviews/**/*.md` 里**每一份**未被 `report_path` 绑定的报告判为孤儿。实测：`grill-adversarial.md`、`grill-adversarial-v1.md`、后续 `/review-loop` 的 `building-review.md` 全部成孤儿。
2. **正文判据不匹配** → 见 B2（7 条 `缺 来源:`）。
3. **`## User Confirmation` 此刻必然缺失**（停轮前本来就不该有）⇒ `evidence.py:141-142` 报缺失。
4. **抽出的 Open Question 是 1–6 六条**：`evidence.py:81-82` 的 `_Q_RE = \bQ(\d+)\b` 是**全文扫描**，`grill-design.md` 的 `## Open Questions` 导语里提到了 Q1/Q2/Q3 ⇒ 实测抽出 `[1,2,3,4,5,6]`，比 design 的 5 条停轮项多一条 Q5（见 B7）。

**结论**：A.5.6 这一步若照现文执行，阶段 A 验收里出现的是**更多红**，与 `design.md:173` 的「收益=第一次有绿的一侧」、`tasks.md:21` 判据⑦、`tasks.md:52` 的「目的」陈述**相反**；且 `design.md:167`/`tasks.md:60` 的 K2 红数（隐含 2 条）随之失真。

### B2（阻塞）— Decision 2「witnessloop 对 grill 报告正文的判据与本仓现有形状同构」**错误**：`来源:` 谓词与本仓（尤其是**最近**的）grill 报告写法系统性不兼容

`design.md:105` 断言两侧同构。**证伪**：`evidence.py:33` 的 `_SOURCE_RE = re.compile(r"来源\s*[:：]")` 要求「来源」后**直接**接冒号（可含空白）；而本仓 grill 报告大量使用 `- **来源**: …`（`**` 夹在中间）或近期的 `- **证据**: …`（根本不写「来源」）。

- 实测本 change 的 `reviews/grill-design.md`：**7/7 条 Confirmed Decision 判「缺 `来源:`」**（同一份文件在本仓侧 `_extract_grill_decisions` 得 7 条、判定完全正常）。
- 逐份扫描 62 份归档 `reviews/grill-design.md`：**完全无 finding 仅 39 份**，13 份至少一块缺 `来源:`，其中 **11 份是「全部块都缺」**。
- **趋势是变坏不是变好**：`2026-10-03-harness-style-web-transcript`（12/12 缺）、`2026-10-07-grill-flow-hardening`（5/5）、`2026-10-07-tool-result-spill-module`（6/6）、`2026-10-03-foreach-*`（6/6）——即**当前正在使用的写法基本都判红**。
- 进一步实测：即使把 `## User Confirmation` 补齐、Q1–Q6 全部确认，**witnessloop 仍然报 7 条 `缺 来源:`**。

**结论**：**grill stage 在现有报告格式下结构性不可能判绿**。这同时击穿 R11 的缓解措施（「阶段 B 用 `manifest build` 产绿的一侧作对照」）与 B1 的样板收益。修法必须是二选一（且是新的决策面，上游整轮未提）：① 改本仓 grill 报告格式（把 `来源:` 写成不被 `**` 包裹的形式），这会牵动 `.claude/commands/grill.md`（本地、不进 PR）与文档规范；② 去 witnessloop 立 issue 放宽 `_SOURCE_RE`。**无论选哪条，都必须写进 design 与 tasks**，否则 A.5.6 / B.2 执行时会得到与文档相反的结果。

### B3（阻塞）— 样板 / 阶段 B 的 manifest 有**未写明的顺序硬约束**：内容 commit 之后不能再改任何非证据文件

`contract.py:272-354` 的 `_check_git_span`：`head_sha` 到被检 revision 之间**只允许** `policy.stale_exempt_paths` 命中的路径（`policy.py:76-92` = `.witnessloop/**`、`openspec/changes/*/reviews/**`、`openspec/changes/*/workflow-events.jsonl`、`archive/**`）。

**实测**：建完 `grill.manifest.json` 后再提交一处 `agent/probe.py` ⇒ 报 `审阅的是旧 revision：head_sha=… 之后又改动了非证据文件：agent/probe.py`。

**后果**：本 change 的收尾 Z.1 要改 `docs/development-guide.md`、**Z.2 要覆盖重写 `openspec/specs/dev-workflow-gate/spec.md`（非证据路径）** ⇒ **A.5.6 的样板在 PR 时必然已 stale**。design / tasks 只写了「跑一次 `manifest build`」，**没有写**「必须在最后一个内容 commit 上产出、其后只允许证据 commit」这条（`docs/gate.md §3.1` 有，design 未落进 tasks）。

### B4（阻塞）— Q4 的推荐值 (a) `uv run pytest -q` 在 `gate.yml` 的 job 环境里**跑不起来**

**实测**（模拟 runner：仅 uv 在 PATH、无全局 pytest、`UV_PROJECT_ENVIRONMENT` 指向新环境）：

```
$ uv run --project /tmp/wl-sim pytest -q --collect-only
Installed 77 packages in 1.74s
error: Failed to spawn: `pytest`
  Caused by: No such file or directory (os error 2)
exit=2
```

`pytest` 在 `[project.optional-dependencies].dev`（`pyproject.toml:48-53`），而 `uv run` 只装**默认**依赖（77 包）——`gate.yml:40-45` 的 job 只有 checkout + `setup-uv`，没有 `uv sync --extra dev`。本机之所以「看起来能跑」，是因为 PATH 上有 `/home/happy/.local/bin/pytest`（pytest 9.1.1，实测 `uv run pytest` 回落到它、在项目环境里 `import pytest` 反而 `ModuleNotFoundError`）。

⇒ `design.md:291` / `:293` 与 grill Q4 里「能跑（`uv run` 会自建环境）」的判断**错误**；**(c) 之外的 (a) 与 (b) 都不可执行**。实测可用的写法是 `uv run --extra dev pytest`（116 包，可用）或 `uv sync --extra dev --locked && uv run pytest -q`。注意 `dev` extra 含 `playwright` / `swebench`，装上之后浏览器用例仍因缺 `playwright install chromium` 而 skip——**Q4 需要重新给推荐值**，而不只是「记已知边界」。

### B5（阻塞）— 照现有 `tasks.md` 归档，本仓自己的归档点完成度门必红

**实测**：直接调用 `scripts.check_openspec_artifacts._untagged_unchecked_tasks('openspec/changes/witnessloop-adoption')` ⇒ **45 条未勾未标**（A/0 节尚未做属正常）。其中 **B.1–B.7（7 条）+ C.1–C.2（2 条）+ N.1–N.5（5 条）= 14 条**按 design 自己的定义**永远不可能在本 PR 内完成**：B 的前提是「另一个真实小需求 change」（`tasks.md:58-64`）、C 明写「**不在本 change 内执行**」（`tasks.md:66`）、N 明写「**不属本 change**」（`tasks.md:82`）。

`_check_archived_completion_gate`（`scripts/check_openspec_artifacts.py:1655-1666`）对归档目录逐条报 `归档 change 存在未勾且未标 (post-merge) 的任务`；**旁证**：122 个归档里存在未勾未标任务的只有 35 个，且**最新一个是 `2026-09-20-fix-issue-191`**——即自 #235（2026-09-23）落地以来，**无一例**归档存在未勾未标任务。⇒ 现在的 tasks.md 只把 Z.6 标了 `(post-merge)`，Z.5 归档时必红。

**修法**：把 B/C/N 三节整体标 `(post-merge)`（逐条加标记）或移出 `tasks.md`。

### B6（阻塞）— Decision 8：三项未知面的「可测性」判断有误，且「新增拦截面」的定性被实测证伪

**(i) 「新增拦截面」定性错误。** `design.md:195` 说 witnessloop 的 guard「会在**本仓现有守卫不管的维度**上新增拦截（缺 grill 证据）」。**实测证伪**：本仓守卫**本来就拦**这一维度——`scripts/workflow_guard.py:640-654` + `_grill_evidence_missing`（`:364-404`）：

```
$ echo '{"tool_name":"Write","tool_input":{"file_path":"agent/x.py"},"cwd":"/tmp/wl-sim"}' | python3 scripts/workflow_guard.py
⛔ change 'witnessloop-adoption' 尚未完成独立 subagent design grilling。… exit=2
```

两侧是**同一维度、不同判据**（本仓=文件+正文；witnessloop=manifest+正文），不是「新增的面」。这直接影响 Decision 8 的结论与 spec delta `:152-156`「新增『缺 grill 证据』拦截面（新增能力）」的表述。

**(ii) plugin 的 guard 在本机是静默空转。** `plugin/hooks/guard.sh:32` 调 **PATH 上的裸 `witnessloop`**；本机那份是 **0.1.0 且没有 `guard` 子命令**。**实测（走完整 shim）**：

```
$ echo '{...file_path=agent/x.py...}' | bash plugin/hooks/guard.sh
witnessloop: error: argument <命令>: invalid choice: 'guard' (choose from init, uninit, check, manifest)
shim exit=0        ← 非 1 一律映射成放行 ⇒ 静默空转
$ PATH=/tmp/wlbin:$PATH bash plugin/hooks/guard.sh   # 换成 uv run 版 CLI
guard：拦住 ✗ … ; shim exit=2
```

`design.md:196` 只把它记成「版本耦合 / schema 可能漂移」，**没有识别**这条会让**整个 Decision 8 的实测归零**（A.4.5 / B.5 若不做「PATH 上那份 CLI 是哪一个」的前置核验，会把「放行」误读成「证据完备」）。design 的缓解措施「验证一律用 `uv run witnessloop`」**覆盖不到 `guard.sh`**（它在 plugin 里、硬编码裸命令）。

**(iii) A.4.5 在 building worktree 上观察不到「两个 hook 并存」。** 实测 building worktree `/home/happy/ax-wt/witnessloop-adoption` 下**没有 `.claude/` 目录**（`.gitignore:9` 忽略 + worktree 无副本）；本仓守卫的 hook 只挂在主 checkout `/home/happy/my-agent/.claude/settings.json`（matcher `Write|Edit|Bash`）。⇒ A.4.5「在 building worktree 上触发一次 Write，记录两个 hook 是否都执行」在该树上只能观察到 plugin 那一个。tasks 未写明在**哪棵树**测。

**可机械验证的部分（回应「三项能不能在阶段 A 机械验证」）**：
- **CC 的 hook 合并语义**（串行/并行、任一 exit 2 即拦、报错归属）——**只在真装 plugin 的宿主上可测**，属真正的「未实测」项。判据应写成：记录两个 hook 各自的 stderr 是否都出现 + 进程退出码，且必须在**两个** cwd（主 checkout 与 worktree）各做一次。
- **命令名撞车**——**可静态判定**：`plugin/.claude-plugin/plugin.json` 的 `"name": "witnessloop"` ⇒ 命令命名空间化，与仓内 `.claude/commands/{grill.md,review-loop.md}` 不同名。不必列为「未实测」（CC 的实际命名空间规则可在 A.4.5 顺手确认）。
- **版本耦合**——**可机械判定**：`command -v witnessloop` + `witnessloop --help` 是否含 `guard`。本机结果：**不含**。

### B7（阻塞）— 「Q5 不停轮」与本仓**自己**的归档点门冲突

`design.md:228` 把停轮项定为 5 条（Q1/Q2/Q3 + Q4/Q6），`design.md:295-301` 声明 Q5「已定案，不停轮」。**实测证伪**（不需要 witnessloop）：把确认记录按「只确认 Q1–Q4+Q6」写入 `## User Confirmation` 后，

- 本仓 `_unconfirmed_open_questions` ⇒ `['Q5']`（`_extract_open_question_indexes` 对本文件抽出 `['Q4','Q5','Q6']`，Q5 在 `## Open Questions` 里是列表项）；
- witnessloop `grill_evidence_findings` ⇒ 除 7 条 `缺 来源:` 外，多一条 `Open Question Q5 未经用户确认`。

归档点门以 `assume_implemented=True` 调 `_check_design_review_task`（`check_openspec_artifacts.py:1611-1614` + `:764-771`）⇒ **Q5 若不写确认记录，归档必红**。而 `design.md:228` 的停轮口径是 5 条——收尾时若照此执行，就会漏 Q5。

**修法**：要么把 Q5 从 `reviews/grill-design.md` 的 `## Open Questions` 里**物理移出**（该文件里 Q5 自己就演示了这种做法：`grill-design.md:49` 的 `## Code-Resolved Questions` 不进停轮队列），要么在停轮清单里把 Q5 一并列上。

---

## 三、其余新发现（非阻塞，但会影响 B/C 的判断）

1. **`phase` 与 `stage` 不是一一对应。** 实测本仓 75 份 `*-review-manifest.json` 的 `phase` 取值只有 `building`(74) / `design`(1)——**`grill` / `grill-adversarial` 从来没有 manifest**（只有 `.md` 报告：62 份 `grill-design.md`、7 份 `grill-adversarial.md`）。⇒ 「两套 manifest 并存」在 grill 这条线上不是「并存」而是**纯新增**；`design.md:103` 的代价陈述（「阶段 B 必须显式多跑一步」）方向对，但没写清本仓侧**根本没有**这两个 stage 的产物。
2. **孤儿规则的迁移成本被低估。** 实测 17 个归档 change 的 `reviews/` 里有 3 份规范报告之外的 `.md`：`building-review-r1.md`(4) / `-r2`(4) / `-r3..r6`(各 1) / `acceptance-evidence.md`(5) / `scope-audit.md` / `fact-check.md` / `migration-comparison.md` / `grill-settled.md` / `design-grill.md` / `design-review.md` / `e0-record.md`。真打开后**每一份都要各配一份 manifest**。`tasks.md:59`（B.2）只安排三份——阶段 B 只要触发第 2 轮 review-loop（`building-review-r1/r2.md`）就会出孤儿。
3. **本报告自身就会成孤儿。** 文件名 `grill-adversarial-v1.md` 不在任何 manifest 的 `report_path` 上；一旦 A.5.6 落下第一份 witnessloop 形态 manifest，它就会被判孤儿（实测已复现）。⇒ 收敛后应清理中间轮产物，或把最终版落到规范名 `grill-adversarial.md`。
4. **「谁在什么时候跑 `manifest build`」未写。** `tasks.md:52`（A.5.6）与 `:59`（B.2）给了命令，未给**执行者**（人 / agent / CI），也没有 B3 的顺序约束。若打算让 CI 跑，`gate.yml` **只做 `check`，不产证据**——必须在本地跑，这条应写明。
5. **R6 中的「命名空间冲突」可由文件定**（见 B6 可测性表），不必留作未知面。

---

## 四、Code-Resolved（本轮新增）

- **`_check_orphan_reports` 的触发条件**：`contract.py:127-148` —— glob 匹配 0 份 ⇒ `:129-135` **早退**，孤儿规则**不执行**；匹配 ≥1 份 ⇒ 逐份 `_validate_one` + `_check_orphan_reports`。⇒「本仓 manifest 不匹配默认 glob」本身**不会**让报告变孤儿，但**落了任意一份 witnessloop 形态 manifest 就会**。
- **`report_path` 缺失的连带后果**（grill CQ1 的推理）：读码确认——缺字段时 `contract.py:240-248` 直接 early-return，因此孤儿绑定集为空**只发生在**「manifest 存在但 `report_path` 解析不到」时（`:173-182` 返回 None）。grill 表述的机制成立。
- **`来源:` 谓词**：`evidence.py:33` `_SOURCE_RE = r"来源\s*[:：]"`；判据在 `:134-138` 逐块执行。这是 B2 的唯一根因。
- **Open Question 抽取**：`evidence.py:81-82`（witnessloop，全文 `\bQ(\d+)\b`，本文件得 `[1..6]`）vs `scripts/check_openspec_artifacts.py`（本仓，节内行首，得 `['Q4','Q5','Q6']`）⇒ **两侧在多 Q 编号上的抽取面不一致**，属 B.4「分叉清单」应记录的项。
- **归档点未勾任务门**：`scripts/check_openspec_artifacts.py:1655-1666` + `_untagged_unchecked_tasks:1043-1064`。
- **`guard.sh` 退出码映射**：`plugin/hooks/guard.sh:38-41`（1→2，其余→0）⇒ 与 B6(ii) 的静默空转直接相关。

---

## 五、Code-Resolved（上游已解决，本轮复核确认）

`constants.py:43-52`（8 条 glob）· `constants.py:95-105`（9 个必填字段，与 design 表逐字对）· `checkcmd.py:77/96/169` · `guardcmd.py:16-17` · `review_manifest.py:95`（`"phase": phase`）· `policy.py:76-92`（`stale_exempt_paths`）· `gate.yml:29/47/83/100` · `plugin/.claude-plugin/plugin.json`（`name: witnessloop`）。

---

## 六、结论

上游 grill 的**事实性结论基本可复现**（CQ1/CQ2/CQ3 成立，CQ4/CQ5/CQ6 已被整合修正，R3/R5 已落进 tasks/spec）。但整合稿在三处**核心判断**上仍然错误，且都指向同一个后果——**阶段 A 的「样板」与阶段 B 的「绿的一侧」拿不到**：

1. 「同构」（`design.md:105`）是错的，`来源:` 谓词让 grill stage 结构性判红（B2）；
2. 因此「样板 = 绿的一侧」（`design.md:173` / `tasks.md:21,52`）不成立，实测反而 2 → 14/16 条红（B1），且样板在 Z.2 后必然 stale（B3）；
3. 加上 B4（Q4 推荐值不可执行）、B5（tasks 归档必红）、B6（Decision 8 定性与实测点）、B7（Q5 停轮口径），**建议打回作者修订后再进入停轮**。

修订后需复跑的判据：在隔离副本上重跑 `witnessloop check`（本 change 自身 + 探针 diff）、在干净环境重跑 Q4 候选命令、直接调用 `_untagged_unchecked_tasks` 与 `_unconfirmed_open_questions` 各一次。
