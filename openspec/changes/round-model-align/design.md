# Design: 轮次口径对齐 witnessloop——有界批次 × 20 轮上限

## Context

用户先把 asterwynd 的「3 轮封顶」改成了「无上限 + 收敛判据」（PR #314），随后**重新定义了
「一轮」**：一轮不是一个 verdict，而是**一个非空 medium+ 批次的闭环**。这个新模型已在
witnessloop 落地（PR #40/#41，issue #24 已关），权威文本是：

- `templates/review-loop.md`（`main` = `98b97b7`）——规范本体；
- `templates/grill.md`——两环同构 + frontier 豁免；
- 归档 change `openspec/changes/archive/2026-10-17-convergence-based-stop/`——完整语义。

asterwynd 当前仍写上一版口径，并且存在一个结构性缺口：**旧口径没有定义「一轮」**。审阅者
可以在修复期间不断追加新问题，轮次不可数、单轮工作量无界。本 change 把本仓镜像到同一模型。

三条来自实测的硬事实决定本设计的形状：

1. **witnessloop 的模型是完整的、可逐字对齐的**：批次、冻结、验证、deferred、20、三出口、
   两环共用、frontier 豁免都有明确文本与 Scenario；本 change 不需要重新发明语义。
2. **asterwynd 的改动面是有限的、可盘点的**：10 个规范/规则落点 + 3 处提示文案 + 2 份当前
   规格；没有运行时代码路径。逐处替换即可，不需要新增任何机械机制。
3. **本地入口不在版本控制内**：`/home/happy/my-agent/.claude/commands/review-loop.md` 被
   gitignore，必须单独同步，否则会出现「仓库里改了、实际加载的入口仍按旧口径跑」。

## Goals / Non-Goals

**Goals:**

- 把 asterwynd 的轮次口径逐字镜像到 witnessloop 的**有界批次 × 20 轮上限**模型。
- 在所有规范面与规则面使用同一套 canonical 措辞；用文档守卫测试钉住「新模型在场、旧口径
  不在场」。
- 把新模型写进两份当前规格，使它成为可引用的规范而不只是散文。
- 让本 change 自己的 PR 在 `gate / check` 下判绿（改了 `scripts/**` ⇒ 会触发
  `building` 与 `grill-adversarial` 两个 stage）。

**Non-Goals:**

- 不改 witnessloop 仓、不动 `v1` / `v1.7.0` tag。
- 不搬 witnessloop 的跨轮账本、manifest 正文解析或判据 A/B′；本仓只对齐流程语义。
- 不新增任何机械正文解析；不改变 checker 的判定逻辑。
- 不回填历史归档与历史 review 报告。
- 不重新讨论用户已拍板的参数（20、medium+/low、两环共用）。

## 术语（规范定义）

- **批次（batch）**：一轮开始时审阅者开出的 **medium+** 问题列表；轮内冻结。
- **轮（round）**：一个**非空**批次的完整闭环（开批 → 全修 → 逐条验证 → 全部通过）。
- **验证（verification）**：只核对当前批次每一项是否修好；不是新一轮审阅。
- **deferred**：验证期间发现的 medium+ 新问题，登记给下一批，不扩当前批次。
- **low / nit**：不进入阻塞批次的低严重度问题；可修，也可登记不修（须写理由）。
- **收口确认（closing check）**：一轮结束后的下一次开批；批次为空 ⇒ `PASS`。初次开批
  （第 0 轮）为空也记作收口确认。
- **已收口的轮**：`B_n` 全部验证通过的轮；只有它计入 20。`BLOCKED` / 超上限 `BLOCKED`
  是终结态，不计为已收口轮。
- **轮内 verdict**：本轮报告里的 `PASS` / `CHANGES_REQUESTED` / `BLOCKED`；只有终结时才写
  「闭环出口」。
- **frontier 追问轮**：grill 在**进入对抗环之前**、为求设计树完备而做的内部轮；不是审阅轮。

## Decisions

### Decision 1: 一轮 = 一个非空 medium+ 批次的闭环

**选择**：按用户口径与 witnessloop 模板，一轮的精确流程为：

1. **开批**：审阅者做一次完整审阅，只列 `blocker` / `high` / `medium`，得到 `B_n`。
   - `B_n = ∅` ⇒ `PASS`（不进入修复，不消耗轮数）。
   - `B_n ≠ ∅` 且已有 20 个已收口轮 ⇒ 超上限 `BLOCKED`。
   - 否则本轮编号为 `n`，`B_n` 冻结。
