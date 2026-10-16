# Building Review: stage-c-required-switch（Round 1）

## Reviewer
- run id: paseo-building-review-stage-c-required-switch-r1
- 被审 revision: `614db932562c52ce3317343f8967e6a07d901c18`
- base: `4b5cc7d1a49d06caa94fe2c35aae2ccfce778e23`（`git merge-base HEAD origin/master`）
- 时间: 2026-10-17
- 零记忆: 是（未继承任何开发上下文；所有结论来自本次实跑与仓库原文）
- 工作区状态: `git status --porcelain` 为空（干净），本报告为唯一新增文件

## Verdict
**CHANGES_REQUESTED**

理由：本 change 的**实质改动（规格同步）经逐条机械比对为逐字正确**，所有涉及实况的断言与 `gh api` / `--verify` / CI 日志逐字对上，四道机械门全绿（T5 按计划未过），**没有发现阻塞性缺陷**。但有 **1 条中等**问题：本 change 自己的记录（`design.md:208` 的 R3 行）**与其记录对象（`reviews/grill-adversarial.md` 的 R3 节）数字不符**——R3 明确写「其余 **6** 条为非阻塞观察」，而 design 把它写成「**2** 条非阻塞观察」，且那 6 条里**实际处置了 2 条、其余 4 条既未处置也未登记为「不处置」**。这与本 change 三轮对抗一直在抓的缺陷同类（记录 vs 产物不一致），且修法是一行，故请求修改后重审。

## Tasks Verification

逐条核对 `[x]`（读文件 / 跑命令，不只看任务行写了什么）：

