# dev-workflow-state-machine 规格 delta

## REMOVED Requirements

### Requirement: 审阅闭环的终止条件为收敛，而非轮数上限

**Reason**: 该 Requirement 的「收敛」定义以「一次审阅下来没有新的 medium+ 可证伪项」为终止条件，
但**没有定义「一轮」本身**：审阅者可以在开发者修复期间不断追加新问题，轮次不可数、单轮工作量
无界；其「无法收敛 = 从第 3 轮起最近两轮开放数没有下降」也只是一个趋势判据，无法给出有界的
最坏情况。用户 2026-10-17 重新定义了轮次模型，并已由 witnessloop（PR #40/#41，issue #24）
落地：一轮 = 一个非空 medium+ 批次的闭环，最多 20 个已收口轮，超限 ⇒ `BLOCKED` +
「建议推倒重开（revise the design）」。

**Migration**: 「无轮数上限 + 收敛趋势」→ 由本 delta 新增的
`### Requirement: 审阅闭环的轮次模型为有界批次，最多 20 个已收口轮` 承载。`PASS` /
`BLOCKED` 的三态值保留，但 `CHANGES_REQUESTED` 明确降为轮内状态；`BLOCKED` 的成因不再包含
「无法收敛趋势」，改为「阻塞性缺陷 / 同一批反复无法收口」；超上限 `BLOCKED` 是独立的第三种出口。

## MODIFIED Requirements

### Requirement: 开发流程精简为 OpenSpec 主干 + 强制审阅闭环

开发流程 SHALL 精简为「OpenSpec 主干」（proposal → grilling → worktree → TDD → spec sync → PR）加「实现完成后强制独立 subagent 审阅闭环」。原四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）SHALL 停用，不再作为开发流程的强制要求。审阅证据 SHALL 存放于 `openspec/changes/<id>/reviews/`（随 change 进 PR，CI 可机械校验）。

其中的 grill 环节 SHALL 为「grilling（独立零记忆设计追问）→ 设计阶段审阅闭环（独立零记忆审阅者对抗分析 → verdict → 修 → 按有界批次模型推进（开批 → 全修 → 只做修复验证 → 收口；最多 20 个已收口轮）；能由代码判定的问题用代码给出带证据的答案）→ 停轮确认」，产出 SHALL 记于 `openspec/changes/<id>/reviews/grill-adversarial.md`。该「设计阶段审阅闭环」与实现完成后的 `/review-loop` **同构但对象不同**（前者审设计、后者审代码），二者分属两阶段、SHALL 并存；实现后的 `/review-loop` SHALL NOT 被本环节替代。

**审阅门的触发条件 SHALL 为「归档点」，而非「tasks.md 全部勾选」。** 依据：留一条未勾选项即可关闭全部下游门禁，构成绕开路径；而 `AGENTS.md` 强制「实现 PR 必须同时包含归档收尾」，故**归档 commit 是 PR 的最后一个 commit，归档点是唯一必要且充分的评估点**。触发集合 SHALL 为 `--base-ref` diff 中 `--diff-filter=AR`、匹配 `openspec/changes/archive/<date>-<id>/` **且该归档子目录在 base 树不存在**的路径——末条为必需，否则「向既有归档目录补文件」会被误判成本 PR 新归档，从而对陈旧 change 追溯求值。对**本 PR 新归档**的 change，checker SHALL 在其**归档目录**上评估非 docs + 有 spec delta 的审阅证据与内容门槛，SHALL NOT 因 tasks 未全勾而跳过。

**归档目录命名 SHALL 合规**（`archive/<YYYY-MM-DD>-<change-id>/`）：diff 中出现于归档根下但不匹配该命名规则的路径 SHALL 报错，SHALL NOT 静默——否则会落进「既不在 active 也不在归档门」的无人覆盖区。

**部分实现的 active change 仍 SHALL NOT 被要求审阅证据**——`tasks.md` 有未勾选项的在途 change 继续不受拦截（保留原「避免误伤在途 change」口径）。

