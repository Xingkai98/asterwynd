# dev-workflow-state-machine 规格 delta

## REMOVED Requirements

### Requirement: Review evidence manifest

**Reason**: 该 Requirement 把每份 review report 绑定到 `reviews/<phase>-review-manifest.json`，由本仓 checker 校验字段、hash、git span 与 `verdict`。接入 witnessloop 后，同一份证据还要维护 `reviews/<stage>.manifest.json`（required 的 `gate / check` 消费），形成两套并存。issue #316 的探索结论确认：两套不是同一份内容的两个文件名，`spec_hash` 算法不同、历史 80 份 manifest 无法干净迁移（27 份 `tasks_hash` 漂移、8 份提交不可解析、全部缺 `author_run_id`），继续并存是重复劳动。其中唯一不被 witnessloop 覆盖的判据是 `verdict == PASS`（witnessloop v1.7.0 明确不读 verdict），由本 delta 新增的 `Review evidence 与终结 verdict` 保留。

**Migration**: 本仓形态 manifest 不再被要求、产出或校验；新 change 只产 witnessloop 形态（`grill` / `grill-adversarial` / `building` 三份 `reviews/<stage>.manifest.json`）。`verdict == PASS` 改由 building review 的 `## 闭环出口` 承载，检查落点为 active 实现完成面与本 PR 新归档面。80 份历史 manifest 保持原样、不追溯；`agent/workflow/review_manifest.py` 与 `workflow_state.py review-manifest` 写通道由第二刀处置。

## MODIFIED Requirements

### Requirement: 审阅闭环的轮次模型为有界批次，最多 20 个已收口轮

实现后的 `/review-loop` 与设计阶段的审阅闭环 SHALL 使用同一套有界批次轮次模型。**一轮** SHALL
定义为一个**非空 medium+ 批次**的完整闭环：审阅者开批 → 开发者全修 → 审阅者只做修复验证 →
全部通过 ⇒ 本轮结束；下一轮才开新一批（含 deferred）。单次审阅意见、单次修复提交、单次验证
SHALL NOT 各自计为一轮。

**批次**：一轮开始时审阅者 SHALL 只把 severity 为 `blocker` / `high` / `medium` 的问题
（合称 medium+）列入批次 `B_n`；开批时发现的 `low` / `nit` SHALL 直接进入本轮 low/nit
登记表，不进入阻塞批次。批次 `B_n` 在开批后 SHALL 冻结——本轮内 SHALL NOT 增加、删除或
替换成员，severity SHALL 随批次冻结。`B_n = ∅` ⇒ 审阅闭环 SHALL 以 `PASS` 结束，不进入
修复，也不消耗轮数。

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
`specs/<capability>/spec.md`、`tasks.md`，以及决策记录 `grill-design.md`。**设计环的出口
SHALL 是实现的前置条件**：设计环以 `BLOCKED` 终结时 SHALL NOT 作为写码许可；只有设计环
`PASS`，或 `BLOCKED` + 成因 + **用户明确裁决继续**，才允许进入实现。用户裁决 SHALL 记入
`grill-design.md` 的 `## User Confirmation`（或 `## Blocked Ruling`）。

**frontier 豁免**：grill 的 frontier 追问轮 SHALL 仅指**进入对抗环之前**、为求设计树完备而做
的内部轮；它 SHALL NOT 算作审阅轮，SHALL NOT 受 20 上限或「验证禁提新问题」约束。由对抗环
批次项驱动的设计探索属于该轮修复，SHALL NOT 改标为 frontier。

**机械门禁**：本模型 SHALL NOT 新增轮次 / 批次 / deferred 等正文解析。两侧既有判据分别为：

- **witnessloop `check`**：change 契约件、review manifest / 报告 / revision / hash /
  `reviewer_run_id != author_run_id`、孤儿报告，以及 `stage=grill` 的既有正文完备性判据；
- **`scripts/check_openspec_artifacts.py`**：building review 的终结 `## 闭环出口` PASS 判据
  （见 `Review evidence 与终结 verdict`）、受保护写入解释事件与归档点完成度门；
  `retire-manifest-check` 起不再校验 review manifest 字段 / hash。

两侧 SHALL NOT 解析报告正文里的批次、severity、轮数、deferred 或 low/nit 理由
（`stage=grill` 的既有正文判据与 `## 闭环出口` 的 PASS 门另计）。20 上限、批次冻结、
deferred 都是**流程规定**，不是机械判据；`check` 绿只证明既有证据判据通过，不证明报告
按本模型执行。

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
- **THEN** **超上限 `BLOCKED`**；报告含「建议推倒重开（revise the design）」与那 2 条问题
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

## ADDED Requirements

### Requirement: Review evidence 与终结 verdict

实现完成与归档点的审阅证据 SHALL 由 witnessloop 形态 manifest 与 building review 报告共同承载，本仓 SHALL NOT 再要求 asterwynd 形态 manifest。witnessloop 形态 manifest（`reviews/<stage>.manifest.json`）SHALL 是唯一被要求的 review manifest；本仓 checker 的 manifest 字段 / hash / git span 校验 SHALL 移除。