- **0.1**: 成立。`reviews/grill-design.md` 存在（22950 B）；`## Confirmed Decisions` 有 **10** 条决策块（门槛 3），用 witnessloop v1.7.0 自己的 `grill_evidence_findings` 实测 `findings = []` ⇒ 每条块内 `来源:` 均为同行裸写法且命中。证据: `reviews/grill-design.md:8`，`findings: []`（实跑，见 Test Results 5）。
- **0.2**: 成立。第 7 维度（触发与门禁）有带证据的结论：`reviews/grill-design.md:13` 用 `.witnessloop/policy.json:11-15` 的 `require_change_for = ["agent/**","scripts/**","web/**"]` 判定本 change 不触达它。另实测确认本 change 的 diff 面（`openspec/**` + `docs/**`）确不触达 `require_change_for`，故「本 change 建立 change 目录即消掉 PR #311 第 1 条红」成立。
- **0.3**: 成立。`reviews/grill-adversarial.md`（66423 B）含 `## Round 2`（`:102`）与 `## Round 3`（`:172`）两节 + Round 1 主体；三轮的 `被审 revision`（`798973e` / `647e349a` / `5a074c78`）**全部在本分支存在**（`git log -1` 逐个验过）。
- **0.4**: 成立。停轮队列为空：`grill-design.md` 的 `## Open Questions`（`:46-47`）与 `## User Confirmation`（`:49`）明写 0 条；`_extract_open_question_indexes` 无 `Q<n>` ⇒ 本仓 checker 的停轮门不会被激活。
- **0.5**: 成立。`design.md:163` 有 `## Pre-Implementation Review`，内含 D1–D8 处置表（`:173-180`）、三轮对抗收敛表（`:205-208`）与停轮结论（`:216`）。
- **0.6**: 成立。格式契约四条齐备且实测 0 findings（同 0.1 证据）；`## User Confirmation` 小节**无条件存在**且说明了理由（`grill-design.md:49-53`）。
- **1.1**: 成立。`specs/platform-gate/spec.md` 的 delta 结构 = `## MODIFIED` 2 条（合入平台闸门 / 平台闸门复用 GitHub branch protection 语义）+ `## ADDED` 1 条（降级为非必过的检查仍须运行），且顶部有「待施加的输入」显式声明（`:3`）。
- **1.2**: 成立。`specs/dev-workflow-gate/spec.md` 的 delta = `## REMOVED` 1 条（带 Reason + Migration，`:9`/`:11`）+ `## MODIFIED` 2 条 + `## ADDED` **2** 条（含 Decision 9 那条「翻开关这一动作自身必须具备 change 记录」），与 I-4 的修法一致。
- **1.3**: **产物成立，但任务行的一个子句未落地（见 I-3）**。`openspec/specs/platform-gate/spec.md` 与 `dev-workflow-gate/spec.md` 的同步**确已完成且逐字正确**：用脚本把 delta 的每个 MODIFIED/ADDED Requirement 块与当前规格逐字比对 → **全部 EXACT**（platform-gate 3 条、dev-workflow-gate 4 条）；REMOVED 的那条在现状里**确已消失**。Requirement 计数：platform-gate **3 → 4**、dev-workflow-gate **11 → 12**，与提交信息及任务行一致；`dev-workflow-gate` 其余 **10** 条逐条保留（Decision 3 的爆炸半径约束成立，基线 vs 现状空白不敏感比对：8 条 UNCHANGED、2 条 CHANGED，CHANGED 的两条正是 delta 声明要改的两条）。**未落地部分**：任务行要求「Requirement 条数前后计数**如实记入 `workflow-events.jsonl` 的 `current_spec_synced` 事件**」，而 `openspec/changes/stage-c-required-switch/` 下**没有** `workflow-events.jsonl`（该文件属任务 5.2，未勾）。⇒ 记为**计划内未完成**而非假勾，但 1.3 把「已完成的同步」与「尚未完成的证据记录」绑在同一行并勾了 `[x]`，是行内粒度问题。
- **1.4**: 成立。`docs/development-guide.md:354` 与 `:355` 两条 bullet 均已按阶段 C 实况改写，且已把对象指向**已归档**的 `witnessloop-adoption`（不再出现「本 change 自己」）。证据: `git diff origin/master...HEAD -- docs/development-guide.md`。
- **1.6**: 成立。`README.md:149` 与 `README_EN.md:149` **两条同改同向**（中英各一行，语义逐字对应），符合 AGENTS.md 的 README 同步规则。
- **1.7**: **成立（proposal 侧的清单漏一项，见 I-2）**。任务行点名的全部位置实测已订正：`Q13:13` / `:15` / `:51` / `:63`、`Q09:15` / `:61`、`walkthrough:3895` 逐行读过，均已是「判失败/报警，阶段 C 之后不再拦合并」口径；全仓 `grep -rn "自动拦截" docs/` = **0 命中**。任务行的写法（按位置列举、明写不写总数口径）是可核对的正确写法。
- **2.1**（T1）: 成立。实跑 `Totals: 30 passed, 0 failed (30 items)`，exit 0，含 `✓ change/stage-c-required-switch`；与任务行期望一致。
- **2.2**（T2）: 成立。实跑 `OpenSpec artifact checks passed`，exit 0。任务行关于「base 必须显式绑 `origin/master`」的告诫**实测成立**：本地 `master` = `3c7196b2531f…` ≠ 上游 `4b5cc7d1…`。
- **2.3**（T3）: 成立。实跑 exit 0，stderr 有一行汇总 `[archived manifest check] tasks_hash 已按归档语境跳过（76 个 change；其余 hash 与字段仍校验）`。
- **2.4**（T4）: 成立。实跑逐字段 `match: true`、输出 `全部一致`、exit 0；`target` 的 `contexts = ['gate / check']` 与 `scripts/platform-gate.json` 声明一致。任务行「不跑 `--apply`」（R7）**被遵守**：本 change 的 diff 里 `scripts/platform-gate.json` 逐字节未变（不在变更面内）。
- **2.4b**（benchmark smoke）: 成立且**可复现**。用任务行**逐字**的命令（仅把 runs-dir 换成审阅者专属目录）重跑，得到**同样的输出与同样的 exit 0**：`success_rate: baseline=1.0000 current=1.0000 delta=+0.0000` / `p95_latency_s: SKIPPED (deterministic task set)` / `result: PASS`。任务行声称的产出目录 `/tmp/benchmark-gate-runs-sc/2026-10-16T19-05-06/` **确实存在**，时间戳（UTC 19:05 = 本机 10-17 03:05）与提交时刻相符。命令行与 `.github/workflows/ci.yml:137` 的 `benchmark-gate` job **仅 runs-dir 不同**，「同形」的说法准确。任务行给出的「为什么无代码面却要跑」的理由（checker 的 `_requires_benchmark_smoke` 被「不影响」清单命中 = 假阳性）**实测可复现**：该函数对本 proposal 返回 `True`，四个正则里**只有 `benchmarks/` 命中 1 处**、另三个 0 命中，capability 名 0 命中 ⇒ 触发源**确为排除清单的措辞**，属真·假阳性。
- **2.5**: 成立。规格里每一条涉及 required 集合 / job 是否运行 / `--apply` 是否已执行的断言，逐条与实测对上（见下「Spec 对齐」）。