**未勾选任务 SHALL 显式分类**：closeout 类任务（PR 合入后的动作，结构上在归档时无法完成）SHALL 以 `(post-merge)` 标记标注；未标的未勾选项在归档点评估时 SHALL 报错，SHALL NOT 静默存在。

**完成度证据 SHALL 存在且可证明完成**：归档 change 的 `tasks.md` SHALL 存在，SHALL 含 ≥1 条 checkbox 行，且 SHALL 至少有一条被勾选。三种形态——缺文件、无 checkbox 行（散文/空文件）、全部未勾选（例如把所有项都标 `(post-merge)`）——在归档点 SHALL 各自报错并指明形态，SHALL NOT 静默通过。缺任一，则「不写 checkbox」或「一条都不勾」就与「留一条 `- [ ]`」同构地关掉了完成度维度。

#### Scenario: 实现完成且已归档的 change 提交 PR

- **GIVEN** 一个非 docs change 已实现、已归档到 `openspec/changes/archive/<date>-<id>/`，且该归档路径出现在本 PR 的 `--diff-filter=AR` diff 中
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 验证 `reviews/building-review.md` 存在
- **AND** 缺审阅证据 SHALL 报错并阻止合入

#### Scenario: 归档 change 的未标未勾任务报错

- **GIVEN** 一个本 PR 新归档的 change，其 `tasks.md` 存在未勾选项且该项**未**标 `(post-merge)`
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 报错（未勾选任务 SHALL NOT 静默存在）

#### Scenario: 标注 post-merge 的未勾任务被豁免

- **GIVEN** 一个本 PR 新归档的 change，其未勾选项标注了 `(post-merge)`（如「PR 合入后关闭 issue」）
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 不因其未勾而报错

#### Scenario: 部分实现的 change 不受拦截

- **GIVEN** 一个 change 处于提案或部分实现阶段（tasks.md 有未勾选项），且**不在本 PR 的归档路径中**
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 不要求审阅证据（避免误伤在途 change）

#### Scenario: 既有归档不被追溯

- **GIVEN** 一个在**过去的** PR 中归档的 change（其归档路径不在本 PR diff 中）
- **WHEN** 运行 artifact checker（含 `--check-archived`）
- **THEN** 检查器 SHALL NOT 要求该 change 补审阅证据或补勾任务

#### Scenario: 向既有归档目录新增文件不被当成新归档

- **GIVEN** 本 PR 向一个**在 base 树中已存在**的归档目录新增了文件（例如补一份 review manifest），该路径以 `A` 出现在 diff 中
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL NOT 把该归档目录的 change 当作本 PR 新归档求值
- **AND** 判据 SHALL 为「该归档子目录在 base 树不存在」，SHALL NOT 仅凭路径匹配正则

#### Scenario: 归档目录命名不合规即报错

- **GIVEN** 本 PR 把 change 移入 `openspec/changes/archive/<id>/`（缺 `YYYY-MM-DD-` 日期前缀）
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 报错，说明该归档目录命名不合规、无法评估完成度门
- **AND** 该 change SHALL NOT 静默落在「既不在 active 也不在归档门」的无人覆盖区

#### Scenario: 归档点门不因 tasks 未全勾而降级

- **GIVEN** 一个本 PR 新归档的非 docs change，其 `tasks.md` 存在未勾选项且 `reviews/grill-design.md` 不存在
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 在该归档目录上评估 grill 证据并报缺失
- **AND** 该评估 SHALL NOT 因 tasks 未全勾而静默跳过

#### Scenario: 归档点门与 manifest 校验模式互斥

- **GIVEN** 运行 artifact checker 时带有 `--check-archived`
- **WHEN** 本 PR 的 diff 中含新归档路径
- **THEN** 归档点完成度门 SHALL NOT 被触发（该模式 SHALL 只做既有 manifest 的漂移检测）
- **AND** 单 change 模式（`--change <id>`）SHALL 同样不触发归档点门

#### Scenario: 状态机仪式停用

