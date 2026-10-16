# Design: 阶段 C 翻开关的记录与规格对账

## Context

`witnessloop-adoption`（已归档 `2026-10-13`）把「asterwynd 自建门禁 → 接入 witnessloop」拆成三个阶段：A 影子接入（只跑不拦）、B 用一个真实小需求跑一遍、**C 真打开**。A 由 PR #308 合入、B 由 PR #309（change `guard-write-allowlist`）跑完，两条都在 issue #305 留了实测结论。

**阶段 C 的形态已由用户在 issue #305 拍板**：required 只留 witnessloop 的 `gate / check`，本仓自建的 `validate` / `benchmark-gate` / `windows-platform` **继续照跑、只是不再拦合并**（降级，不是关闭）。该决策的**实现本体已随 PR #311 合入并 `--apply` 落地**。

本 change 因此**不重新讨论**那个决策，只解决它留下的两个缺口：

1. **阶段 C 没有 change 记录**。PR #311 的 `gate / check` 实测判红 **2 项**——`scripts/platform-gate.json` 属于 `policy.require_change_for` 但该 diff 里没有 change 目录；`.witnessloop/init-manifest.json` 是受保护路径写入但没有结构化解释事件。**两条都属实**（是 `building` 门禁与受保护写入门禁在正常工作）。当时**没有**为了让门变绿去放宽 `require_change_for` 或删 protected path——于是「翻开关」这件事本身缺一条记录。
2. **两处规格与实况不符**（`openspec/specs/**` 是受保护路径，同步它需要 `current_spec_synced` 解释事件，而解释事件必须挂在某个 change 的事件日志上）：
   - `openspec/specs/platform-gate/spec.md:11` / `:13-17`：仍写 required = `validate` + `benchmark-gate`，且有一个名为「benchmark-gate 为 required check」的 Scenario。
   - `openspec/specs/dev-workflow-gate/spec.md:7`：Purpose 段把「阶段 A、只跑不拦、required 仍为两项」写成现状。

三条来自实测的硬事实决定本设计的形状：

1. **实况已核验**：`gh api repos/Xingkai98/asterwynd/branches/master/protection` 的 `required_status_checks.contexts = ["gate / check"]`，`strict=true`、`required_conversation_resolution=true`、`required_approving_review_count=0`、`enforce_admins=true`；`python scripts/platform_gate.py --verify` exit 0「全部一致」。
2. **三个本仓 job 仍在跑**：试探 PR #312 的第二次推送实测——`validate` pass 6m54s、`benchmark-gate` pass 15s、`windows-platform` pass 2m2s 与 `gate / check` fail 并存，`mergeStateStatus = BLOCKED`。⇒ 「照跑但不拦」是**实测事实**，本 change 把它写成规范。
3. **本 change 的 diff 不触达 `require_change_for`**：改动面只有 `openspec/**` 与 `docs/**`。⇒ 它会**建立** change 目录，从而消掉 PR #311 的第 1 条红；第 2 条红（`.witnessloop/init-manifest.json` 受保护写入）**不在本 change 的 diff 里**（那是 #311 已合入的内容），本 change 不为它补证据（见 Decision 7）。

## Goals / Non-Goals

**Goals:**

- 给阶段 C 补一条**完整**的 change 记录（proposal / design / tasks / spec delta / reviews / 事件日志），并走完本仓流程：grill → 设计阶段对抗收敛 → 实现（规格同步）→ 独立审阅闭环 → 三份 stage manifest → `gate / check` 判绿 → 归档。
- 把 `platform-gate` 与 `dev-workflow-gate` 两份规格同步到实况，并把「**降级不是关闭**」写成规范约束。
- 让本 change 自己的 PR **满足** witnessloop 契约（`gate / check` 绿），证明这套流程对「只改规格与文档」的 change 是可走通的。

**Non-Goals:**