未勾任务（1.5、3.1、3.2、4.1–4.3、5.1–5.6、6.1–6.2 带 `(post-merge)`）经核对**均为计划内**，且 `6.1` / `6.2` 已正确标注 `(post-merge)`。**注**：1.5 描述的工作（Purpose / 阶段划分段就地改写 + 死链修正）**实际已在提交 `614db93` 完成**（见 Spec 对齐），却仍为 `- [ ]`——这是**保守方向**（少勾只会拦自己），但 5.3 结算时必须把它勾掉，否则归档点会报「未勾且未标 (post-merge)」。

## Spec 对齐（内容真实性，逐条与实测对上）

实测命令：`gh api repos/Xingkai98/asterwynd/branches/master/protection --jq '{contexts:.required_status_checks.contexts,strict:.required_status_checks.strict,conv:.required_conversation_resolution.enabled,approvals:.required_pull_request_reviews.required_approving_review_count,admins:.enforce_admins.enabled}'` → `{"admins":true,"approvals":0,"contexts":["gate / check"],"conv":true,"strict":true}`。

| 规格断言 | 实况 | 结论 |
|---|---|---|
| `required_status_checks.contexts` = `["gate / check"]` 且只有它 | `["gate / check"]` | ✅ |
| `required_status_checks.strict` = true | `true` | ✅ |
| `required_conversation_resolution` 开启 | `true` | ✅ |
| `required_approving_review_count` = 0 | `0` | ✅ |
| `enforce_admins` 开启 | `true` | ✅ |
| 该值由 `scripts/platform-gate.json` 声明 | 该文件 `contexts = ["gate / check"]` | ✅ |
| `validate` / `benchmark-gate` / `windows-platform` 三个 job 仍在每个 PR 上跑 | `.github/workflows/ci.yml` 三个 job 齐备（`:10` / `:99` / `:147`）；PR #312 三个 job 与 `gate / check` **并存**且均 success | ✅ |
| 「照跑但不拦」是实测事实 | PR #312：`gate / check` failure 与三 job success 并存 | ✅ |
| 本 change 不改平台实况（R7） | `--verify` 全部一致；`platform-gate.json` 不在 diff 内 | ✅ |
| Purpose 段的死链已改指归档路径 | `dev-workflow-gate/spec.md:10` 现指 `openspec/changes/archive/2026-10-13-witnessloop-adoption/reviews/acceptance-stage-a.md`，**该文件存在**（26456 B） | ✅ |