- **GIVEN** 开发流程精简已生效
- **WHEN** agent 开始新 change 开发
- **THEN** 无需 phase/sub_state 推进、handoff.json 或 gate 停止
- **AND** 开发流程遵循 OpenSpec 主干 + 实现完成后 `/review-loop` 审阅闭环

#### Scenario: 归档 change 需设计阶段审阅证据

- **GIVEN** 一个本 PR 新归档的、非 docs + 属 DESIGN_TYPES（feature/refactor/process）+ 有 spec delta 的 change（bugfix/research 不走 grill，故豁免本门）
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 验证 `reviews/grill-adversarial.md` 存在
- **AND** 缺失 SHALL 报错（归档点要求设计阶段审阅闭环证据）

#### Scenario: grill 环节含设计阶段审阅闭环

- **GIVEN** 一个非平凡 change 完成 grilling 并产出 `reviews/grill-design.md`
- **WHEN** 进入停轮确认前
- **THEN** SHALL 先运行设计阶段审阅闭环（独立零记忆审阅者，对抗分析 → verdict → 修 → 按有界批次模型验证直到收口），产出 `reviews/grill-adversarial.md`
- **AND** 该闭环与实现完成后的 `/review-loop` 同构但对象不同（审设计 vs 审代码）
- **AND** 实现后的 `/review-loop` SHALL 继续存在，不被本闭环替代

## ADDED Requirements

### Requirement: 审阅闭环的轮次模型为有界批次，最多 20 个已收口轮

实现后的 `/review-loop` 与设计阶段的审阅闭环 SHALL 使用同一套有界批次轮次模型。**一轮** SHALL
定义为一个**非空 medium+ 批次**的完整闭环：审阅者开批 → 开发者全修 → 审阅者只做修复验证 →
全部通过 ⇒ 本轮结束；下一轮才开新一批（含 deferred）。单次审阅意见、单次修复提交、单次验证
SHALL NOT 各自计为一轮。

**批次**：一轮开始时审阅者 SHALL 只列 severity 为 `blocker` / `high` / `medium` 的问题
（合称 medium+）；批次 `B_n` 在开批后 SHALL 冻结——本轮内 SHALL NOT 增加、删除或替换成员，
severity SHALL 随批次冻结。`B_n = ∅` ⇒ 审阅闭环 SHALL 以 `PASS` 结束，不进入修复，也不消耗轮数。

**全修**：开发者 SHALL 修完 `B_n` 的每一项。实现环每项 SHALL 附一条**能变红的回归测试**
（先红后绿）；设计环的对应物 SHALL 是可复现反例 / 一条改前失败、改后通过的文档守卫 /
逐条决策记录（三选一），SHALL NOT 填 `N/A`。

**修复验证**：审阅者 SHALL 只逐条确认 `B_n` 每一项是否修好；未修好 ⇒ 开发者继续修，
**仍是同一轮**，SHALL NOT 另计一轮。**验证重试的终止点**：同一项被再次（第二次及以后）判
`未修好`、且开发者拿不出**新的、可验证的修复方案**时，审阅者 SHALL 以 `BLOCKED` + 成因终结
（记录验证次数、每次的修复提交与测试）；第一次判 `未修好` 时开发者就明确拿不出新方案，也立即
触发。「新的、可验证的修复方案」= 实现环：新 commit + 一条修复前红、修复后绿的回归测试
（或可复现失败的命令）；设计环：具体文本修改 + 可复现反例 / 文档守卫 / 逐条决策记录。
**若上述终止点发生在第 20 轮，出口是超上限 `BLOCKED`，不是通用 `BLOCKED`**。

**验证期禁提新问题**：验证阶段 SHALL 只做「当前批次逐项是否修好」的确认。审阅者在验证期间
发现的任何**新**问题 SHALL：

- severity 为 medium+ ⇒ 写入本轮报告的 `deferred`（下一批）清单，**不得**当场要求修复，
  **不得**扩大 `B_n`；
- severity 为 low / nit ⇒ 写入本轮报告的 low/nit 登记表。