- **不下掉任何检查**（原阶段 C 的 C.2）。三个本仓 job 继续跑；「逐项下掉旧件」是后续独立 change。
- **不改 `.github/workflows/ci.yml`**、**不关任何 workflow**、**不删任何检查**、**不改 `scripts/platform-gate.json`**（目标状态已由 #311 落地）。
- **不改任何运行时代码**（`agent/**` / `scripts/**` / `web/**` / `benchmarks/**`）⇒ 本 change **无代码测试面**，TDD 一节按「无代码」处置（见 Decision 5）。
- 不统一 manifest schema（N.4）、不处理 `add-minimal-tui-runtime-view` 的已知红（K1）、不碰 witnessloop 仓与 `v1` / `v1.7.0` tag。
- 不为 PR #311 那第 2 条红补证据（Decision 7）。

## Decisions

### Decision 1: `primary: process` + `research_tier: exempt`

**选择**：`## Change Type` 取 `primary: process`（`secondary: []`）；`research_tier: exempt` + `status: disabled`。

**理由**：
- `process` 与唯一的同类先例一致——`openspec/changes/archive/2026-10-13-witnessloop-adoption/`（同一条迁移线的阶段 A）就是 `primary: process`。本 change 改的是**流程/治理形态与规格**，不是某个功能域的能力，`feature` / `refactor` / `docs` 都不贴。
- `exempt` 的判据是「**上游决策锁定**（引用已关闭决策 issue/架构评审结论，无待定设计项）」：required 的最终形态由用户在多阶段跟踪 issue #305 拍板，分阶段顺序与「阶段 A 不勾 required」的依据已记录在 `openspec/changes/archive/2026-10-13-witnessloop-adoption/` 的 Decision 4 / Decision 5 / tasks C.1，实现已随 PR #311 合入。**本 change 没有可供业界对比的设计空间**——它不是「有设计空间的新功能」（那类按判据表至少要 light）。
- ⚠️ 诚实标注：`process` 与 `exempt` 的组合按 AGENTS.md 的判据表**不是唯一解**（也可以论成 `light`）。选 `exempt` 的理由是「本 change 没有引入任何能力面、也没有任何待定取舍」这一实质，而不是「调研太贵」。**该选择在 `reviews/grill-adversarial.md` 里被独立审阅者专门挑战过一次**（见该报告）。

### Decision 2: `platform-gate` 规格用 **MODIFIED 覆盖重写**既有 Requirement，不平行新开一条

**选择**：delta 用 `## MODIFIED Requirements` 覆盖重写 `### Requirement: 合入平台闸门` 与 `### Requirement: 平台闸门复用 GitHub branch protection 语义` 两条；同步时**就地覆盖**当前规格里对应段落。

**理由**：
- 这两条 Requirement 的**语义变了但意图没变**（「合入受平台闸门约束」这件事没改，改的是约束里列举的 required 集合）。平行新增一条会让规格里同时存在「required 是 validate+benchmark」与「required 是 gate/check」两条互相矛盾的 Requirement。
- 先例：`guard-write-allowlist` 同步 `workspace-safety` 时对 `### Requirement: 工作区策略支持配置扩展` 用的就是 MODIFIED 覆盖重写（其后按 `platform-gate` 先例在 `witnessloop-adoption` 的 Z.2 里也有整份覆盖重写的做法）。

**被否决的替代方案**：① 只加 ADDED 不动旧条 —— 规格自相矛盾；② 整份覆盖重写（Z.2 那次的做法）—— 本 change 只动两条 Requirement，整份重写会制造无法独立评估的 diff（`dev-workflow-gate` 那份有 12 条 Requirement，其中 10 条与阶段 C 无关）。

### Decision 3: `dev-workflow-gate` 的阶段 A 专属 Requirement 按 **REMOVED** 处置，另加阶段 C 条目

**选择**：`### Requirement: 影子接入阶段不改变任何既有强制` 走 `## REMOVED Requirements`（带 Reason / Migration 两段）；新增 `### Requirement: 阶段 C 翻开关后的 required 形态`。

