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

### Decision 1: `primary: process` + `research_tier: light`

**选择**：`## Change Type` 取 `primary: process`（`secondary: []`）；`research_tier: light` + `status: enabled`（findings 与 design impact 写在 `proposal.md` 的 `## Reference Implementation Research`）。

**理由**：
- `process` 与唯一的同类先例一致——`openspec/changes/archive/2026-10-13-witnessloop-adoption/`（同一条迁移线的阶段 A）就是 `primary: process`。本 change 改的是**流程/治理形态与规格**，不是某个功能域的能力，`feature` / `refactor` / `docs` 都不贴。
- **档位从初稿的 `exempt` 改成 `light`——这是设计阶段对抗闭环 I-6 的直接结论，改由本设计自行拍定、不停轮**。理由：初稿用 `exempt`（reason 命中「上游决策锁定」+ `#305` + 归档路径），机械上能过（审阅者实测 `_check_reference_implementation_research(..., assume_implemented=True)` 返回 `[]`），但**实质不成立**——AGENTS.md 的判据表把「**走 grill 的非平凡 change**」列在 `full` 行，而本 change 走了 grill、有 11 条 Decision，并在 delta 里新增了一条上游没有的规范（Decision 9）⇒ 「无待定设计项」这句站不住。**两处都改的话，`light` 是同时满足判据表两种读法的最小档位**（`exempt` 的反例是「有设计空间的新功能」，本 change 有设计动作但不属于新功能；`full` 要求「架构级改造 / 新框架 / 新协议 / 对标业界产品」，本 change 一条都不命中）。
- ⇒ 代价是一段如实的 findings + design impact（本就不是零调研：下面的调研问题是真实的问题，答案也来自可核对的既有实践）。**这不是为了过闸而抬档，是因为有人能合理地论证「走 grill 的非平凡 change」应当调研**——把它写实比争档位便宜。
- ⚠️ **该判断在 `reviews/grill-adversarial.md` 的 I-6 里被独立审阅者标为「唯一需要人拍的一条」，并同时给出了「改 `light` + `enabled`」的推荐；本设计采纳该推荐 ⇒ 该争点消解，不再构成停轮项。**

### Decision 2: `platform-gate` 规格用 **MODIFIED 覆盖重写**既有 Requirement，不平行新开一条

**选择**：delta 用 `## MODIFIED Requirements` 覆盖重写 `### Requirement: 合入平台闸门` 与 `### Requirement: 平台闸门复用 GitHub branch protection 语义` 两条；同步时**就地覆盖**当前规格里对应段落。

**理由**：
- 这两条 Requirement 的**语义变了但意图没变**（「合入受平台闸门约束」这件事没改，改的是约束里列举的 required 集合）。平行新增一条会让规格里同时存在「required 是 validate+benchmark」与「required 是 gate/check」两条互相矛盾的 Requirement。
- 先例：`guard-write-allowlist` 同步 `workspace-safety` 时对 `### Requirement: 工作区策略支持配置扩展` 用的就是 MODIFIED 覆盖重写（其后按 `platform-gate` 先例在 `witnessloop-adoption` 的 Z.2 里也有整份覆盖重写的做法）。

**被否决的替代方案**：① 只加 ADDED 不动旧条 —— 规格自相矛盾；② 整份覆盖重写（Z.2 那次的做法）—— 本 change 只动两条 Requirement，整份重写会制造无法独立评估的 diff（`dev-workflow-gate` 那份有 12 条 Requirement，其中 10 条与阶段 C 无关）。

### Decision 3: `dev-workflow-gate` 的阶段 A 专属 Requirement 按 **REMOVED** 处置，另加阶段 C 条目

**选择**：`### Requirement: 影子接入阶段不改变任何既有强制` 走 `## REMOVED Requirements`（带 Reason / Migration 两段）；新增**两条** `## ADDED Requirements`——`### Requirement: 阶段 C 翻开关后的 required 形态`（形态与证据次序）与 `### Requirement: 翻开关这一动作自身必须具备 change 记录`（见 Decision 9）。

**理由**：那条 Requirement 的正文与三个 Scenario **全部是阶段 A 的过渡态约束**，其中第三条（「合入之后新 PR 会跑但不拦」）在阶段 C 之后**已被证伪**——`gate / check` 现在是 required，会拦。留着它就是让规格描述一个不存在的世界；就地改名会让 MODIFIED 的语义对不上（改的是 Requirement 的**主体**而不只是内容）。REMOVED 的先例见 `openspec/changes/archive/2026-09-22-retire-4phase-state-machine/specs/dev-workflow-state-machine/spec.md`。

**REMOVED 的判据（设计阶段对抗闭环 I-5 要求写死）**：删一条的**唯一**依据是「它含**被本次变更直接证伪的断言**」，**不是**「它属于阶段 A」。用这条判据逐条复核其余 10 条：

