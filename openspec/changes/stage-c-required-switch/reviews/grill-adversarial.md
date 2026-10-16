# Grill 对抗（设计阶段审阅闭环）: stage-c-required-switch — Round 1

## Reviewer
- run id: paseo-grill-adversarial-stage-c-required-switch-r1
- 时间: 2026-10-17
- 零记忆: 是
- 被审 revision: `798973e`（工作区干净；本轮期间主 session 从 `cb61ee6` 前进到 `798973e`，结论基于 798973e）

## Verdict
**CHANGES_REQUESTED**

理由：设计主体（规格 delta 的机械正确性、Decision 6 的次序理由、Decision 11 的格式契约）经实测**成立**，但有 6 条 medium 级问题会直接影响落地：归档 move 的机制未被写死且 `openspec archive` 在本环境会产出**前一天的目录名**（I-1）；上一轮 D5/D3/RN1 的修正**没有回落到 `tasks.md`**（I-3/I-4）；文档影响面扫查漏了 3 处同类"自动拦截"（含**本 change 已改的那个文件内部**，I-2）；Decision 3 的 REMOVED 判据未对称适用（I-5）；Decision 1 的 `exempt` 与 AGENTS.md 判据表正面冲突（I-6，且这是唯一需要人拍的一条）。

## 逐条对抗结论

- **挑战点 1（Decision 1 档位：`primary: process` + `research_tier: exempt`）**：**机械豁免成立，实质豁免不成立——裁定「机械过闸」**。证据三条：
  ① 机械侧实测通过：`_exempt_reason_satisfies`（`scripts/check_openspec_artifacts.py:507-521`）对 reason 命中 `上游决策锁定`（`:84`）、`#305`（`:519` 的 `#\d+`）、`openspec/changes/archive/`（`:88`）三重依据；直接以归档点语义调用 `_check_reference_implementation_research(..., assume_implemented=True)` 实测返回 `[]`（无 finding），`assume_implemented=False` 亦为 `[]`。占位词表 `SELF_ADMITTED_INCOMPLETE_PHRASES`（`:92-99`）不含"待定"，故 reason 里的"没有任何待定设计项"不会误触发。
  ② 但 AGENTS.md:37 的判据表把「**走 grill 的非平凡 change**」列在 `full 必调研`行内（`docs/development-guide.md:316` 同文），而 AGENTS.md 的设计追问门禁是**非平凡 change 才必须走 grill**；本 change 走了 grill（`reviews/grill-design.md` 存在）、有 11 条 Decision，却在 `proposal.md:74` 声称"**没有任何待定设计项**"。两者不能同真：要么它是非平凡 change（⇒ 按表至少 `light`，且该行字面指向 `full`），要么 grill 本不该跑。
  ③ 更硬的一条：delta 的第二条 ADDED（`specs/dev-workflow-gate/spec.md:64-72`「翻开关这一动作自身必须具备 change 记录」）是**本次新造的规范义务**——上一轮 grill 的 D3 自己写它"在三份上游文档里都没有来源"。上游决策**没有**锁定它，所以"上游决策锁定、无待定设计项"对这条不成立。`design.md:47` 已诚实标注"不是唯一解"并把它交给我裁定；我的裁定是：**改 `light` + `status: enabled`，补一段 findings + design impact**（成本极低，且与 `design.md:46` 自称的"没有可供业界对比的设计空间"相比，本仓历史上有 `guard-write-allowlist`、`witnessloop-adoption` 两次同类"门禁切换"可对比——这正是 `light` 档要做的一句话结论）。保留 `exempt` 的唯一出路是解释 AGENTS.md:37「走 grill 的非平凡 change」这一行对本 change 为何不适用，那是**仓库规则解释权**，不是我能替用户拍的。
- **挑战点 2（Decision 3 的 REMOVED 是否把该留的留下）**：**计数与机械结果全对，但处置判据不对称——裁定「部分成立」**。
  ① 计数成立：现状 11 条 Requirement（`grep -c '^### Requirement:' openspec/specs/dev-workflow-gate/spec.md` = 11；`:15/:32/:52/:75/:86/:97/:113/:129/:145/:176/:197`），delta 为 REMOVED 1 + MODIFIED 1 + ADDED 2 ⇒ 同步后 12 条。用**真工具**在隔离副本实测（见下"排除掉的疑点"第 1 条）：dev-workflow-gate 落成 12 条、platform-gate 落成 4 条，无重复 Requirement、无孤儿 Scenario、首行 SHALL 全中。
  ② 不对称在判据：Decision 3 的 REMOVED 理由是"正文与三个 Scenario **全部是阶段 A 的过渡态约束**……留着它就是让规格描述一个不存在的世界"（`design.md:63`）。同一条判据同样命中被保留的 `### Requirement: 影子接入阶段的验收判据`（`openspec/specs/dev-workflow-gate/spec.md:75-84`：正文是"**阶段 A** SHALL 用可机械复核的判据收口"，Scenario 是"两次原始输出 SHALL 并列记入**阶段 A** 验收报告"——不可再被触发的义务）、`已知红如实记录且不放宽判据`（`:86-95`：该红"SHALL 记入**阶段 B** 的验收报告，作为「真打开」决策的输入"，而"真打开"已发生）、`本地守卫的能力退步必须随接入写明`（`:97-111`："`design.md` 的 `## Risks / Trade-offs` SHALL 保留该退步条目**至阶段 C 决策**"——阶段 C 决策已做出）。它们不是**假**，但都是**已耗尽的规范性文本**，且同步后紧跟在改写为阶段 C 口径的 Purpose 段之后，形成"Purpose 说阶段 C、下面四条说阶段 A"的口径错位。
  ③ 附带一条**未被任何文档处置的状态迁移**：阶段 C 之后 `gate / check` 是 required，`add-minimal-tui-runtime-view`（实测存在、无 `reviews/` 目录）的已知红从"只出现在 job 日志里"变成"**拦合入**"——它一旦开 PR 就合不进去。`proposal.md:40` 只写"不处理 K1"，但没写这个后果；同步后的规格 `:86-95` 仍只把它描述为"阶段 B 的输入"。（实测 `gh pr list --state open` 为空 ⇒ 当前无即时断裂，故列为 medium 而非 high。）
- **挑战点 3（Decision 9 是否是只对本 change 有利的自利规范）**：**是可判据的、误伤面窄，但它既无执行者、又与 AGENTS.md 最高优先级规则冲突——裁定「低价值自利，须补边界」**。
  ① 误伤面：范围写死为"关闭阶段 C 的动作"（`specs/dev-workflow-gate/spec.md:66`），不会卷进 docs-only 小改动 ⇒ 误伤风险低。
  ② 无判据：`scripts/check_openspec_artifacts.py` 无任何对应判据（全文无"翻开关"相关谓词），witnessloop 侧也只能对**在途 PR** 判"改了 require_change_for 路径却没挂 change"；而本 change 承认的形态恰恰是"行为先落地、事后补记录"——**事后**这件事没有任何门禁能发现。真正的价值（阶段翻开关必须挂 change）其实已被 witnessloop 的 building 门禁覆盖，因为 `scripts/platform-gate.json` 命中 `require_change_for` 的 `scripts/**`（`.witnessloop/policy.json:11-15`，实测）。⇒ 这条规范净增的可判性接近于零。
  ③ 冲突：`design.md:115` 的边界句"它承认了「先落地后补记录」这个形态**存在且合法**"直接与 AGENTS.md 的最高优先级规则「**需求先行**：……没有把目标、边界、验收标准、测试策略聊清楚之前，**不写实现代码**」相抵。一处规格义务把违反本仓最高优先级规则的形态写成"合法"，而 `design.md` 全篇没有提这个冲突。
  ④ 自利性读法可辩：它确实把"本 change 自己的迟到形态"写成了被规范要求的东西。这本身不算错，但**必须付出可判性的对价**。
- **挑战点 4（Decision 11 三条契约 vs witnessloop v1.7.0 真实实现）**：**三条逐条对得上，但"逐条契约"自称穷尽却漏一条——裁定「基本成立，一处不全」**。实测（`/home/happy/wl170` 的 v1.7.0 安装，非引用设计行号）：
  ① `_SOURCE_RE = re.compile(r"来源\s*[:：]")`（`.../witnessloop/evidence.py:33`）：`'- **决策**: x；来源: run-1'` → 命中；`'- **决策**: x；- **来源**: run-1'` → **不命中**；`'来源： run-2'`（全角）→ 命中。与 delta `specs/dev-workflow-gate/spec.md:15` 逐字一致。
  ② `USER_CONFIRMATION_TITLE = "User Confirmation"`（`:26`），`user_confirmation is None` ⇒ `缺少 ## User Confirmation 小节`。把本 change 报告的该小节整段删掉后实测恰好产出 **1 条** finding（`缺少 \`## User Confirmation\` 小节`），**与有没有 Open Question 无关**——契约②成立。
  ③ `## Open Questions` 逐字标题存在性：删掉该节后实测产出 `缺少 \`## Open Questions\` 小节`；`_open_question_sections` 还会把"以 Open Questions 结尾的尾短语标题"（如 `## 逐条对抗（… / Open Questions）`）也算候选 ⇒ 契约③方向正确。
  ④ **本 change 自己的报告实测 0 findings**：`grill_evidence_findings(open(...grill-design.md).read())` → `[]`（6 个二级标题被识别：Confirmed Decisions / Open Questions / Reviewer / User Confirmation / 需要修改的设计点 / 风险）。⇒ `design.md:130` 的"实测 0 findings"属实。
  ⑤ 不全之处：同一个函数在 `:29` 有硬门槛 `MIN_CONFIRMED_DECISIONS = 3`，`len(blocks) < 3` 直接判红（我在源码里读到该分支）；而 delta 把三条契约写成"判据的**逐条契约**……SHALL 为：①②③"，未收录这一条。后续 change 若只写 2 条决策会拿到一条规格里没写的红。