**理由**：那条 Requirement 的正文与三个 Scenario **全部是阶段 A 的过渡态约束**，其中第三条（「合入之后新 PR 会跑但不拦」）在阶段 C 之后**已被证伪**——`gate / check` 现在是 required，会拦。留着它就是让规格描述一个不存在的世界；就地改名会让 MODIFIED 的语义对不上（改的是 Requirement 的**主体**而不只是内容）。REMOVED 的先例见 `openspec/changes/archive/2026-09-22-retire-4phase-state-machine/specs/dev-workflow-state-machine/spec.md`。

**不是 REMOVED 的部分**：`dev-workflow-gate` 里其余 10 条 Requirement（承载分工、定制 policy 前置、验收判据、已知红、守卫退步、两个开关、保留清单、manifest 并存、grill 正文不兼容、双 PreToolUse 守卫）描述的是**仍然成立**的接入形态，逐条保留，只改 Purpose 段。

### Decision 4: 「**降级不是关闭**」写成独立 Requirement，住在 `platform-gate`

**选择**：新增 `### Requirement: 降级为非必过的检查仍须运行`（含「三个 job 照跑」「不得删除或停用」「不得以 `continue-on-error` 之类的开关制造假绿」三条约束与对应 Scenario），放进 `platform-gate` 规格。

**理由**：
- 这是阶段 C **最容易被后人读反**的一条——看到 required 只剩一个，很自然会想「另外两个是不是可以删了」。issue #305 的排期 comment 已把这条区分写死（「『只开 witnessloop 必过』≠『把其他 CI 关掉』…直接关掉 = 门禁**净损失**，不是切换」），但**它此前只活在 issue 与 PR 描述里，不在规格里**。
- 放 `platform-gate` 而不是 `dev-workflow-gate`：这条约束的判据是**平台面**（branch protection 的 required 集合与 `ci.yml` job 的关系），与 `platform-gate` 能力域「定义合入平台闸门的能力边界」的定位一致；`dev-workflow-gate` 描述的是「哪些门禁由谁承载」。

### Decision 5: 无代码面 ⇒ 不写 TDD 测试、不跑 benchmark smoke，判据换成「规格文本可机械复核」

**选择**：tasks 里**不排**「先写失败测试」一节，也**不排** benchmark smoke；验收判据换成四条机械可复核的命令（`openspec validate --all --strict`、`check_openspec_artifacts.py` 两步、`platform_gate.py --verify`、`witnessloop check`）。

**理由**：
- 本 change 的 diff 只有 `openspec/**` 与 `docs/**`，**没有任何可执行代码路径**。「测试先行」在这里没有可测对象；硬造一个测试反而是在测别的 change 留下的行为（`tests/test_platform_gate.py` 的钉子已由 PR #311 一并更新）。
- checker 的 benchmark smoke 触发面是「capability 命中 `BENCHMARK_SMOKE_CAPABILITIES`」或「proposal 提到 `agent/loop.py` / `agent/tools/` / `agent/workspace_policy.py` / `benchmarks/`」——本 change 两条都不命中（能力域是 `platform-gate` / `dev-workflow-gate`）。⇒ **不排 benchmark smoke 是判据的结果，不是漏排**。
- 规格文本的验收靠 `openspec validate --all --strict`（结构）与人工/审阅者逐条对照实况（内容）。**内容真实性无法机械校验**——这正是本 change 要用「实测命令的输出」而不是「引用文档」来支撑每一条断言的原因（见 Testing Strategy）。

### Decision 6: 归档次序按下游修复后的新口径——纯 rename 独立提交 + **归档后**用归档目录名重绑 witnessloop manifest

**选择**：收尾次序固定为 ① 内容提交（含规格同步与 backlog 清理）→ ② 在最终 head 产 witnessloop 三份 manifest → ③ 独立**纯 rename** 提交做归档 move → ④ **在归档目录上、用归档目录名（`2026-10-17-stage-c-required-switch`）重建** witnessloop 三份 manifest。