2. **全修**：开发者修完 `B_n` 每一项；实现环每项附一条**能变红的回归测试**（先红后绿）；
   设计环的对应物是可复现反例 / 改前失败改后通过的文档守卫 / 逐条决策记录（三选一）。
3. **只做修复验证**：审阅者逐条确认 `B_n` 每一项是否修好。未修好 ⇒ 开发者继续修，
   **仍是第 n 轮**，不另计轮。
4. **收口**：`B_n` 全部验证通过 ⇒ 本轮结束；下一次开批（完整审阅）才开始新一轮。

**理由**：批次冻结后一轮的工作量有上界；验证不通过只是同轮重试，不产生「第 N 轮」的歧义。
**备选**：按「审阅者给一次 verdict」计轮（旧口径）——不可数；按「每次修复提交」计轮——
会把同一批的多次修复算成多轮，偏离用户口径。

### Decision 2: 批次冻结，验证期禁提新问题

**选择**：

- 批次成员与 severity 在开批后冻结；本轮内 SHALL NOT 增加、删除、替换或静默降级。
- 验证阶段唯一允许的变化是：`B_n` 各项的验证状态、`deferred` 清单、low/nit 登记表。
- 验证期间新发现的 medium+ 只写入 `### 第 <n> 轮 · 下一批（deferred）`，**不得**当场要求
  修复，**不得**扩大 `B_n`；low/nit 只写入登记表。
- **例外**：该新问题使当前轮验证失去意义，或继续实现/验证本身不安全 ⇒ `SHALL` 以
  `BLOCKED` + 成因终结，并在成因里写明为什么不能 deferred；其余安全漏洞仍进 deferred。
- 所有 deferred medium+ 的「延后理由」列 SHALL 写「为什么可以延后一轮」；安全项额外写
  「为什么晚一轮仍安全」。
- 下一次开批 SHALL 先读上一轮的 deferred 与 low/nit 表；每个 deferred medium+ SHALL 以
  **原 id** 进入下一轮批次，或出现在本轮 `BLOCKED` 的成因里。

**理由**：「不许边改边提」是「一轮有界」的关键；否则审阅者可以在验证时不断追加，轮次仍不可数。
**备选**：允许验证期追加问题——已被用户明确否决（会退化为无界）。

### Decision 3: 最多 20 个已收口轮；超限 = 建议推倒重开设计

**选择**：

- 最多存在 **20 个已收口轮**（`B_n` 全部验证通过）；`BLOCKED` / 超上限 `BLOCKED` 的终结态
  不计入。
- **第 20 轮自身无法收口**：若达到验证重试终止点（同一项第二次及以后判 `未修好`，且开发者
  拿不出**新的、可验证的修复方案**；第一次判 `未修好` 时开发者就明确拿不出新方案也立即触发），
  出口 SHALL 是**超上限 `BLOCKED`**（不是通用 `BLOCKED`）。
- **第 20 轮收口后、收口确认前**：等待收口确认，不开启第 21 轮，不做修复。
- **收口确认**：第 20 轮收口后做一次下一次开批——空批 ⇒ `PASS`；非空 ⇒ **超上限 `BLOCKED`**，
  SHALL NOT 开始第 21 轮修复。
- 超上限报告 SHALL 明确写「**建议推倒重开（revise the design）**」，并附第 20 轮账本与仍未
  收口的 medium+ 列表。
- 超上限的停轮原因 SHALL 表述为「20 轮有界修复仍未收口，说明问题在设计层」，SHALL NOT
  表述为「到轮数就停」或「照合交人」。

**计数口径**：

- 只有非空 medium+ 批次且全部验证通过的轮计入 20；收口确认（空批）不占轮。
- 轮数按 **change（且按环）** 累计：后续报告 SHALL 保留前序轮次，或引用同一份叠写报告；
  换审阅者 run / 另写一份从第 1 轮开始的新报告 SHALL NOT 重置计数。重置只能来自用户的
  明确裁决，并记为 `BLOCKED` / 建议重开设计。
- **零轮 PASS 与收口确认 id**：初次开批（第 0 轮）为空 ⇒ `PASS`；报告写
  `### 初次开批 · 收口确认`，low/nit 用 `R0-<序号>`。第 20 轮收口后的收口确认若发现
  medium+ ⇒ 超上限 `BLOCKED`，标识用 `C-<序号>`（或 `R20-C<序号>`）。

**理由**：用户拍板 20；有界模型下 20 轮足够大，再大说明该推倒重开。**这不是收敛判据**——
真正的 `PASS` 来自收口确认空批；20 只是安全上限。
**备选**：无限轮（上一版）——已被用户否决；把收口确认也计一轮——会让第 20 轮恰好收敛的
change 无法 `PASS`，与「某一轮没有任何 medium+ ⇒ PASS」冲突。

