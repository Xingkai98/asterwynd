# Design: 审阅闭环去掉轮数上限，改为「无收敛才停」

## Context

用户的指令是：「**不用管 3 轮这个上限了，你修到收敛，然后项目里把 3 轮上限去掉**」。它同时给了两个动作：**实际工作按无收敛才停跑**（已经在跑：witnessloop 侧跑到 12 轮 / 8 轮才收敛，本仓阶段 C 也跑了多轮），以及**把仓库里的规则文案改掉**。

本 change 只做**后者**——仓库里的规则与门禁文案仍写着「PASS 或 3 轮封顶」，落后于实际执行，而且落后在「收紧」的方向（会让人在未收敛时停下）。

三条来自实测的硬事实决定本设计的形状：

1. **本仓自己的两半流程用了两套终止条件**：`openspec/specs/dev-workflow-state-machine/spec.md` 已为**设计阶段**闭环写了「再审直到收敛」，而**实现后**的 `/review-loop` 仍写「PASS 或 3 轮封顶」。同一条流程不能一半收敛、一半数轮数。
2. **「cap 与收敛脱钩」有实录**：witnessloop 的 change `convergence-based-stop`（issue #24）逐条复核过——一个环在 3 轮 cap 下**照旧跑到 R5**，另一个环把「封顶」写成停轮理由后**又跑了 R4–R6**。⇒ cap 是一个与收敛无关的任意常数，这不是本 change 新造的推理。
3. **没有测试钉住这句文案**：`git grep "3 轮封顶" -- tests/` 为空 ⇒ 门禁提示的字符串可以安全改写，不需要改测试。

## Goals / Non-Goals

**Goals:**

- 删掉**版本控制内**所有现行规则里的「3 轮封顶 / 轮数封顶」，统一改成「**无轮数上限**：审 → 改 → 再审，直到**收敛**」。
- 把终止条件**写进规格**（`dev-workflow-state-machine` 新增一条 Requirement），使它成为可引用的规范而不只是散文。
- 把「**无法收敛 ⇒ 停下来报告阻塞**」写成显式出口；明确**不以轮数作为停止条件**。
- 让本 change 自己的 PR 在 `gate / check` 下判绿（它改了 `scripts/**` ⇒ 会触发 `building` 与 `grill-adversarial` 两个 stage 判定）。

**Non-Goals:**

- **不引入任何新的数值上限或下限**（不写「最多 N 轮」「至少 M 轮」）。
- **不搬 witnessloop 的收敛账本 / 判据 A,B′ / 终止性证明**——那是工具自身的实现级设计；本仓只需要规则层面的终止条件（Decision 3）。
- **不改判定逻辑**：`scripts/check_openspec_artifacts.py` 只改两处提示字符串。
- **不回填历史归档**（`openspec/changes/archive/**` 与历史 review 报告记录的是**当时**的规则）。
- **不把 `.claude/commands/review-loop.md` 混进本 PR**（本地文件、被 gitignore、不在版本控制内——见 R3 的如实登记）。

## Decisions

### Decision 1: `primary: process` + `research_tier: light`

**选择**：`## Change Type` 取 `primary: process`；`research_tier: light` + `status: enabled`。

**理由**：
- 改的是**开发流程规则**，不是某个能力域的运行时行为 ⇒ `process`（与 `witnessloop-adoption`、`stage-c-required-switch` 两个流程 change 的先例一致）。
- `light`：这是「成熟模式的局部应用」——同一条迁移线上的 witnessloop 已经做过同一件事（`convergence-based-stop` / issue #24），有直接可比的先例；不引入框架/协议/依赖，也不是架构级改造。**不是 `exempt`**：本 change 有一处真实的取舍（对齐到哪一层，见 Decision 3），不是「无待定设计项」。

### Decision 2: 终止条件写成**可判定的自然语言**，不写任何数值阈值

**选择**：规范与文案统一使用这套判据——

> **无轮数上限**：审 → 改 → 再审，直到**收敛**——一次审阅下来**没有新的可证伪项**，且此前列出的**所有「必须修改项」都已落库**。出现 `BLOCKED`、或反复修仍不断冒出新的可证伪项（**无法收敛**）时，停下来报告**阻塞**；**不以「已达某个轮数」作为停止理由**。

**理由**：
- 用户的指令明确要求「**别自作主张加码**」：任何「最多 N 轮」「至少 M 轮」都是把同一个任意常数换个名字。
- 「收敛」必须**可判定**，否则会退化成「感觉差不多了就停」：故写清两个条件（**没有新的可证伪项** + **必须修改项全部落库**）。这两条都能在审阅报告里逐条对照，不需要新机制。
- 「无法收敛」必须有自己的出口，否则「去掉上限」会被读成「无限循环」——出口就是 `BLOCKED` / 报告阻塞（与现有三态 verdict 对齐）。

