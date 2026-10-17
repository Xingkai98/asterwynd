# Grill 对抗（设计阶段审阅闭环）: review-loop-no-round-cap — Round 1

## Reviewer
- run id: paseo-grill-adversarial-review-loop-no-round-cap-r1
- 时间: 2026-10-17
- 零记忆: 是（未继承开发上下文；只读工作区文档、仓库事实与兄弟 worktree 的先例文档）

## Verdict
CHANGES_REQUESTED

## 六个挑战点

- **挑战点 1（D1 可判定性 + 窗口是否变相上限）**: **部分解决，仍未唯一可判定。** 给定序列按轮末开放数计算：R1=5 → R2=6 → R3=5 → R4=4（R2 关 3 开 4、R3 关 5 开 4、R4 关 6 开 5）。按「比较最近两轮轮末开放数、每轮检查」的读法，R2 的 5→6 没有下降 ⇒ **R2 即判无法收敛**；按「最近两轮中**新开**的必须修改项数」的另一种读法，R2 新开 4 < R1 新开 5（下降）、R3 新开 4 = R2 新开 4（不降）⇒ **R3 才判无法收敛**；若只在 R4 回看最近两轮，R3=5→R4=4 是下降，又**不应**判无法收敛。三种读法给出的停止点不同，设计/规格没有钉死度量对象与检查时点，因此「唯一判定」不成立。终局上该序列每一轮都有新项，永远不满足「没有新的可证伪项」，最终只能判无法收敛；但把 R2 就停掉的规则会掐掉一个 R3/R4 仍在净进展的闭环——这正是用户对 3 轮封顶的反感点。**「最近两轮」不是数值上限**（不限制轮数），但它是比先例 B′ 更严的**单区间停止触发**：先例是「最近两轮累计净额 ≤ 0」且最早第 3 轮才触发（`/home/happy/wl-wt/convergence-based-stop/openspec/changes/convergence-based-stop/design.md:169-173`、`:192-196`），本设计的一轮不降即停、且无 floor。证据：`design.md:47-48`、`:55-58`；spec delta `specs/dev-workflow-state-machine/spec.md:7`、`:11-13`、`:27-31`；`proposal.md:26`。
- **挑战点 2（BLOCKED 语义扩展的副作用）**: **版本控制内没有既有定义可冲突，但实际运行入口仍冲突。** 版本控制内检索 `BLOCKED` 只有 `AGENTS.md:107` 列出它是 verdict 之一，没有定义；`scripts/`、`docs/`、`openspec/specs/` 无 BLOCKED 判定规则。因此 spec 扩展本身不会与版本控制内文档产生歧义。但 agent 实际加载的入口 `/home/happy/my-agent/.claude/commands/review-loop.md:62-64` 明确写着 `BLOCKED: 阻塞性缺陷（核心功能缺失/安全漏洞/测试大面积失败）`，`:76` 的处理是「停，向用户报告阻塞项，等指示（不自行修复）」；新规格把 BLOCKED 扩为「闭环无法自行推进到 PASS」并加入「无法收敛」成因（spec delta `:7`），而 `tasks.md:65` 的 7.3 只同步 `:78`/`:87`/`:153` 三处轮数文案，**没有同步 `:64` 的 BLOCKED 定义**。⇒ 合入后规格说「无法收敛 → BLOCKED」，实际入口仍只把「阻塞性缺陷」认作 BLOCKED。另：spec 的「中等及以上严重度」只锚定在这份 gitignored 本地文件的 `:62-64`，版本控制内没有该 verdict 规则的定义。证据：`AGENTS.md:107`；`/home/happy/my-agent/.claude/commands/review-loop.md:62-64`、`:76`；spec delta `:7`；`tasks.md:65`；`design.md:122`。
- **挑战点 3（change-documentation MODIFIED delta 是否逐字正确）**: **正确，未发现非预期改动。** 用 `difflib.unified_diff` 对比 `openspec/specs/change-documentation/spec.md:29-118` 与 delta 的完整 Requirement，只有两个 hunk：① 正文 `until PASS or a round cap is reached` → `until the loop converges — no fixed round cap SHALL apply (see the termination-condition requirement in the dev-workflow-state-machine capability)`（含必要的换行重排）；② Scenario `until PASS or a round cap is reached` → `until the loop converges — no fixed round cap SHALL apply`。其余段落、6 个 Scenario、标题与空行均一致，没有漏行、改词或空白差异；新增的跨 capability 引用是收敛口径的组成部分，不是意外改动。`openspec validate --strict` 也通过（`30 passed, 0 failed`）。证据：上述 diff 命令输出；当前规格 `:46-47`、`:94`；delta `:22-24`、`:72`。
- **挑战点 4（T6 能否收敛到无命中）**: **不能——仍有设计未排除的假阳性，T6 的 exit 1 依旧不可达。** 实跑设计里的 T6（`design.md:140` / `tasks.md:37`）当前返回 **13 行**；其中 12 行是计划要改的现行规则（AGENTS 2、README 2、Q14 2、requirements-process 2、change-documentation 规格 2、checker 2），第 13 行是 **`tests/benchmark/test_c3_cli.py:3`**：`Covers the confirmed budget semantics: per-round cap stops remaining rounds,`。`-e "round cap"` 会命中 `per-round cap` 这个 benchmark 预算语义，而它**与审阅闭环无关、也不应被本 change 修改**。设计自己的 grill 记录已经知道这个文件（`reviews/grill-design.md:10`），但 T6 没加排除，所以改完 12 行后仍是 exit 0，和 grill D3 想消灭的失败模式完全同类。补充扫描：`docs/interview-bullets/interview-prep.md:185`、`walkthrough.md:1131` 的「最多 3 轮」是 `patterns.py` 的 PeerReviewPattern（多 agent 编排模式），`docs/architecture.md:95` / `agent/team/orchestrator.py:13` 的「每轮上限/封顶」是群聊轮次，均不属于审阅闭环、也不被 T6 模式命中；除上述测试文件外没有别的现行审阅闭环残留。证据：T6 实跑输出；`tests/benchmark/test_c3_cli.py:3`；`design.md:140`、`:144`；`tasks.md:37`；`reviews/grill-design.md:10`。
- **挑战点 5（RIR 升 full 是否名副其实）**: **档位与字段成立，但先例转述有一处过度定性。** `## Reference Implementation Research` 有 `research_tier: full`、`status: enabled`、reason、3 个 research questions、5 条 findings、4 条 design impact，字段齐全且有实质内容；reason 引用的 `AGENTS.md:37` 与 `docs/development-guide.md:316` 都确实是「走 grill 的非平凡 change ⇒ full」判据行。先例「草稿、未提交、未停轮」的转述与事实一致：`git ls-files` = 0、`git status` 为 `?? openspec/changes/convergence-based-stop/`、分支 `convergence-based-stop/2026-10-15`、proposal 自述草稿、design 的 Open Questions 未裁定。**但** `proposal.md:79` 与 `design.md:68` 把「另一处把封顶写成停轮理由后又跑了 R4–R6」写成「先例中可复核实录的部分 / 仓内记录里」；先例自己明确标注该样本是 **「时点旁证，在审 revision 之外，不可在 `ef8b3ab` 上复核」**，且文件在兄弟 worktree 里未提交、同日已从 R4 漂到 R6（先例 `design.md:73`、`:95`、`:105`）。可复核实录只有「3 轮 cap 下跑到 R5」这一条；R4–R6 只能作为时点旁证。证据：`proposal.md:69-87`；`design.md:62-71`；先例 `design.md:73`、`:95`、`:105`。
- **挑战点 6（新的阻塞性洞）**: **没有发现会让 strict validate / checker 判红的规格或结构错误，但有几处跨文档不一致。** 机械门全绿（见下）；新 Requirement 第一行含 SHALL，没有重复标题；`dev-workflow-state-machine` 现有 Requirement（`:254-258`）确实没有写轮数上限，用 ADDED 补终止条件而不是 MODIFIED 是合理的。具体不一致：① `design.md:122` 说本地任务在 `tasks.md` 的 **0.7** / `(post-merge)` 7.3，但 `tasks.md` 的 0 节只有 0.1–0.6，没有 0.7（实际只有 7.3）；② `proposal.md` 的 Impact Analysis（`:51-66`）没有列 `docs/openspec-change-backlog.md`，而 `tasks.md:54` 的 6.1 明确要改它；且 backlog 头部维护规则要求「新增 OpenSpec change 后……应把它加入本队列」，当前 `docs/openspec-change-backlog.md` 搜不到本 change（`grep review-loop-no-round-cap` 无命中）；③ `tasks.md:11` 的 0.1 与 `:16` 的 0.6 事实上已完成（`reviews/grill-design.md` 已存在、`grill_evidence_findings` 返回 `[]`），却仍是 `[ ]`——如果约定是「实现阶段再统一勾选」，应在 tasks 里说明，否则与实际状态不一致；④ BLOCKED 的运行入口未同步（挑战点 2）。证据：上述文件行号与 `grep` 输出；机械门输出见下。

