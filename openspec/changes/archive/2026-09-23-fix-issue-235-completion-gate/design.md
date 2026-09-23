# Design — fix-issue-235-completion-gate

## Context

见 `proposal.md`。本设计经**五轮独立方案审阅**（`PLAN-issue-235.md` v1–v6，R1–R5）收敛，R5 判 PASS。核心事实：

- `_tasks_all_complete`（`:982`）是「全勾才开门」的触发器，用于 `:585` / `:733` / `:750` / `:1031` 四处。
- `f4a4272` 是有意收窄（修未实现 change 误报），且**已规格化**：`dev-workflow-state-machine/spec.md:256` 正文写「非 docs + 有 spec delta + **tasks 全部勾选**的 change SHALL 有 building-review.md + manifest」，`:258-266` 有两条 Scenario 对（实现完成提交 PR / 部分实现不受拦截）。**本 change 要改的正是这个触发条件。**
- `iter_change_dirs:1277` 排除 archive（`:1283`）→ 归档 change 不被 `check_change` 覆盖。
- four 门读的路径随目录一起移动（实测 `specs/*/spec.md` 91/93、`proposal.md` 93/93、`reviews/` 45/93）⇒ 归档后可评估。

## Goals / Non-Goals

**Goals**

- 堵住「留一条 `[ ]` 绕开全部四道门」。
- 补上「归档路径完全不查完成度」（问题二）。
- **不反转 `f4a4272`**（不重新引入未实现 change 的误报）。
- 复杂度最小（相对方案审阅中出现的 v4 形态）。

**Non-Goals**

- 不改 active 阶段四道门的现有触发（仍是 `_tasks_all_complete`）。
- 不做 `has_impl` 判定 / `delivery_candidates` / 双调用点（审阅已排除）。
- 不修「实现 PR 完全不归档」（记 known-debt）。

## Decisions

### D1: 触发点取归档点

```
new_archived_ids := { id | p ∈ git diff --name-only --diff-filter=AR <base>
                       ∧ p 匹配 ^openspec/changes/archive/\d{4}-\d{2}-\d{2}-([^/]+)/
                       ∧ 该 archive 子目录 <date>-<id> 在 base 树**不存在** }
```

**依据**：门要阻止坏 change **合入**，而 AGENTS.md:25 强制「实现 PR 必含归档」⇒ **归档 commit 是 PR 最后一个 commit** ⇒ 归档点是唯一必要且充分的评估点。

**为什么 `AR` 而非 `A`**（实测）：源目录在 base 树 → git 报 `R`（rename），源目录不在（同一 PR 内先建后 mv）→ 报 `A`。两种都产出 archive 路径，故须 `AR`。实测 PR 级计数 #236 = 10、#238 = 5（**注**：早前引用的「#236 A=2/AR=9」是**内层归档 commit** `e095bdd` 的数据，非 PR 级——已纠正）。

**为什么必须再叠「base 树不存在」条件**（grill 风险②，用户已确认采纳）：正则只判「路径长什么样」，判不出「这个归档目录是不是本 PR 新建的」。**往一个已存在的归档目录里补文件**（例如补 manifest——#234 / #236 / #238 干的正是这件事）同样产出匹配正则的 `A` 路径，于是把**旧的、不该追溯的** change 拉进求值面。实测该形态在 89 个可解析归档上会让 **69 个变红**。判定 `git ls-tree -d --name-only <base>:openspec/changes/archive`（实测 base 树 93 个目录）与 diff 中出现的归档目录名取差集：旧目录被排除，纯 rename 的新目录仍入选。

**为什么不是 directories**：目录改名被 git 拆成文件级 rename（实测 `5ca237d` 的 7 个 R100 全给出 archive 新路径，旧路径一条不出）；`--name-only` 对 rename **只印新路径**（实测）；仓库无 `.gitattributes`；即使 rename 检测被关，`D`+`A` 里的 `A` 侧仍带 archive 路径 ⇒ 三重保险。