**被否决的替代方案**：① 写「最多 5 轮」（换一个常数，同样与收敛脱钩）；② 只写「直到收敛」不定义收敛（不可判定，等于把判断权留给感觉）；③ 保留 cap 但改成「软上限」（仍是没被要求的新机制）。

### Decision 3: 语义对齐 witnessloop 的 `convergence-based-stop`，但**只对齐「停的条件」**，不搬它的机制

**选择**：本 change 只取先例的**终止语义**（无上限 + 收敛即停 + 不收敛则交人/报阻塞）；**不引入**它的收敛账本、判据 A/B′、DP 终止性证明。

**理由**：
- 先例的机制是为**工具自身**服务的：它要处理机器可读的跨轮账本（同一个 id 跨轮沿用、新增 / 遗留 / 已关闭），所以需要形状判定与终止性证明。本仓的 `/review-loop` 是**人/agent 按文档执行**的流程，没有那样的账本；为它发明一套等于**加码**，正是用户明确不要的。
- 但**语义必须同向**：两套流程描述的是同一件事（审阅闭环什么时候停），若本仓写成「数轮数」，就会与已经收敛口径的设计阶段闭环、以及 witnessloop 侧互相矛盾。
- ⇒ 这是本 change **唯一的实质取舍**：**对齐到「停的条件」，不对齐到「机制」**。理由已写进本 Decision，而不是留成开放问题。

### Decision 4: 规格用 **ADDED** 一条新 Requirement，不 MODIFIED 现有条目

**选择**：在 `dev-workflow-state-machine` 的 delta 里用 `## ADDED Requirements` 新增 `### Requirement: 审阅闭环的终止条件为收敛，而非轮数上限`；现有的 `### Requirement: 开发流程精简为 OpenSpec 主干 + 强制审阅闭环` **不删不改**。

**理由**：
- 现有条目**没有**写轮数上限（它写的是「强制独立 subagent 审阅闭环」，终止条件没提）⇒ 没有「被证伪的断言」需要 MODIFIED。本 change 是**补上**一条此前缺失的规范。
- MODIFIED 需要逐字重现那条很长的 Requirement（含 9 个 Scenario），本 change 与它的内容**零冲突**；整条重写只会制造无法独立评估的 diff。

### Decision 5: 门禁文案只改字符串，不改任何判定逻辑

**选择**：`scripts/check_openspec_artifacts.py:1139` 与 `:1623` 的「请用 /review-loop 跑审阅闭环（审→改→再审直到 PASS 或 3 轮封顶）。」改为收敛口径；**周围的条件、返回值、调用点一行不改**。

**理由**：这两处只是给人看的提示；改判定逻辑会改变门禁语义，超出「把 3 轮上限去掉」的范围。实测也确认**没有测试钉住**这句文案（否则需要同步改测试）。

### Decision 6: 历史归档不回填；`.claude/` 本地文件不进 PR

**选择**：
- `openspec/changes/archive/**` 与历史 `reviews/*.md` 里的「3 轮封顶 / 封顶轮」**一律不动**。
- `.claude/commands/review-loop.md`（本地、gitignore、不在版本控制内）**不进本 PR**；它仍是旧文案这件事在 R3 里如实登记。

**理由**：
- 归档与历史报告描述的是**当时的规则**；回填会让「当时到底怎么规定的」失去可追溯性（与本仓对历史归档的一贯口径一致）。
- `.claude/` 不进 diff、不产生 PR、不受门禁约束；把它混进来会制造「改了但版本控制里看不到」的假象。

### Decision 7: 用**一套 canonical 措辞**逐处替换，并用 grep 机械校验

**选择**：所有落点使用 Decision 2 的同一套措辞（按篇幅可压缩，但**四要素不得缺**：① 无轮数上限；② 收敛 = 没有新的可证伪项 + 必须修改项全部落库；③ 无法收敛 ⇒ 报告阻塞；④ 不以轮数为停止理由）。改完后用 `git grep` 证明：版本控制内（排除 archive）**再无**「3 轮封顶 / 轮数封顶」。

**理由**：同一概念多套说法是未来的漂移点——正是本 change 要消除的那种不一致（两半流程两套终止条件）。grep 校验让「改齐了」成为**可复核**的结论，而不是「我记得都改了」。

## Pre-Implementation Review

> 本节由 grill 与设计阶段对抗闭环的结论回填。

