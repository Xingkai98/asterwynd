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
                       ∧ p 匹配 ^openspec/changes/archive/\d{4}-\d{2}-\d{2}-([^/]+)/ }
```

**依据**：门要阻止坏 change **合入**，而 AGENTS.md:25 强制「实现 PR 必含归档」⇒ **归档 commit 是 PR 最后一个 commit** ⇒ 归档点是唯一必要且充分的评估点。

**为什么 `AR` 而非 `A`**（实测）：源目录在 base 树 → git 报 `R`（rename），源目录不在（同一 PR 内先建后 mv）→ 报 `A`。两种都产出 archive 路径，故须 `AR`。实测 PR 级计数 #236 = 10、#238 = 5（**注**：早前引用的「#236 A=2/AR=9」是**内层归档 commit** `e095bdd` 的数据，非 PR 级——已纠正）。

**为什么不是 directories**：目录改名被 git 拆成文件级 rename（实测 `5ca237d` 的 7 个 R100 全给出 archive 新路径，旧路径一条不出）；`--name-only` 对 rename **只印新路径**（实测）；仓库无 `.gitattributes`；即使 rename 检测被关，`D`+`A` 里的 `A` 侧仍带 archive 路径 ⇒ 三重保险。

### D2: 归档点评估门集合（全四道 + 未勾任务）

对每个 `id`，在 `openspec/changes/archive/<date>-<id>/` 上评估：

| 门 | 复用 | 继承的豁免 |
|---|---|---|
| RIR 内容门槛 | `_check_reference_implementation_research:505` | `:508` 的 **docs 豁免** |
| grill 证据 | `_check_design_review_task:711` | `:712` 的 `all_types & DESIGN_TYPES`（**bugfix 不在其中 → 不要求**） |
| Open Question 确认 | 同 `_check_design_review_task` 内的 `_unconfirmed_open_questions` | 同上 |
| building-review | **仅存在性**（`reviews/building-review.md`） | `:1029-1031` 的 `primary != "docs"` + `_changed_capabilities` |
| 未勾任务 | 新增 `_untagged_unchecked_tasks` | 见 D4 |

**为什么 building-review 只做存在性、不复用 `_check_review_manifests`**（五轮审阅 R5 结论）：后者在 `archived=False` 时走 `review_manifest.py:175` 的**严格 `tasks_hash` 比较**，而归档 `tasks.md` 在 PASS 后必然被继续勾选 → 一定误报 `tasks hash mismatch`（即 #232 B 记录的现象）。**manifest 完整性留给 CI 第二步 `--check-archived`**（它有 archived 语义与 tasks_hash 降级，且遍历工作树 `archive/`，会覆盖本 PR 新归档的 change）。分工闭环：有 review 无 manifest → 第二步报；两者都缺 → 第一步报。

> **grill 输入 O1**：D2 表格的"继承豁免"需在实现中**显式验证**（复用函数即继承），并补一条「docs-only 归档 → 不要求四门」测试。

### D3: 解耦机制（四道门如何脱离 `_tasks_all_complete`）

**这是 R5 的点名观察项（O3），design 必须明写。** 现状四处调用点都是 `if _tasks_all_complete(change_dir):`。归档点要「四门全评估」就必须让它们在未全勾时也跑。两条路线：

- **A（推荐）**：把四处判定改为接受显式参数（如 `assume_implemented: bool`），active 侧传 `_tasks_all_complete(...)`（行为不变），归档侧传 `True`。
- **B**：抽出「四门评估」为独立函数，归档侧直接调它，`check_change` 原样不动。

**本设计倾向 B**——它**完全不动 active 路径**，`test_partial_change_does_not_require_building_review:241` 天然原样通过，回归面最小。

> **grill 必答**：A 还是 B？（B 的代价是四道门判定逻辑在两处被调用，需保证不漂移。）

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
- **不能被 `--skip-protected-paths` 关掉**（新门走独立的 diff 计算）。
- fail-closed：`ref 不可解析 ∧ --require-base` → 报错（保持现状）；`changed_paths 为空`（master push）→ 不报错。

### D7: 残余面（记 known-debt）

- 「实现 PR 完全不归档」→ 门不触发。**流程违规**（违反 AGENTS.md:25），非静默绕过；change 仍以 active 可见。
- **O5**：归档到**无日期前缀**目录 → 正则不匹配 + 不在 active ⇒ 彻底无门。需先违反 AGENTS.md:25 命名硬规则，风险低；记 known-debt 或对非规范归档目录单独报错（**grill 裁定**）。

## Pre-Implementation Review

非平凡 change（改 CI 门禁触发语义 + 动受保护 spec），进入实现前由独立零记忆 subagent 执行 `/grill`，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），Open Questions 停轮抛用户确认后写入 `## User Confirmation`。

**grill 输入 = R5 的 7 条观察项**：O1（类型豁免）· O2（CI 理由改写，已并入 D6）· **O3（解耦机制 A/B，本设计给 B）** · O4（RIR 口径统一）· O5（无日期前缀归档）· O6（补 2 条测试）· O7（9/12 口径重叠）。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 反转 `f4a4272`（未实现 change 误报） | 归档点触发 + D3 路线 B（不动 active 路径）；`test_partial_change...:241` 原样通过作为判据 |
| 爆炸半径失控（波及历史归档） | 只评估本 PR 的 AR 路径；实测历史 93 归档不在本 PR diff；`--check-archived` 不进新门 |
| manifest 严格校验误报 `tasks hash mismatch` | D2 只做存在性，完整性留给 CI 第二步 |
| 新 tag 约定未文档化 → future change 误红 | D5 强制文档 + 测试锁定 |
| 四门判定逻辑两处漂移（D3 路线 B） | 复用同一判定函数（不复制逻辑）；测试覆盖两路径一致 |
| 无日期前缀归档绕过（O5） | 记 known-debt 或单独报错（grill 裁定） |
| `--skip-protected-paths` 关掉新门 | D6 独立 diff 计算 + test 锁定 |

## Testing Strategy

见 `proposal.md` 测试计划。**核心判别性断言**：

1. 本 PR 新归档 + 缺 `building-review.md` → 门触发（问题二）。
2. 本 PR 新归档 + 一条无 tag 未勾任务 → 门触发（问题一）。
3. 同 fixture 该未勾任务加 `(post-merge)` tag → 不报。
4. `test_partial_change_does_not_require_building_review:241` **原样通过**（不反转）。
5. 既有归档（M 路径）+ `--check-archived` → 不触发。
6. 纯 rename 归档（`R100`）→ 仍取到 id（`AR` 的理由）。
7. tag 8 变体全识别 + 无 tag closeout 行报错。