| Requirement | 是否含被证伪的断言 | 处置 |
|---|---|---|
| 流程骨架与项目规则的承载分工 | 否——分工表在阶段 C 后逐条仍成立 | 保留 |
| 接入 witnessloop 前的定制 policy 前置 | 否——policy 四字段与触发面未变 | 保留 |
| 影子接入阶段的验收判据 | 否——它断言的是「阶段 A 用可机械复核的判据收口」，而阶段 A **确实**那样收口了；该 Requirement 记录的是**已履行的验收义务**，不是关于现状的断言 | 保留（见下） |
| 已知红如实记录且不放宽判据 | 否——`add-minimal-tui-runtime-view` **仍**无 `reviews/`，该红仍在；其「不放宽判据」的姿态在阶段 C 反而更重要 | 保留 + **MODIFIED**（补状态迁移，见下） |
| 本地守卫的能力退步必须随接入写明 | 否——退步是**事实**（Bash 拦截面收窄），且其「保留至阶段 C 决策」已被阶段 C 履行 | 保留 |
| 交互层与 CI 层是两个独立开关 | 否——两层仍独立；阶段 C 只改了 CI 层的 required | 保留 |
| 保留为本地规则的项目特有检查 | 否——八项仍在（这正是「降级不关闭」的依据） | 保留 |
| review manifest 两套并存，schema 统一延后 | 否——两套仍并存 | 保留 |
| grill 报告正文判据的已知不兼容 | **是**——原断言「本仓 grill 记录通篇加粗 ⇒ grill stage 结构性不可能判绿」已被阶段 B 实测证伪（63 份归档中 39 份零 finding） | **MODIFIED**（见 Decision 11） |
| 双 PreToolUse 守卫并存且未知面必须实测 | 否——实测结论（并行、并集拦）仍然成立 | 保留 |

**保留「影子接入阶段的验收判据」的理由要说清**（I-5 点名质疑过它）：它读起来像历史，但它的正文是**判据方法**（负向对照：换出厂 policy 后两条 stage 判定消失），而且它的断言从未被证伪——阶段 A 的收口确实按它做了。删掉它会连带丢掉「怎么证明定制 policy 必要」这条可复用的验收方法。**本 change 承认这条保留是「历史义务 vs 规范」的边界情形**，若后续有人要求规格只留「当前有效的规范」，处置方式是把这一组阶段 A 条目集中迁进一个「阶段 A 验收记录」小节，而不是逐条删——那是独立 change 的事。

**另补一条状态迁移（I-5 的第二个发现，本次新增）**：「已知红如实记录且不放宽判据」那条 Requirement 记的是 `add-minimal-tui-runtime-view` 的已知红。**阶段 C 之后这条红的性质变了**——它此前只是日志里的红（`gate / check` 不 required），现在**会拦合入**。这个迁移此前没有任何文档记录，必须写进规格（见 delta 对那条的 MODIFIED）：否则「已知红」会被读成「可以放着不管」，而它现在的正确读法是「**任何触达该 change 的改动都会被它挡住，必须先收尾**」。

### Decision 4: 「**降级不是关闭**」写成独立 Requirement，住在 `platform-gate`

**选择**：新增 `### Requirement: 降级为非必过的检查仍须运行`（含「三个 job 照跑」「不得删除或停用」「不得以 `continue-on-error` 之类的开关制造假绿」三条约束与对应 Scenario），放进 `platform-gate` 规格。**同一条不变量 SHALL NOT 在 MODIFIED 的「合入平台闸门」条目里再写一遍**：MODIFIED 条目只保留 required 集合的断言（唯一 `gate / check`），「仍须运行」的规范性内容**全部**收进本条。理由（设计追问 D7 的实测结论）：两处并存时，未来改一处漏一处不会被任何门禁发现——那是白送的漂移点。

**理由**：
- 这是阶段 C **最容易被后人读反**的一条——看到 required 只剩一个，很自然会想「另外两个是不是可以删了」。issue #305 的排期 comment 已把这条区分写死（「『只开 witnessloop 必过』≠『把其他 CI 关掉』…直接关掉 = 门禁**净损失**，不是切换」），但**它此前只活在 issue 与 PR 描述里，不在规格里**。
- 放 `platform-gate` 而不是 `dev-workflow-gate`：这条约束的判据是**平台面**（branch protection 的 required 集合与 `ci.yml` job 的关系），与 `platform-gate` 能力域「定义合入平台闸门的能力边界」的定位一致；`dev-workflow-gate` 描述的是「哪些门禁由谁承载」。

### Decision 5: 无代码面 ⇒ 不写 TDD 测试；benchmark smoke 因**触发面假阳性**而照跑；判据换成「规格文本可机械复核」

**选择**：tasks 里**不排**「先写失败测试」一节；**benchmark smoke 照排并照跑**（tasks 2.4b，实测 PASS）；验收判据换成五条机械可复核的命令（`openspec validate --all --strict`、`check_openspec_artifacts.py` 两步、`platform_gate.py --verify`、`witnessloop check`）。

> ⚠️ **本节标题与选择句在第二轮对抗复核（N-1）时被指出自相矛盾**：初稿写的是「不跑 benchmark smoke」，而下面的订正段又说「触发面命中就跑」。已按订正后的口径统一为「**照跑**」。