- **挑战点 5（"0 个需要用户拍板的问题"是否成立）**：**大体成立，但有一条例外——裁定「1 条需要人拍」**。
  ① `docs/interview-script/**` 的改动**不需要**停轮，理由是可判定的：AGENTS.md 的「文档影响检查」要求关键词扫描并更新"当前变更造成的事实变化"，`docs/interview-script/` 属 `docs/`；AGENTS.md 对 interview-script 只有"**建议性**维护约束、不设机械门禁"，没有任何一条把讲稿排除在影响面外；改动是事实订正（job 数 2→3、required 集合、`自动拦截`→`会报警`），可逆、不发布、不改对外承诺。故属 agent 权限内的就地订正 ✓。（但这次订正本身不完整，见 I-2。）
  ② 例外是**挑战点 1 的档位**：AGENTS.md:37 的「走 grill 的非平凡 change ⇒ full」与本 change 的 `exempt` 不能同真，且 delta 里确有一条**无上游来源的新规范**（Decision 9）。我给了推荐（改 `light`），但若作者要坚持 `exempt`，就必须回答"那一行为何不适用"——这是仓规解释权，属用户。除此之外我没有找到第二个只有人能拍的问题（`U7`/`U11` 的格式裁定经查是**已有用户裁定**，不属新增取舍，见"排除掉的疑点"第 6 条）。
- **必验项 A（上一轮 D1–D8 是否真的落实，逐条实测）**：
  - **D1 已落实** ✓：`_untagged_unchecked_tasks(change_dir)` 实测返回 24 条未勾任务（含 0.3/0.4/0.5、1.1–1.7、2.1–2.5、3.1/3.2、4.1–4.3、5.1–5.5），`git log --oneline -5` 只有 3 个本 change 提交，`ls openspec/changes/archive/2026-10-17-stage-c-required-switch` → 不存在，`find openspec/changes/stage-c-required-switch -type f` → 7 个文件（无 `workflow-events.jsonl`、无任何 `*.manifest.json`）⇒ 勾选状态与仓库事实一致，无"提前勾"。
  - **D2 部分落实**：1.3 已恢复 `- [ ]` ✓；但"delta 是**待施加的输入**"这句话只写在 `design.md:143` 的评审表格行里，**两份 delta 文件本身没有任何"未施加"标记**，而 1.1/1.2（"写 delta"）仍标未勾却已完成 ⇒ 执行者仍有误读空间（I-11）。
  - **D3 部分落实**：`design.md:110-115` Decision 9 与 `proposal.md:31` 需求 #7 已补 ✓；但 `tasks.md:21`（1.2）仍只写"增 `### Requirement: 阶段 C 翻开关后的 required 形态`"一条，既漏 Decision 9 那条 ADDED、也漏"grill 报告正文判据"那条 MODIFIED ⇒ 残留（I-4）。
  - **D4 已落实** ✓：`design.md:117-123` Decision 10 存在，明确"Purpose/阶段划分段由人手就地改写、不经 delta"；死链属实（`ls openspec/changes/witnessloop-adoption` → No such file or directory，实体在 `openspec/changes/archive/2026-10-13-witnessloop-adoption/reviews/acceptance-stage-a.md`），修正动作排在 `tasks.md:24`（1.5，未做，属计划内）。
  - **D5 部分落实**：`design.md:179-192` 的 Testing Strategy 已重写（T2 绑 `origin/master`、T4 改 `uv run python`、T5 锚 `/home/happy/wl170`）✓；**`tasks.md` 未同步**：`:31`（2.2）仍是 `--base-ref <base>` 占位、`:33`（2.4）仍是裸 `python`、`:44`（4.2）仍无 wl170 锚定 ⇒ 残留（I-3）。另实测 T2 的 base 陷阱属实：本地 `master`=`3c7196b`、`origin/master`=`4b5cc7d`，`git diff --name-only master --` = **115 个文件**（PR #311 的整份 diff）✓。
  - **D6 已落实** ✓：`reviews/grill-design.md:49-53` 有 `## User Confirmation` 小节（且明写"即使为空也必须存在"），实测 `grill_evidence_findings` = 0 findings；Decision 11（`design.md:125-130`）存在；delta 把三条契约并进 MODIFIED 条目（`specs/dev-workflow-gate/spec.md:13-29`）。
  - **D7 已落实** ✓：`specs/platform-gate/spec.md:7` 的 MODIFIED 正文只保留 required 集合断言，不变量全部收进 ADDED 条目（`:44-65`），并有一行指针注记（`:9`）。
  - **D8 部分落实**：README/README_EN/Q12/Q13 已在 `798973e` 改 ✓（且 README 两条同改、口径一致）；backlog 未改（`tasks.md:49` 的 5.1 计划内）；**但扫查漏 3 处同类**（I-2）。
  - **RN1（合入方式）部分落实**：`design.md:93`（Decision 6 补充约束：SHALL 用 `--merge`、SHALL NOT squash）与 `:168`（R8 声称"tasks 收尾节复述"）都在，但 **`grep -n "merge\|squash" tasks.md` 只命中 `(post-merge)` 标签行**，收尾节（5.1–5.5）无一条合入方式约束 ⇒ 残留（I-3）。
- **必验项 B（delta 与现状之间会不会静默出错）**：**机械同步无静默错误；静默风险不在 delta，而在"用哪个工具做归档 move"**。
  ① 在 `/tmp/sim-sc`（隔离副本）用真工具 `npx --yes @fission-ai/openspec@1.4.1 archive stage-c-required-switch -y` 实测：输出 `dev-workflow-gate: +2 added / ~1 modified / -1 removed`、`platform-gate: +1 added / ~2 modified`、`Totals: +3, ~3, -1` —— 与 `design.md` 声称的"REMOVED 一条、MODIFIED 两条+一条、ADDED 三条"**逐字吻合**；同步后 `dev-workflow-gate` 12 条、`platform-gate` 4 条，无重复 Requirement、无孤儿 Scenario；`validate --all --strict` → `29 passed, 0 failed`（比 baseline 的 30 少 1 是因为该 change 已不在 active）。四个 MODIFIED/REMOVED 目标标题在现状里逐字存在（`platform-gate/spec.md:9`、`:56`；`dev-workflow-gate/spec.md:52`、`:176`）⇒ 不会静默 no-op。
  ② 静默风险转移到了 move 机制上：该命令**一次动作同时完成"规格同步 + 目录搬移"**，与 `design.md:86`（Decision 6 ③"独立**纯 rename** 提交"）和 `tasks.md:52`（5.4）明写的 `git mv` 方案**不是同一件事**；且它产出的目录名是 `2026-10-16-stage-c-required-switch`——**不是** `tasks.md:52` 与 `design.md:86` 写死的 `2026-10-17-…`（原因见 I-1）。若执行者用了这个命令，Decision 6 的第 ④ 步（"在归档目录上用**归档目录名**重建 manifest"）会绑到错误名字，`change_id` 与目录不符 ⇒ 判红；`workflow-events.jsonl` 的 `change_archived` 与 backlog 条目也会指错路径。

## Issues

- **I-1（medium）**：归档 move 用哪个机制**没有被写死**，而 `openspec archive` 在本环境会给出前一天的目录名、并与 Decision 6 要求的提交形状冲突。
  证据：`/home/happy/.npm-global/lib/node_modules/@fission-ai/openspec/dist/core/archive.js:313-316`（`getArchiveDate(){ return new Date().toISOString().split('T')[0] }` ⇒ **UTC 日期**；同版本 `:252` `archiveName = \`${this.getArchiveDate()}-${changeName}\``）；实测本机 `date` = `Sat Oct 17 02:54 CST 2026`，而在 `/tmp/sim-sc` 跑 `npx --yes @fission-ai/openspec@1.4.1 archive stage-c-required-switch -y` 输出 `Change 'stage-c-required-switch' archived as '2026-10-16-stage-c-required-switch'`。对照：npx 缓存里另一份 1.14.1 的 `dist/utils/date.js` 用**本地**日期（`formatLocalDate`），说明这是 1.4.1 的实现特性而非环境异常。另：`tasks.md:52` / `design.md:86` 写死 `2026-10-17`。
  建议修法：在 `design.md` Decision 6 与 `tasks.md` 5.4 里**写死**「归档 move 用 `git mv` 手工完成，**不要**跑 `openspec archive`」，并给出两条理由（① 该命令把规格同步与 move 原子合成一次提交，与 Decision 6 ③ 的纯 rename 与 R4 的次序理由冲突；② 1.4.1 的日期前缀取 UTC，本地 00:00–08:00 之间会得到前一天）。若要改走工具，则必须把 `2026-10-17` 全部改成"以工具实际产出的目录名为准"，并把 Decision 6 ②③ 合并。