**独立设计追问（grill）**：由独立零记忆 subagent 对本文档逐项挑战，产出 `reviews/grill-design.md`。重点挑战面见 `grill.md` 的 7 个维度；其中**第 7 条（触发与门禁）**对本 change 尤其关键——它改了 `scripts/**`，会触发 witnessloop 的 `building` 与 `grill-adversarial` 两个 stage 判定。

**设计阶段对抗闭环**：grill 产出后、停轮前，按 issue #298 的口径再跑一个与 `/review-loop` **同构**（独立零记忆审阅者 → 对抗分析 → verdict → 修 → 再审直到**收敛**）但**审设计而非代码**的闭环，产出 `reviews/grill-adversarial.md`。能由仓库事实判定的问题用证据（`文件:行号`）给出答案、移出停轮队列。

**停轮结论**：本 change 的语义**已由用户拍板**（去掉上限、修到收敛）。设计里**不应有需要用户拍板的 Open Question**——所有争点都应能用仓库事实（grep 结果、规格行号、先例文档）判掉。**若确实冒出一个只有用户能拍的问题，就停下来写清楚留给他，不代拟答案。**

## Risks / Trade-offs

| # | 风险 | 缓解 |
|---|---|---|
| R1 | **「无上限」被读成「无限循环」** | Decision 2 把终止性写成两个出口：**收敛**（可判定）或 **报告阻塞**；规范里明写「不以轮数为停止理由」，并**不写任何新上限** |
| R2 | **改漏某个落点**，或某处仍留着旧口径 | Decision 7 的 grep 校验：`git grep -n "3 轮封顶\|轮数封顶"` 在**排除 archive 后必须为空**；任务里把它写成一条机械验收 |
| R3 | **`.claude/commands/review-loop.md` 仍是旧文案**（本地、gitignore、不在版本控制内） | 如实登记：本 change 只保证**版本控制内**一致；本地文件的下次同步不在本 PR 范围内。**不把它写成「已改」** |
| R4 | **误改历史归档** | 明确 Non-Goal；`git diff --stat origin/master...HEAD -- openspec/changes/archive/` 必须为空（本 change 只会**新增**自己的归档目录） |
| R5 | **同一概念出现多套说法**（漂移点） | Decision 7 的四要素 canonical 措辞 + grep 校验 |
| R6 | **本 change 触发 witnessloop 的 `building` / `grill-adversarial`**（改 `scripts/**` ⇒ `code_hits` 非空） | 按本仓现行口径产三份 witnessloop 形态 manifest；**不放宽任何判据** |
| R7 | **证据带的 PR 被 squash** ⇒ manifest 的 `head_sha` 不再是祖先，日后触及本 change 目录的 PR 判红 | **必须 `--merge`**（witnessloop v1.7.0 的 `_check_git_span`） |
| R8 | **归档次序导致 stale** | 内容（含 `docs/**`）先于证据；归档 move 是独立纯 rename 提交；归档后用**归档目录名**重建 manifest |

## Testing Strategy

本 change **无运行时行为改动**（只改文档、规格与两处提示字符串）⇒ 没有要新增的单元测试。验收由**机械可复核的命令**承担，全部要留原始输出：

| # | 命令 | 期望 | 前置 |
|---|---|---|---|
| T1 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `N passed, 0 failed` | 无 |
| T2 | `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | `OpenSpec artifact checks passed`（exit 0） | 内容已提交 |
| T3 | `uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` | `OpenSpec artifact checks passed`（exit 0） | 内容已提交 |
| T4 | `uv run python scripts/platform_gate.py --verify` | `全部一致`（exit 0）——证明本 change 没动平台实况 | 无 |
| T5 | `/home/happy/wl170/bin/witnessloop check --root . --base origin/master --head HEAD`（**v1.7.0**） | `check：通过 ✓`（0 项） | **内容已提交** |
| T6 | `git grep -n "3 轮封顶\|轮数封顶" -- ':!openspec/changes/archive'` | **无命中**（exit 1） | 无 |
| T7 | `git diff --stat origin/master...HEAD -- openspec/changes/archive/` | 只出现**本 change 自己**的归档路径 | 无 |

**T5 的 revision 必须锚定**：PATH 上那份 witnessloop 是 0.1.0、`/home/happy/witnessloop` 克隆在 tag `v1`，**都不是 CI 用的 v1.7.0**；本 change 用 `/home/happy/wl170`（已装 v1.7.0）。T2/T3/T5 只对**已提交**内容有效（untracked 不进 `git diff`）。

## Impact Analysis

见 `proposal.md` 的 `## Impact Analysis`（同一份清单，避免两处维护漂移）。