building review 报告 SHALL 在 `reviews/building-review.md` 中以二级标题 `## 闭环出口` 记录终结 verdict。解析规则 SHALL 为：标题以 `闭环出口` 为前缀即命中（容忍中文括号后缀，`###` 级不命中）；fenced code（` ``` ` / `~~~`）内的标题与 token SHALL 被忽略；只认该小节**首个非空行**，剥掉行首 list/bold/引用符/反引号标记后该行 SHALL 以 `PASS` / `BLOCKED` / `CHANGES_REQUESTED` 之一开头，且首个 token 后 SHALL 紧跟行尾/空白/`（`/`(`/`：`/`:` 等终止符（`PASSED` 不合规），首个 token 之后 SHALL NOT 出现 `|` 分隔的其它终结 token（官方模板占位行 `PASS | BLOCKED（…） | BLOCKED（…）` 不合规）；`PASS（此前 CHANGES_REQUESTED 已收口）` SHALL 视为合法；报告中出现多个 `## 闭环出口` 小节 SHALL 报错。终结出口 SHALL 为 `PASS` 才视为审阅通过；该判据只覆盖 building review，非 building 的 `*-review.md` PASS 门随旧 manifest 校验退役并由 known-debt 登记。

本仓 checker SHALL 在两类触发面机械校验：

- **宽触发（terminal 非 PASS）**：只要 `reviews/building-review.md` 存在且出口首个 token 为 `BLOCKED` / `CHANGES_REQUESTED`，SHALL 报错，SHALL NOT 区分 change 类型、spec delta 或 `tasks.md` 勾选状态；
- **完成面（必须 PASS）**：**active** 侧为非 docs、有 spec delta、且 `tasks.md` 全部勾选的 change；**归档点**为本 PR `--diff-filter=AR` 新建、在 base 树不存在、且**有 spec delta** 的非 docs 归档 change。完成面 SHALL 要求出口小节存在且为 `PASS`；`未定` 或小节缺失只在完成面报错。

**在完成面上**，小节缺失、首个非空行不以任何终结 token 开头、或以非 `PASS` token 开头 SHALL 报错，SHALL NOT 静默通过；**宽触发只对 terminal 非 `PASS` 报错**，不因 `未定` 或缺小节报错。多个同名小节 SHALL 在任何触发面都报错（见解析规则第 4 条）。该判据 SHALL NOT 扩大到历史归档报告，SHALL NOT 解析轮次、severity、deferred 或 low/nit 内容；`design-review.md` 等非 building 报告不在本判据覆盖面。

#### Scenario: PASS 出口通过

- **GIVEN** 一个实现完成的非 docs change，`tasks.md` 全部勾选
- **AND** `reviews/building-review.md` 含 `## 闭环出口`，首个非空行以 `PASS` 开头（允许 `PASS（...）` 说明）
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL NOT 报告审阅证据错误
- **AND** SHALL NOT 要求 `reviews/<phase>-review-manifest.json`

#### Scenario: 非 PASS 出口被拒

- **GIVEN** `reviews/building-review.md` 的 `## 闭环出口` 首个非空行以 `BLOCKED` 或 `CHANGES_REQUESTED` 开头
- **WHEN** 运行项目 artifact checker
- **THEN** 系统 SHALL 判定失败并报告出口不是 `PASS`

#### Scenario: 完成面上出口缺失、无效或多小节被拒

- **GIVEN** 一个**完成面** change（非 docs、有 spec delta、`tasks.md` 全部勾选）
- **AND** `reviews/building-review.md` 没有 `## 闭环出口` 小节，或首个非空行为 `未定` / `不是 PASS` / `PASSED` / 模板占位行 `PASS | BLOCKED（…） | BLOCKED（…）`，或出现多个同名小节
- **WHEN** 运行项目 artifact checker
- **THEN** 系统 SHALL 判定失败并报告「缺少闭环出口」「出口未填 / 不以终结 token 开头」「出口不唯一」或「闭环出口小节不唯一」

#### Scenario: fenced code 中的示例不参与判定

- **GIVEN** `reviews/building-review.md` 在 fenced code 中引用了 `## 闭环出口` 与 `BLOCKED` 的模板文本
- **AND** 真正的 `## 闭环出口` 小节首个非空行以 `PASS` 开头
- **WHEN** 运行项目 artifact checker
- **THEN** fenced code 内的标题与 token SHALL 被忽略
- **AND** checker SHALL 判定通过

#### Scenario: partial change 的未终结报告不被误伤

- **GIVEN** 一个非 docs change 有 spec delta，但 `tasks.md` 仍有未勾选项
- **AND** `reviews/building-review.md` 存在且出口为 `未定` 或没有 `## 闭环出口`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL NOT 因该报告报错（完成面才触发）

#### Scenario: 宽触发覆盖 docs / 无 spec delta / partial

- **GIVEN** 一个 docs change、一个无 spec delta 的 process change，或一个 `tasks.md` 未全勾的 change
- **AND** 其 `reviews/building-review.md` 存在且出口首个 token 为 `BLOCKED` 或 `CHANGES_REQUESTED`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 判定失败（宽触发，不看类型 / spec delta / 勾选状态）

#### Scenario: 归档点完成面要求 spec delta，宽触发不看

- **GIVEN** 一个本 PR 新归档的非 docs change 没有 spec delta
- **WHEN** 运行归档点完成度门
- **THEN** SHALL NOT 要求 `## 闭环出口` 存在（完成面不触发）
- **AND** 若其 `building-review.md` 存在且出口为 terminal 非 PASS，SHALL 仍按宽触发报错

#### Scenario: 历史归档不追溯

- **GIVEN** 一个早于本 change 的归档 change，其 `building-review.md` 没有 `## 闭环出口`
- **WHEN** 运行 `--check-archived`
- **THEN** checker SHALL NOT 因该历史报告格式报错
- **AND** SHALL NOT 校验其历史 asterwynd 形态 manifest
