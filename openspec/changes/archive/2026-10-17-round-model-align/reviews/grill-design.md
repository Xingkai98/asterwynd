# Grill: round-model-align 设计追问

## Reviewer
- run id: grill-round-model-align-2026-10-17
- 时间: 2026-10-17（UTC）
- 零记忆: 是

## Confirmed Decisions
- **决策**: 一轮 = 一个非空 medium+ 批次的完整闭环（开批 → 开发者全修 → 审阅者只做修复验证 → 全部通过收口）；未修好仍是同一轮，不另计轮。；理由: 与 witnessloop `templates/review-loop.md` 及归档 `2026-10-17-convergence-based-stop` 的逐字定义一致，直接修复旧口径「轮不可数、单轮工作量无界」的缺陷。；来源: grill-round-model-align-2026-10-17-d1
- **决策**: 最多 20 个已收口轮；第 20 轮自身达到验证重试终止点，或第 20 轮收口后的收口确认仍有 medium+ ⇒ 超上限 `BLOCKED` +「建议推倒重开（revise the design）」；`CHANGES_REQUESTED` 只是轮内状态，不是出口。；理由: 20 是安全上限而不是「到点收工」；三种出口与上游一致，且能区分通用 `BLOCKED` 与超上限 `BLOCKED`。；来源: grill-round-model-align-2026-10-17-d2
- **决策**: medium+ 必须全部修完并验证通过；low/nit 可登记不修但须逐条写理由；severity 随批次冻结；deferred medium+ 以原 id 进入下一轮批次；最终 `PASS` 报告携带累积 low/nit 登记。；理由: 与用户拍板口径及上游 Requirement 一致，防止「为收口而改级」和「把早期登记从报告面抹掉」。；来源: grill-round-model-align-2026-10-17-d3
- **决策**: 设计对抗环与实现审阅环共用同一批次模型；frontier 追问轮豁免仅指进入对抗环之前、为求设计树完备的内部轮；设计环的 `BLOCKED` 成因映射与修复证据对应物按上游定义。；理由: 两环同构是用户拍板项；不把 frontier 混计为审阅轮，避免 20 上限错误约束设计探索。；来源: grill-round-model-align-2026-10-17-d4
- **决策**: 机械门禁不新增正文解析；文档守卫使用显式 allowlist 且不回填历史归档/历史 review；本地 gitignored 入口 `/home/happy/my-agent/.claude/commands/review-loop.md` 单独同步。；理由: 本 change 是规则镜像而非门禁增强；显式 allowlist 可避免全仓减排除误伤历史，但必须补足 per-file 映射与旧词表。；来源: grill-round-model-align-2026-10-17-d5
- **决策**: issue #305 保持 OPEN，作为阶段 C 的跟踪入口；本 change 合入后只追加 comment，不关闭该 issue。；理由: 用户已明确指定；但该决定与 `AGENTS.md:17` 的「合入即关闭」字面冲突，必须在 post-merge comment 中说明这是刻意的阶段 C 例外。；来源: grill-round-model-align-2026-10-17-d6

