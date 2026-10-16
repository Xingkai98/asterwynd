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