验证期间若审阅者确认 low/nit 登记表里的某项实际是 medium+，它 SHALL 从 low/nit 表移到
`deferred`，**不得**当场加入当前批次。验证阶段的唯一允许变化是：`B_n` 各项的验证状态、
`deferred` 清单、low/nit 登记表；批次成员 SHALL 保持不变。**例外不是「新问题」**：若该新问题使当前轮的验证失去意义，或继续实现/验证
本身不安全 ⇒ SHALL 以 `BLOCKED` + 成因终结；其余安全漏洞 SHALL 进 `deferred`。所有 deferred
medium+ 的「延后理由」列 SHALL 写「为什么可以延后一轮」；安全项额外写「为什么晚一轮仍安全」。

**deferred 传递**：下一次开批 SHALL 先读上一轮的 `deferred` 与 low/nit 表；每个 deferred
medium+ SHALL 以**原 id** 出现在下一轮批次，或出现在本轮 `BLOCKED` 的成因里。

**severity 与处置**：medium+ SHALL 全部修完并验证通过，SHALL NOT 以「登记不修」放行。
low / nit SHALL NOT 阻塞本轮收口或 `PASS`；可修，也可登记不修，但报告 SHALL 逐条写明理由。
severity SHALL 由审阅者定级；开发者 SHALL NOT 自行把 medium+ 降级以跳过修复。验证期若审阅者
认为定级错误，只能二选一：（a）按原 severity 要求修完；或（b）`BLOCKED` 并把争议写进成因；
SHALL NOT 静默把批次项移出批次或降为 low/nit。最终 `PASS` 报告 SHALL 携带**累积** low/nit
登记表，或逐项链接到首次登记的轮次小节。

**20 轮上限**：审阅闭环 SHALL 最多存在 **20 个已收口的轮**（`B_n` 全部验证通过的轮；
`BLOCKED` / 超上限 `BLOCKED` 的终结态不计入）。轮数 SHALL 按 **change（且按环）** 累计；
后续报告 SHALL 保留前序轮次，或引用同一份叠写报告；换审阅者 run / 另写一份从第 1 轮开始的
新报告 SHALL NOT 重置计数。重置计数只能来自用户的明确裁决，并 SHALL 记为 `BLOCKED` /
建议重开设计。第 20 轮自身达到验证重试终止点 ⇒ SHALL 以**超上限 `BLOCKED`**
终结。第 20 轮收口后、收口确认前 SHALL NOT 开启第 21 轮或做修复；审阅者 SHALL 做一次
**收口确认**（下一次开批）：批次为空 ⇒ `PASS`；批次非空 ⇒ **超上限 `BLOCKED`**，附第 20 轮
账本与未收口 medium+ 列表，SHALL NOT 开启第 21 轮修复。超上限报告 SHALL 明确写
「**建议推倒重开（revise the design）**」，其停轮原因 SHALL 表述为「20 轮有界修复仍未收口，
说明问题在设计层」，SHALL NOT 表述为「到轮数就停」或「照合交人」。

**零轮 PASS 与 id**：初次开批（第 0 轮）为空 ⇒ `PASS`；报告 SHALL 写
`### 初次开批 · 收口确认`，low/nit 用 `R0-<序号>`。第 20 轮收口后的收口确认若发现 medium+
⇒ 超上限 `BLOCKED`，标识用 `C-<序号>`（或 `R20-C<序号>`）；若只发现 low/nit ⇒ 仍可
`PASS`，同样用 `C-<序号>`。一般批次项 id SHALL 形如 `R<首次出现轮次>-<序号>`；deferred 项
进入下一轮批次时 SHALL 沿用原 id。多轮同文件时，每轮小节标题 SHALL 带轮次（例：
`### 第 3 轮 · 批次`），以便第三方只读相邻轮次即可复核。

**报告形态**：每轮报告 SHALL 至少包含（轮内 verdict 与闭环出口分开）：