**理由**（三步都是实测教训，不是推理）：
- **纯 rename**：`witnessloop-adoption` 的 Decision 3 实测「`git mv` 与内容改动同提交 ⇒ git 记作 `A`/`D` ⇒ 归档识别失效」。
- **先内容、后证据**：witnessloop 的 stale 判定只豁免 `<changes_root>/*/reviews/**`、`<changes_root>/*/workflow-events.jsonl`、`.witnessloop/**`、`archive/**`；`docs/**` 与 `openspec/specs/**` **不在豁免内** ⇒ 删 backlog 条目与同步规格必须**排在证据产出之前**。
- **归档后用归档目录名重绑**：阶段 B/C 实测，witnessloop 形态 manifest 里的 `change_id` 必须与 change 目录名一致；归档后目录名带 `YYYY-MM-DD-` 前缀 ⇒ 用 active 名字产的 manifest 会被判「`change_id` 与目录不符」。**在归档目录上用归档目录名重建**是已验证的解法。

### Decision 7: **不为** PR #311 的第 2 条红补证据；本 change 只消掉第 1 条

**选择**：本 change 建立自己的 change 目录（消掉「改了 `require_change_for` 却没挂 change」这条**同类**风险），但**不**为 `.witnessloop/init-manifest.json` 那次已合入的受保护写入补解释事件。

**理由**：
- 那是一次**已合入**的写入，事件只能追加在某个 change 的事件日志里。为它补一条事件，等于**事后给历史提交制造证据**——与本仓在 `guard-write-allowlist` N.6 里拒绝「往已归档目录加文件」的理由同源（会造成语义漂移：事后补的事件不等于当时有的证据）。
- 该红已经**如实记录**在 issue #305 的阶段 C comment 里，作为「翻开关这件事当时没有 change 记录」的**证据**保留。抹掉它反而丢掉了这条教训的可追溯性。
- 若将来有人要一个「干净」的历史，正确做法是在 witnessloop 侧讨论「`init` 升级这类簿记写入该不该算受保护写入」（上游 issue 面），而不是在本仓事后补事件。

### Decision 8: 顺手订正 `docs/development-guide.md` 里阶段 A 遗留的两条 bullet

**选择**：把 witnessloop 节里的「已知红（预期，不放宽判据）：…② 本 change 自己（缺 witnessloop 形态 manifest）」与「`reviews/` 的一致状态…把本 change 自己的红从 2 条拉到 14/16 条」两条按阶段 C 实况改写。

**理由**：这两条是 PR #311 之前的阶段 A 文案，其中的「本 change 自己」指的是**已经归档的** `witnessloop-adoption`。它们描述的对象不存在了，属于**本 change 直接造成的事实变化**（AGENTS.md 的「文档影响检查」要求只更新当前变更造成的事实变化，历史口径问题另记债务）——阶段 C 翻开关正是让它们过期的原因。

## Pre-Implementation Review

> 本节由 grill 与设计阶段对抗闭环的结论回填。两份报告的原文见 `reviews/grill-design.md` 与 `reviews/grill-adversarial.md`。

**独立设计追问（grill）**：由独立零记忆 subagent 对本文档逐项挑战，产出 `reviews/grill-design.md`。挑战面覆盖 `grill.md` 的 7 个维度，其中**第 7 条（触发与门禁：本 change 自身会不会死锁或误伤）**是本 change 的关键维度——它正好要回答「一条只改规格的 change，在 `gate / check` 已是 required 的前提下能不能判绿」。

**设计阶段对抗闭环**：grill 产出后、停轮前，按 issue #298 的口径再跑一个与 `/review-loop` **同构**（独立零记忆审阅者 → 对抗分析 → verdict → 修 → 再审直到收敛或轮数封顶）但**审设计而非代码**的闭环，产出 `reviews/grill-adversarial.md`。**能由代码/仓库事实判定的问题用证据（`文件:行号`）给出答案、移出停轮队列**。