**理由**：
- 本 change 的 diff 只有 `openspec/**` 与 `docs/**`，**没有任何可执行代码路径**。「测试先行」在这里没有可测对象；硬造一个测试反而是在测别的 change 留下的行为（`tests/test_platform_gate.py` 的钉子已由 PR #311 一并更新）。
- **⚠️ 订正（本次实测）**：设计初稿写「本 change 不命中 benchmark smoke 触发面 ⇒ 不排它」。**实测是错的**——`_requires_benchmark_smoke` 除了 capability 名，还有一条**对 proposal 正文的四个正则**（`agent/loop.py` / `agent/tools/` / `agent/workspace_policy.py` / `benchmarks/`），而本 change 在「不影响」清单里**逐项列出了** `benchmarks/**` 这类路径 ⇒ 命中。**这是一次真实的假阳性**（本 change 的 diff 里没有任何 benchmark 代码，触发它的是排除清单的措辞），**但它照跑**：判据命中就跑，跑出来的是真结论；**不靠改一句话让正则不命中来绕开**（那是「为了让门变绿而放宽判据」的邻域）。
  ⇒ 处置：tasks 排 **2.4b** 跑一条 gate-smoke（与 `ci.yml` 的 `benchmark-gate` job 同形）；同时把这条假阳性如实登记，供将来决定是否收窄该启发式（例如让它只在 proposal 的「需求 / Impact Analysis」段内匹配，而不是全文匹配）。**这是本 change 顺带产出的第三条工程发现**（前两条是 Decision 10 的死链与 Decision 11 的 `## User Confirmation` 无条件判据）。
- 规格文本的验收靠 `openspec validate --all --strict`（结构）与人工/审阅者逐条对照实况（内容）。**内容真实性无法机械校验**——这正是本 change 要用「实测命令的输出」而不是「引用文档」来支撑每一条断言的原因（见 Testing Strategy）。

### Decision 6: 归档次序按下游修复后的新口径——纯 rename 独立提交 + **归档后**用归档目录名重绑 witnessloop manifest

**选择**：收尾次序固定为 ① 内容提交（含规格同步与 backlog 清理）→ ② 在最终 head 产 witnessloop 三份 manifest → ③ 独立**纯 rename** 提交做归档 move → ④ **在归档目录上、用归档目录名（`2026-10-17-stage-c-required-switch`）重建** witnessloop 三份 manifest。

**归档 move 的**机制**也必须写死（设计阶段对抗闭环 I-1）：用 `git mv` **手工**做，SHALL NOT 跑 `openspec archive`。**两条实测理由**：
- `openspec` 1.4.1 的 `getArchiveDate()` 用 `new Date().toISOString()`——**UTC**。本机本地日期是 2026-10-17（CST），实测该版本跑 `archive` 输出的是 `archived as '2026-10-16-stage-c-required-switch'`（**前一天的目录名**），与 Decision 6 与 tasks 写死的 `2026-10-17` 不符。
- 该命令把「规格同步 + move」**原子合成一次提交**，直接违反本条 ③ 的「独立纯 rename 提交」，也就破坏了 R4 的 stale 次序理由。

**理由**（三步都是实测教训，不是推理）：
- **纯 rename**：`witnessloop-adoption` 的 Decision 3 实测「`git mv` 与内容改动同提交 ⇒ git 记作 `A`/`D` ⇒ 归档识别失效」。
- **先内容、后证据**：witnessloop 的 stale 判定只豁免 `<changes_root>/*/reviews/**`、`<changes_root>/*/workflow-events.jsonl`、`.witnessloop/**`、`archive/**`；`docs/**` 与 `openspec/specs/**` **不在豁免内** ⇒ 删 backlog 条目与同步规格必须**排在证据产出之前**。
- **归档后用归档目录名重绑**：阶段 B/C 实测，witnessloop 形态 manifest 里的 `change_id` 必须与 change 目录名一致；归档后目录名带 `YYYY-MM-DD-` 前缀 ⇒ 用 active 名字产的 manifest 会被判「`change_id` 与目录不符」。**在归档目录上用归档目录名重建**是已验证的解法。

**补充约束（设计追问 RN1）：本 change 的 PR SHALL 用 `--merge` 合入，SHALL NOT squash。** witnessloop v1.7.0 的 `_check_git_span` 要求 manifest 的 `head_sha` 是「本次被检 head」的**祖先**；squash 会把 PR 的 head sha 从 `master` 历史里抹掉 ⇒ 日后任何触及该 change 目录的 PR 都会因此判红（阶段 A 已有一次实测先例）。前三个 PR（#308 / #309 / #311）都是 merge commit，但那是**惯例不是约束**——本 change 把它写成显式约束。

### Decision 7: **不为** PR #311 的第 2 条红补证据；本 change 只消掉第 1 条

**选择**：本 change 建立自己的 change 目录（消掉「改了 `require_change_for` 却没挂 change」这条**同类**风险），但**不**为 `.witnessloop/init-manifest.json` 那次已合入的受保护写入补解释事件。