**引用溯源（本轮专核，因前两轮各抓到一次假出处）**——抽查 12 处，**全部成立**：
- `AGENTS.md:226` ✅ 逐字成立（「由主 session 在 PR 合入后执行——合入前 apply 会把对话 resolution 闸门锁住 PR 自身」）。
- CI 日志原文 ✅ **逐字**：`##[notice]witnessloop 包 ref = 00192abe45d2d72a4389eccb202faad48c34fa26（来源：job.workflow_sha（被复用的那个 workflow 文件自己的 commit））`（从 PR #311 的 `gate / check` job log 第 91 行抓到，另有 `Uses: …gate.yml@refs/tags/v1.7.0 (00192ab…)` 佐证）。
- PR #311 ✅ `headRefOid = 18d5bfbf2aa16f1994b1fa2bb7de1f7b8bd42d20`、`mergeCommit = 4b5cc7d1a49d06caa94fe2c35aae2ccfce778e23`，与 proposal 逐字一致。**且那条最微妙的断言成立**：在 head 上 `gate / check = failure` 而 `validate`/`benchmark-gate`/`windows-platform` 三项 `success`；在 merge commit `4b5cc7d1` 上 `gate / check` 这个 check-run **根本不存在**（只剩三个 success）——与 proposal:19 的描述逐字相符。
- PR #311 的两条红 ✅ **逐字**：log 第 342/343 行正是 `scripts/platform-gate.json`（属于 `require_change_for` 但无 change 目录）与 `.witnessloop/init-manifest.json`（受保护写入无解释事件）。
- PR #312 的三个时长 ✅ 由 check-run 时间戳算出：`validate` 18:21:16→18:28:10 = **6m54s**、`benchmark-gate` 18:21:16→18:21:31 = **15s**、`windows-platform` 18:21:16→18:23:18 = **2m2s**，与 `design.md:19` 逐字一致。
- `src/witnessloop/evidence.py:295-297` ✅ 精确（`user_confirmation = sections.get(...)` / `if user_confirmation is None:` / `findings.append(…缺少 ## User Confirmation 小节…)`）；`MIN_CONFIRMED_DECISIONS = 3` 在 `:29`、`_SOURCE_RE = re.compile(r"来源\s*[:：]")` 在 `:33`。
- 规格行号 ✅ `openspec/specs/platform-gate/spec.md:11`（required 列举句）与 `:13-17`（「benchmark-gate 为 required check」Scenario）、`dev-workflow-gate/spec.md:7`（阶段 A Purpose）逐行核对无误。
- 归档先例 ✅ `archive/2026-09-22-retire-4phase-state-machine/specs/dev-workflow-state-machine/spec.md` 存在且确含 REMOVED；`archive/2026-08-16-platform-gate/design.md:13` 确记「只有 `validate` 被 protection 要求」；`guard-write-allowlist` 的 `workspace-safety` delta 确有 MODIFIED 覆盖重写先例。
- `tests/test_platform_gate.py` 已钉 `gate / check` ✅（`:68` / `:151` / `:187`）。
- 本地/上游 master sha ✅ `3c7196b2…` / `4b5cc7d1…`。

## Issues

- **I-1（medium）: `design.md:208` 的 R3 行把它所记录的对象写错了数，且 6 条非阻塞观察中有 4 条既未处置也未登记为「不处置」。**
  证据: `design.md:208` 写「新发现 **B-1（唯一阻塞项）**… + **2 条非阻塞观察**」，处置格写「2 条非阻塞项一并修（…）」。而 `reviews/grill-adversarial.md` 的 R3 节 Verdict **逐字**写「其余 **6** 条为非阻塞观察」，其「非阻塞观察」小节列了 6 条（`:211` 起往下 1–6）。逐条核当前仓库：① Decision 4 的「只写一处」规则范围（**部分**处置：dev-workflow-gate 的 ADDED 加了指针，但见 I-5）；② `tasks.md:13` 的 `exempt` 字样 → **已修**（现写「初稿是 `exempt`，对抗轮 I-6 后已改 `light`」）；③ 讲稿面处数残留 → **未修**（`design.md:191` 仍写「共 **6 处**」而同行自列 **7** 项；`proposal.md:64` 仍漏 `Q13:15`）；④ `tasks.md:56`（4.1）未点名 5.1/5.2/5.3 → **未修**；⑤ Decision 5 的 benchmark 假阳性无耐久落点、`grep -n "不转债务" design.md` = 0 命中 → **未修**；⑥ `grill-design.md` 的 `## Open Questions` 说明句 → 该节现有说明文字（`:47`），可视为已满足。
  ⇒ 问题不在「选择只修 2 条」（那可以是合法取舍），而在**记录把 6 写成 2**：后人按 `design.md` 的收敛表读本轮结论，会以为 R3 只留下 2 条非阻塞观察、且都处置了。这与本 change 三轮对抗反复定性的一类缺陷同源（记录与产物不一致），而本 change 的全部价值恰在记录准确。
  建议: 把 `:208` 的「+ 2 条非阻塞观察」改为「+ 6 条非阻塞观察（本轮处置 2 条：Decision 4 规则范围、`tasks.md` 的 `exempt` 字样；其余 4 条如实登记为**接受不处置**，逐条列明）」，并顺带修 ③（`design.md:191` 改「共 9 处」或直接删总数口径）与 ④/⑤ 中愿意就地修的部分。