1. **本轮判定（verdict）**：`PASS` / `CHANGES_REQUESTED` / `BLOCKED`（轮内可见，不是终结出口）；
2. **批次表**：`id` / severity / 锚点（`文件:行`）/ 问题；
3. **验证表**：`id` / 结果（已修好 / 未修好）/ 修复提交 / 回归测试或设计环对应物；
4. **deferred 表**：`id` / severity / 锚点 / 问题 / 来源 / 延后理由；
5. **low/nit 登记表**：`id` / severity / 处置（已修 / 登记不修）/ 理由（累积或链接）；
6. **收口确认**：`### 第 <n> 轮后 · 收口确认`；`PASS` 出口 SHALL 引用这一节；`BLOCKED` /
   超上限 `BLOCKED` 报告 SHALL NOT 伪造收口确认，改记「终止状态 / 验证账本 / 未通过项」；
7. **闭环出口**：只在终结时填 `PASS` / `BLOCKED`（成因）/ 超上限 `BLOCKED`（建议重开设计）；
   轮内写「未定」。

**三种出口**：审阅闭环的终结态 SHALL 只有：

| 出口 | 条件 |
|---|---|
| `PASS` | 收口确认批次为空（含初次开批） |
| `BLOCKED` + 成因 | 阻塞性缺陷 / 同一批反复无法收口（验证重试终止点）；停下报告、不自行修复 |
| 超上限 `BLOCKED` | 20 个轮已收口且收口确认仍有 medium+，或第 20 轮自身达到验证重试终止点；附「建议推倒重开（revise the design）」 |

`CHANGES_REQUESTED` SHALL NOT 被视为出口；它只表示「本批仍有未验证通过的项」，对应动作是
继续修 / 继续验证。

**两环共用**：设计阶段对抗环与实现后 `/review-loop` SHALL 使用同一套轮次模型（批次 / 验证 /
deferred / 20 / 三出口）。设计环的 `BLOCKED` 成因映射 SHALL 为：核心需求缺失 / 设计自相矛盾 /
依赖不可满足 / 同一批反复无法收口；作者负责改该 change 的设计制品：`design.md`、`proposal.md`、
`specs/<capability>/spec.md`、`tasks.md`，以及决策记录 `grill-design.md`。

**frontier 豁免**：grill 的 frontier 追问轮 SHALL 仅指**进入对抗环之前**、为求设计树完备而做
的内部轮；它 SHALL NOT 算作审阅轮，SHALL NOT 受 20 上限或「验证禁提新问题」约束。由对抗环
批次项驱动的设计探索属于该轮修复，SHALL NOT 改标为 frontier。

**机械门禁**：本模型 SHALL NOT 新增任何正文解析。两侧既有判据分别保持不变：

- **witnessloop `check`**：change 契约件、review manifest / 报告 / revision / hash /
  `reviewer_run_id != author_run_id`、孤儿报告，以及 `stage=grill` 的既有正文完备性判据；
- **`scripts/check_openspec_artifacts.py`**：review manifest 字段 / hash / verdict、
  `*-review.md` 绑定与归档点完成度门；本 change 只改其提示字符串，判定逻辑一行不改。

两侧 SHALL NOT 解析报告正文里的 verdict、批次、severity、轮数、deferred 或 low/nit 理由
（`stage=grill` 的既有正文判据另计）。20 上限、批次冻结、deferred 都是**流程规定**，不是
机械判据；`check` 绿只证明既有证据判据通过，不证明报告按本模型执行。

#### Scenario: 第 1 轮验证不通过 ⇒ 继续修，不另计轮

- **GIVEN** 第 1 轮批次为 A/B/C（均为 medium+）
- **WHEN** 开发者修完 A/B/C，审阅者复验发现 A/B 已修好、C 未修好
- **THEN** 本轮不结束；开发者继续修 C；C 修好并复验通过后，本轮结束
- **AND** 轮数仍为 1；第 2 轮仅在开新批次时开始

#### Scenario: 验证期发现新 medium+ ⇒ 只进 deferred

- **GIVEN** 第 3 轮批次 `B_3` 有 4 项，验证到第 2 项时发现一个 medium+ 新问题
- **WHEN** 审阅者写本轮报告
- **THEN** 该新问题只出现在 `### 第 3 轮 · 下一批（deferred）`；`B_3` 仍为 4 项
- **AND** 第 3 轮批次全部验证通过后，本轮结束；该新问题进入第 4 轮批次