- **I-2（medium）**：文档影响面扫查不完整，且**本 change 已改的那个文件内部出现自相矛盾**。
  证据：`docs/interview-script/questions/Q13-benchmark.md:15` 已改成"不再自动拦合并"（`798973e` 只改了这一行），但**同文件 `:63`** 仍写"还接 CI **自动拦截**劣化（#78 第二批）"；`docs/interview-script/questions/Q09-observability.md:15`（"劣化超阈值**自动拦截**"）与 `:61`（"还接 CI——benchmark 对比基线**自动拦截**劣化"）同类未改；`docs/interview-bullets/walkthrough.md:3895` 仍写"`.github/workflows/ci.yml` | CI pipeline — validate + benchmark-gate **两个 job**"（与 Q12 被改的那处同类，实测 `ci.yml` 三个 job：`:10 validate` / `:99 benchmark-gate` / `:147 windows-platform`）。而上游文档 `proposal.md:64` 与 `tasks.md:26` 把这一面描述为"两处……**直接造成/直接证伪**的事实变化" ⇒ 口径不实。
  建议修法：至少补齐 `Q13:63`（同一文件内、直接证伪，必须修）；`Q09:15/:61` 与 `walkthrough:3895` 二选一——要么同批订正（推荐，成本 4 行），要么在 `proposal.md` 的 Impact Analysis 里显式登记为"已知未同步面"（`walkthrough:3895` 的 job 数错误早于本次变更，可归"历史口径"另记债务，但**不能**留白）。
- **I-3（medium）**：`design.md` 的修正没有回落到 `tasks.md`（执行者的勾选清单、也是归档点完成度门的唯一输入）。
  证据：`tasks.md:31`（2.2）仍为 `--base-ref <base>` 占位（`design.md:182` 已改为 `--base-ref origin/master`）；`tasks.md:33`（2.4）仍为裸 `python scripts/platform_gate.py --verify`（`design.md:184` 已改为 `uv run python`；实测本机 `command -v python` 无输出）；`tasks.md:44`（4.2）仍为 `witnessloop check …（v1.7.0）`，无 `/home/happy/wl170` 锚定（`design.md:185` 有）；`grep -n "merge\|squash" tasks.md` 无命中，而 `design.md:168` 的 R8 明写"tasks 收尾节复述"。
  建议修法：把上列四处按 `design.md` 的最终口径抄进 `tasks.md`（2.2/2.4/4.2 各一行），并在收尾节补一条"合入方式：`--merge`，SHALL NOT squash"的任务行。
- **I-4（medium）**：D3 的修法没有同步 `tasks.md` 1.2，留下"按 tasks 重写 delta 会删掉 Decision 9 那条 Requirement"的路径。
  证据：`tasks.md:21`（1.2）只列一条 ADDED（`阶段 C 翻开关后的 required 形态`），漏掉 `specs/dev-workflow-gate/spec.md:64` 的第二条 ADDED 与 `:13-29` 的 MODIFIED（grill 判据）；而 `design.md:61` 写的是"新增**两条**"。
  建议修法：`tasks.md:21` 补齐"ADDED 两条 + MODIFIED 一条（grill 报告正文判据）"。
- **I-5（medium）**：Decision 3 的 REMOVED 判据未对称适用，且一处状态迁移无人记录。
  证据：判据"全部是阶段 A 的过渡态约束 ⇒ 留着就是描述不存在的世界"（`design.md:63`）同样命中保留的 `openspec/specs/dev-workflow-gate/spec.md:75-84`（阶段 A 验收判据）、`:86-95`（"记入**阶段 B** 验收报告，作为真打开的输入"）、`:97-111`（"保留该退步条目**至阶段 C 决策**"）；`add-minimal-tui-runtime-view` 实测无 `reviews/` 目录且 `gh pr list --state open` 为空，阶段 C 后其已知红从"不挡"变为"拦合入"，`proposal.md:40` 与同步后的规格均未记录。
  建议修法：在 Decision 3 里补一段"保留理由的分类"——哪些是**仍然成立的接入形态**（承载分工、policy 前置、两个开关、保留清单、manifest 并存、双守卫）、哪些是**不可再触发的历史义务**（验收判据、已知红、守卫退步的"至阶段 C"）并说明后者为何仍留在规格（作为历史判据的记录而非活义务，建议在这三条正文首句加"（历史判据：阶段 A 已按此验收）"之类限定）；同时在 `proposal.md` 的 Impact Analysis 里补一行"阶段 C 使 `add-minimal-tui-runtime-view` 的已知红升级为拦合入——本 change 不处理，后果如实记录"。
- **I-6（medium，需人拍）**：`research_tier: exempt` 与 AGENTS.md 判据表正面冲突。
  证据：AGENTS.md:37 / `docs/development-guide.md:316` 把"走 grill 的非平凡 change"列入 `full`；本 change 走了 grill、有 11 条 Decision、并新增一条无上游来源的规范（`specs/dev-workflow-gate/spec.md:64-72`，即上一轮 D3 自认的"三份上游文档都没提"），却在 `proposal.md:74` 声称"没有任何待定设计项"。豁免 reason 在机械上可过（实测 `assume_implemented=True` 返回 `[]`）。
  建议修法：**改 `research_tier: light` + `status: enabled`**，补 `findings`（本仓两次同类门禁切换 `openspec/changes/archive/2026-10-13-witnessloop-adoption/`、`…/2026-10-14-guard-write-allowlist/` 的对照结论）与 `design impact` 两段；若坚持 `exempt`，须在 `proposal.md` 的 RIR reason 里显式回答"走 grill 的非平凡 change"这一行为何不适用。**这条超出 agent 自决范围（仓规解释），需用户拍板。**

- **I-7（low）**：Decision 9 缺边界限定，与 AGENTS.md 最高优先级规则冲突。
  证据：`design.md:115`"承认「先落地后补记录」这个形态**存在且合法**" vs AGENTS.md"需求先行：……没有把……聊清楚之前，**不写实现代码**"；无任何机械判据（checker 全文无对应谓词）；价值已被 witnessloop building 门禁对 `scripts/**` 覆盖（`.witnessloop/policy.json:11-15`）。
  建议修法：① 加时效边界（"记录 SHALL 在行为落地后的**同一收尾批**内归档；未归档前该阶段 SHALL 视为未闭合"）；② 加一句"该形态 SHALL NOT 被援引为先例（`需求先行` 仍适用于常规变更）"，把冲突显式化；③ 或承认它是无执行者的软规范并降级为 `docs/development-guide.md` 的一段说明。
- **I-8（low）**：Decision 11 的"逐条契约"漏了 `MIN_CONFIRMED_DECISIONS = 3`。
  证据：`/home/happy/wl170/lib/python3.12/site-packages/witnessloop/evidence.py:29`（`MIN_CONFIRMED_DECISIONS = 3`）与 `grill_evidence_findings` 里 `len(blocks) < MIN_CONFIRMED_DECISIONS` ⇒ 报"少于硬门槛 3 条"；delta `specs/dev-workflow-gate/spec.md:15` 把契约写成"SHALL 为：①②③"三条，未含此硬门槛。
  建议修法：在契约①里补"`## Confirmed Decisions` SHALL 至少 3 条（`MIN_CONFIRMED_DECISIONS`）"。
- **I-9（low）**：规格里"本仓模板与 `/grill` 的产出格式随之对齐"（`specs/dev-workflow-gate/spec.md:27`）指向仓外未跟踪载体。
  证据：`.claude/` 被 gitignore（`.gitignore:9`），本 worktree 连 `.claude/commands/opsx/` 都不存在；`openspec/changes/archive/2026-10-13-witnessloop-adoption/design.md:304` 的 U7 否决备选也把"要动 `.claude/commands/grill.md`（本地、不进 PR、无评审记录）"列为代价。
  建议修法：删掉该半句，或把"产出格式"的载体明确指向仓内已有记载（`docs/development-guide.md` 的 witnessloop 节已含该格式契约——`798973e` 新增的 bullet）。
- **I-10（low）**：实现内容先于设计阶段闭环落盘。
  证据：`798973e`（对应 `tasks.md:23/25/26` 的 1.4/1.6/1.7）在 `cb61ee6`（D1–D8 落实）之后立即提交，而 `tasks.md:13/14/15` 的 0.3（本对抗闭环）/0.4（停轮检查）/0.5（回填）当时与现在都未勾 ⇒ 与 `tasks.md:14`"若无 ⇒ 直接进入实现"的次序声明不一致（无害：doc-only、可逆、grill 已给出 0 Open Question）。
  建议修法：在 tasks 0.5 回填时如实注明"1.4/1.6/1.7 的落地早于 0.3/0.4 完成"，或调整 0.4 的措辞为"实现内容落盘前完成"。
- **I-11（low）**：delta 无"待施加"标记。
  证据：`design.md:143` 表格行有"delta 明确定位为**待施加的输入**"，但两份 delta 文件本身无此标记，`tasks.md:20-21`（1.1/1.2）仍标未勾却已完成。
  建议修法：在 `tasks.md` 1.1/1.2 的行内加"（delta 已成稿，本项=核对/补齐，勿重写）"，避免执行者把已定稿的 delta 当作待办而重写。