- **I-2（low）: 同一份清单在 proposal 与 tasks 两处不一致。**
  证据: `tasks.md:26` 列 `Q13-benchmark.md:13/:15/:51/:63`（4 项），`proposal.md:64` 列 `Q13-benchmark.md:13/:51/:63`（漏 `:15`）。实测 `docs/interview-script/questions/Q13-benchmark.md:15` **确已**订正（含「阶段 C 之后它不再是 required check…照跑但不拦」）⇒ tasks 对、proposal 漏。这正是 R3 非阻塞观察 ③②，未修。
  建议: proposal 补 `:15`（一行）。
- **I-3（low）: 任务 1.3 勾 `[x]`，但它自称的取证动作尚未发生。**
  证据: `tasks.md:22` 要求「同步后核对：Requirement 条数前后计数**如实记入 `workflow-events.jsonl` 的 `current_spec_synced` 事件**」；`ls openspec/changes/stage-c-required-switch/` 无 `workflow-events.jsonl`（该文件属未勾的 5.2）。同步本身**确已完成**（见 Tasks Verification 1.3），故**不是假勾**；问题是任务行把「已完成的正文改动」与「未完成的证据记录」绑成一行。
  建议: 收尾时确保 5.2 写入的 `current_spec_synced` 事件**确实带上 3→4 / 11→12 的计数**（该事件同时是本 change 触达受保护路径 `openspec/specs/**` 的**必需**解释事件，不是可选）；或把 1.3 的取证子句拆到 5.2。
- **I-4（low）: 1.3 与 1.5 对同一件事各写一遍，且完成状态相反。**
  证据: `tasks.md:22`（1.3，`[x]`）含「（Purpose 段一并按阶段 C 实况改写）」，`tasks.md:24`（1.5，`[ ]`）又单独要求「Purpose / 阶段划分段的人手就地改写」。两行指的是同一份工作，而该工作**实际已完成**（`openspec/specs/dev-workflow-gate/spec.md:5-11` 的 Purpose 与阶段划分段已改写、死链已修）。⇒ 目前是「已勾的行覆盖了未勾行的工作」。
  建议: 5.3 结算时把 1.5 勾掉（该工作有产物），或把 1.3 括号里的 Purpose 子句删掉避免两处维护同一事实。
- **I-5（low）: 「只写一处」的规则仍未对称适用——required 集合的取值仍住在两份规格里。**
  证据: 规则在 `design.md:87`（同一条不变量不得在 MODIFIED 与 ADDED 两处各写一遍），`design.md:208` 声称已「**对称**适用到 `dev-workflow-gate` 的 ADDED 条目」。实测：`dev-workflow-gate` 的 ADDED 条目**确实**加了指针 blockquote（不变量指向 `platform-gate`）✅，但其 Scenario 仍**独立断言** `required_status_checks.contexts` SHALL 为 `["gate / check"]`——而同一个取值 `platform-gate` 规格的 Scenario 也断言了。⇒ 不变量做到了单点，**取值仍是两点**，与 Decision 4 自己写的理由（「两处并存时，未来改一处漏一处不会被任何门禁发现」）命中同一形态。R3 非阻塞观察 1 说的正是这件事，未完全处置。
  建议: 或把 `dev-workflow-gate` 该 Scenario 的断言改为纯指针（「该取值由 `platform-gate` 能力域规定」），或在 Decision 4 里把规则范围写清为「不变量单点、取值允许在两处各断言一次并说明理由」。