## Code-Resolved Questions
- `## REMOVED Requirements` + `## ADDED Requirements` 的 delta 合法吗？ → 合法；delta 使用标准节（`openspec/changes/round-model-align/specs/dev-workflow-state-machine/spec.md:3-21`），实测 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 为 30 passed / 0 failed。
- 本 change 改 `scripts/**` 会触发哪些 witnessloop stage？ → `grill` 恒被要求；`code_hits` 另触发 `grill-adversarial` 与 `building`（证据：`.witnessloop/policy.json:11-13`、`witnessloop/src/witnessloop/checkcmd.py:86-108`）。因此 design Goals 的「两个 stage」少算了 `grill`，tasks 6.1 的三份 manifest 才是正确口径。
- asterwynd 的 `scripts/check_openspec_artifacts.py` 会检查孤儿报告或 `reviewer_run_id != author_run_id` 吗？ → 不会；它只 glob `*-review.md` 并校验 manifest 字段/hash（证据：`scripts/check_openspec_artifacts.py:1150`、`agent/workflow/review_manifest.py:136-170`）。孤儿报告与 reviewer/author 身份是 witnessloop `check` 的判据（`witnessloop/src/witnessloop/contract.py:146-215,258`）。
- 旧口径还有哪些规范面落点未被 Impact Analysis 覆盖？ → `openspec/specs/dev-workflow-state-machine/spec.md:258`（Requirement 正文）与 `:347`（Scenario）仍写「再审直到收敛」；proposal 的影响面只列了 `:445-486`（`openspec/changes/round-model-align/proposal.md:90-91`）。
- `change-documentation` 的 MODIFIED delta 是否保留了其余正文？ → 是；与当前 spec 逐段 diff 仅命中设计环段落与一个 Scenario（当前 `openspec/specs/change-documentation/spec.md:41-55,88-98` vs delta `:17-36,69-85`），其余正文逐字一致。
- 设计环 verdict 列表在两个 delta 间一致吗？ → 不一致；`change-documentation` delta `:21,:74` 只写 `PASS` / `CHANGES_REQUESTED`，而 `dev-workflow-state-machine` delta `:83,:93-102` 的轮内 verdict 与出口包含 `BLOCKED`。
- 本地入口在哪里、是否被 gitignore？ → `/home/happy/my-agent/.claude/commands/review-loop.md`；`git check-ignore` 命中 `.gitignore:9`；该文件当前仍写「3 rounds」「无轮数上限」（`/home/happy/my-agent/.claude/commands/review-loop.md:3,8,78,87,153`），task 4.4 的同步方向正确。
- 归档 move 会把 `reviews/` 下的证据一起搬走吗？ → 取决于跟踪状态：当前 `openspec/changes/round-model-align/reviews/` 为空；报告生成后若未 `git add`，`git mv` 只移动已跟踪文件，归档目录会缺 grill/building 证据（tasks 7.4 只写「手工 git mv」）。
- 本 change 改文档/规格会触发 asterwynd 本地 guard 死锁吗？ → 不会；`.claude/` 被 gitignore（worktree 没有本地 hook），且 change 文档与 `reviews/` 写操作被 `_is_change_doc_write` 豁免（`scripts/workflow_guard.py:517-533`）。真正的门槛是 CI 的 witnessloop `check`。
- `review-loop` 的三处提示文案有测试断言吗？ → 没有；`tests/` 无对应断言，新增测试必须自己钉住（证据：`scripts/check_openspec_artifacts.py:1139,1623,1640`；`git grep` tests 无命中）。
- issue #305 与 AGENTS.md 的 issue 关闭规则冲突吗？ → 有字面冲突：`AGENTS.md:17` 要求合入时给 issue 加完成说明并关闭；`openspec/changes/round-model-align/proposal.md:3` 与本次任务指定保持 OPEN。按用户指定保留 OPEN，但 tasks 8.1 的 post-merge comment 应写明阶段 C 例外理由。
- `change-documentation` delta 的「implementation-phase `/review-loop` SHALL remain unchanged」与新模型冲突吗？ → 冲突；同一 delta 要求两环共用有界批次模型，而 `openspec/changes/round-model-align/specs/change-documentation/spec.md:33-36` 仍写 implementation loop「remain unchanged」，应改为「继续作为独立环存在，且两环都使用同一批次模型」。
- 当前工作区是否有未提交的 delta 改动？ → 有；`git status` 显示 `openspec/changes/round-model-align/specs/change-documentation/spec.md` 有一处措辞微调（去掉 `"until convergence"` 括注）。收尾提交时不要丢失该改动。

## Open Questions
（无）