## 排除掉的疑点

1. **"delta 同步会不会静默出错（重复 Requirement / 孤儿 Scenario / 首行缺 SHALL）"**——查过，不是问题。在 `/tmp/sim-sc` 用**真工具**（`npx --yes @fission-ai/openspec@1.4.1 archive`）机械施加后：`grep -c '^### Requirement:'` → dev-workflow-gate **12**、platform-gate **4**；标题逐一列出无重复；`validate --all --strict` → `29 passed, 0 failed`（strict 只读 Requirement 正文第一行，本 change 三条新 Requirement 正文均为单行长句、句首含 SHALL）。四个 MODIFIED/REMOVED 目标标题在现状里逐字存在（`platform-gate/spec.md:9`、`:56`、`dev-workflow-gate/spec.md:52`、`:176`）。
2. **Decision 11 的三条格式契约**——查过，逐条属实（见挑战点 4 的 5 组实测），且本 change 报告本身实测 0 findings。
3. **Decision 6 的 stale 豁免集**——查过，与 v1.7.0 实现逐字一致：`.../witnessloop/policy.py:77-93` 的 `stale_exempt_paths` = `(".witnessloop/**", "<changes_root>/*/reviews/**", "<changes_root>/*/workflow-events.jsonl", "<archive_root>/**")`，`docs/**` 与 `openspec/specs/**` 确实不在内 ⇒ "内容先于证据"的次序理由成立。
4. **"照跑但不拦"这条核心事实**——查过，实物佐证：`gh api repos/Xingkai98/asterwynd/branches/master/protection` → `{"admins":true,"approvals":0,"contexts":["gate / check"],"conv":true,"strict":true}`；`uv run python scripts/platform_gate.py --verify` → exit 0（逐字段 `match: true`）；`gh api …/commits/18d5bfb…/check-runs` → `gate / check | failure` 与 `validate|benchmark-gate|windows-platform = success` 并存，而 merge sha `4b5cc7d1` 上没有 `gate / check` 这条 check-run ⇒ `proposal.md:19` 的"引错 sha 会把结论说反"警告正确。
5. **`.witnessloop/policy.json` 与规格里写的定案值**——查过，逐字一致：`require_change_for = ["agent/**","scripts/**","web/**"]`、`protected_paths` 五项、`review_manifest_glob = reviews/*.manifest.json`。且本 change 的 diff 实测不触达受管路径：`git diff --name-only origin/master...HEAD` 只有 `README.md` / `README_EN.md` / `docs/**`(3) / `openspec/**`(6)。
6. **"Decision 11 改格式是不是推翻了用户已拍的 U7"**——查过，**不是**新取舍：阶段 A 的 U7（`openspec/changes/archive/2026-10-13-witnessloop-adoption/design.md:302-304`）确实写着"等上游修谓词、本仓零改动"，但其"后续"段留了口子（"若上游长期不修，再由那时的停轮项决定是否走「本仓改格式」那条路"）；阶段 B 的 **U11（原 Q11）** 已由用户在 2026-10-14 裁定"`reviews/grill-design.md` 保持**同行裸 `来源:`** 写法"（`openspec/changes/archive/2026-10-14-guard-write-allowlist/design.md:292-298`）。⇒ MODIFIED 后的"改记录格式优先于改判据"是**既有用户裁定的延续**，不构成新的停轮项。
7. **归档搬移会不会被受保护写入门拦**——查过，不会：v1.7.0 有 `_archive_move_exempt`（`.../witnessloop/checkcmd.py:324-342`，源必须在 active change 目录下、目标在本次到达目录下），与 delta `specs/dev-workflow-gate/spec.md:53` 的"或包含一条把该 change 归档进来的 `git mv`"一致。
8. **`exempt` 的 reason 会不会被占位词表误杀**——查过，不会：`SELF_ADMITTED_INCOMPLETE_PHRASES`（`scripts/check_openspec_artifacts.py:92-99`）只有 `尚未完成/待补充/待调研/tbd/todo/待确认`，reason 里的"没有任何**待定**设计项"不在表内；直接调用 `_check_reference_implementation_research(..., assume_implemented=True)` 返回 `[]`。
9. **`add-minimal-tui-runtime-view` 的 K1 会不会让本 change 自身判红**——查过，不会：witnessloop 的 stage 判定按**本次 diff** 求值，该 change 不在本 change 的 diff 里；`gh pr list --state open` 为空 ⇒ 也没有在途 PR 会被新 required 拦下。
10. **报告文件名会不会撞 manifest glob**——查过，不会：`evidence.review_manifest_glob = reviews/*.manifest.json`，本文件名为 `grill-adversarial.md`（不以 `-review.md` 结尾，也非 `*.manifest.json`）；checker 侧对它在归档点只做**存在性**校验（`scripts/check_openspec_artifacts.py:1629-1639`）。

## Round 2（复核 Round 1 的 11 条 + 找新洞）

- run id: paseo-grill-adversarial-stage-c-required-switch-r2
- 被审 revision: `647e349a492121ad72a80ad9a9f3d97e4eb50dd7`（工作区干净；本文件除本轮追加外无改动）
- 时间: 2026-10-17
- 零记忆: 是（不继承 Round 1 与任何开发上下文；Round 1 原文现读现核）

### Verdict

**CHANGES_REQUESTED**

理由：**设计主体无异议，11 条里 8 条已处置、3 条部分处置，新发现 9 条全部是「本轮自己的修改没落齐」这一类 artifact 一致性问题——没有一条推翻设计结论、没有一条需要用户拍板**。但其中 N-1 是 Decision 5 内部（标题 + 选择句）与它自己的订正段、以及 `tasks.md` 的已勾任务**正面矛盾**，N-3 让 Decision 11 点名的可审计载体（`docs/development-guide.md`）少记一条契约——按本仓「修正要落齐所有 artifact」的口径，这两类必须回写后再收敛。N-1/N-3/N-2/N-4 都是纯文本订正，成本约 6 行。

### I-1…I-11 逐条复核

- **I-1**: **已处置**。`design.md:107-109` 写死「用 `git mv` **手工**做，SHALL NOT 跑 `openspec archive`」并给出两条理由（UTC 日期产出前一天目录名、把规格同步与 move 原子合成一次提交）；`tasks.md:54`（5.4）复述同口径。全仓 `grep -n "git mv\|openspec archive"` 在这两份文档里无相反表述。
- **I-2**: **已处置**。全仓重扫：`grep -rn "自动拦截" docs/` → **0 命中**；`Q13:13/:51/:63`、`Q09:15/:61`、`walkthrough:3895`、`Q12:5/:24-29` 已逐处改为「判失败／不再拦合并」（`647e349` 改 6 处、`798973e` 改 3 处）。唯一残留的「两个 job」在 `docs/testing-guide.md:43`，讲的是 locale/UTF-8 的历史教训（对象是「原本」两个 job），不是本次被证伪的 CI 口径，见「排除掉的疑点」8。（处数口径另有问题，见 N-4。）
- **I-3**: **已处置**。`tasks.md:31`（2.2）= `--base-ref origin/master`；`:33`（2.4）= `uv run python`；`:46`（4.2）= `/home/happy/wl170/bin/witnessloop check`；`:56`（5.6）= `--merge`／SHALL NOT squash。**实测**：`uv run python scripts/platform_gate.py --verify` → 逐字段 `match: true`、`全部一致`、**exit 0**。
- **I-4**: **已处置**。`tasks.md:21` 与 delta 实际结构逐条对得上：dev-workflow-gate = REMOVED 1（`specs/dev-workflow-gate/spec.md:7`）+ MODIFIED 2（`:15`、`:33`）+ ADDED 2（`:53`、`:84`）；platform-gate = MODIFIED 2（`specs/platform-gate/spec.md:7`、`:32`）+ ADDED 1（`:46`）。
- **I-5**: **部分处置**。做齐的：判据写死为「含**被本次变更直接证伪的断言**」（`design.md:66`）、10 行逐条复核表（`:68-79`）、对边界情形的如实标注（`:81`）、状态迁移入 delta（`specs/dev-workflow-gate/spec.md:17`、新 Scenario `:26-31`）与 `design.md:83`。**我独立复核了这张表**：现状 11 条 Requirement（`openspec/specs/dev-workflow-gate/spec.md:15/:32/:52/:75/:86/:97/:113/:129/:145/:176/:197`）逐条读过，表中 10 个「否」我**同意**——最接近的两条（`:75-84` 阶段 A 验收判据、`:97-111` 守卫退步「保留至阶段 C 决策」）是**已履行／已到期**的义务，不是被证伪的断言，按写死的判据不该删。**未落的**：Round 1 明确要求在 `proposal.md` 的 Impact Analysis 补的那一行没写（见 N-6）。
- **I-6**: **已处置**。`proposal.md:72-73` 逐字为 `research_tier: light` / `status: enabled`。**实测硬门槛**：`C._check_reference_implementation_research(d, p, ct, assume_implemented=True)` → `[]`；`_requires_benchmark_smoke` → `True`、`_check_benchmark_smoke_task` → `[]`；findings/design impact 无占位词（`尚未完成/待补充/待调研/tbd/todo/待确认` 零命中）。findings 三条中 2、3 经我独立核验属实（见「排除掉的疑点」2、3），**finding 1 的出处引错**（见 N-2）。
- **I-7**: **部分处置**。`design.md:140-143` 三段齐备（判据＋执行者、与「需求先行」的关系、非先例限定），内容达标。但**边界只落在 `design.md`，没有随 delta 进规格**——冲突的另一方是规范文本本身（`specs/dev-workflow-gate/spec.md:84-92`），见 N-7。
- **I-8**: **部分处置**。`design.md:155`（Decision 11）与 delta 正文（`specs/dev-workflow-gate/spec.md:35`）都已是**四条**且含 `MIN_CONFIRMED_DECISIONS = 3`（该常量实测存在于 `/home/happy/wl170/lib/python3.12/site-packages/witnessloop/evidence.py:29`，判红分支在其 `grill_evidence_findings` 内）。但「三条」的口径残留在**三处**（delta 的 Scenario 标题、`design.md` 的 R13、以及 Decision 11 点名的可审计载体 `docs/development-guide.md`），见 N-3。
- **I-9**: **已处置**。`grep -n "claude/"` 在 design/proposal/两份 delta 里只剩**解释性**句子（`design.md:159` 说明 `.claude/` 被 gitignore ⇒ 规格 SHALL NOT 指向它；`specs/dev-workflow-gate/spec.md:35` 末句同义）。原「与 `/grill` 的产出格式对齐」半句已删。
- **I-10**: **已处置（如实承认，未粉饰）**。`design.md:197`：「**如实承认**：确有次序倒置（文档订正在设计闭环收敛前就提交了）。**无害但不合规**，处置 = 不回滚……」。没有把它写成「没有问题」。
- **I-11**: **已处置**。两份 delta 顶部各有显式 `>` 声明（`specs/platform-gate/spec.md:3`、`specs/dev-workflow-gate/spec.md:3`）：「本文件是**待施加的输入**，不是已同步的结果……**不要**据本文件的存在推断同步已完成」。