**理由**：
- 那是一次**已合入**的写入，事件只能追加在某个 change 的事件日志里。为它补一条事件，等于**事后给历史提交制造证据**——与本仓在 `guard-write-allowlist` N.6 里拒绝「往已归档目录加文件」的理由同源（会造成语义漂移：事后补的事件不等于当时有的证据）。
- 该红已经**如实记录**在 issue #305 的阶段 C comment 里，作为「翻开关这件事当时没有 change 记录」的**证据**保留。抹掉它反而丢掉了这条教训的可追溯性。
- 若将来有人要一个「干净」的历史，正确做法是在 witnessloop 侧讨论「`init` 升级这类簿记写入该不该算受保护写入」（上游 issue 面），而不是在本仓事后补事件。

### Decision 8: 顺手订正 `docs/development-guide.md` 里阶段 A 遗留的两条 bullet

**选择**：把 witnessloop 节里的「已知红（预期，不放宽判据）：…② 本 change 自己（缺 witnessloop 形态 manifest）」与「`reviews/` 的一致状态…把本 change 自己的红从 2 条拉到 14/16 条」两条按阶段 C 实况改写。

**理由**：这两条是 PR #311 之前的阶段 A 文案，其中的「本 change 自己」指的是**已经归档的** `witnessloop-adoption`。它们描述的对象不存在了，属于**本 change 直接造成的事实变化**（AGENTS.md 的「文档影响检查」要求只更新当前变更造成的事实变化，历史口径问题另记债务）——阶段 C 翻开关正是让它们过期的原因。

### Decision 9: 「翻开关这一动作自身必须具备 change 记录」写成一条规范义务

**选择**：在 `dev-workflow-gate` 新增 `### Requirement: 翻开关这一动作自身必须具备 change 记录`（见 delta），要求关闭某个阶段的动作本身由一条 OpenSpec change 承载并归档，且该 change 的 `proposal.md` 必须**如实写明「行为已先落地、本 change 只做记录与规格对账」**。

**理由**（设计追问 D3 的实测结论）：这条内容此前**只存在于 delta 文件里**，而 `proposal.md` 的「需求」、`design.md` 的 Decisions、`tasks.md` 的 1.2 三处**都没提它**——一条没有任何上游来源的规范内容，是审查上的黑洞。它的实质价值是真的：本 change 自己就是「先落地（PR #311）、后补记录」这个形态，而翻开关之后**任何**触达 `require_change_for` 的改动都必须挂 change——若翻开关自己的动作不挂 change，它就是在用自己的豁免把新规则挡在门外，并让「哪些检查被降级、每个还在不在跑」失去可追溯记录。
**边界**：这条只约束「关闭阶段」这类动作的形式（必须有 change），SHALL NOT 被读成「行为落地必须先有 change」——它承认了「先落地后补记录」这个形态**存在且合法**，要求的是记录**必须补上**并如实注明次序。

**判据与执行者（设计阶段对抗闭环 I-7 要求补）**：
- **机械判据是 witnessloop 的 `building` 门禁**——它要求触达 `require_change_for`（`agent/**` / `scripts/**` / `web/**`）的 diff 必须挂 change 目录。关阶段动作通常会改 `scripts/**`（本 change 记录的那次就改了 `scripts/platform-gate.json`）⇒ 该门禁**结构上**覆盖了这条规范的主场景。**本仓 `check_openspec_artifacts.py` 没有对应判据**——如实标注：这条约束在此没有本仓侧的机械门，它靠「review 时人来核」。
- **它与 AGENTS.md 最高优先级规则「需求先行」的关系必须写清**（否则这条规范看起来是在给「先写代码后补文档」开后门）：「需求先行」要求的是「**需求讨论与需求文档**先于实现」；本 change 的记录对象——阶段 C——其**需求讨论确实先发生了**（issue #305 的多轮讨论、分叉清单、以及用户的拍板），滞后的是**记录落到 OpenSpec change 目录这个形态**，不是需求讨论本身。⇒ 本规范 SHALL NOT 被读成对「需求先行」的豁免：它要求「记录必须存在且如实注明次序」，**不**授权「需求没聊清楚就先写实现」。若某次关阶段动作**连需求讨论都没有**，它违反的是「需求先行」，与本条无关。
- **非先例限定**：这是一条**只针对「关闭阶段 / 切换门禁」这类治理动作**的规范，SHALL NOT 被类推到普通功能 change 的工作流上。

### Decision 10: Purpose / 「阶段划分」段由**人手就地改写**，不经 delta；并顺手修掉段内死链

**选择**：两份规格的 `## Purpose` 段与 `dev-workflow-gate` 的「阶段划分」段，由同步步骤**直接改写当前规格文本**（不经 delta），改写前后的文本差异记入 `workflow-events.jsonl` 的 `current_spec_synced` 事件；同时把 `dev-workflow-gate` Purpose 段里那条**死链**改为归档路径。