## 机械门（实跑原始结论）

- `timeout 300 npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → `Totals: 30 passed, 0 failed (30 items)`，exit 0。
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` → `OpenSpec artifact checks passed`，exit 0。
- `grill_evidence_findings(grill-design.md, report_path='reviews/grill-design.md')` → `grill findings: []`，exit 0。
- T3（`--check-archived --skip-protected-paths --skip-backlog`）→ `OpenSpec artifact checks passed`，exit 0。
- T7a（归档前 `git diff --stat origin/master...HEAD -- openspec/changes/archive/`）→ 空输出，exit 0；当前 `git rev-list --left-right --count origin/master...HEAD` = `0 2`（落后 0、领先 2）。
- T5（当前时点）→ `check：未通过 ✗（2 项）`：缺 review manifest、无 stage=grill 的 manifest；这是实现/证据尚未产出的预期状态，不是设计缺陷。
- T6（当前时点）→ 13 行命中；按设计改完 12 行现行规则后，`tests/benchmark/test_c3_cli.py:3` 仍会命中（见挑战点 4）。

## D1–D8 的落实核验

- **D1**: **部分处置**。已把「必须修改项」钉到中等及以上严重度，并补了净进度判据；但「收敛」第一句仍是未加严重度限定的「没有出现新的可证伪项」，与「低价值建议不延长闭环」矛盾；且「最近两轮开放数」在 0→0 时也会被判「没有下降」⇒ 与「风格建议不阻断收敛」Scenario 冲突。证据：spec delta `:7`、`:15-19`；`design.md:47-48`；`proposal.md:26`。
- **D2**: **已处置**。`specs/change-documentation/spec.md` 的 MODIFIED delta 存在，逐字比对只改了两处 round cap，当前规格 `:46-47`、`:94` 都会被覆盖，`validate --strict` 通过。证据：上述 diff；delta `:22-24`、`:72`。
- **D3**: **部分处置**。T6 已加 change 目录/backlog 排除和英文变体，但仍漏掉 `tests/benchmark/test_c3_cli.py:3` 的 `per-round cap` ⇒ exit 1 仍不可达。证据：T6 实跑输出；`design.md:140`、`:144`；`tasks.md:37`。
- **D4**: **已处置**。T7 拆成 T7a（归档前必须为空）/T7b（归档后只出现自己的目录），R4 与 T7 的时序矛盾已消除；T7a 实测空输出。证据：`design.md:141-142`、`:123`；`tasks.md:38`；实跑输出。
- **D5**: **部分处置**。先例「草稿、未提交、未停轮」的订正是准确的；但 R4–R6 样本的「时点旁证、不可在 `ef8b3ab` 上复核」限定没有保留，仍被称为「可复核实录 / 仓内记录」；Decision 3 的边界也仍比先例严（单区间停止 vs 两轮累计净额、无 floor）。证据：`proposal.md:79`；`design.md:68`；先例 `design.md:73`、`:95`、`:105`、`:169-173`、`:192-196`。
- **D6**: **已处置**。`(post-merge)` 7.3 写死了 `/home/happy/my-agent/.claude/commands/review-loop.md` 的 `:78/:87/:153`、路径、grep 验收与「已改/未改」登记；但 `design.md:122` 把任务写成 `tasks.md` 0.7（不存在），实际是 7.3。证据：`tasks.md:65`；`tasks.md:9-16`（无 0.7）；`design.md:122`。
- **D7**: **已处置**。`research_tier: full` + `status: enabled` + reason + 3 个 research questions + 5 条 findings + 4 条 design impact 全字段齐全；`AGENTS.md:37` / `docs/development-guide.md:316` 判据行核对无误。证据：`proposal.md:67-87`。
- **D8**: **部分处置**。spec delta `:7` 已逐字定死「BLOCKED = 闭环无法自行推进到 PASS」并要求写成因（阻塞性缺陷 / 无法收敛），不新增终态；但运行入口 `.claude/commands/review-loop.md:64` 仍只把 BLOCKED 定义为阻塞性缺陷，7.3 没有同步该定义与收敛判据。证据：spec delta `:7`；`/home/happy/my-agent/.claude/commands/review-loop.md:62-64`、`:76`；`tasks.md:65`。