### Decision 4: medium+ 全修；low/nit 登记不修须写理由

**选择**：

- 批次内 severity ≥ `medium` 的每一项 SHALL 被修完并验证通过；SHALL NOT 以「登记不修」放行。
- `low` / `nit` SHALL NOT 阻塞本轮收口或 `PASS`；可修，也可登记不修，但报告必须逐条写理由。
- severity 由审阅者定级；开发者 SHALL NOT 自行把 medium+ 降级以跳过修复。若认为定级错误，
  SHALL 在报告中提出具体理由，由审阅者复核并给出结论。
- **severity 随批次冻结**：验证期若审阅者认为定级错误，只能二选一：
  （a）按原 severity 要求修完；或（b）`BLOCKED` 并把争议写进成因；SHALL NOT 静默把批次项
  移出批次或降为 low/nit。
- **累积登记**：最终 `PASS` 报告 SHALL 携带累积 low/nit 登记表，或逐项链接到首次登记的
  轮次小节——不得只留最后一轮。

**理由**：用户拍板 medium+ 全修、low/nit 可登记；severity 冻结防止「为了收口而改级」。

### Decision 5: 出口只有三种；`CHANGES_REQUESTED` 不是出口

**选择**：

| 出口 | 条件 | 报告必须写 |
|---|---|---|
| `PASS` | 收口确认批次为空（含初次开批） | 收口确认结论 + 累积 low/nit 登记表 |
| `BLOCKED` + 成因 | 阻塞性缺陷 / 同一批反复无法收口（验证重试终止点） | 成因 + 当前批次/验证状态 + 交人决策项 |
| 超上限 `BLOCKED` | 20 个轮已收口且收口确认仍有 medium+；或第 20 轮自身达到验证重试终止点 | 「建议推倒重开（revise the design）」+ 第 20 轮账本 + 未收口 medium+ 列表 |

- `CHANGES_REQUESTED` SHALL NOT 被视为出口；它只表示「本批仍有未验证通过的项」，对应动作是
  继续修 / 继续验证。
- `BLOCKED` 不自行修复：它是终结态，把问题交回用户。
- 轮内 verdict 与闭环出口分开：`## 本轮判定` 可写 `PASS` / `CHANGES_REQUESTED` / `BLOCKED`；
  `## 闭环出口` 只在终结时填三种出口之一，轮内写「未定」。

**理由**：避免「三轮 CHANGES_REQUESTED 就停下」的旧读法；也让 `BLOCKED` 的成因与超上限
可区分。

### Decision 6: 设计对抗环与实现审阅环共用同一模型；frontier 追问轮豁免

**选择**：

- `grill` 的设计阶段对抗环与实现后 `/review-loop` SHALL 使用同一套轮次模型（批次 / 验证 /
  deferred / 20 / 三出口）。
- **设计环的 `BLOCKED` 成因映射**：核心需求缺失 / 设计自相矛盾 / 依赖不可满足 / 同一批反复
  无法收口；作者负责改该 change 的设计制品：`design.md`、`proposal.md`、
  `specs/<capability>/spec.md`、`tasks.md`，以及决策记录 `grill-design.md`。
- **设计环的「能变红的回归测试」对应物**：可复现反例 / 一条改前失败、改后通过的文档守卫 /
  逐条决策记录（三选一，SHALL NOT 填 `N/A`）。
- **frontier 豁免**：grill 的 frontier 追问轮仅指**进入对抗环之前**、为求设计树完备而做的
  内部轮；它不是审阅轮，不受 20 上限与「验证禁提新问题」约束。**由对抗环批次项驱动的设计
  探索属于该轮修复**，SHALL NOT 改标为 frontier。

**理由**：两环同构是用户拍板的；frontier 求完备与「批次闭环」是不同阶段，混计会让 20 上限
错误地约束设计探索。

### Decision 7: 机械门禁零变化，只改提示文案

**选择**：

- `scripts/check_openspec_artifacts.py` 只改三处提示字符串（`:1139`、`:1623`、`:1640`）；
  判定逻辑、触发条件、返回值一行不改。
- **不新增任何正文解析**：`check` 仍只判证据存在、manifest 绑定、hash/revision、孤儿报告；
  20 上限、批次冻结、deferred、severity 都是**流程规定**。
- **诚实边界**：`check` 绿只证明既有证据判据通过，不证明报告按新模型执行；`stage=grill`
  的正文结构仍会被既有判据解析（不是本 change 新增）。