- **I-6（low，观察）: 引用的「63 份 / 39 份 / 加粗 3 份」今已过期一位（今为 64 / 40 / 4），但**溯源成立**。
  证据: 实测归档 `grill-design.md` = **64** 份、零 finding = **40** 份、含加粗 `**来源**` = **4** 份。**但把 `guard-write-allowlist`（归档日 2026-10-14，晚于阶段 B 的测量时点）排除后，三个数字**恰好**是 63 / 39 / 3**，与引用逐字吻合；且该测量在 `archive/2026-10-14-guard-write-allowlist/reviews/grill-design.md:36` 里有独立记载（「63 份…39 份零 finding」）⇒ **不是编造，是阶段 B 当时的真数字，且文本已用「阶段 B 实测」如实标注了时点**。本 change 的 `grill-design.md` 与 `design.md` 亦实测 `findings = []`。
  建议: 不阻塞。若求严谨可在数字后加「（阶段 B 测点；此后归档数 +1，结论不变）」——本 change 的 delta 已把该句同步进了 `openspec/specs/dev-workflow-gate/spec.md`，是**受保护路径**，改动需同步改两处。
- **I-7（low，观察）: `design.md:152` 的「**76** 份归档 delta 中仅 1 份含 `## Purpose`」数额错配。**
  证据: 76 实为**归档 change 数中带 `reviews/*-review.md` 的那一批**（本仓 checker 自己的口径，见 T3 的 stderr 一行「76 个 change」）；归档 change 目录实为 **124** 个、归档 delta 文件实为 **219** 份。**实质结论成立**：全仓确实**只有 1 份**归档 delta 含 `## Purpose`（`archive/2026-07-08-multi-agent-dev-workflow/specs/dev-workflow-state-machine/spec.md`）⇒ Decision 10「Purpose 无 delta 载体」的判断为真。
  建议: 不阻塞。把「76 份归档 delta」改为「124 个归档 change 里仅 1 份的 delta 含 `## Purpose`」即可，属措辞精度。
- **I-8（low，观察）: `proposal.md:83` 把 `00192ab` 称作「`v1.7.0` tag 的 commit」——它实际是**附注 tag 对象**的 sha。**
  证据: `git cat-file -t 00192abe…` = `tag`；`git rev-parse 'v1.7.0^{commit}'` = `c9b281167ad20b63e4832ad9ab8510964a2adc60`。**但引用的合法性不因此受损**：GitHub 自己就把 `refs/tags/v1.7.0` 报成 `00192ab`（CI 日志 `Uses: …gate.yml@refs/tags/v1.7.0 (00192ab…)`），且被引的 `##[notice]` 原文逐字一致。另 `design.md:244` 称 `/home/happy/witnessloop` 检出在 `v1`（`ae99256`）**正确**（`v1` 的 tag 对象是 `1d0032a`、commit 是 `ae99256`）。
  建议: 不阻塞。把「就是 `v1.7.0` tag 的 commit」改为「就是 GitHub 对 `refs/tags/v1.7.0` 报出的 sha（附注 tag 对象；其 commit 为 `c9b2811`）」更精确。
- **I-9（low，观察）: 同步动作在每个 Requirement 标题后多插了一个空行，使被声明「逐条保留」的 10 条也进了 diff。**
  证据: `git diff origin/master...HEAD -- openspec/specs/` 显示 12 个 Requirement 标题后各有 `+` 空行；空白不敏感比对确认 **8 条内容 UNCHANGED**、2 条 CHANGED（正是 delta 声明要改的两条），`platform-gate` 的「平台配置即代码」UNCHANGED。⇒ 纯空白噪声，无内容影响，`openspec validate --strict` 通过（T1）。
  建议: 不阻塞（可选清理）。
- **其他**: 无。RIR 的 `research_tier: light` 与判据表自洽（本 change 走 grill、有 11 条 Decision、delta 新增一条上游没有的规范 ⇒ 至少 `light`）；I-6 升档的裁定有据。设计阶段对抗闭环以 3 轮封顶结束（R3 verdict 仍为 CHANGES_REQUESTED，但唯一阻塞项 B-1 已在 `6578635` 修复），与本仓「直到 PASS 或 3 轮封顶」口径一致，且 `design.md:210` **如实写明是封顶而非 PASS**，未粉饰。