**理由**（设计追问 D4 的实测结论）：
- OpenSpec 的 delta 只能表达 **Requirement** 的增删改；`## Purpose` 不是 Requirement，**没有 delta 载体**（实测：仓内 76 份归档 delta 中仅 1 份含 `## Purpose`）。而 `proposal.md` 与 `tasks.md` 都写了要改 Purpose 段 ⇒ 若不显式声明这条路径，执行者会以为 delta 已经覆盖它而漏掉。
- 那条死链是实测事实：当前规格引用 `openspec/changes/witnessloop-adoption/reviews/acceptance-stage-a.md`，而该目录**已归档**到 `openspec/changes/archive/2026-10-13-witnessloop-adoption/`。它正好位于要改写的 Purpose 段内 ⇒ 顺手修正，不让"改写过的段落仍指向不存在的路径"。

### Decision 11: grill 决策记录的**格式契约**按 v1.7.0 实测写死

**选择**：grill 决策记录 SHALL 满足**四条**契约（① `## Confirmed Decisions` **至少 3 条**决策块——`MIN_CONFIRMED_DECISIONS = 3` 是同一函数里的硬门槛，设计阶段对抗闭环 I-8 指出初稿的「逐条契约」漏了它；② 每条决策块内含**同行裸** `来源:`；③ `## User Confirmation` 小节**无条件存在**；④ 候选 Open Questions 小节存在且其 `Q<n>` 均有非占位确认），并把它们写进 `dev-workflow-gate` 的「grill 报告正文判据的已知不兼容」条目（该条走 MODIFIED）。

**理由**（设计追问 D6 的实测结论，**本次新发现**）：v1.7.0 的 `grill_evidence_findings`（`src/witnessloop/evidence.py:295-297`）对 `## User Confirmation` 的判据是**无条件存在性**——`user_confirmation is None` 就报「缺少 `## User Confirmation` 小节」，**与有没有 Open Question 无关**。本仓此前只记录了 `_SOURCE_RE` 不认加粗 `来源:` 那一条 ⇒ 一份「一条 Open Question 都没有」的报告**仍然**会因为缺该小节判红。这条不补记，后续每个 change 都会重复踩。
**同条目内的一处订正**：原条目写「本仓 grill 记录通篇使用加粗 ⇒ **grill stage 结构性不可能判绿**」，该断语已被阶段 B 的实测**证伪**（63 份归档 `grill-design.md` 中 **39 份**零 finding；用加粗写法的只有 3 份）。实测把它定性为**写法选择**（同行裸 `来源:` 命中，加粗不命中），因此 MODIFIED 条目把「结构性不可能」改为「格式决定」，并保留「改格式优先于改判据」的姿态。本 change 自己的 `grill-design.md` 就用同行裸写法，并用 v1.7.0 的 `grill_evidence_findings` 实测得 **0 findings**。
**契约的落点要说准（I-9）**：这四条契约的**可审计载体是版本控制内的文档**——`docs/development-guide.md` 的 witnessloop 节（已补记）与本条规格。`/grill` 命令文件本身住在 `.claude/`（**被 `.gitignore` 忽略、不进版本控制**，本 worktree 下连 `.claude/` 都没有）⇒ 规格里**SHALL NOT** 把「与 `/grill` 的产出格式对齐」写成可审计义务，只能写成「本仓文档里记录的格式契约」。

## Pre-Implementation Review

> 本节由 grill 与设计阶段对抗闭环的结论回填。两份报告的原文见 `reviews/grill-design.md` 与 `reviews/grill-adversarial.md`。

**独立设计追问（grill）**：由独立零记忆 subagent（paseo agent，未继承任何开发上下文）对本文档逐项挑战，产出 `reviews/grill-design.md`。挑战面覆盖 `grill.md` 的 7 个维度，其中**第 7 条（触发与门禁：本 change 自身会不会死锁或误伤）**是本 change 的关键维度——它正好要回答「一条只改规格的 change，在 `gate / check` 已是 required 的前提下能不能判绿」。

**结论：8 个设计点必须改（D1–D8，全部已落实）、10 条已确认（带 `文件:行号` / 命令原始输出）、0 个需要用户拍板的问题。** 逐条处置：

| # | grill 发现 | 处置 |
|---|---|---|
| D1 | `tasks.md` 把未做的任务标成 `[x]`（1.3/2.x/3.x/4.x/5.1/5.2/5.4/5.5）——提前勾 = 伪造归档点完成度门的唯一输入 | **已改回 `- [ ]`**，随落地逐条勾 |
| D2 | proposal/design 把「规格同步」写成已完成的实质，但同步尚未发生 | 1.3 恢复未完成；delta 明确定位为**待施加的输入**，当前规格是**待改写的目标** |
| D3 | delta 里第二条 ADDED Requirement 在三份上游文档里都没有来源 | 新增 **Decision 9** + proposal 需求 #7 |
| D4 | Purpose / 阶段划分段**没有 delta 载体**，且段内有死链 | 新增 **Decision 10**（人手就地改写、差异记入事件）+ 修死链 |
| D5 | Testing Strategy 五条命令里三条不可照抄执行（T2 base 未绑定、T4 裸 `python`、T5 未锚定 witnessloop revision） | 整表重写，补「前置」列与四处口径 |
| D6 | **新发现**：v1.7.0 对 `## User Confirmation` 是**无条件存在性**判据，零 Open Question 也判红 | 新增 **Decision 11** + 写进规格的「grill 报告正文判据」条目；本 change 报告已补该节并实测 0 findings |
| D7 | 同一条不变量在 MODIFIED 与 ADDED 两处各写一遍（漂移点） | MODIFIED 只留 required 集合断言，「仍须运行」全收进 ADDED（Decision 4 已注明） |
| D8 | 文档影响面漏 4 处（README / README_EN / interview-script Q12·Q13 / backlog） | 全部纳入本 change；interview-script 的两处按「本变更直接造成的事实变化」就地订正 |

