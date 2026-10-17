# Proposal: 审阅闭环去掉轮数上限，改为「无收敛才停」

关联跟踪 issue：[#305](https://github.com/Xingkai98/asterwynd/issues/305)（阶段 C 之后的流程收尾项；本 change 是**规则/流程变更**，不是 docs-only 的随手改）。

## Change Type

- primary: process
- secondary: []

## Why

用户已下过指令：「**不用管 3 轮这个上限了，你修到收敛，然后项目里把 3 轮上限去掉**」。

这条指令不是「3 太小」，而是**「固定轮数」与「有没有收敛」不是一回事**——两者可以完全脱钩：

- **本仓自己的记录就证明 cap 没刹住**：`openspec/specs/dev-workflow-state-machine/spec.md` 已经为**设计阶段**闭环写了「再审直到收敛」，说明「收敛」这个语义在本仓早已被采用；但**实现后的 `/review-loop`** 仍写着「PASS 或 **3 轮封顶**」。同一条流程的两半用了两套终止条件。
- **实际工作早就在按「无收敛才停」跑**（用户点明）：witnessloop 侧的对抗环跑到 **12 轮 / 8 轮**才收敛；本仓阶段 C 的 change 也跑了多轮。⇒ 仓库里的规则文案**落后于实际执行**，而且落后在「收紧」的方向上（文案会让人在未收敛时停下）。
- **「到 3 轮就停」会把「还在净进展」的闭环掐掉**：第 3 轮仍 `CHANGES_REQUESTED` 但每轮都有可修复的新问题，正确动作是继续修，而不是「数到 3」就升级人类。真正该升级人类的是**无法收敛**（`BLOCKED`、或反复修仍不断冒出新问题），那与轮数无关。

⇒ 本 change 把规则与门禁文案改成**收敛即停**，并把这条终止条件写进规格，使它不再只活在对话里。

## 需求

1. **删掉所有现行规则里的「3 轮封顶 / 轮数封顶」表述**，改成「**无轮数上限**：审 → 改 → 再审，直到**收敛**」。
2. **把终止条件写进规格**：新增一条 Requirement，明确「收敛 = 一次审阅下来没有新的可证伪项、且所有必须修改项都已落库」；`BLOCKED` / 无法收敛时**停下来报告阻塞**，**不以轮数作为停止条件**。
   **判据必须可判定**（设计追问 D1 指出初稿的定义在两个场景上会给出相反结论）：① 「必须修改项」SHALL 对齐现有 verdict 规则的**中等及以上严重度**——风格偏好与低价值建议不阻断 `PASS`、不延长闭环；② 补一条**净进度**判据——「最近两轮开放的必须修改项数没有下降」即判为**无法收敛**、报告阻塞。这条是**判定窗口**、不是新的上限（不限制轮数），用于把「还在净进展」与「原地打转」区分开。
3. **定死「无法收敛」的终结语义**：`BLOCKED` 的语义扩为「闭环无法自行推进到 `PASS`」，报告里 SHALL 写明成因，至少区分「阻塞性缺陷」与「无法收敛」；**不新增独立终态**（避免与现有三态 verdict 再分叉）。
4. **统一口径**：`AGENTS.md`（两处）、`README.md` / `README_EN.md`、`docs/requirements-process.md`（两处）、`docs/interview-script/questions/Q14-dev-process.md`（两处）用同一套措辞。
5. **门禁提示文案同步**：`scripts/check_openspec_artifacts.py` 两处提示里的「PASS 或 3 轮封顶」改为收敛口径——**只改提示文字，不改任何判定逻辑**。
6. **补上一条**在现行规格里也写着轮数封顶的地方**：`openspec/specs/change-documentation/spec.md` 的 `Pre-implementation design grilling` Requirement 里同时写着「until PASS or a round cap is reached」与「until convergence」（**文件内部自相矛盾**）——用 MODIFIED delta 改成收敛口径。
7. **不回填历史**：`openspec/changes/archive/**` 与历史 review 报告一律不动（它们记录的是**当时**的规则）。

## 非目标

- **不引入新的上限**（例如「最多 N 轮」「至少 M 轮」都不写）——用户明确要求「别自作主张加码」。
- **不引入 witnessloop 侧那套完整的收敛账本 / 判据 A、B′ / DP 终止性证明**：那是对**工具自身**的实现级设计（witnessloop issue #24），本仓只需要**规则与文案**层面的终止条件。两者语义同向（收敛即停），但**不复制其机制**。
- **不改判定逻辑**：`scripts/check_openspec_artifacts.py` 只动两处字符串。
- **不给历史归档补轮次记录**：`openspec/changes/archive/**` 不动。
- **不改 `.claude/commands/review-loop.md`**（本地文件、被 gitignore、不进版本控制）——它在本地仍是旧文案这件事**如实记录**在 `design.md` 的风险里，处置是「下次本地操作时同步」，不混进本 PR。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `dev-workflow-state-machine`：**新增**一条 Requirement「审阅闭环的终止条件为收敛，而非轮数上限」——把「无轮数上限 + 收敛定义 + 无法收敛时报告阻塞」写成规范约束，并给出**六个** Scenario（没有轮数上限 / 风格建议不阻断收敛 / 收敛即停 / 原地打转判为无法收敛 / 开放数为零时不做净进度判定 / 无法收敛时报告阻塞）。
- `change-documentation`：**修改**一条 Requirement（`Pre-implementation design grilling`）——把该条目内部两处「round cap」改成收敛口径，其余逐字保留。

## Impact Analysis

- **影响规格（两份）**：
  - `openspec/specs/dev-workflow-state-machine/spec.md`：**ADDED 1 条 Requirement**（终止条件为收敛）。现有「开发流程精简为 OpenSpec 主干 + 强制审阅闭环」条目**不删不改**——它没有写轮数上限，本 change 只是把终止条件补成显式的规范。
  - `openspec/specs/change-documentation/spec.md`：**MODIFIED 1 条 Requirement**（`Pre-implementation design grilling`）。该条目**同时**写着「re-review until `PASS` or a round cap is reached」（正文与一个 Scenario 各一处）与「until convergence」（同一段），**文件内部自相矛盾**；本 change 把两处 round cap 改成收敛口径，其余逐字保留。**这是设计追问 D2 抓到的漏项**——初稿只列了 `dev-workflow-state-machine`。
- **影响规则文档**（均为**现行规则**，不是历史记录）：
  - `AGENTS.md`：`:18`（设计阶段闭环的「直到 PASS 或轮数封顶」）与 `:104`（实现后闭环的「直到 PASS 或 3 轮封顶」）。
  - `README.md:148` + `README_EN.md:148`（流水线图里的同一句，**必须同改**）。
  - `docs/requirements-process.md:45`（实现后闭环）与 `:189`（设计阶段闭环）。
  - `docs/interview-script/questions/Q14-dev-process.md:13`（讲稿正文）与 `:56`（要点「3 轮封顶：审阅不会无限循环…」）。
- **影响代码（仅提示文案，无逻辑）**：`scripts/check_openspec_artifacts.py:1139` 与 `:1623` 的提示字符串。**判定逻辑一行不改**，也没有测试钉住这句文案（实测 `git grep "3 轮封顶" -- tests/` 为空）。
- **影响簿记**：`docs/openspec-change-backlog.md`（**登记本 change → 收尾前结算/移除**；受保护路径，配 `backlog_updated` 解释事件）。**时序是硬约束**：backlog 一致性规则要求它不得引用已归档 change，且 `docs/**` 不在 witnessloop 的 stale 豁免集内 ⇒ 移除必须排在证据产出之前。（对抗轮 I-7 指出初稿的 Impact Analysis **漏列**了这一项。）
- **受影响但本 change 不处置（如实登记）**：`.claude/commands/review-loop.md`（本地、gitignore、**不在版本控制内**）仍写着轮数封顶。它不进 PR、也不受任何门禁约束；本 change 只保证**版本控制内的规则**一致，本地文件的下次同步见 `design.md` 的 R3。
- **不影响**：`agent/**`、`web/**`、`.github/workflows/**`、`scripts/flow-policy.json`、branch protection 实况。
- **行为变更（用户可见）**：**无运行时行为变化**；变的是**开发流程规则**——审阅闭环不再有轮数上限，停止条件是收敛。
- **不新增外部依赖**。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: **判据表命中「走 grill 的非平凡 change」**（`AGENTS.md:37` / `docs/development-guide.md:316`）：本 change 明确安排独立 grill（`tasks.md` 0.1）、有 7 条 Decision 与一份 spec delta。初稿声明 `light` 被设计追问 D7 判为「与必须 grill 自相矛盾」⇒ **改为 `full`**，并补齐完整 RIR（研究问题 / findings / design impact 全字段）。它没有引入框架/协议/依赖，也不是架构级改造；但「非平凡」这一条独立命中，足以按 `full` 做。
- research questions:
  1. 「审阅闭环去掉固定轮数上限、改为收敛即停」在同类工具里有没有先例？先例怎么定义「收敛」？
  2. 去掉上限之后，**终止性**怎么保证（会不会「永远在修」）？「还在净进展」与「原地打转」怎么区分？
  3. 本仓与先例的语义**该对齐到什么程度**（只对齐「停的条件」，还是连账本/证明机制一起搬）？「无法收敛」该用什么终态表达？
- findings:
  1. **有直接可比的先例，但它是**未提交的草稿**——引用时必须这么说**：witnessloop（本仓抽出的流程门禁工具）有一个 change `convergence-based-stop`（issue #24），目标正是同一件事。**实测其 change 目录在该工作树里完全未提交**（`git ls-files` = 0、`git status` = `??`），`proposal.md` 自述「草稿」、其 `design.md` 的 Open Questions **尚未停轮确认**。⇒ 它可作为**设计参照**，SHALL NOT 被引作「已经落地的实现」。
     > ⚠️ 初稿写「witnessloop 已经把它自己的审阅闭环改成收敛即停」——**那是事实错误**（它还没落地）。已按实测订正。这正是本项目反复抓到的同类错误：**引用的东西必须真的存在且处于所声称的状态**。
  2. **先例中可复核实录的只有一条**：一个环在 3 轮 cap 下**照旧跑到 R5**（cap 没刹住）。另一处「把『封顶』写成停轮理由后又跑了 R4–R6」在那边被**明确标为时点旁证、在被审 revision 之外、不可在 `ef8b3ab` 上复核**（对抗轮 I-4 指出初稿把它写成了「仓内记录」）⇒ 本 change 按同样口径标。⇒ 「cap 与收敛脱钩」有实录支撑（**不是本 change 新造的推理**）。而「cap 会在还在净进展时掐掉闭环」在那边被**明确标为反事实（风险，非已观测缺陷）**——本 change 沿用同样诚实的定性，不把它写成缺陷。
  3. **先例的终止性靠「收敛判据」，且它拒绝「只删掉 3、跑到 PASS 为止」**：它把「有没有收敛」定义成可判定的形状（`PASS` 即停 / 零位移 / **最近两轮累计净额 ≤ 0** ⇒ `HANDOFF（未收敛）`），并明确以「放弃终止保证」为由拒绝更简的方案。⇒ **去掉上限不等于允许无限循环**；但**只删掉「3」而不补任何收敛判据**，确实会丢掉终止保证。
  4. **对齐程度：对齐「停的条件」的语义，不搬账本机制，但**必须**补一条净进度判据**。先例的完整机制（跨轮账本、判据 A/B′、DP 终止性证明）是为**工具自身**服务的；本仓 `/review-loop` 是**人/agent 按文档执行**的流程，没有账本，不必为它发明一套。但「没有新的可证伪项」本身不足以判定收敛——**原地打转**（每轮都有新项、但开放项数不降）必须能被识别。⇒ 本 change 采用**自然语言的净进度判据**（最近两轮开放必须修改项数是否下降），不引入账本。
  5. **终态语义**：先例用独立 `HANDOFF`（verdict 仍 `CHANGES_REQUESTED` + 终止原因）；本仓现有是三态 verdict（`PASS` / `CHANGES_REQUESTED` / `BLOCKED`）。为避免再分叉出一个终态，本 change 把 `BLOCKED` 的语义扩为「闭环无法自行推进到 `PASS`」并**要求写明成因**（阻塞性缺陷 / 无法收敛）——用现有的状态表达同一件事。
- design impact:
  - ⇒ 终止条件写成**可判定的自然语言判据**：无轮数上限；收敛 = 没有新的可证伪项 + 必须修改项（**中等及以上严重度**）全部落库；**净进度** = 最近两轮开放必须修改项数在下降。**规范里不得出现新的轮数上限**。
  - ⇒ 「无法收敛」的出口：`BLOCKED` + **成因写明**（阻塞性缺陷 / 无法收敛）；明确**不以「已跑满 N 轮」为停止理由**。
  - ⇒ 本 change **不引入** witnessloop 的账本/判据机制（那是工具面）；若将来本仓也要**机器判定**收敛，应去 witnessloop 立 issue 或另立 change。
  - ⇒ 对先例的引用必须标注「**草稿、未提交、未停轮**」——否则就是在引用一个不存在的落地状态。

## 用户故事

- 作为本仓维护者，我读 `AGENTS.md` / `README.md` / `requirements-process.md` 时看到的是**一条**终止条件（收敛），而不是与设计阶段闭环互相矛盾的两种（一半说收敛、一半说 3 轮封顶）。
- 作为执行审阅闭环的 agent，我在第 3 轮之后仍有可修复的新问题时**继续修**，而不是因为「到了封顶轮」停下——除非**无法收敛**，那时我停下来报告阻塞。
- 作为后续接手者，我能从规格里看到这条终止条件是**规范**，而不只是一段文档散文。