## Issues

- **I-1（severity high）**: **T6 的「无命中」判据仍不可达。** 改完设计列出的 12 行现行规则后，`tests/benchmark/test_c3_cli.py:3` 的 `per-round cap` 仍被 `-e "round cap"` 命中，T6 依旧 exit 0；它记录的是 benchmark 预算语义，不是审阅闭环，且不属于本 change 的修改面。证据：T6 实跑输出；`tests/benchmark/test_c3_cli.py:3`；`design.md:140`；`tasks.md:37`；`reviews/grill-design.md:10`。建议修法：在 T6 中显式排除 `':!tests/**'`（或至少 `':!tests/benchmark/test_c3_cli.py'`），或把英文模式收窄为不会被 `per-round cap` 命中的形式；在 T6 说明里点名该文件是排除项，并实跑确认全改完后 exit 1。
- **I-2（severity medium）**: **收敛定义仍有严重度/零基线矛盾。** 「收敛 = 没有出现新的可证伪项」没有限定中等及以上；一个低价值但可证伪的新项会同时（a）阻止收敛、（b）按「低价值建议不延长闭环」不应阻止 PASS。另，「最近两轮开放的必须修改项数没有下降」在 0→0 时也字面成立，会把「只有风格建议/零必须修改项」的干净闭环判成无法收敛，与 Scenario「风格建议不阻断收敛」冲突。证据：spec delta `:7`、`:15-19`；`design.md:47-48`；`proposal.md:26`。建议修法：把收敛第一句改成「没有新的中等及以上严重度可证伪项」，并把净进度判据限定为「开放必须修改项数 > 0 时比较」，或显式规定「下降」必须有正基线；同时规定两条判据的优先级。
- **I-3（severity medium）**: **「最近两轮」的度量对象与检查时点未钉死，且比先例的 B′ 更严。** 「最近两轮里开放的必须修改项数」可读作「最近两轮轮末的开放积压数」，也可读作「最近两轮中新开的项数」；设计没有说每轮检查还是回看检查。给定序列 R1=5→R2=6→R3=5→R4=4 在两种读法下分别于 R2/R3 触发；若 R4 回看又不应触发。先例的 B′ 是「最近两轮累计净额 ≤ 0」且 `n ≥ 3` 才触发；本设计是单区间不降即停、无 floor，会在 R2 掐掉之后仍在净进展的闭环——与用户「别在还净进展时停」的诉求相反。证据：`design.md:48`、`:58`；spec delta `:7`、`:27-31`；`proposal.md:26`；先例 `design.md:169-173`、`:192-196`。建议修法：采用先例的「最近两轮累计净额 ≤ 0」与第 3 轮 floor（或明确论证单区间规则的必要性），并把度量对象写成「每轮结束时开放的必须修改项数」；把该序列作为设计中的 worked example 或测试断言。
- **I-4（severity medium）**: **RIR/design 把 R4–R6 样本写成「可复核实录 / 仓内记录」，先例自己标的是「时点旁证、不可在 `ef8b3ab` 上复核」。** 这会重犯 D5 刚抓到的同类事实错误。证据：`proposal.md:79`；`design.md:68`；先例 `design.md:73`、`:95`、`:105`。建议修法：在 findings 与 design 中给 R4–R6 加「时点旁证、不可按图索骥」限定，并明确只有 R5 那一条是可复核实录。
- **I-5（severity medium）**: **BLOCKED 的语义扩展没有落到实际入口；「中等及以上」也没有版本控制锚点。** spec delta 把 BLOCKED 扩为包含「无法收敛」，但 agent 实际加载的 `.claude/commands/review-loop.md:64` 仍是窄定义，7.3 只同步三处轮数文案；照此合入，规格与实际操作会分叉。spec 的「审阅 verdict 规则里的中等及以上严重度」也只存在于该 gitignored 文件 `:62-64`。证据：spec delta `:7`；`/home/happy/my-agent/.claude/commands/review-loop.md:62-64`、`:76`；`tasks.md:65`；`design.md:122`。建议修法：把 7.3 扩为同时更新 `:64` 的 BLOCKED 定义和步骤 5 的收敛/无法收敛规则，并在 tasks 中登记；或在规格里直接写出「中等及以上」的判定口径，避免依赖版本控制外的文件。
- **I-6（severity low）**: **`design.md:122` 引用了不存在的 `tasks.md` 0.7。** 实际本地任务只有 `(post-merge)` 7.3；0 节只有 0.1–0.6。证据：`design.md:122`；`tasks.md:9-16`、`:65`。建议修法：改为「`tasks.md` 的 `(post-merge)` 7.3」。
- **I-7（severity low）**: **backlog 的 Impact Analysis/维护规则不一致。** `proposal.md:51-66` 的 Impact Analysis 没有列 `docs/openspec-change-backlog.md`，但 `tasks.md:54` 的 6.1 明确要修改它；且 backlog 头部维护规则要求新增非占位 change 后加入队列，当前 backlog 搜不到本 change。证据：`proposal.md:51-66`；`docs/openspec-change-backlog.md:5-9`；`grep -n "review-loop-no-round-cap" docs/openspec-change-backlog.md` 无命中；`tasks.md:54`。建议修法：把 backlog 加进 Impact Analysis，并在 proposal 或 tasks 里说明「本 change 在收尾时登记并移除」的时序理由，或现在就补登条目。