### 新发现

- **N-1（medium）Decision 5 的标题与「选择」句，和它自己的订正段 + `tasks.md` 正面矛盾**。
  证据：标题 `design.md:93`「### Decision 5: 无代码面 ⇒ 不写 TDD 测试、**不跑 benchmark smoke**」；选择句 `design.md:95`「tasks 里**不排**「先写失败测试」一节，也**不排** benchmark smoke」；而同一 Decision 的订正段 `:99-100` 写「设计初稿写……⇒ 不排它。**实测是错的**……⇒ 处置：tasks 排 **2.4b**」，`tasks.md:3` 亦写「**benchmark smoke 仍然排了（2.4b）**」，且 `tasks.md:34` 已勾 `[x]`、证据实测存在（见「排除掉的疑点」1）。⇒ 一份读者会照做的 Decision，标题与「选择」说的一套、订正段与任务线做的是另一套。这是本轮引入的（订正段是新增的，标题/选择句没同步改）。
  建议修法：把 `design.md:93` 标题与 `:95` 选择句改成「**跑** benchmark smoke（触发启发式命中，见订正）」／「tasks 排一条 gate-smoke（2.4b）」。**这是本轮唯一必须改的实质矛盾**。
- **N-2（low-medium）`light` findings 的第 1 条把出处引错了**。
  证据：`proposal.md:80` 断言「本仓 `scripts/platform-gate.json` 的 `_description` 与 `scripts/platform_gate.py` 的自述**都写明**：`--apply` 若在同一 PR 合入前执行，会把该 PR 自身的 conversation resolution 闸门锁住」。**实测两处都没有**：`scripts/platform-gate.json` 三条 `_description`（`:9` / `:13` / `:17`）无此句；`scripts/platform_gate.py` 的模块 docstring（`:1-34`，`--apply` 段落全文）只说 GET-modify-PUT 与「apply 前打印目标 vs 实况 diff」，`grep -n "合入前"` 在该文件零命中。该事实的真身是 `AGENTS.md:226`（「合入前 apply 会把对话 resolution 闸门锁住 PR 自身」）与本 change 自己的 delta `specs/platform-gate/spec.md:42`。⇒ 事实成立、**出处假**；I-6 之所以要求升到 `light` 就是要 findings 可核对，出处错会让后人按引用去查却查不到。
  建议修法：把引用从 json/py 改为 `AGENTS.md:226`（或直接引本 delta 的那条 SHALL）。
- **N-3（low）I-8 的「三条 → 四条」没落齐三处，其中一处正是 Decision 11 点名的可审计载体**。
  证据：① `docs/development-guide.md:356`（该 bullet 由 `798973e` 新增）只记了**三条**：`## Confirmed Decisions`（同行裸 `来源:`）、`## User Confirmation`（无条件存在）、Open Questions 小节——**漏 `MIN_CONFIRMED_DECISIONS = 3`**；而 `design.md:159` 明写「这四条契约的**可审计载体是版本控制内的文档**——`docs/development-guide.md` 的 witnessloop 节（已补记）与本条规格」。⇒ 已落地的那份载体「已补记」的其实是三条。② `specs/dev-workflow-gate/spec.md:37` 的 Scenario 标题仍是「三条判据逐条可复核」（正文 `:35` 已是四条，`:47` 也已改口「上述四条契约」）。③ `design.md:222`（R13）仍写「Decision 11：把**三条**格式契约写进规格」。
  建议修法：三处「三条」补成四条并补 `MIN_CONFIRMED_DECISIONS = 3`（`docs/development-guide.md` 那处是一个括号短语）。
- **N-4（low）讲稿面的处数口径仍然自相矛盾——正是 I-2 要求根除的那类写法**。
  证据：`proposal.md:64` 与 `tasks.md:26` 都写「讲稿面**共 6 处**」，但其**自列清单**为 `Q12`（1）+ `Q13:13/:51/:63`（3）+ `Q09:15/:61`（2）+ `walkthrough:3895`（1）= **7 项**；而实测 diff 其实是 **9 处**——`git show 798973e` 另改了 `Q13:15` 与 Q12 两处，其中 **`Q13:15` 未出现在任何清单里**（`prop`/`tasks` 只列 `:13/:51/:63`）。⇒ 「共 6 处」既与自己的清单（7）不符，也与仓库事实（9）不符。
  建议修法：改成「共 9 处（本轮 6 处 + `798973e` 的 Q12×2 与 Q13:15）」，或改成「讲稿面逐处清单如下」不带总数。
- **N-5（low）`tasks.md` 2.4b 记录的命令不是真正跑过的那条，且结果没记**。
  证据：任务行 `tasks.md:34` 写 `--runs-dir /tmp/benchmark-gate-runs`，但该目录里最新一次是 `2026-10-05T19-11-16`（**没有 10-17 的产出**）；真实证据在 **`/tmp/benchmark-gate-runs-sc/2026-10-16T19-05-06/`**（`run.json`：`task_count: 2 / passed: 2 / failed: 0`，`started_at 2026-10-16T19:05:06+00:00` = 本机 10-17 03:05:06，与 `647e349` 的提交时刻 03:05:20 相隔 14 秒 ⇒ 是本次提交前跑的）。`design.md` Decision 5 与 `tasks.md` 2.4b **都没有记录结果**（2/2 passed）。⇒ 不是假勾（确实跑了并通过），但「任务行写的命令」与「产出证据的目录」对不上，且无结果记录；后人照任务行去 `/tmp/benchmark-gate-runs` 核验会看到一次陈旧运行。（另：产物里看不出是否带了 `--baseline` / `--require-baseline`——`run.json` 两个字段都不落，故无法核实是否与 `ci.yml` 的 `benchmark-gate` job「同形」，这条我不断言。）
  建议修法：任务行改成实际用的 `--runs-dir`（或补一句「本次实际产出目录」），并记一行「结论：2/2 passed（`run.json`）」。
- **N-6（low）I-5 要求的 proposal 侧那一行没补**。
  证据：Round 1 的 I-5 建议修法含「同时在 `proposal.md` 的 Impact Analysis 里补一行『阶段 C 使 `add-minimal-tui-runtime-view` 的已知红升级为拦合入——本 change 不处理，后果如实记录』」。现状：`proposal.md:40` 只有「**不处理** `add-minimal-tui-runtime-view` 的已知红（K1）」，`## Impact Analysis`（`:54-68`）无对应行；该迁移只进了 delta（`specs/dev-workflow-gate/spec.md:17`、`:26-31`）与 `design.md:83`。按 AGENTS.md 的「CI 与影响分析」条（发现新影响面先回写 change 文档），这里应有一行。
- **N-7（low）I-7 的边界只进了 design，没进规格——而冲突的一方正是规格义务**。
  证据：`design.md:140-143` 的「判据与执行者／与「需求先行」的关系／非先例限定」都在；但 delta 的 Requirement 正文与 Scenario（`specs/dev-workflow-gate/spec.md:84-92`）**没有任何**「SHALL NOT 被援引为先例」「需求先行仍适用」的限定。归档后规格是耐久规范，读者单看规格仍会读到一条**无护栏**的「先落地后补记录合法」义务——这正是 I-7 指出的与 AGENTS.md 最高优先级规则的相抵点。
  建议修法：在 delta 那条 Requirement 正文末尾补一句「本条 SHALL NOT 被读成对『需求先行』的豁免，也 SHALL NOT 被类推到常规功能 change」（与 `design.md:143` 同义即可）。