**非规范归档目录即报错**（Q5，用户已确认「报错 + known-debt 双写」）：diff 中 `startswith("openspec/changes/archive/")` 但不匹配日期正则的路径 → 进 `errors`。否则「`archive/foo/`（漏日期前缀）」这种归档**既不匹配正则、又被 `iter_change_dirs:1283` 排除在 active 之外**，落成「既不在任何门里」的静默面——正是本 change 要消灭的形态。当前语料触发面为零（93/93 都有日期前缀）。

### D2: 归档点评估门集合（全四道 + 未勾任务）

对每个 `id`，在 `openspec/changes/archive/<date>-<id>/` 上评估：

| 门 | 复用 | 继承的豁免 |
|---|---|---|
| RIR 内容门槛 | `_check_reference_implementation_research:505` | `:508` 的 **docs 豁免** |
| grill 证据 | `_check_design_review_task:711` | `:712` 的 `all_types & DESIGN_TYPES`（**bugfix 不在其中 → 不要求**） |
| Open Question 确认 | 同 `_check_design_review_task` 内的 `_unconfirmed_open_questions` | 同上 |
| building-review | **仅存在性**（`reviews/building-review.md`） | `:1029-1031` 的 `primary != "docs"` + `_changed_capabilities` |
| 未勾任务 | 新增 `_untagged_unchecked_tasks` | 见 D4 |

**为什么 building-review 只做存在性、不复用 `_check_review_manifests`**：**理由经 grill 实跑修正**（用户已确认，Q4 附带修正项）。原 design 称「后者在 `archived=False` 时走 `review_manifest.py:175` 的严格 `tasks_hash` 比较 → 一定误报 `tasks hash mismatch`」——**该理由被证伪**：把归档目录喂给 `_check_review_manifests(..., archived=False)` 实际报的是 `review manifest missing: openspec/changes/<id>/reviews/building-review-manifest.json`（**active 路径**），根因在更上游——`verify_review_manifest` 用 `change_dir_for(repo_root, change_id, archived=False)` 解析回 **active 目录**，该目录在归档后已不存在；`tasks_hash` 那行根本走不到。**结论不变**（不复用、只做存在性），但错误的是理由，**spec delta 不得固化错理由**。

**manifest 完整性留给 CI 第二步 `--check-archived`**（它有 archived 语义与 tasks_hash 降级，且遍历工作树 `archive/`，会覆盖本 PR 新归档的 change）。分工闭环（grill 端到端验证）：有 review 无 manifest → 第二步报 `review manifest missing`；两者都缺 → 第一步报。

> **豁免继承与触发覆盖**（Q1，用户已确认两条测试都补）：D2 表格的"继承豁免"要显式断言，但**只验豁免会漏掉真正的洞**——`_check_design_review_task` 的**判据本身**也挂在 `_tasks_all_complete` 上（见 D3），归档目录残留未勾项时它对「无 `reviews/`」的输入返回 `[]`。故须同时补：(a) docs-only 归档 → 四门不报；(b) **无 `reviews/` 的非 docs 归档 → 报需要 grill 证据**。

### D3: 解耦机制（四道门如何脱离 `_tasks_all_complete`）

**这是 R5 的点名观察项（O3）。** 现状四道门里有**两道的判据本身就是 `_tasks_all_complete`**：RIR 内容门（`:585`）与 grill 完整性门（`:733` 的 OpenQuestion 覆盖 + `:750` 的证据强制）。归档目录只要残留一条未勾任务（35/93 历史归档如此），这两道门就**静默返回空**——恰是本 change 要堵的洞。

**grill 实跑否决了 B**：抽出独立评估函数、原样复用判定函数 ⇒ 复用的正是带 `_tasks_all_complete` 判据的函数 ⇒ 归档侧两道门静默。**「复用同一判定函数、不复制逻辑」与「四门全评估」在 B 框架下不可兼得**。

