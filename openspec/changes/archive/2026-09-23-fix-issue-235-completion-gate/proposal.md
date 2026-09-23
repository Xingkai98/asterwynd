# Proposal: 完成度门禁改挂归档点（fix-issue-235-completion-gate）

关联跟踪 issue：[#235](https://github.com/Xingkai98/asterwynd/issues/235)（任务完成度无机械兜底：`_tasks_all_complete` 是「全勾才开门」的触发器，不勾反而绕开门禁；归档路径完全不查）。

## Change Type

- primary: process
- secondary: []

## Why

`scripts/check_openspec_artifacts.py:982` 的 `_tasks_all_complete`（判据 = tasks.md 有 ≥1 个 `[x]` 且无 `[ ]`）被当**触发器**用于四道门（`:585` RIR 内容门槛 / `:733` grill OpenQuestion 确认覆盖 / `:750` grill 证据强制 / `:1031` building-review 强制），**全部是「全勾才开门」**。

**后果**：agent 留一条 `- [ ]` → 四道门全关，checker 全绿。

### 实测事实（五轮方案审阅中验证）

1. **绕开复现**：全勾 → 报 `building-review.md missing`；改一条未勾 → **零 gate 错误**。
2. **设计本意**：commit `f4a4272` 加 `_tasks_all_complete` 是**有意的**——为修「门禁对**未实现** active change 误报（spec delta 从 proposal 阶段即存在）」，且该行为已规格化进 spec（`dev-workflow-state-machine:258-266` 的「部分实现的 change 不受拦截」Scenario）。**不能简单回退。**
3. **历史实证**：93 个归档 change 中，「有 spec delta + 有未勾选 + 缺 `reviews/`」三者交叉 = **19**；缺整个 `reviews/` 目录 = **48**。
   - **未勾项分类口径更正**（O7，用户已确认）：issue #235 正文的表写「有未勾选 35 / 其中全部未勾项都是『合入后』类 9 / 含『合入后』类但不全是 **12** / 纯『做完了忘勾』23」，但 **9+12+23=44≠35，表本身不自洽**。本 change 独立重算 93 个归档（closeout 启发式 = `合入后|合入时|合并后|PR 合入|归档后|issue.*(comment|关闭)`）：有未勾项 **35**、全部未勾项都是 closeout 类 **9**、含 closeout 但不全是 **3**、纯「做完了忘勾」**23** ⇒ 9+3+23=35 自洽。**「12」有误，实测为 3**；收尾给 issue #235 写完成 comment 时 SHALL 使用更正后的数。
4. **问题二**：`iter_change_dirs:1277` **排除 archive**（`:1283`），而 AGENTS.md:25 强制「实现 PR 必含归档收尾」⇒ **正常交付 PR 的最终 head 上 change 已在 archive，四道门永不开火**。跳過 review-loop 直接归档者可绿着合入。
5. **零 impl 路径的归档 PR 真实存在**：PR `9c48a419`（归档 `evaluation-narrative`，`primary: process` 有 delta），diff 20 条路径、impl **0** 条。

## 需求

1. **触发点改挂归档点**：在 `--base-ref` 模式下，对 `git diff --name-only --diff-filter=AR <base>` 里匹配 `^openspec/changes/archive/\d{4}-\d{2}-\d{2}-([^/]+)/` **且该归档子目录在 base 树不存在**（`git ls-tree -d <base>:openspec/changes/archive` 取差集）的路径取 change id，对该 id 的**归档目录**评估四道门 + 未勾任务。
2. **归档点四道门全评估**（不因未全勾而降级）：RIR 内容门槛 / grill 证据 / Open Question 确认 / building-review 存在性 + 未勾实现任务。
3. **未勾任务需 tag 豁免**：closeout 类任务（PR 合入后动作，结构上归档时无法完成）须标 `(post-merge)`；无 tag 的未勾行进 `errors`。
4. **不追溯**：既有归档（非本 PR 的 AR 路径、或归档目录在 base 树已存在）不受影响；`--check-archived` 与 `--change <id>` 不进新门（守 48 的爆炸半径）。
5. **不破坏 `f4a4272`**：active 阶段行为不变（`test_partial_change_does_not_require_building_review:241` 原样通过）——解耦走 A′（加 `assume_implemented` 参数，`check_change` 一行不动）。
6. **新约定文档化**：`(post-merge)` tag 写入 `AGENTS.md` + `docs/development-guide.md`。
7. **残余面记 known-debt**：「实现 PR 完全不归档」不被本门覆盖（流程违规，非静默绕过）；无日期前缀归档目录则由新门**直接报错**（报错 + debt 双写）。

## 背景

五轮独立方案审阅（R1–R5）得出的综合形态：**取「归档点」作触发（v5）+ 取「全部门集合」作评估（v4）+ tag + known-debt**。根本依据：**门的职责是阻止坏 change 合入，而合入必经归档 ⇒ 归档点是唯一必要且充分的评估点**；更早评估（active 阶段）只买到反馈速度，代价是反转 `f4a4272` 的误伤面 + 引入 `has_impl`/`delivery_candidates`/双调用点三块复杂度。

业界对照（见 RIR）：CI 门普遍区分 merge-time 与 release-time enforcement，且倾向把「慢/易 flaky/需人工核对」的检查推到**更晚的必要节点**（如 SKA-Low-CBF 的 `verify-integration-tested` 只在 tag pipeline 的 `.pre` 阶段执法）。本 change 同构：把完成度门从「实现全程」推到「归档」这一必经且唯一的交付节点。

## 非目标

- **不修复「实现 PR 完全不归档」**——记 `docs/known-debt.md`（见需求 7）。
- **不改 active 阶段四道门的现有行为**（继续由 `_tasks_all_complete` 触发，不反转 `f4a4272`）。
- **不动 `--check-archived`**（它只对已有 `reviews/` 的归档做 manifest 漂移检测，覆盖面固有上界已记 debt）。
- 不引入 `has_impl` 排除法 / `delivery_candidates` / active+归档双调用点（五轮审阅已排除的复杂化）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| Artifact checker | `scripts/check_openspec_artifacts.py`：新增归档点评估路径（`main()` 中，**放在 `if not args.skip_protected_paths:` 块之外**，用 `not args.check_archived and not args.change` 显式守卫），复用现有四道门的判定函数（继承其 docs/类型豁免）；后者需按 A′ 加 `*, assume_implemented: bool = False` |
| 任务约定 | `tasks.md` 新增 `(post-merge)` tag 约定（closeout 类任务）；`_tasks_all_complete` 的扫描需同步放宽（`[X]`、`+`）以解析 tag |
| CI 门禁 | 新门只挂 CI 第一步（带 `--base-ref`）；第二步（`--check-archived`）不评估——**理由**：`--check-archived` 是唯一能把归档语境的完整性与新门区分开的开关（`--base-ref` 默认值是 `master`，不传也会算 diff，故不能用它作区分）。**注意**：CI 第二步同时传了 `--skip-protected-paths`，故新门不能放在该 flag 守卫的代码块内 |
| Specs | `openspec/specs/dev-workflow-state-machine/spec.md`：MODIFIED「开发流程精简为 OpenSpec 主干 + 强制审阅闭环」（触发条件从「tasks 全勾」改为「归档点」）+ 可能的 ADDED 归档点 Requirement |
| Tests | 新增归档点门回归测试（含 tag 语法、AR 触发、既有归档不追溯、不反转 `f4a4272`）；既有 `test_partial_change_does_not_require_building_review:241` **原样通过** |
| Docs | `AGENTS.md`（tag 约定 + 门禁描述）、`docs/development-guide.md`（tag 语法与用途）、`docs/known-debt.md`（残余面） |
| Migration / compatibility | 既有 93 个归档不受影响；active 阶段行为不变；**唯一行为变化**是「本 PR 新归档的 change 若缺审阅证据/有未 tag 未勾任务 → 归档 PR 红」 |
| 明确不受影响 | AgentLoop、ToolRegistry、Web UI、benchmark、MCP、记忆系统、受保护路径解释门禁 |

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 走 grill 的非平凡 change（改 CI 门禁触发语义 + 引入新任务约定 + 动受保护 spec）。需对标业界「**何时/在哪一节点执法完成度门**」的实践。
- research questions:
  - CI 门在 merge-time 与 release-time 的执法分工是什么？哪些检查应推到更晚的必要节点？
  - 「定义完成」（DoD）类人工清单如何自动化，且如何避免「清单项结构上无法在该节点完成」导致的误报？
  - 触发点选「全程」还是「必经节点」——业界倾向哪种，代价如何？
- findings:
  - **merge-time vs release-time 分工**（业界共识）：merge-time 门执行**快、确定性**的检查（format/lint/typecheck/unit），release-time 门执行**慢/易 flaky/需集成**的检查与审计（E2E、安全、审批）。典型实现：SKA-Low-CBF 的集成测试在 MR 流水线**只警告不阻断**，改由 `verify-integration-tested` 在 **tag pipeline 的 `.pre` 阶段**执法，失败则阻断 registry/helm 发布。→ **检查应挂在"它真正成为必要"的节点，而非尽早**。
  - **DoD 自动化与例外**：Gaudi 工作流把 DoD 落为「建 MR 前的最低要求」并允许**例外绕过——但被跳过的项必须以最高优先级记账**；aidevops 的 CI gate 政策按分支风险分级（develop 快门 / staging 加 E2E / main 加 release 与安全审计）。→ 与本 change 的「tag 豁免 + known-debt 记残余面」同构。
  - **merge queue 只放确定性检查**（Erigon `ci-gate`）：flaky 测试不得进门禁。→ 支持本 change 把"归档点评估"做成**确定性**（纯路径 + 文件存在性 + 文本解析），不含时序/网络。
  - **本地参考仓库不可用**（`.dev/reference-repos.txt` 不存在），改用上述公开实践 + 仓库内证据（`f4a4272` 的历史、五轮审阅结论）。
- design impact:
  - 触发点取**归档点**（必经且唯一的交付节点）而非「实现全程」——与 release-time gate 的业界倾向一致；同时避免 v4 的 PR 全程红灯。
  - 保留 **tag 豁免**并**显式记账**残余面（known-debt），对应业界的「例外必须可追踪」。
  - 门内检查必须**确定性**（不做需要网络的校验），符合 merge queue 只放确定性的原则。

## 测试计划

- **触发**：本 PR 新归档（AR 路径，含纯 rename 形态）→ 门触发；既有归档的 M 路径 → 不触发；**往旧归档目录新增文件（`A` 路径）→ 不触发**（base 树不存在条件）；`--check-archived` / `--change <id>` → 不触发。
- **非规范归档目录**（`archive/<id>/` 无日期前缀）→ 报错，不静默。
- **四道门各自独立断言**（防"只实现了一道"）。
- **tag 机制**：8 个语法变体（含全角、编号在前、粗体、`+`/`*`）全部识别为豁免；无 tag 的 closeout 行 → 报错。
- **不反转 `f4a4272`**：`test_partial_change_does_not_require_building_review:241` 原样通过。
- **豁免继承**（Q1a）：docs-only 归档 → 不要求四道门。
- **触发覆盖**（Q1b）：**无 `reviews/` 的非 docs 归档 → 报需要 grill 证据**（A′ 的判别性断言——只验豁免会漏掉这个真正的洞）。
- **分工闭环**（O6a）：新归档有 `building-review.md` 但缺 manifest → 第一步过、第二步报 `review manifest missing`。
- **fail-closed**：base 不可解析 ∧ `--require-base` → 新门同样报错（不静默放行）。
- 全量 `uv run pytest -q` + OpenSpec strict validate + artifact checker + `--check-archived`。