**停轮结论**：本 change 的设计**没有需要用户拍板的 Open Question**——它记录的是一个**已经拍过板、且已经落地**的决定（issue #305 阶段 C）。任何被挑战出来的「待定项」都必须用仓库内的事实（`gh api` 输出、`--verify` 输出、规格行号）当场判掉，而不是留给用户。若确实冒出一个只有用户能拍的问题，处置是**停下来、写清楚留给他**，绝不代拟答案。

## Risks / Trade-offs

| # | 风险 | 缓解 |
|---|---|---|
| R1 | **规格同步写错实况**（把 required 写成别的值） | 每条涉及实况的断言都必须来自**实测命令的输出**：`gh api …/protection` 的 `contexts`、`platform_gate.py --verify` 的 exit code 与逐字段输出。testing strategy 里把这四条列为验收命令 |
| R2 | **「降级」被后人读成「可以删」** | Decision 4 把「三 job 照跑、不得删除/停用」写成独立 Requirement + Scenario；`docs/development-guide.md` 与 `AGENTS.md` 的同向记载已在 PR #311 落地 |
| R3 | **REMOVED 一条 Requirement 会把仍然成立的内容一起删掉** | Decision 3 明确：只 REMOVE 那条**阶段 A 专属**的 Requirement；其余 10 条逐条保留。同步后用 `openspec validate --all --strict` + 逐条核对 Requirement 数量（前/后计数须如实记入事件） |
| R4 | **归档次序踩 stale** | Decision 6：内容（含 `docs/**` 与 `openspec/specs/**`）先于证据；归档 move 是独立纯 rename 提交；归档后用归档目录名重建 witnessloop manifest |
| R5 | **本 change 自己的 `gate / check` 判红**（重演 PR #311） | 本 change 建立 change 目录 + 三份 witnessloop manifest，且不触达 `require_change_for`。实测口径：本地 `witnessloop check` 与 CI 的 `gate / check` 都要绿，**不放宽任何判据** |
| R6 | **`exempt` 档位被质疑为「省事」** | Decision 1 已如实标注它不是唯一解；交由设计阶段对抗闭环专门挑战，结论记入 `reviews/grill-adversarial.md` |
| R7 | **本 change 合入后若再 `--apply`** | **不需要**：`scripts/platform-gate.json` 与实况本 change 前后逐字段一致（`--verify` 已实测 exit 0）。tasks 里显式写「不做 apply」，避免执行者条件反射地跑一遍 |

## Testing Strategy

本 change **无代码面**（Decision 5），验收由四条机械可复核的命令承担，全部要留原始输出：

| # | 命令 | 期望 |
|---|---|---|
| T1 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `N passed, 0 failed` |
| T2 | `uv run python scripts/check_openspec_artifacts.py --base-ref <base> --require-base` | `OpenSpec artifact checks passed`（exit 0） |
| T3 | `uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` | `OpenSpec artifact checks passed`（exit 0） |
| T4 | `python scripts/platform_gate.py --verify` | `全部一致`（exit 0）——**证明本 change 没动平台实况** |
| T5 | `witnessloop check --root . --base origin/master --head HEAD`（v1.7.0） | `check：通过 ✓`（0 项）——**本 change 的出口判据** |

**内容真实性**（T1–T3 管不到的那一半）：规格里每一条涉及 required 集合、job 是否运行、`--apply` 是否已执行的断言，都要能与 T4 的输出、以及 `gh api repos/Xingkai98/asterwynd/branches/master/protection` 的原始 JSON 逐字对上。审阅者按 `文件:行号` 抽查。

## Impact Analysis

见 `proposal.md` 的 `## Impact Analysis` 一节（同一份清单，避免两处维护漂移）。