## 非阻塞观察

- `design.md:144` 的「32 行 / 22 行」算术在 `reviews/grill-design.md` 落盘后已过时：同一「排除 archive」的中文扫描现在返回 **39 行**（新增的 grill 报告自己引用了旧口径）。这不影响 T6（该目录被排除），但下一个人复跑时会对不上数字。
- `tasks.md:11` 的 0.1 与 `:16` 的 0.6 事实已完成却仍为 `[ ]`；如果约定是实现阶段统一勾选，建议在 tasks 顶部写明，避免完成度门禁/审阅者把「已做未勾」误读为未完成。
- `design.md` 的 Testing Strategy 用 `uv run python ...`；本 worktree 里 `uv` 不在 PATH（本次用 `PYTHONPATH=. python3` 跑通）。这是环境提示，不是设计缺陷；执行者按仓库惯例先 `export PATH=/home/happy/.local/bin:$PATH` 或直接用 `python3`。
- 关联 issue #305 在 `tasks.md:63`（7.1）明确「保持 OPEN」，与 AGENTS.md 的通用「合入时关闭关联 issue」规则存在表面张力；因为它是多阶段跟踪 issue，这个选择合理，但 proposal 可以补一句「跟踪 issue，不随单个 change 关闭」，避免后续收尾审查追问（grill R-I 已提过）。