## Test Results

| # | 命令 | 原始结论 |
|---|---|---|
| T1 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: **30 passed, 0 failed** (30 items)`，**exit 0**（含 `✓ change/stage-c-required-switch`、`✓ spec/platform-gate`、`✓ spec/dev-workflow-gate`） |
| T2 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | `OpenSpec artifact checks passed`，**exit 0** |
| T3 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` | `OpenSpec artifact checks passed`，**exit 0**（stderr：`[archived manifest check] tasks_hash 已按归档语境跳过（76 个 change；其余 hash 与字段仍校验）`） |
| T4 | `uv run python scripts/platform_gate.py --verify` | 逐字段 `match: true`，输出 `全部一致`，**exit 0** |
| T5 | `/home/happy/wl170/bin/witnessloop check --root . --base origin/master --head HEAD` | **未通过 ✗（2 项）**，exit 1：① `缺少 review manifest`（= 任务 3.1/4.1 未做）② `无 stage=grill 的 manifest（现有 stage：（无））`（= 任务 4.1/4.2 未做）。**两项均为计划内未完成**（对应任务未勾），不是缺陷；它是本 change 的出口判据（4.2），当前未达成属预期。自报版本：`requested_revision=v1.7.0，commit_id=c9b2811…`（= `v1.7.0^{commit}`，锚定正确） |
| 附 | `.github` 逐字节性 | `git diff origin/master...HEAD -- .github/` **无输出、变更文件数 0** ⇒ `ci.yml` 与 `witnessloop.yml` **逐字节未变**，本 change **未弱化任何 CI 配置** |
| 附 | benchmark smoke 复现 | 重跑任务行逐字命令 → `BENCHMARK GATE / success_rate: baseline=1.0000 current=1.0000 delta=+0.0000 / p95_latency_s: SKIPPED (deterministic task set) / result: PASS`，**exit 0**（与任务行记录逐字一致） |
| 附 | `_requires_benchmark_smoke(proposal)` | 返回 `True`；四个正则中**仅 `benchmarks/` 命中 1 处**，`agent/loop.py` / `agent/tools/` / `agent/workspace_policy.py` 各 0 命中，5 个 capability 名 0 命中 ⇒ 任务行 2.4b 与 Decision 5 的「假阳性」定性**可复现** |
| 附 | `grill_evidence_findings(reviews/grill-design.md)`（v1.7.0） | `[]`（**0 findings**），exit 0 ⇒ 任务 0.6 实测成立 |

## 结论

本 change 的**实质改动是可信的**：规格同步逐字正确（delta 的每一条 MODIFIED/ADDED 与当前规格逐字相同、REMOVED 确已删除、被声明保留的 10 条 Requirement 内容未动），规格里每一条涉及合入门禁实况的断言都与 `gh api` 的原始 JSON 和 `--verify` 的输出逐条对上，`.github/` 逐字节未变（没有弱化 CI），benchmark smoke 可复现且其「假阳性」理由可复现，`grill` 证据在 v1.7.0 自己的判据下 0 findings，且本轮专核的 12 处引用（含最容易被伪造的 CI 日志原文、PR head/merge sha、源码行号）**全部真实且逐字一致**——前两轮抓到的「引假出处」这一形态在本轮**未再出现**。

问题集中在**记录自身的准确性**上，不在产物内容上：`design.md:208` 的 R3 行把 6 条非阻塞观察写成 2 条（I-1），同一份讲稿面清单在 proposal 与 tasks 两处不一致（I-2），1.3/1.5 对同一件事各写一遍（I-4），以及若干措辞/数值精度问题（I-6…I-9）。鉴于本 change 的全部价值就是「把阶段 C 记录对账清楚」，而 I-1 让后人按收敛表读到的本轮结论与产物不符——这与本 change 三轮对抗反复追打的缺陷同类——故判 **CHANGES_REQUESTED**，请求按 I-1（主要）与 I-2 修改后重审（修改成本均为一行级）。T5 未通过属计划内，不是本轮判红的理由。