## 风险
- R1｜规范面漏改：`openspec/specs/dev-workflow-state-machine/spec.md:258,347` 仍以「再审直到收敛」描述设计环；若不改，新的「有界批次 × 20 上限」与旧流程叙述并存，文档守卫也不会变红。
- R2｜守卫是「全局在场」而非「逐文件映射」：`design.md:206-209` / `tasks.md:25-26` 只要求七要素出现在 allowlist 合并文本中；某个文件可以整体保留旧口径但不含旧词表条目而仍通过。上游 dogfood 已踩过「七要素→文件映射只部分落地」（`witnessloop/openspec/changes/archive/2026-10-17-convergence-based-stop/tasks.md` 的 C1 与 R1-4），应镜像其 per-file 映射。
- R3｜旧词表不完整：`无轮数上限` / `最近两轮` / `3 轮封顶` / `轮数封顶` / `round cap` / `no fixed round limit` / `no round limit` 之外，`再审直到收敛`、`until convergence`、`收敛即停` 仍在当前规范/README/requirements-process 中出现；若实现漏改，守卫不会报。
- R4｜归档证据搬移：`reviews/` 是未跟踪目录，`git mv` 不会自动带走未 `git add` 的报告；归档目录缺 `grill-design.md` / `grill-adversarial.md` / `building-review.md` 会让归档点门和 witnessloop 孤儿规则同时变红。
- R5｜机械判据表述混用：delta 的「既有判据」把 witnessloop `check` 的孤儿报告/reviewer 身份与 asterwynd `check_openspec_artifacts.py` 的 manifest/hash 判据混在一起；读者可能误以为本地 checker 也检查这些。
- R6｜归档后未重跑 witnessloop `check`：tasks 6.2 在归档前跑；7.5 归档后才重建 manifest，若不在归档后重跑一次，本地绿证据与最终 head 不一致（CI 会兜底，但本地证据不完整）。
- R7｜本地 `/grill` 入口未同步：本 change 只计划同步 `review-loop.md`；`/home/happy/my-agent/.claude/commands/grill.md` 没有设计阶段对抗环的说明，可能继续按旧流程执行设计环。
- R8｜squash 合入：manifest 的 `head_sha` 会失去祖先链，后续触及本 change 目录的 PR 会假红；tasks 7.6 的 `--merge` 要求必须保留。
- R9｜测试断言不可执行：tasks 1.4 的「用 diff/结构断言判定逻辑未被改」没有一个在合入后仍稳定的实现（对 `origin/master` 做 diff 会在合入/变基后失真）；应改为「新提示文案在场 + 旧提示文案不在场」的稳定断言，逻辑不变由审阅/witnessloop 证据承担。

## User Confirmation
- **Q1**: 用户答复：轮 = 一个非空 medium+ 批次的闭环（开批 → 全修 → 只做修复验证 → 收口）；确认时间: 2026-10-17
- **Q2**: 用户答复：最多 20 个已收口轮，超限 ⇒ 超上限 `BLOCKED` +「建议推倒重开（revise the design）」；确认时间: 2026-10-17
- **Q3**: 用户答复：medium+ 必须全修；low/nit 可登记不修但须逐条写理由；确认时间: 2026-10-17
- **Q4**: 用户答复：设计对抗环与实现审阅环共用同一模型；grill 的 frontier 追问轮豁免（仅指进入对抗环之前的求完备阶段）；确认时间: 2026-10-17