- **N-8（low）`tasks.md` 的勾选状态此刻与仓库事实不符（方向是「少勾」，非「提前勾」）**。
  证据：1.4（`docs/development-guide.md`）已在 `798973e` 落地、1.6（`README.md` + `README_EN.md`）同在 `798973e` 落地、1.7（讲稿 6 处）在 `647e349` 落地——三项都仍是 `- [ ]`（`tasks.md:23/:25/:26`）；0.3（对抗闭环）的产物 `reviews/grill-adversarial.md` 已存在（本文件，含 Round 1），但闭环尚未收敛到 PASS，`- [ ]` **可辩护**。⇒ 与 Round 1 D1 的「提前勾」相反，这是**保守方向**，不构成归档点完成度门的风险（门要求全勾，少勾只会拦自己），但「勾选状态=仓库事实」这条不成立。
  建议修法：5.3 结算时按实际落地情况勾齐 1.4/1.6/1.7，无需回滚任何提交。
- **N-9（low）风险表 R6 仍以 `exempt` 为已选档位**。`design.md:215`：「R6 | **`exempt` 档位被质疑为「省事」** | Decision 1 已如实标注它不是唯一解……」。档位已改 `light`，此行的风险描述与缓解指向的是**不再存在**的选择（同一改动的 `design.md:48` 已加 ⚠️ 说明、Decision 1 `:46` 已改口径）。建议把 R6 改写为「档位从 `exempt` 上调为 `light`（I-6）」的闭环记录。

### 排除掉的疑点

1. **`tasks.md` 2.4b 是不是假勾**——不是。实测证据在 `/tmp/benchmark-gate-runs-sc/2026-10-16T19-05-06/`：`run.json` `task_count 2 / passed 2 / failed 0`，`summary.md` 两条 task 全 `passed`，时间戳与本 change 最后一次提交（`647e349`，本机 03:05:20）相隔 14 秒。⇒ smoke 确实跑过并通过（问题只在记录口径，见 N-5）。
2. **RIR finding 2 的 CI 日志断言是不是编的**——不是。`gh api repos/Xingkai98/asterwynd/actions/jobs/117127446958/logs` 精确命中：`notice]witnessloop 包 ref = 00192abe45d2d72a4389eccb202faad48c34fa26（来源：job.workflow_sha（被复用的那个 workflow 文件自己的 commit））`，与 `proposal.md:81` 的引用**逐字一致**；且 `gh api repos/Xingkai98/witnessloop/git/refs/tags/v1.7.0` → `00192abe45d2d72a4389eccb202faad48c34fa26`（type `tag`）⇒「`00192abe…` 就是 `v1.7.0` tag 的 commit」属实。
3. **RIR finding 3 的引用是否属实**——属实。`openspec/changes/archive/2026-08-16-platform-gate/design.md:13` 确有「`benchmark-gate` 未进 required，可绕过」与「但只有 `validate` 被 protection 要求」，与 `proposal.md:82` 的转述一致。
4. **delta 的 REMOVED/MODIFIED 目标标题会不会静默 no-op**——不会。四个目标在现状里逐字存在：`openspec/specs/dev-workflow-gate/spec.md:52`（REMOVED）、`:86`、`:176`（MODIFIED），`openspec/specs/platform-gate/spec.md:9`、`:56`（MODIFIED）。
5. **MODIFIED 会不会静默丢掉原有 Scenario**——不会。逐条比对了现状与 delta：`platform-gate/spec.md:56` 那条 Requirement 现状**只有一个** Scenario，delta 的 MODIFIED 也是那一个（改掉「（validate / benchmark-gate）」并补 `--apply` 次序 SHALL）；`dev-workflow-gate/spec.md:86` 现状 1 个 Scenario → delta 2 个（保留 + 新增迁移条）；`:176` 现状 2 个 → delta 2 个（内容按 Decision 11 重写，属预期替换）。无「delta 里少写从而静默删条」的情况。
6. **`add-minimal-tui-runtime-view` 的前提断言是否还成立**——成立。`openspec/changes/add-minimal-tui-runtime-view/` 仍在 active（未归档），目录内无 `reviews/`；delta 与 `design.md:73` 描述一致。
7. **讲稿面还有没有同类旧口径**——除 `docs/testing-guide.md:43` 外没有。`grep -rn "自动拦截" docs/` = 0；剩余「拦截」命中全部属沙箱/命令守卫语境（`Q02:53`、`Q10:72`、`Q14:38`、`walkthrough:1084`、`interview-prep.md` 等），与 CI 门禁无关。`docs/testing-guide.md:43` 的「原本两个 job 都是 `ubuntu-latest`」是 locale 历史教训（描述的是**当时**的 job 集合），不因阶段 C 过期。
8. **机械门是否被绕过/是否有隐藏红**——没有，四条命令我都实跑：
   - `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **Totals: 30 passed, 0 failed (30 items)**，exit 0（本 change 本身也列出：`✓ change/stage-c-required-switch`）。
   - `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` → **`OpenSpec artifact checks passed`**，exit 0。
   - `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` → `OpenSpec artifact checks passed`，exit 0（stderr 一行汇总：`tasks_hash 已按归档语境跳过（76 个 change；其余 hash 与字段仍校验）`）。
   - `uv run python scripts/platform_gate.py --verify` → 五字段 `match: true`、`全部一致`，exit 0。
9. **`open_question_sections` 的四条契约④是否写准**——准。源码 `.../witnessloop/evidence.py` 的 `_open_question_sections(sections)` 分支：存在候选小节时逐个 `Q<n>` 校验确认（缺则报「Open Question Q<n> 未经用户确认」、占位则报「确认是占位文本」），不存在时走 else 报「缺失」——与 delta `specs/dev-workflow-gate/spec.md:35` 的 ④ 同义。

## Round 3（封顶轮：复核 N-1…N-9 + 阻塞性新洞扫查）

- run id: paseo-grill-adversarial-stage-c-required-switch-r3
- 被审 revision: `5a074c784c4f371565c59cbe1b1ec70d7748524f`（工作区干净；本文件除本轮追加外无改动）
- 时间: 2026-10-17
- 零记忆: 是（不继承 Round 1/2 与任何开发上下文；Round 2 的 N-1…N-9 原文现读现核）

### Verdict

**CHANGES_REQUESTED**

理由：**N-1…N-9 逐条复核后 9 条全部已处置**（每条的原文要求都已在仓库里找到对应产物，证据见下），设计主体、四道机械门、delta 的增删改与 Decision 的逐条对应关系**全部实测通过**，本轮**没有推翻任何设计结论、没有需要用户拍板的问题**。但跨文档扫查找到 **1 条阻塞项**：`proposal.md:81` 的 RIR finding 1 在订正出处（N-2）时**新写进一个仓库里不存在的出处**——「同向记载另见 `docs/development-guide.md` 的 witnessloop 节」，而该文件全篇（含 witnessloop 节 `:343-420`）**没有任何** `--apply` 次序 / conversation resolution 的记载。这与 N-2 同类（出处假），且按本轮判据「**断言了仓库里查不到的事实**」属阻塞类；修法是一行（删该半句或改引本 delta 的 `specs/platform-gate/spec.md:42`）。其余 6 条为非阻塞观察，不列入 issue。

### N-1…N-9 逐条复核

- **N-1**: **已处置**。① 标题 `design.md:93` 现为「### Decision 5: 无代码面 ⇒ 不写 TDD 测试；benchmark smoke 因**触发面假阳性**而照跑；判据换成「规格文本可机械复核」」——与订正段同向；② 选择句 `:95` 现为「tasks 里**不排**「先写失败测试」一节；**benchmark smoke 照排并照跑**（tasks 2.4b，实测 PASS）」；③ `:97` 新增 `> ⚠️ **本节标题与选择句在第二轮对抗复核（N-1）时被指出自相矛盾**…已按订正后的口径统一为「**照跑**」`，把矛盾本身如实记档；④ 与 `tasks.md:3`「**benchmark smoke 仍然排了（2.4b）**」、`tasks.md:34` 的 `[x]` 一致。三方（标题 / 选择句 / 订正段 / tasks）现同向。
- **N-2**: **已处置（但修法自身引入新错，见「阻塞性新发现」）**。主引用已改对：`proposal.md:81` 现写「**本仓自己的记载**（出处 = `AGENTS.md:226`：「由主 session 在 PR 合入后执行——合入前 apply 会把对话 resolution 闸门锁住 PR 自身」…）」——实测 `grep -n "锁住" AGENTS.md scripts/platform-gate.json scripts/platform_gate.py` → 仅 `AGENTS.md:226` 命中且逐字一致；`scripts/platform-gate.json` 的五条 `_description`（`:3` / `:9` / `:13` / `:17` / `:21`）与 `scripts/platform_gate.py` docstring 均无该句（N-2 的事实判断成立）；`:82` 有 ⚠️ 出处订正段。
- **N-3**: **已处置**。三处齐了：① `docs/development-guide.md:356` 现为「- **grill 决策记录的格式契约（v1.7.0 实测，2026-10-17 补记）四条**：`reviews/grill-design.md` 必须含 `## Confirmed Decisions`（**至少 3 条**决策块——`MIN_CONFIRMED_DECISIONS = 3` 是硬门槛；且每条决策块内有**同行裸** `来源:`…）」；② delta 的 Scenario 标题 `specs/dev-workflow-gate/spec.md:37` = 「四条判据逐条可复核」（正文 `:35` 同为四条，`:47` 已改口「上述四条契约」）；③ `design.md:224`（R13）= 「把**四条**格式契约（含 `MIN_CONFIRMED_DECISIONS = 3`）写进规格与 `docs/development-guide.md`」。Decision 11 点名的两个可审计载体都已是四条。
- **N-4**: **已处置**。`proposal.md:64` 与 `tasks.md:26` 都删掉了总数口径，改为按位置列举并明写「**不写「共 N 处」这种会被自己文件证伪的总数口径**」；全仓 `grep -n "共 6 处\|共 N 处"` 只剩 `design.md:191`（Round 1 处置表的**历史记录行**，见非阻塞观察 3）。残留一处清单不完整（`proposal.md:64` 漏 `Q13:15`），非阻塞。
- **N-5**: **已处置**。`tasks.md:34-45` 现记录**实际执行的那条命令**（`--runs-dir /tmp/benchmark-gate-runs-sc`，与 `ci.yml:137` 的 `benchmark-gate` job 逐字同形、仅 runs-dir 不同）与原始输出，并记「**已跑，PASS**」。实测：产出确在 `/tmp/benchmark-gate-runs-sc/2026-10-16T19-05-06/`（`run.json`：`task_count 2 / passed 2 / failed 0`；`summary.md` 两条 task 全 `passed`），`/tmp/benchmark-gate-runs/` 仍是 10-05 的旧运行（与说明一致）。展示的输出块与 `benchmarks/gate.py:88-114` 的 `report()` 逐字同形（`BENCHMARK GATE` / `delta={:+.4f}` ⇒ `+0.0000` / `p95_latency_s: SKIPPED (deterministic task set)` / `result: PASS`），且 `benchmarks/baseline.json` 的 `metrics.success_rate = 1.0` ⇒ `baseline=1.0000 current=1.0000` 成立。
- **N-6**: **已处置**。`proposal.md:66` 新增独立条目「**受影响但本 change 不处置的既有状态（如实登记）**：active change `add-minimal-tui-runtime-view` 无 `reviews/`。**阶段 C 使这条已知红的性质发生迁移**——它此前只是 `gate / check` 的日志红…现在**会拦合入**。⇒ 任何触达该 change 目录的改动都会被它挡住；解除阻塞的前提是**收尾它**（补 `reviews/` 证据），**不是**为它放宽判据。本条已写进 `dev-workflow-gate` 的对应 Requirement（delta 的 MODIFIED）。」——I-5 要求的「proposal 侧那一行」到位，且与 delta `specs/dev-workflow-gate/spec.md:17`、`:26-31` 同向。
- **N-7**: **已处置**。delta 的 ADDED 正文 `specs/dev-workflow-gate/spec.md:86` 末尾现为「本条 SHALL 有三条边界：① **时效**——记录 SHALL 在行为落地后的**同一收尾批**内归档，未归档前该阶段 SHALL 视为未闭合；② **非先例**——它只约束「关闭接入阶段 / 切换门禁」这类治理动作，SHALL NOT 被类推为常规功能 change 的工作流；③ **不豁免需求先行**——本仓「需求先行」规则要求的是**需求讨论与需求文档**先于实现，本条只承认「记录形态的落地可以滞后」，SHALL NOT 被读成「需求没聊清楚就可以先写实现」」——三条边界随 delta 进规格，冲突方（规格义务）与 `design.md:140-145` 现同口径。
- **N-8**: **已处置**。`tasks.md:23`（1.4）/`:25`（1.6）/`:26`（1.7）已全部 `[x]`，且**每一项都能在仓库里找到产物**：1.4 → `docs/development-guide.md:354`（「② 阶段 A 的 change `witnessloop-adoption` 当时缺 witnessloop 形态 manifest（该 change **已归档**）」）与 `:355`（不再出现「本 change 自己」，改为阶段 A 实测口径）；1.6 → `README.md:149` 与 `README_EN.md:149` 已同改同向（实测两条逐字对应）；1.7 → `grep -rn "自动拦截" docs/` = **0 命中**。
- **N-9**: **已处置**。`design.md:217`（R6）现为「**档位被质疑为「省事」** | **已实发生并被处置**：初稿的 `exempt` 被设计阶段对抗闭环 I-6 判为「机械过闸」，**已改 `light` + `enabled`** 并补 findings / design impact（Decision 1）」；`:225`（R14）同向——不再把 `exempt` 写成已选档位。

