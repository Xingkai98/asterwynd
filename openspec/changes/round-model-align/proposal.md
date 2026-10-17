# Proposal: 轮次口径对齐 witnessloop——有界批次 × 20 轮上限

关联跟踪 issue：[#305](https://github.com/Xingkai98/asterwynd/issues/305)（保持 OPEN；本 change 是流程规则镜像，不是该 issue 的关闭动作）。

> **状态：用户已把全部核心参数拍板。** 轮 = 一个非空 medium+ 批次的闭环；最多 20 个已收口轮；
> medium+ 必须全修、low/nit 可登记不修但须写理由；两环共用；frontier 追问轮豁免。
> 本 change 不重开这三个参数，设计里不应再有需要用户拍板的 Open Question。

## Change Type

- primary: process
- secondary: []

## Why

上一版 `review-loop-no-round-cap`（PR #314，merge `d0197b1`）把固定的「3 轮封顶」换成了
「**无上限 + 收敛判据**」：收敛 = 一轮下来没有新的 medium+ 可证伪项且所有必须修改项已落库；
无法收敛 = 从第 3 轮起最近两轮开放的必须修改项数没有下降。这个模型解决了「固定轮数把还在
净进展的闭环掐掉」的问题，但**没有定义「一轮」本身**：审阅者可以在开发者修复期间不断追加
新问题，轮次仍然不可数、单轮工作量仍然无界。

用户随后重新定义了「一轮」，并已在 witnessloop 落地（PR #40/#41，issue #24 已关闭）：

> **一轮 = 一个非空 medium+ 批次的闭环**：审阅者开一批 medium+ → 开发者全部修完 →
> 审阅者只做修复验证（新问题不许当场提，只能记入下一批 deferred）→ 全部修好 ⇒ 本轮结束；
> 下一轮才提新一批（含 deferred）。**不许边改边提。**
>
> 参数：最多 **20 个已收口轮**；第 20 轮后下一次开批仍非空 ⇒ 超上限 `BLOCKED` +
> 「**建议推倒重开（revise the design）**」。medium+ 必须全修；low/nit 可登记不修但须写理由。
> 出口只有 `PASS` / `BLOCKED` + 成因 / 超上限 `BLOCKED`。设计对抗环与实现审阅环共用；
> grill 的 **frontier 追问轮豁免**（仅指进入对抗环之前的求完备阶段）。

asterwynd 的规则面仍写着上一版口径，与 witnessloop 已落地的模型不一致。本 change 把本仓
**镜像到同一口径**，避免「同一个流程在两个仓里按两套轮次定义执行」。

## 需求

1. **重定义「一轮」**：一轮 SHALL 是一个**非空 medium+ 批次**的闭环（开批 → 全修 → 只验证 →
   收口）；单次审阅意见、单次修复提交、单次验证 SHALL NOT 各自计为一轮。
2. **批次冻结**：批次成员与 severity 在开批后冻结；轮内不得增删替换，不得静默降级。
3. **验证期禁提新问题**：验证只确认当前批次逐项是否修好；新发现的 medium+ 只进
   `deferred`（下一批），low/nit 只进登记表；例外是「该问题使当前轮验证失去意义或继续不安全」
   ⇒ `BLOCKED` + 成因。
4. **20 轮上限**：最多 20 个**已收口轮**；第 20 轮收口后做一次收口确认，若仍有 medium+ ⇒
   超上限 `BLOCKED` +「建议推倒重开（revise the design）」；第 20 轮自身达到验证重试终止点
   同样判超上限。**这不是「到轮数就停」**。
5. **severity 口径**：medium 及以上必须全部修完并验证通过；low/nit 可登记不修，但必须逐条
   写理由；最终 `PASS` 报告带累积登记。
6. **出口**：只有 `PASS` / `BLOCKED` + 成因 / 超上限 `BLOCKED` 三种；
   `CHANGES_REQUESTED` 只是轮内状态，不是出口。
7. **两环共用 + frontier 豁免**：设计阶段对抗环与实现后 `/review-loop` 使用同一模型；
   grill 在进入对抗环之前的 frontier 追问轮不计入 20，也不受「验证禁提新问题」约束。
8. **同步全部规范面**：`AGENTS.md`、`README.md` / `README_EN.md`、`docs/requirements-process.md`、
   `docs/interview-script/questions/Q14-dev-process.md`、两份当前规格，以及
   `scripts/check_openspec_artifacts.py` 的**提示文案**（判定逻辑一行不改）。
9. **同步本地入口**：`/home/happy/my-agent/.claude/commands/review-loop.md`（被 gitignore、
   不进版本控制，但它是 agent 日常实际加载的入口）也改为同一口径。

## 非目标

- **不改 witnessloop 仓**，也不动它的 `v1` / `v1.7.0` tag；只读引用其模板与归档 change。
- **不新增任何机械正文解析**：`check` 仍只判证据存在与 manifest 绑定；20 上限、批次冻结、
  deferred、severity 都是**流程规定**，不是机械判据。
- **不改 `scripts/check_openspec_artifacts.py` 的判定逻辑**：只改三处提示字符串。
- **不回填历史**：`openspec/changes/archive/**` 与历史 review 报告记录的是当时的规则，不动。
- **不改任何运行时行为**：`agent/**`、`web/**`、benchmark、CI workflow 均不受影响。
- **不重新讨论用户已拍板的参数**（20、medium+/low、两环共用）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `dev-workflow-state-machine`：**删除**旧的「终止条件为收敛，而非轮数上限」Requirement，
  **新增**「审阅闭环的轮次模型为有界批次，最多 20 个已收口轮」Requirement（含轮定义、
  批次冻结、验证禁提新问题、deferred、severity、20 上限、三出口、两环共用 + frontier 豁免、
  机械门禁不新增正文解析，以及对应 Scenario）；**修改**「开发流程精简为 OpenSpec 主干 +
  强制审阅闭环」中的两处「再审直到收敛」为批次模型（`:258` 与 `:347`）。
- `change-documentation`：**修改** `Pre-implementation design grilling` Requirement——把
  「no fixed round limit / until convergence」改成与 witnessloop 一致的有界批次模型，
  其余正文与 Scenario 逐字保留。

## Impact Analysis

> 行号基于 `origin/master` = `d0197b1`（2026-10-17 fetch）。

- **规格（当前树，受保护路径）**：
  - `openspec/specs/dev-workflow-state-machine/spec.md:445-486`：旧 Requirement「审阅闭环的
    终止条件为收敛，而非轮数上限」整条删除（REMOVED），由新模型 Requirement（ADDED）承载。
  - `openspec/specs/dev-workflow-state-machine/spec.md:254-350`：`开发流程精简为 OpenSpec
    主干 + 强制审阅闭环` 的正文（`:258`）与一个 Scenario（`:347`）仍写「再审直到收敛」；
    本 change 以 MODIFIED delta 把它改成「按有界批次模型推进」，其余正文与 Scenario 逐字保留。
  - `openspec/specs/change-documentation/spec.md:29-120`：`Pre-implementation design grilling`
    的正文（`:41-55`）与一个 Scenario（`:88-98`）仍写 `no fixed round limit` / `until
    convergence`，需同步为批次模型；其余段落与 Scenario 逐字保留。
- **规则文档（现行规则，不是历史记录）**：
  - `AGENTS.md:18`（设计阶段闭环「再审直到收敛——无轮数上限」）与 `:104`（实现后闭环
    同一口径）。
  - `README.md:148` 与 `README_EN.md:148`（同一句流水线图，**必须同改**）。
  - `docs/requirements-process.md:45`（实现后闭环）与 `:189`（设计阶段闭环）。
  - `docs/interview-script/questions/Q14-dev-process.md:13` 与 `:56`（现行规则要点）；
    `:17` 的 #99 历史案例（「3 轮审阅」）**保留原文**——它记录的是当时的经过。
  - `docs/development-guide.md`：**无需改正文**；已核对无旧口径，只有 `:296` 的 manifest
    时序与 `:391` 的命令命名，与本模型不冲突。
- **代码（仅提示文案）**：`scripts/check_openspec_artifacts.py:1139`、`:1623`、`:1640`
  三处提示字符串。**判定逻辑、触发条件、返回值一行不改**。已检索 `tests/`，没有断言这三句
  文案的测试。机械判据分属两侧：witnessloop `check` 管孤儿报告 / reviewer 身份 /
  revision/hash / `stage=grill` 正文；`scripts/check_openspec_artifacts.py` 管 manifest
  字段 / hash / verdict 与归档点完成度门。本 change 不新增任何正文解析。
- **测试**：新增 `tests/test_round_model_alignment.py`，用**显式 allowlist + per-file 映射**
  钉住规范面：每个规范文件各自含有与它角色相符的核心要素（轮定义 / 批次冻结 / deferred /
  20 上限 / 三出口等），旧口径词表（`无轮数上限` / `最近两轮` / `3 轮封顶` / `round cap` /
  `no fixed round limit` / `再审直到收敛` / `until convergence` / `收敛即停` 等）不在规范面；
  同时断言 checker 三处提示已同步。历史归档与历史 review 报告**不在扫描面**。
- **簿记（受保护路径）**：`docs/openspec-change-backlog.md` 先在 `## 未实现队列` 登记本
  change，收尾前移除；配 `backlog_updated` 解释事件。
- **本地入口（不进版本控制）**：`/home/happy/my-agent/.claude/commands/review-loop.md`
  同步为批次模型；不混进 PR。
- **不影响**：`agent/**`、`web/**`、`.github/workflows/**`、`scripts/flow-policy.json`、
  `.witnessloop/policy.json`、branch protection 实况。
- **行为变更（用户可见）**：无运行时行为变化；变的是**开发流程规则**与门禁提示文案。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 命中 `AGENTS.md` 判据表的「走 grill 的非平凡 change」——本 change 明确安排独立 grill
  与设计阶段对抗闭环，有 8 条 Decision 与两份 spec delta；同时它是规则/流程变更，需逐字对齐
  一个已落地的上游实现（witnessloop），属于「对标业界产品/上游实现」。因此按 `full` 做完整 RIR。
- research questions:
  1. witnessloop 最新模型对「一轮」「已收口轮」「20 上限」「deferred」「三出口」的**逐字定义**
     是什么？哪些细节容易在镜像时丢失（验证重试终止点、severity 冻结、收口确认、累积登记、
     frontier 豁免）？
  2. asterwynd 当前规则面（PR #314 之后）与 witnessloop 最新模型的**差异面**有哪些？
     哪些是文本、哪些是规格、哪些是机械门禁文案？
  3. 镜像到什么程度：只对齐「流程语义」，还是也搬 witnessloop 的机械判据？
- findings:
  1. **权威模板已落地**（`gh api repos/Xingkai98/witnessloop/contents/templates/review-loop.md`,
     `main` = `98b97b7`）：一轮 = 一个非空 medium+ 批次闭环；开批只列 `blocker/high/medium`；
     批次冻结（含 severity）；验证只做修复确认；验证期新问题进 `deferred`；medium+ 全修；
     low/nit 登记不修须写理由；最多 20 个已收口轮；收口确认空批 ⇒ `PASS`，非空 ⇒ 超上限
     `BLOCKED` +「建议推倒重开（revise the design）」；`CHANGES_REQUESTED` 不是出口。
  2. **`templates/grill.md` 明确两环同构 + frontier 豁免**：设计阶段对抗环按同一批次模型；
     frontier 追问轮仅指进入对抗环之前、为求设计树完备的内部轮，不计入 20，也不受「验证禁提
     新问题」约束；由对抗环批次项驱动的设计探索属于该轮修复，不得改标为 frontier。
  3. **归档 change `2026-10-17-convergence-based-stop` 给出了完整语义与边界**：验证重试终止点
     （同一项第二次及以后判 `未修好` 且拿不出新的可验证修复方案 ⇒ `BLOCKED`；第 20 轮触发则
     是超上限 `BLOCKED`）、severity 冻结、deferred 以原 id 传递、轮数按 change/环累计、
     报告 schema（本轮判定 / 批次 / 验证 / deferred / low-nil / 收口确认 / 闭环出口）、
     `check` 不新增正文解析。其 spec delta 的 7 条 Requirement 是本 change 语义对齐的直接依据。
  4. **asterwynd 现状**（`d0197b1`）：`AGENTS.md:18,104`、`README.md:148`、`README_EN.md:148`、
     `docs/requirements-process.md:45,189`、`Q14:13,56` 与
     `scripts/check_openspec_artifacts.py:1139,1623,1640` 仍写「无轮数上限」；
     `openspec/specs/dev-workflow-state-machine/spec.md:445-486` 的 Requirement 仍以
     「最近两轮净进度」定义无法收敛；`openspec/specs/change-documentation/spec.md:47,52,88,96`
     仍写 `no fixed round limit`。PR #314 只改了这些点，没有定义「一轮」。
  5. **机械面差异**：asterwynd 的 `check_openspec_artifacts.py` 对 `building-review` /
     `grill-adversarial` 只判存在（`scripts/check_openspec_artifacts.py:1636-1640`），
     witnessloop 的 `stage=grill` 正文判据仍会解析决策记录。⇒ 本 change 不新增任何正文解析，
     20 上限/批次冻结/deferred 仍靠模板与独立审阅者执行；文档守卫只钉措辞在场，不证明语义执行。
  6. **本地入口独立**：`/home/happy/my-agent/.claude/commands/review-loop.md` 是 gitignored 的
     本地命令，版本控制内的改动不会自动传播；必须单独同步（对照 `git check-ignore` 实测）。
- design impact:
  - ⇒ 用 witnessloop 的**批次模型**替换 asterwynd 的「收敛趋势」定义；保留 `PASS` / `BLOCKED`
    三态值，但明确 `CHANGES_REQUESTED` 只是轮内状态。
  - ⇒ 采用 `REMOVED + ADDED` 的 spec delta 形态替换旧 Requirement，避免在标题仍写
    「而非轮数上限」的情况下塞入 20 上限造成自相矛盾。
  - ⇒ 所有规范面使用同一套 canonical 措辞；测试用显式 allowlist 做文档守卫，历史归档不回填。
  - ⇒ 不搬 witnessloop 的机械判据（跨轮账本、manifest 正文解析）；只对齐流程语义与出口。

## 用户故事

- 作为本仓维护者，我在 `AGENTS.md` / `README.md` / 规格里看到的是**同一个**轮次模型，
  而不是「本仓无上限、上游有界批次」的两套口径。
- 作为执行审阅闭环的 agent，我开一批 medium+ 后只修这一批，验证期发现的新问题记入下一批，
  不会「边改边提」把单轮工作量拖成无界。
- 作为设计阶段执行者，我知道 grill 的 frontier 追问轮不计入 20，但一旦进入对抗环，
  就必须按批次模型推进。
- 作为后续接手者，我能从规格里看到 20 上限是**安全上限**（超限 = 建议重开设计），
  不是「到点收工」。