## 需要修改的设计点
1. **【必须修改】补当前规格的两处旧口径落点**（问题：`openspec/specs/dev-workflow-state-machine/spec.md:258` 的 Requirement 正文和 `:347` 的 Scenario 仍写「再审直到收敛」，与新的有界批次模型并存；proposal 的 Impact Analysis 只列 `:445-486`）。建议：在 `specs/dev-workflow-state-machine/spec.md` delta 增加对「开发流程精简为 OpenSpec 主干 + 强制审阅闭环」的 MODIFIED 块（或至少让这两处引用新 Requirement），并同步 proposal/tasks 的影响面清单与 `design.md:206-209` 的旧词表。
2. **【必须修改】修正 change-documentation delta 的「remain unchanged」**（问题：delta 的 `:33-36` 说实现环「SHALL remain unchanged」，与本 change 让两环共用批次模型矛盾）。建议：改为「继续作为独立的实现后审阅环存在；两环都使用 `dev-workflow-state-machine` 的有界批次模型」。
3. **【必须修改】补齐 change-documentation delta 的 verdict/出口**（问题：`:21` 与 `:74` 只列 `PASS` / `CHANGES_REQUESTED`，漏了轮内 `BLOCKED` 与三种出口；第 20 轮重试终止点也未写）。建议：在 verdict 列表加入 `BLOCKED`（并说明只有终结时的 `BLOCKED`/超上限 `BLOCKED` 才是出口），同时写明第 20 轮终止点 ⇒ 超上限 `BLOCKED`。
4. **【必须修改】补齐 dev-workflow-state-machine delta 的上游镜像缺口**（问题：`specs/dev-workflow-state-machine/spec.md:51-54` 未写「验证期把 low 重分类为 medium+ ⇒ 进 deferred」；`:76-79` 未写第 20 轮收口确认发现 low/nit 仍可 `PASS` 并用 `C-<序号>`；`:67-69` 未写「重置计数只能来自用户明确裁决并记为 `BLOCKED`/建议重开设计」；`:66-74` 缺「第 20 轮第一次未修好但开发者有新可验证方案 ⇒ 同轮继续」Scenario；`:81-91` 未要求多轮同文件时每轮小节标题带轮次）。建议：逐条补入 delta 的 Requirement 或 Scenario。
5. **【必须修改】把文档守卫改成 per-file 映射**（问题：`design.md:206-209` 与 `tasks.md:25-26` 只断言七要素在 allowlist 合并文本中出现；某个文件可以整体保留旧口径而仍通过）。建议：为每个必须文件定义它必须包含的核心要素（至少 `AGENTS.md`/两份规格/README/requirements-process/Q14 各自覆盖轮定义与 20 上限），并补入 `再审直到收敛`、`until convergence`、`收敛即停` 到旧词表。
6. **【必须修改】修改 tasks 1.4 的「判定逻辑未被改」断言**（问题：`tasks.md:27` 要求用 diff/结构断言证明 checker 判定逻辑未变；对 `origin/master` 的 diff 在合入或变基后会失真，无法作为长期测试）。建议：测试只断言三处新提示文案在场、旧文案不在场；逻辑未变由 building review 逐行核对 + witnessloop 证据承担。
7. **【必须修改】补归档 move 的证据前置检查**（问题：`tasks.md:70-71` 只写手工 `git mv`；当前 `reviews/` 为空且未跟踪，报告生成后若未 `git add`，`git mv` 不会搬走未跟踪文件，归档目录会缺证据）。建议：在 7.4 前增加「`git add reviews/` 并确认 `git ls-files` 包含三份报告」的检查；归档后核对归档目录包含 `grill-design.md`、`grill-adversarial.md`、`building-review.md` 及两套 manifest。
8. **【必须修改】点名机械判据属于哪一侧 checker**（问题：`specs/dev-workflow-state-machine/spec.md:113-117` 与 `design.md:186-191` 把 witnessloop `check` 的孤儿报告/reviewer 身份判据与 `scripts/check_openspec_artifacts.py` 的 manifest/hash 判据混写）。建议：分别写「witnessloop `check`：孤儿报告、reviewer/author、revision/hash、stage=grill 正文」与「`check_openspec_artifacts.py`：manifest 字段/hash/verdict、`*-review.md` 绑定；本 change 只改三处提示字符串」。
9. **【低风险/补强】修正 design Goals 的 stage 数**（问题：`design.md:33-34` 写「触发 building 与 grill-adversarial 两个 stage」，但 witnessloop 对每个 change 恒要求 `grill`；tasks 6.1 已写三份 manifest）。建议：改为「恒有 `grill`；因 `scripts/**` 另触发 `grill-adversarial` 与 `building`，共三份」。
10. **【低风险/补强】归档后重跑 witnessloop `check`**（问题：tasks 6.2 在归档前跑，7.5 归档后才重建 manifest，缺少归档后的一次本地复核；上游归档 tasks E3 有此步骤）。建议：在 7.5 后增加 `witnessloop check --root . --base origin/master --head HEAD` 并记录原始输出；CI 的 `gate / check` 仍作为最终门。
11. **【低风险/补强】本地 `/grill` 入口核对**（问题：本 change 只同步 `review-loop.md`；`/home/happy/my-agent/.claude/commands/grill.md` 没有设计阶段对抗环的说明，可能继续按旧流程执行设计环）。建议：至少把该文件的「设计阶段对抗环 / frontier 豁免 / 20 上限」补齐，或在 tasks 4.4 明确记录「本地 grill 入口另行核对，未同步」的边界。