### 阻塞性新发现

- **B-1（阻塞）`proposal.md:81` 新写进一个仓库里不存在的出处**。
  证据：该句为「**本仓自己的记载**（出处 = `AGENTS.md:226`：「…」；**同向记载另见 `docs/development-guide.md` 的 witnessloop 节**与 `openspec/specs/platform-gate/spec.md` 的「平台配置走 PR review」Scenario）」。逐项实测：
  - `AGENTS.md:226` ✅ 逐字成立。
  - `openspec/specs/platform-gate/spec.md` 的该 Scenario ✅ 成立（`:72`「合入后由持 admin 权限的执行者运行 `--apply` 落地，并用 `--verify` 复核」）。
  - `docs/development-guide.md` 的 witnessloop 节 ❌ **不成立**。`grep -ni "apply\|conversation\|锁\|闸门" docs/development-guide.md` → 全文件仅 `:318` / `:327` 命中（都在「业界调研门禁」档位表里，是「上游决策**锁定**」，与 platform-gate 无关）；witnessloop 节（`:343-420`）逐行读过：`:353` 只说「`platform_gate.py` … 全部照旧」、`:419` 只说「回退不需要动 `ci.yml`、`scripts/**` 或 branch protection」，**全节零 `--apply` 次序 / conversation resolution 记载**。
  为什么算阻塞：这条正是 N-2 定性的那类缺陷（「事实成立、**出处假**；升档到 `light` 的全部意义就是 findings 可核对，出处错会让后人按引用去查却查不到」——该判语就写在 `proposal.md:82` 的订正段里）。**它是 N-2 的修法自己引入的**，属本轮扫查要求专找的「修复引入新不一致」。按本轮判据「断言了仓库里查不到的事实」→ 阻塞类。
  修法（一行）：删掉「与 `docs/development-guide.md` 的 witnessloop 节」这半句；或改引本 change 自己的 delta `openspec/changes/stage-c-required-switch/specs/platform-gate/spec.md:42`（那条 SHALL 同步后自会成为当前规格的该 Scenario，届时原引用才成立）。

### 非阻塞观察

1. **Decision 4 的「不写两遍」规则只覆盖了 platform-gate 一侧，两份规格仍在重复断言同一件事**。`design.md:87` 的规则字面只约束「MODIFIED 的「合入平台闸门」条目」，而 dev-workflow-gate 的 ADDED 条目正文（`specs/dev-workflow-gate/spec.md:55`）**又把 required 集合（「`gate / check` 唯一」）与不变量（「SHALL 继续照跑但不拦合并」）各写了一遍** ⇒ 同步后同两件事同时住在两份规格里，而 Decision 4 的理由（「两处并存时，未来改一处漏一处不会被任何门禁发现——那是白送的漂移点」）恰好命中它。建议照 `specs/platform-gate/spec.md:11` 的做法在 dev-workflow-gate 那条加一行指针（把「仍须运行」指向 `platform-gate` 的 ADDED 条目），或把 Decision 4 的规则范围写清为「两份规格」。
2. **`tasks.md:13`（0.3）仍指向一个不再存在的选择**：现文为「对 Decision 1（`process` + **`exempt`** 的档位选择）与 Decision 3（REMOVED 的爆炸半径）做专门挑战」，而 Decision 1 已是 `light`（`design.md:40`、`:46`）。属「档位改 `light` 的修正没落齐到 tasks」这一类（同一改动的 `proposal.md:75` / `design.md:217` / `:225` 都改了）。该任务已由本文件的三轮记录实质完成，建议顺手把括号里的 `exempt` 改为 `light`（或删掉括号）。
3. **讲稿面处数/清单口径两处残留**：① `design.md:191`（Round 1 处置表 I-2 行）仍写「扫全 `docs/`：共 **6 处**一次性订正（Q12 / Q13×3 / Q09×2 / walkthrough:3895）」——同一行的括号自列 **7** 项，且与实测的 **9** 处（`798973e`：Q12×2 + `Q13:15`；`647e349`：Q13×3 + Q09×2 + walkthrough×1）都不符；② `proposal.md:64` 的清单漏 `Q13:15`（`tasks.md:26` 已列 `:13/:15/:51/:63`）。design 那处是历史记录行、proposal 那处是遗漏（不是假断言），故不列 issue；建议把 ① 改为「共 9 处（按位置列举）」、② 补 `:15`。
4. **收尾次序的两步在 tasks 的节顺序里有被误读的空间**（机制真实、修法一行）。Decision 6 ① 要求「内容提交」先于 ② 产 manifest，`tasks.md:56`（4.1）也写「在**所有内容提交之后**（含 1.4 与 backlog 清理）」——但 5.1 / 5.2 / **5.3（结算 `tasks.md`）** 都是内容提交，却排在 4.1 之后。实测机制：v1.7.0 的 `stale_exempt_paths`（`.witnessloop/policy.json` 未覆写时取默认，`policy.py:77-93`）= `(".witnessloop/**", "openspec/changes/*/reviews/**", "openspec/changes/*/workflow-events.jsonl", "openspec/changes/archive/**")`——**`changes_root/*/tasks.md` 不在豁免内**，而 `_check_git_span`（`contract.py:679-690`）要求「head_sha 之后只允许出现证据文件」⇒ 若先按 4.1 产 manifest、再按 5.3 改 `tasks.md`，T5 立刻判 stale（阶段 B 的 PR 亲身踩过并重排提交）。4.1 的「所有内容提交」在字面上已覆盖 5.3，建议再点名一次（「含 5.1 / 5.2 / 5.3」）把它钉死。
5. **Decision 5 记录的「benchmark 触发面假阳性」没有耐久落点**：`design.md:101-102` 写「如实登记，供将来决定是否收窄该启发式」，`tasks.md:46` 同向，但 `proposal.md:65` 明写本 change **不新增债务条目** ⇒ 归档后这条待决事项只活在本 change 的历史文档里，将来没人会翻到。要么在 `docs/known-debt.md` 记一条（那会引入受保护写入 + 解释事件，成本高于收益），要么在 `design.md` 那处明写「本条不转债务，理由：…」把「不去哪」也写实。
6. **`reviews/grill-design.md` 的 `## Open Questions` 节里仍是 D6/D7/D8 三条未被处置的**问句**（无 `Q<n>` 编号）**。归档点门实测不判红（见「排除掉的疑点」2），但读者可能误读为「本 change 仍有 3 条未决」。建议在该节加一句「（D6/D7/D8 已在 `design.md` 就地处置，非停轮项；本 change 的 Open Question 数为 0）」。