**理由**：本 change 是规则镜像，不是门禁增强；机械解析正文会引入格式规范、历史回填与覆盖
成本，且无法防伪造。

### Decision 8: 用显式 allowlist 做文档守卫，历史归档不回填

**选择**：

- 新增测试 `tests/test_round_model_alignment.py`，只扫描**显式 allowlist**：
  `AGENTS.md`、`README.md`、`README_EN.md`、`docs/requirements-process.md`、
  `docs/interview-script/questions/Q14-dev-process.md`、
  `openspec/specs/dev-workflow-state-machine/spec.md`、
  `openspec/specs/change-documentation/spec.md`、`scripts/check_openspec_artifacts.py`、
  本 change 的两份 spec delta。
- **词表**：新模型七要素必须出现（轮 = 非空 medium+ 批次 / 批次冻结 / 验证禁提新问题 +
  deferred / 20 上限 / 超限建议重开 / medium+ 全修 + low/nit 登记须理由 / 三出口）；
  旧口径词表（`无轮数上限`、`最近两轮`、`3 轮封顶`、`轮数封顶`、`round cap`、
  `no fixed round limit`、`no round limit`）在规范面**不得出现**。
- **不回填历史**：`openspec/changes/archive/**`、历史 `reviews/*.md`、`docs/openspec-change-backlog.md`
  的历史条目不在扫描面。
- **本地入口**：单独同步 `/home/happy/my-agent/.claude/commands/review-loop.md`，不混进 PR。

**理由**：旧口径散落在多个文件；显式 allowlist 让「改齐了」成为可复核的结论，而全仓减排除
容易误伤历史记录与无关的基准预算语义。

## Testing Strategy

1. **先红**：新增 `tests/test_round_model_alignment.py`，钉住：
   - 新模型七要素在各自的必须文件里出现；
   - 旧口径词表在规范面不出现；
   - checker 三处提示已同步；
   - 两份当前规格与 delta 的 Requirement 标题/正文一致。
   先跑指定测试确认**红**（记录原始输出）。
2. **再改**：先改规则文档与规格，再改 checker 提示字符串，最后同步本地入口。
3. **变异验证**：临时把 `AGENTS.md:104` 的措辞改回旧口径，指定测试至少 1 failed；恢复后复绿。
   变异不提交，结果记入 `reviews/building-review.md` 的测试节。
4. **全量**：`uv run pytest -q` 全绿；`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`；
   `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`；witnessloop
   `check --base origin/master --head HEAD` 在内容提交 + 三份 manifest 之后判绿。

## 诚实边界

- 20 上限、批次冻结、deferred、severity 是**流程规定**，不是机械门禁判据；`check` 不解析
  这些正文。文档守卫只钉「措辞在场」，不证明语义执行；语义由独立零记忆审阅者逐项核对。
- 不承诺「20 轮内一定收敛」；只承诺「超过 20 轮时给出可行动的结论：重开设计」。
- 本 change 不改任何运行时行为；`agent/**`、`web/**`、benchmark 与 CI workflow 均不受影响。

## Open Questions

（无）

用户 2026-10-17 已把模型、20 上限、medium+/low 口径、两环共用全部拍板；本设计没有需要用户
再拍板的开放问题。若实现或评审中出现只有用户能拍的（例如改变 20 这个数、改变 severity 口径），
按停轮门要求停下报告，不自行编答案。

## Risks / Trade-offs

- **R1｜措辞扩散**：旧口径散落在 10 个规范/规则落点 + 3 处提示文案；漏一处就会出现两套规则。
  → 显式 allowlist + 全仓 grep 验收项逐处核对。
- **R2｜`CHANGES_REQUESTED` 语义漂移**：旧读法把它当出口；新模型必须写明它**不是出口**。
  → 规格与规则文档各写一条；文档守卫钉住「不是出口」。
- **R3｜20 上限被误读成「到点收工」**：必须写「超限 = 建议重开设计」，不是照合。
  → 规格 Scenario 与规则文档逐字写。
- **R4｜`check` 绿 ≠ 模型被执行**：诚实边界必须写进 design/proposal，避免过度承诺。
- **R5｜本地入口漂移**：`/home/happy/my-agent/.claude/commands/review-loop.md` 不在版本控制内；
  不同步就会出现「仓库已改、实际入口仍旧」。
- **R6｜证据时序**：manifest 与内容改动不得同提交；归档 move 之后用归档目录名重建 manifest
  （#29 次序）。squash 合入会切断证据祖先链，必须 `--merge`。

## Pre-Implementation Review

> 本节由 grill 与设计阶段对抗闭环的结论回填。

（待回填）