#### Scenario: 下次开批必须携带上一轮 deferred

- **GIVEN** 第 3 轮 deferred 表含 `R3-2`
- **WHEN** 第 4 轮开批
- **THEN** `R3-2` SHALL 以原 id 出现在第 4 轮批次，或出现在本轮 `BLOCKED` 的成因里

#### Scenario: 开批为空 ⇒ PASS（零轮）

- **GIVEN** 初次开批没有发现任何 medium+，但有 2 条 low/nit
- **WHEN** 判定出口
- **THEN** 以 `PASS` 结束；报告写 `### 初次开批 · 收口确认`，low/nit 用 `R0-1` / `R0-2`

#### Scenario: medium+ 写成「登记不修」⇒ 不合格

- **GIVEN** 批次里有一条 severity = medium 的项，开发者标为「登记不修」
- **WHEN** 审阅者验证
- **THEN** 该项 SHALL 判为**未修好**；本轮不结束，直到它被修完并验证通过

#### Scenario: 第 20 轮收口后仍有 medium+ ⇒ 超上限 BLOCKED

- **GIVEN** 第 1–20 轮均已收口；收口确认发现 2 条 medium+（id 用 `C-1` / `C-2`）
- **WHEN** 判定出口
- **THEN** `BLOCKED`；报告含「建议推倒重开（revise the design）」与那 2 条问题
- **AND** 不会开始第 21 轮修复

#### Scenario: 第 20 轮收口后批次为空 ⇒ PASS

- **GIVEN** 第 1–20 轮均已收口；收口确认没有 medium+
- **WHEN** 判定出口
- **THEN** `PASS`——收口确认不占第 21 轮，也不把「第 20 轮」改写成停轮理由

#### Scenario: 第 20 轮自身达到验证重试终止点 ⇒ 超上限 BLOCKED

- **GIVEN** `B_20` 有 1 项，第二次验证仍为 `未修好`，开发者拿不出新的可验证修复方案
- **WHEN** 判定出口
- **THEN** **超上限 `BLOCKED`**；报告含「建议推倒重开（revise the design）」+ 第 20 轮账本
- **AND** 不会开启第 21 轮，也不会退化成不带「建议重开」的通用 `BLOCKED`

#### Scenario: 本批仍有未通过项 ⇒ 不是出口

- **GIVEN** 第 5 轮批次尚有 1 项未修好
- **WHEN** 写报告
- **THEN** 报告可以写 `CHANGES_REQUESTED` 作为轮内状态，但 `## 闭环出口` 写「未定」
- **AND** SHALL NOT 据此停下交人，除非命中 `BLOCKED` 的成因

#### Scenario: grill frontier 的内部轮不占 20

- **GIVEN** grill 为求 frontier 为空内部走了 5 轮追问
- **WHEN** 进入设计对抗环
- **THEN** 对抗环仍从第 1 轮开始计数；frontier 的 5 轮不占 20 上限

#### Scenario: 对抗环的验证期发现新问题

- **GIVEN** 设计对抗环第 2 轮批次已全部修完，验证时又发现一条必须修改
- **WHEN** 审阅者写报告
- **THEN** 该条进 deferred，进入第 3 轮批次；不得当场扩第 2 轮批次

#### Scenario: 第 20 轮第一次未修好但开发者有新方案 ⇒ 同轮继续

- **GIVEN** `B_20` 有 1 项，第一次验证判 `未修好`，开发者提交了新 commit + 先红后绿的回归测试
- **WHEN** 判定出口
- **THEN** **不是**超上限 `BLOCKED`；继续第 20 轮修复/验证（同轮，不另计轮）

#### Scenario: 验证期把 low 重分类为 medium+ ⇒ 进 deferred

- **GIVEN** low/nit 登记表里有一项，验证期间审阅者确认它实际是 medium+
- **WHEN** 写本轮报告
- **THEN** 它 SHALL 从 low/nit 表移到 `deferred`，**不得**当场加入当前批次