### 机械门（实跑原始结论，本轮）

| # | 命令 | 结论 |
|---|---|---|
| 1 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 30 passed, 0 failed (30 items)`，**exit 0**（含 `✓ change/stage-c-required-switch`） |
| 2 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | `OpenSpec artifact checks passed`，**exit 0** |
| 3 | `… --check-archived --skip-protected-paths --skip-backlog` | `OpenSpec artifact checks passed`，**exit 0**（stderr 一行：`[archived manifest check] tasks_hash 已按归档语境跳过（76 个 change；其余 hash 与字段仍校验）`） |
| 4 | `/home/happy/wl170/bin/python -c "…grill_evidence_findings(grill-design.md)…"` | `grill finevidence findings: []`，**exit 0** |

### 排除掉的疑点

1. **归档点门会不会被当前文档判红**——不会（本轮新做的模拟，非引用）。把 change 目录复制到 `/tmp` 的归档路径、把**除 `(post-merge)` 外**的全部任务勾掉（含 5.3），直接调 `_check_archived_completion_gate(dir)` → 只剩 **1 条**：`building-review.md missing — 归档点要求独立 subagent 审阅证据`（= 任务 3.1 未做，计划内）；`_untagged_unchecked_tasks(dir)` = **[]**。即 RIR 门、grill 门、Open Question 确认门、未勾任务门在归档点都**已具备通过条件**。另实测：任务 5.3 的正文虽含 `(post-merge)` 字样，但因不紧接任务号，`(post-merge)` 标记识别**不会**误命中它（该项被正确报为「未勾且未标」）。
2. **停轮确认门（`_unconfirmed_open_questions`）**——不会判红：`_extract_open_question_indexes(grill-design.md)` = `[]`、`_extract_user_confirmation_indexes` = `[]`、`_unconfirmed_open_questions` = `[]`（6 个二级标题：Reviewer / Confirmed Decisions / 需要修改的设计点 / Open Questions / User Confirmation / 风险）。「该节里是 D6/D7/D8 而非 `Q<n>`」这个**形式**恰好让判据沉默——机制见非阻塞观察 6。
3. **引用的行号是否都指对了位置**（抽查 6 处，全部成立）：`AGENTS.md:226` ✅；`design.md:159` 的 `src/witnessloop/evidence.py:295-297` ✅（`git show v1.7.0:src/witnessloop/evidence.py` 的该三行正是 `user_confirmation = sections.get(USER_CONFIRMATION_TITLE)` / `if user_confirmation is None:` / `findings.append(…缺少 ## User Confirmation 小节…)`）；`proposal.md:16-17` 的 `openspec/specs/platform-gate/spec.md:11`（required 列举句）与 `:13-17`（「benchmark-gate 为 required check」Scenario）✅；`proposal.md:17` / `design.md:14` 的 `openspec/specs/dev-workflow-gate/spec.md:7`（「阶段 A、只跑不拦、required 仍为两项」的 Purpose 段）✅；`design.md:153` 的死链 ✅（实测在 `:11`，属 Purpose 段 `:3-11` 内）；`design.md:242` 的「`AGENTS.md` 与 `platform-gate.json` 的 `_description` 里的裸 `python`」✅（`scripts/platform-gate.json:17` 确有 `python scripts/platform_gate.py --apply`）。
4. **设计里的「硬事实」是否都还能复核**（逐条实跑，全部成立）：`gh api …/branches/master/protection` → `contexts=["gate / check"]`、`strict=true`、`required_approving_review_count=0`、`enforce_admins.enabled=true`、`required_conversation_resolution.enabled=true`；`uv run python scripts/platform_gate.py --verify` → 逐字段 `match: true`、**exit 0**；PR #312（`gh pr view 312`）→ `mergeStateStatus BLOCKED` + `gate / check` FAILURE 与 `validate` / `benchmark-gate` / `windows-platform` 三项 SUCCESS 并存，三个时长 **6m54s / 15s / 2m2s** 与 `design.md:19` 逐字一致；`git rev-parse master origin/master` → `3c7196b2…` / `4b5cc7d1…`（= `design.md:241`）；`command -v python` → 无（= `:242`）；`/home/happy/witnessloop` HEAD `ae99256` 且 `describe --tags` = `v1`（= `:244`）；`tests/test_platform_gate.py` 已钉 `gate / check`（`:68` / `:151` / `:187`）（= `:100`）。
5. **delta 的 REMOVED / MODIFIED 目标会不会静默 no-op，以及 MODIFIED 会不会静默丢 Scenario**——都不会。四个目标标题在现状里逐字存在：`dev-workflow-gate/spec.md:52`（REMOVED）、`:86`、`:176`（MODIFIED）、`platform-gate/spec.md:9`、`:56`（MODIFIED）。逐条比对现状与 delta 的 Scenario 数：`platform-gate/spec.md:56` 现状 1 → delta 1；`dev-workflow-gate/spec.md:86` 现状 1 → delta 2（保留 + 新增迁移条）；`:176` 现状 2 → delta 2（按 Decision 11 重写，属预期替换，且替换掉的正是**被本 change 证伪的断言**「通篇加粗 ⇒ 结构性不可能判绿」与「7/7 条缺 `来源:`」）。delta 侧结构 = dev-workflow-gate（REMOVED 1 / MODIFIED 2 / ADDED 2）、platform-gate（MODIFIED 2 / ADDED 1），与 `design.md:52`、`:62`、`:87`、`tasks.md:20-21` 的逐条描述一致。
6. **两份 delta 覆盖的 `require_change_for` / 受保护路径面**——`.witnessloop/policy.json` 实测：`require_change_for = ["agent/**","scripts/**","web/**"]`、`protected_paths` 五项、`evidence.review_manifest_glob = reviews/*.manifest.json`、`events_file = workflow-events.jsonl`；本 change 的 diff 面（`docs/**` + `openspec/**`）不触达 `require_change_for` ⇒ R5 的「本 change 建立 change 目录即消掉 PR #311 第 1 条红」成立。另：本 change 自己的 PR 会触达 `openspec/specs/**` 与 `docs/openspec-change-backlog.md`（受保护写入）⇒ 任务 5.2 的 `current_spec_synced` / `backlog_updated` 解释事件是**必需**的（不是可选），且归档后事件文件仍被识别（`archive/**` 在 stale 豁免集内）。
7. **仓内路径引用全扫（26 条）**——不存在的 4 类全部「已声明为待修 / 待产 / 仓外」：`openspec/changes/witnessloop-adoption/reviews/acceptance-stage-a.md`（= Decision 10 / `tasks.md:24` 明写要修的**死链本体**）、`reviews/{grill-design,grill-adversarial,building-review}.md` 与 `reviews/building-review-manifest.json`（相对 change 目录，前两者已存在，后两者是 3.1 / 5.5 的待产）、`src/witnessloop/evidence.py`（**仓外** witnessloop 仓路径）、`.dev/reference-repos.txt`（`design.md:244` 自己写明本 worktree 不存在）。**无一条是「凭空引用的仓库事实」**——唯一的例外是本轮 B-1 指出的那段文字正文（不在路径扫描范围内，故靠人工逐句核出）。