**一处订正**（grill 复核 D6 时指出）：设计初稿在 Decision 11 里写「已补记进规格」时，规格尚未改到——该措辞已按如实口径改正（规格侧的补记由任务 1.3 落地——**该任务已完成**，见 `workflow-events.jsonl` 的 `current_spec_synced` 事件；本句在写作时点是对的，保留原文以记录订正发生的时刻）。

### 设计阶段对抗闭环（Round 1）

由另一个独立零记忆审阅者（paseo agent）以「**试图推翻**」为默认立场复核，产出 `reviews/grill-adversarial.md`（被审 revision `798973e`）。**verdict：CHANGES_REQUESTED**——11 条 issues（6 条 medium / 5 条 low）。逐条处置：

| # | 对抗发现 | 处置 |
|---|---|---|
| I-1（medium） | 归档 move 机制未写死；`openspec archive`（1.4.1）用 UTC 日期 ⇒ 本机实测产出**前一天**的目录名，且把「规格同步 + move」合成一次提交 | Decision 6 增补：**手工 `git mv`，SHALL NOT 跑 `openspec archive`**；tasks 5.4 复述 |
| I-2（medium） | 文档影响面漏 3 处同类「自动拦截」，且**已改的文件内部自相矛盾**（`Q13:15` 改了、`:63` 没改） | 扫全 `docs/`，**按位置列举**一次性订正（`Q12` / `Q13:13/:15/:51/:63` / `Q09:15/:61` / `walkthrough:3895`）；proposal 与 tasks 的口径由「两处」改为实测清单。**不写「共 N 处」总数**——那是会被自己文件证伪的写法（见 N-4） |
| I-3（medium） | D5 的修正只落在 design.md，**没回落到 tasks.md**（2.2 仍是 `<base>`、2.4 仍是裸 `python`、4.2 无版本锚定） | tasks 2.2 / 2.4 / 4.2 逐条改齐；收尾补 5.6（合入方式） |
| I-4（medium） | D3 的修法没同步 tasks 1.2（只列 1 条 ADDED，漏 Decision 9 那条与 MODIFIED 的 grill 条目）⇒ 按 tasks 重写 delta 会删掉它 | tasks 1.2 改为完整列出 REMOVED 1 / MODIFIED 2 / ADDED 2 |
| I-5（medium） | Decision 3 的 REMOVED 判据未对称适用；且 `add-minimal-tui-runtime-view` 的已知红**性质迁移**无人记录 | Decision 3 增补**逐条复核表**（判据写死为「含被证伪的断言」而非「属于阶段 A」）+ 新 delta MODIFIED 记录状态迁移 |
| I-6（medium） | `exempt` 与判据表「走 grill 的非平凡 change ⇒ full」冲突 | **采纳其推荐**：改 `light` + `enabled`，补 findings / design impact（Decision 1） |
| I-7（low-med） | Decision 9 无判据/执行者，且边界句与「需求先行」相抵未说明 | Decision 9 增补判据（witnessloop `building` 门禁，本仓无对应门——如实标注）、与「需求先行」的关系、非先例限定 |
| I-8（low） | Decision 11 的「逐条契约」漏了 `MIN_CONFIRMED_DECISIONS = 3` | 契约由三条改**四条**，同步进 delta |
| I-9（low） | 「与 `/grill` 产出格式对齐」指向 `.claude/`（gitignore、无可审计载体） | 改为指向版本控制内文档；delta 同改 |
| I-10（low） | 实现内容（`798973e` 的 docs 改动）先于 0.3/0.4/0.5 落盘，与 tasks 0.4 的次序声明矛盾 | **如实承认**：确有次序倒置（文档订正在设计闭环收敛前就提交了）。**无害但不合规**，处置 = 不回滚（回滚会制造更多噪声），而是在此处记录事实，并把 0.3/0.4/0.5 的勾选时点保持在其真实完成之后 |
| I-11（low） | D2 的「待施加」只写在 design 的评审表格里，delta 文件本身没有标记 | 两份 delta **顶部各加一条 `>` 显式声明「这是待施加的输入、不是已同步的结果」** |

**对抗闭环的收敛（3 轮，封顶）**：全部轮次记录见 `reviews/grill-adversarial.md`（同一文件按 `## Round N` 节追加）。