**采纳 A′**（grill 裁决，用户已确认）：
- 给 `_check_reference_implementation_research` 与 `_check_design_review_task` 各加 `*, assume_implemented: bool = False`；
- 函数内三处判据 `if _tasks_all_complete(change_dir):` → `if assume_implemented or _tasks_all_complete(change_dir):`（`:585` / `:733` / `:750`）；
- **`check_change` 一行不动**（不传参 → 默认 `False` → active 行为逐字节不变，`test_partial_change_does_not_require_building_review:241` 天然原样通过）；
- 归档侧调用时传 `assume_implemented=True`。

**A′ 相对 B 的第二个优势**（grill 风险观察）：`check_change` 跑约 10 类检查，归档侧按 D2 只跑 5 类——A′ 把「两套独立实现的漂移」压缩成「归档侧少调 5 类检查」这一处**有意的**差异。`:1031`（`requires_building_review`）**不需要**参数化——归档侧只做存在性、不走 `_check_review_manifests`（D2 已定），故三处而非四处。

### D4: `(post-merge)` tag 机制

**语法**（实测 8/8 通过）：
```
^\s*[-*+]\s*\[[ xX]\]\s*(?:\*\*)?(?:\d+(?:\.\d+)*)?(?:\*\*)?\s*[（(]\s*post-merge\s*[)）]
```
（`re.I`）——容忍编号/粗体在前、全半角括号、大小写。

**为什么必需**：归档时 PR **尚未合入**，「PR 合入后关 issue」类任务**结构上无法完成**。实测 93 归档中 35 个有未勾项、**9 个的全部未勾项均属 post-merge 类**。无 tag 则每个 well-formed 新归档都会红。

**只有带 tag 的未勾行被豁免**；无 tag 一律算实现未完成。**不做标题 legacy 兜底**（唯一能 fail-open 的面）。

**顺带修扫描窄口径**：现只认 `- [x]`/`* [x]`（`:996-998`），不认 `[X]`/`+`。一并覆盖，保留「缩进子项也算」。实测现存 `+ [ ]`/`- [X]` 命中 0 ⇒ 零影响。

### D5: 新约定的文档化（必需）

closeout 类任务须带 tag——这是**新强制约定**。实测现有 closeout 行**全无 tag**（`- [ ] 5.6 PR 合入时，给关联 issue #133 添加 comment 并关闭。`），不文档化则每个 future change 归档时误红。

落地：`AGENTS.md` + `docs/development-guide.md` + archive 命令文件（**注**：`.claude/commands/opsx/archive.md` 当前不存在，需先 `npx openspec init --tools claude` 生成；存在则改）+ **一条测试锁定该约定生效**。

### D6: CI 挂载与 fail-closed

- **只挂 CI 第一步**（`ci.yml:62`，带 `--base-ref`）。
- 第二步（`ci.yml:70`）不评估。**区分依据是 `--check-archived`，不是 `--base-ref`**——后者 argparse 默认值是 `"master"`（`:1388`），不传也会算 diff（这是 R5 纠正我的一处理由错误）。
- **新门必须放在 `if not args.skip_protected_paths:` 块之外**（Q2，用户已确认）：CI 第二步命令行是 `--check-archived --skip-protected-paths --skip-backlog`，**它同时也传 `--skip-protected-paths`** ⇒ 若新门放进该块内，`--skip-protected-paths` 事实上成了区分开关，违反「不能被它关掉」；而 AGENTS.md 速查表推荐本地跑 `check_openspec_artifacts.py --check-archived`（**不加**该 flag），新门会在全部 93 个归档上求值。守卫用 `not args.check_archived`（显式），不靠 flag 副作用。
- **`--change <id>` 非空时跳过新门**（风险小a，用户已确认）：否则本地跑 `--change <id>`（`--base-ref` 默认 master、`--check-archived` 为假 → 新门触发）会**额外**评估分支上的归档 id，用户以为只查了一个 change。
- **新门自己兑现 `--require-base`**（风险小b，用户已确认）：`_changed_paths_since_base:1352` 在 base 不可解析时返回空集合 + warning，`main()` 只在 `--require-base` 时把它升级成 error（`:1456-1461`）。新门独立算 diff，**必须同样消费 warning**，否则 `git clone --depth 1` 下新门 0 个 id → 静默放行（fail-open）。
- fail-closed：`ref 不可解析 ∧ --require-base` → 报错；`changed_paths 为空`（master push）→ 不报错。