## 排除掉的疑点

- **delta 不是整条重写**：`difflib.unified_diff` 只产生两个 hunk；除两处 round-cap 改写和一处跨 capability 引用外，Requirement 正文、6 个 Scenario、标题、空行与当前规格一致；没有漏 Scenario。
- **ADDED 选型正确**：`openspec/specs/dev-workflow-state-machine/spec.md:254-258` 的现有「开发流程精简为 OpenSpec 主干 + 强制审阅闭环」确实没有写实现后闭环的轮数上限，所以不需要 MODIFIED 重写这条长 Requirement；新增终止条件 Requirement 是补缺。
- **RIR full 不是空壳**：`proposal.md:67-87` 的 research_tier/status/reason/research questions/findings/design impact 全字段存在且有实质内容；判据行 `AGENTS.md:37`、`docs/development-guide.md:316` 核对无误。
- **先例「草稿、未提交、未停轮」属实**：`/home/happy/wl-wt/convergence-based-stop` 的 `git ls-files` = 0、`git status` = `?? openspec/changes/convergence-based-stop/`、分支 `convergence-based-stop/2026-10-15`、proposal 自述草稿、design 的 Open Questions 未裁定。
- **T7a/T7b 拆分正确**：归档前 T7a 实测空输出；归档后 T7b 的「只出现自己的归档目录」对应另一个时点，二者不再共用同一期望。
- **不会因 SHALL/标题/Schema 判红**：`openspec validate --all --strict` 通过；新 Requirement 第一行含 SHALL；现有 spec 中无同名 Requirement。
- **没有别的审阅闭环残留**：`docs/interview-bullets/interview-prep.md:185`、`walkthrough.md:1131` 的「最多 3 轮」属于 `patterns.py` 的 PeerReviewPattern；`docs/architecture.md:95` / `agent/team/orchestrator.py:13` 属于群聊轮次；`docs/interview-script/questions/Q14-dev-process.md:17` 的「3 轮审阅」是 #99 的历史案例，保留正确。它们都不是现行审阅闭环规则，也都不被 T6 的模式命中。
- **checker 只改提示文案是安全的**：`scripts/check_openspec_artifacts.py:1139`、`:1623` 的字符串没有测试钉住（`git grep "3 轮封顶" -- tests/` 为空）；改字符串不影响判定逻辑。
- **T5 当前红不是设计错误**：当前时点还没有 review manifest 与 stage=grill manifest；设计的 T5 明确要求在所有内容提交并产出三份 manifest 之后才跑。
- **`.claude/commands/review-loop.md` 的本地性判断正确**：该文件被 `.gitignore` 忽略、不在版本控制内，本 PR 不应包含它；但它仍是实际入口，所以需要 7.3 的本地同步（见 I-5）。
- **README 中英同步已覆盖**：`tasks.md:22`（1.3）同时列了 `README.md:148` 与 `README_EN.md:148`，符合仓库的 README/README_EN 同步规则。
- **无运行时行为/依赖变化**：本 change 只改文档、规格和两处提示字符串；不需要新增单元测试，测试策略由 T1–T7 的机械验收承担。