| 轮 | 被审 revision | verdict | 发现 | 处置 |
|---|---|---|---|---|
| R1 | `798973e` | CHANGES_REQUESTED | I-1…I-11（6 medium / 5 low） | 全部处置（见上表）；I-6 采纳其推荐改 `light` |
| R2 | `647e349` | CHANGES_REQUESTED | 复核 I：8 条已处置 / 3 条部分处置；新发现 N-1…N-9（全部是**本轮自己的修改没落齐**的 artifact 一致性问题） | 全部处置 |
| R3 | `5a074c7` | CHANGES_REQUESTED | 复核 N：**9 条全部已处置**；新发现 **B-1（唯一阻塞项）**：修 N-2 出处时**又引入一个假出处**（`docs/development-guide.md` 的 witnessloop 节实测无该记载）+ **6 条非阻塞观察** | B-1 已修（只保留实测过的 `AGENTS.md:226`，并把「两次引假出处」的共同形态写进 finding）。6 条非阻塞观察：**5 条已处置 / 1 条接受不处置**——逐条去向见下表（该表由实施后审阅 R2 的 I-1 促成：初稿把「2 条处置 / 4 条登记不处置」写成账面，而其中 2 条其实已在同一轮被修掉，账面与产物相反） |

**闭环到 3 轮封顶时 R3 的唯一阻塞项已修复**；按本仓口径（「直到 PASS 或 3 轮封顶」）该闭环到此结束，**没有剩下需要用户拍板的问题**——R1 的 I-6 被审阅者标为「唯一需要人拍的一条」，但它同时给出了明确推荐（改 `light`），本设计采纳该推荐即消解该争点；R2/R3 的发现全部是文档一致性问题，均有唯一解。

**R3 的 6 条非阻塞观察的最终去向（按处置结果如实登记，不是「留了几条」的模糊账）**：

| R3 观察 | 最终去向 |
|---|---|
| ① Decision 4 的「只写一处」规则未对称适用到 `dev-workflow-gate` 的 ADDED 条目 | **已处置**——在那一侧加了指向 `platform-gate` 的指针 blockquote，并把断言取值的那条 Scenario 标注「该取值由 `platform-gate` 规定」 |
| ② `tasks.md` 0.3 仍写 `exempt` | **已处置**——改为「初稿是 `exempt`，对抗轮 I-6 后已改 `light`」 |
| ③ `design.md` 的历史行仍写「共 6 处」+ `proposal.md` 清单漏 `Q13:15` | **已处置**——设计行改为按位置列举且不写总数；proposal 补上 `:15` |
| ④ 收尾次序在 tasks 的节顺序里有被误读的空间（4.1 的「所有内容提交」未点名 5.1/5.2/5.3） | **已处置**——4.1 现显式点名三项，并写明 `changes_root/*/tasks.md` **不在** v1.7.0 的 `stale_exempt_paths` 内（先产 manifest 再结算 tasks 会让 T5 立刻 stale） |
| ⑤ Decision 5 记录的「benchmark 触发面假阳性」没有耐久落点 | **接受、不处置**——收窄那条启发式属**上游/后续 change**；本 change 只负责如实记录这次触发，并**显式声明不转债务**（理由：登记进 `docs/known-debt.md` 要引入受保护写入 + 解释事件，成本高于收益；而这条待决事项的证据已在本 change 的 `tasks.md` 2.4b 与本节）。**「不去哪」也写成实**——不留给后人猜 |
| ⑥ `grill-design.md` 的 `## Open Questions` 节可能被读成仍有未决问句 | **已处置**——该节现明写「**本 change 的 Open Question 数为 0**」并加一句说明：D1–D8 是**设计改动项**（不是开放问题），已全部就地处置 |

**实施后审阅（building-review R1）追加的一条非阻塞观察**：required 集合的**取值**仍同时断言在 `platform-gate`（它的所有者）与 `dev-workflow-gate` 的 ADDED Scenario 里。**接受、不处置**：两处断言的**粒度不同**——`platform-gate` 规定取值与不变量，`dev-workflow-gate` 只断言「阶段 C 之后的接入形态长这样」且已显式标注「该取值由 `platform-gate` 规定」。把后者也删掉会让「阶段 C 完成了什么」在接入规格里失去可读的落点。