### D7: 残余面（记 known-debt）

- 「实现 PR 完全不归档」→ 门不触发。**流程违规**（违反 AGENTS.md:25），非静默绕过；change 仍以 active 可见。
- **无日期前缀归档**（O5）：**报错 + known-debt 双写**（用户已确认）——见 D1 末段。只记 debt 会留一个「既不在 active 也不在任何门」的静默面，与本 change 的立意冲突。

## Pre-Implementation Review

非平凡 change（改 CI 门禁触发语义 + 动受保护 spec），进入实现前由独立零记忆 subagent 执行 `/grill`，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），Open Questions 停轮抛用户确认后写入 `## User Confirmation`。

**grill 已完成**（run `7a0c0462`，2026-09-23）：9 条 Confirmed Decisions / 7 条 Open Questions，全部 7 条 + 3 条新风险经用户逐项拍板（见 `reviews/grill-design.md` 的 `## User Confirmation`）。**grill 的两处实质改动**：D3 由 B 改为 **A′**（B 被实跑否决）；新增 D1 的「base 树不存在」条件与「非规范归档目录报错」。另修正 D2 的错误理由（见 D2）。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 反转 `f4a4272`（未实现 change 误报） | 归档点触发 + D3 路线 A′（`check_change` 一行不动）；`test_partial_change...:241` 原样通过作为判据 |
| 爆炸半径失控（波及历史归档） | 只评估本 PR **新建**归档（AR + base 树不存在）；实测历史 93 归档不在本 PR diff；`--check-archived` 不进新门 |
| **误伤既有归档**（往旧归档目录补文件被判「新归档」） | D1 的「base 树不存在」条件 + 判别性测试（grill 风险②；实测该形态会让 69/89 归档变红） |
| 四道门在归档侧静默（判据挂在 `_tasks_all_complete`） | D3 路线 A′ 的 `assume_implemented` 参数（三处判据） |
| manifest 严格校验误报 | D2 只做存在性，完整性留给 CI 第二步（理由已按 grill 实跑修正） |
| 新 tag 约定未文档化 → future change 误红 | D5 强制文档 + 测试锁定 |
| 四门判定逻辑两处漂移 | D3 路线 A′ 复用同一对函数（不复制逻辑）+ 双路径一致性测试 |
| 无日期前缀归档绕过 | D1 末段：报错 + known-debt 双写 |
| `--skip-protected-paths` 关掉新门 | D6：新门放该块外 + `not args.check_archived` 守卫 + test 锁定 |
| 浅检出下新门 fail-open | D6：新门消费 `--require-base` warning |
| `--change <id>` 额外触发新门 | D6：`--change` 非空时跳过新门 |

## Testing Strategy

见 `proposal.md` 测试计划。**核心判别性断言**：

1. 本 PR 新归档 + 缺 `building-review.md` → 门触发（问题二）。
2. 本 PR 新归档 + 一条无 tag 未勾任务 → 门触发（问题一）。
3. 同 fixture 该未勾任务加 `(post-merge)` tag → 不报。
4. `test_partial_change_does_not_require_building_review:241` **原样通过**（不反转）。
5. 既有归档（M 路径）+ `--check-archived` → 不触发。
6. 纯 rename 归档（`R100`）→ 仍取到 id（`AR` 的理由）。
7. **往旧归档目录新增文件（`A` 路径）→ 不评估该旧 id**（D1「base 树不存在」条件的判别性测试；O6b 换命题后的形态）。
8. 非规范归档目录（`archive/foo/` 无日期前缀）→ 报错（D1 末段）。
9. tag 8 变体全识别 + 无 tag closeout 行报错。
10. 无 `reviews/` 的非 docs 归档 → 报需要 grill 证据（Q1 的触发覆盖；A′ 的判别性断言）。
11. `--change <id>` 非空 → 新门不触发；`--check-archived` → 新门不触发（两条独立守卫）。