**三次对抗产出的最值得记的一条元教训**：**R1 的 N-2 与 R3 的 B-1 是同一种错误、发生在同一句话上**——为了把 findings 的出处写得丰满，补了一个**没有实测过**的来源（第一次指向 `platform-gate.json` / `platform_gate.py`，第二次指向 `docs/development-guide.md`）。这正是本 change 把档位从 `exempt` 升到 `light` 的理由本身（findings 必须可核对）被自己的修法违反。⇒ 结论写进 findings 的订正段：**出处只能引实测过的位置；「同向记载另见…」这种边角引用是最容易造假的地方，不要为了显得完整而补。**

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
| R6 | **档位被质疑为「省事」** | **已实发生并被处置**：初稿的 `exempt` 被设计阶段对抗闭环 I-6 判为「机械过闸」，**已改 `light` + `enabled`** 并补 findings / design impact（Decision 1）。结论记入 `reviews/grill-adversarial.md` |
| R7 | **本 change 合入后若再 `--apply`** | **不需要**：`scripts/platform-gate.json` 与实况本 change 前后逐字段一致（`--verify` 已实测 exit 0）。tasks 里显式写「不做 apply」，避免执行者条件反射地跑一遍 |
| R8 | **证据带的 PR 被 squash 合入** ⇒ manifest 的 `head_sha` 不再是 `master` 的祖先，日后触及该 change 目录的 PR 全判红（阶段 A 实测先例） | Decision 6 的补充约束：**必须 `--merge`，SHALL NOT squash**；tasks 收尾节复述 |
| R9 | **change 目录在验证前一直是 untracked**，误删/`git clean` 即全损 | 立项文档一落盘即提交（本 change 已做：`893e74b`）；所有验证性操作在提交之后跑 |
| R10 | **T2/T3/T5 在「内容未提交」时假绿**，污染验收记录 | Testing Strategy 的「前置」列 + 留证据时同时留 `git status --porcelain` 与 `HEAD` |
| R11 | **本地 witnessloop 与 CI 的版本不一致**（PATH 0.1.0 / 克隆 `v1` / CI `v1.7.0`），本地绿推不出 CI 绿 | T5 锚定 `/home/happy/wl170`（实测装的 `v1.7.0`）；证据里写明该版本 |
| R12 | **本 change 自己的 `gate / check` 在提交前「通过 ✓」是假绿** | 见 R10；出口判据只在提交后取，且 CI 侧再核一次（tasks 4.3） |
| R13 | **设计追问新发现的不兼容被遗漏**：v1.7.0 对 `## User Confirmation` 是**无条件存在性**判据，零 Open Question 也照判 | Decision 11：把**四条**格式契约（含 `MIN_CONFIRMED_DECISIONS = 3`）写进规格与 `docs/development-guide.md`，本 change 的 `grill-design.md` 已带该小节并用 v1.7.0 的 `grill_evidence_findings` 实测 **0 findings** |
| R14 | **`exempt` 档位被质疑**（Round 1 I-6） | 已改 `light` + `enabled`（Decision 1）；该争点由本设计自行拍定、不停轮 |

## Testing Strategy

本 change **无代码面**（Decision 5），验收由五条机械可复核的命令承担，全部要留原始输出。**每条命令都是逐字可执行的**（设计追问 D5 修正了三条：T2 绑定了 base、T4 换掉本环境不存在的裸 `python`、T5 锚定了 witnessloop 的 revision）。

| # | 命令 | 期望 | 前置 |
|---|---|---|---|
| T1 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `N passed, 0 failed` | 无 |
| T2 | `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | `OpenSpec artifact checks passed`（exit 0） | **内容已提交** |
| T3 | `uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` | `OpenSpec artifact checks passed`（exit 0） | **内容已提交** |
| T4 | `uv run python scripts/platform_gate.py --verify` | `全部一致`（exit 0）——**证明本 change 没动平台实况** | 无 |
| T5 | `/home/happy/wl170/bin/witnessloop check --root . --base origin/master --head HEAD` | `check：通过 ✓`（0 项）——**本 change 的出口判据** | **内容已提交** |

**四处口径必须写死，否则判据会被误读成「可验」**：

- **T2 的 base 必须绑定 `origin/master`**。checker 的默认 base 是 `master`，而本 worktree 里本地 `master`（`3c7196b2`）≠ 上游（`4b5cc7d1`）⇒ 用默认值会去校验**另一个变更集**（实测 `git diff --name-only master --` 列出的是 PR #311 的整份 diff）。
- **T4 用 `uv run python`，不用裸 `python`**。本环境没有 `python` 这个名字（`command not found`、exit 127）。`AGENTS.md` 与 `platform-gate.json` 的 `_description` 里的裸 `python` 属仓内既有风格，但**验收判据必须可跑**。
- **T2 / T3 / T5 只对「已提交」的内容有效**：三者都基于 `git diff`，而 **untracked 文件不进 `git diff`**。实测反例：内容提交**前**跑 T5 报「0 个变更文件，0 个 change 目录 / 通过 ✓」——**假绿**；提交后同一命令报「6 个变更文件，1 个 change 目录 / 未通过 ✗（1 项）：缺少 review manifest」。⇒ 留证据时必须同时留 `git status --porcelain` 与 `HEAD` sha，**SHALL NOT** 把提交前的绿写进验收记录。
- **T5 必须锚定 witnessloop 的 revision**：PATH 上那份是 0.1.0、`/home/happy/witnessloop` 克隆检出在 tag `v1`（`ae99256`），**两者都不是 CI 实际用的 `v1.7.0`**（`00192ab`）。本 change 用装在 `/home/happy/wl170` 的 v1.7.0 环境跑 T5（`uv pip install "git+…@v1.7.0"` 建的一次性 venv），证据里写明该路径与版本。`.dev/reference-repos.txt` 在本 worktree 不存在（该文件 gitignore、属本地配置），故 T5 的入口**不依赖它**。

**内容真实性**（T1–T3 管不到的那一半）：规格里每一条涉及 required 集合、job 是否运行、`--apply` 是否已执行的断言，都要能与 T4 的输出、以及 `gh api repos/Xingkai98/asterwynd/branches/master/protection` 的原始 JSON 逐字对上。审阅者按 `文件:行号` 抽查。

## Impact Analysis

见 `proposal.md` 的 `## Impact Analysis` 一节（同一份清单，避免两处维护漂移）。
