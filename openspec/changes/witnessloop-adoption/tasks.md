# Tasks: witnessloop 影子接入（阶段 A）

> **状态：立项文档**。以下任务全部**未开始**。设计追问（`grilling`）与 `## Open Questions` 三条确认完成前，不得执行阶段 A 的任何写操作（不跑 `witnessloop init`、不建 caller workflow、不装 plugin）。
>
> **测试先行**含义：本 change 不写 Python 测试，它的「测试」是**在新流程上跑一个真实需求**。因此每个阶段的顺序都是「**先定义验收判据与负向对照 → 再落产物**」——不能先落产物再补判据，那会把「判据」退化成「事后自证」。

## 0. 设计追问与用户确认（前置门，不完成不开工）

- [ ] 0.1 用 `grilling` skill 对本 `design.md` 做独立设计追问，产出结构化决策记录到 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条）。
- [ ] 0.2 把 `design.md` 的 `## Open Questions` 三条（Q1 解释事件类型名映射 / Q2 `require_change_for` 最终面与 `benchmarks/**` 取舍 / Q3 `openspec/specs/**` 是否列 protected）**逐条停下抛给用户**，每条附 design 里的推荐值 + 具体例子，等待明确答复。
- [ ] 0.3 把三条答复逐条记进 `reviews/grill-design.md` 的 `## User Confirmation`（格式 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`）。
- [ ] 0.4 按 `grill-flow-hardening`（issue #298）跑**设计阶段审阅闭环**（独立零记忆审阅者 → 对抗分析 → verdict → 修 → 再审，直到 PASS 或轮数封顶），产出 `reviews/grill-adversarial.md`；**能由代码判定的 Open Question 用带证据（`文件:行号`）的答案移出停轮队列**。
- [ ] 0.5 把三条答复落到 `design.md` 的 `## Decisions`（从 Open Questions 升级为已定决策），并据此定稿 policy seed 的四个字段值。

## 阶段 A：影子接入（只跑不拦）

**A 的出口判据**：本分支 PR 的 CI 里出现 `gate / check` job 并**跑出 findings**；`master` 的 required 仍是 `["validate", "benchmark-gate"]`；旧 checker 与 `validate` job 行为**逐字节不变**。

### A.1 先写判据与负向对照（测试先行）

- [ ] A.1.1 写下阶段 A 的验收判据（7 条）：① `init --dry-run` 待建文件 = 4 个且零冲突；② 本分支 PR CI 出现 `gate / check` 并跑出结果；③ **触发面验证**（用**探针 diff**，见 A.3.4 的说明——本 change 自己的 diff 不触 `require_change_for`，`code_hits` 为空，所以两条 stage 判定**本来就不触发**，必须用探针才能验）；④ **负向对照**：同一探针 diff 下换出厂 policy，这两条判定**消失**；⑤ `validate` / `benchmark-gate` 与本 change 前逐字节一致、branch protection 的 `contexts` 未变；⑥ **双守卫实测**（A.4.5）；⑦ **本 change 自己有一份 witnessloop 形态的 grill manifest**（A.5.6），验收里第一次出现「绿」的一侧。
- [ ] A.1.2 记录基线：本分支起点 `gh api repos/Xingkai98/asterwynd/branches/master/protection` 的 `contexts` / `strict` / `required_approving_review_count` / `required_conversation_resolution.enabled` 四项实况，写进阶段 A 验收报告（供 A.5.3 复比对）。

### A.2 定制 policy seed（仓外临时文件，不入库）

- [ ] A.2.1 按 0.5 定稿的字段值，在仓外临时路径（如 `/tmp/witnessloop-asterwynd-policy.json`）写**完整** policy：`changes_root` / `protected_paths` / `require_change_for` / `required_artifacts` / `evidence.review_manifest_glob` / `evidence.events_file` / `evidence.protected_write_event_types`（基线形态见 `design.md` Decision 1；三个待定值按 0.3 的答复填）。
- [ ] A.2.2 自查 seed：`protected_paths` **不含** `openspec/changes/archive/**`（Decision 3）；`review_manifest_glob` **保持 witnessloop 默认 `reviews/*.manifest.json`**（Decision 2——**不放宽**成 `*-manifest.json`）；`protected_paths` 与 `protected_write_event_types` **配套**（否则出现死配置，见 Q6）；`required_artifacts` 与 asterwynd 现有 change 目录必需件同形。
- [ ] A.2.3 确认 seed **不进 PR**（`git status` 干净、仓外路径），产物 `.witnessloop/policy.json` 才入库。

### A.3 落接入产物

- [ ] A.3.1 在 building worktree 跑 `witnessloop init --root . --policy <seed> --test-command "<asterwynd 测试命令>"`；`--test-command` 的值取本仓现有 CI 的测试口径（对应 `.github/workflows/ci.yml` 的 `validate` 里那一步），**必须是真实可跑的命令**、不得留哨兵 `<<REPLACE-ME>>`。
- [ ] A.3.2 核对产物 = 4 个文件（`.witnessloop/policy.json` / `.witnessloop/init-manifest.json` / `.github/workflows/witnessloop.yml` / `.github/witnessloop-tests.txt`），且 `.github/workflows/ci.yml` **未被触碰**。
- [ ] A.3.3 本地跑一次 `witnessloop check`（`uv run witnessloop check --root .`，用 worktree 里的补丁版本、**不用**全局安装的那份——**验证一律用 `uv run witnessloop`**，裸 `witnessloop` 可能是另一份 uv-tool 装的、测不到本 worktree 的补丁），逐条读 findings 并把原始输出粘进阶段 A 验收报告。
- [ ] A.3.4 **触发面验证与负向对照**（判据 ③/④，需**探针 diff**）：本 change 自己的 diff **不触** `agent/**` / `scripts/**` / `web/**` ⇒ `code_hits` 为空 ⇒ `building` / `grill-adversarial` 判定**本来就不触发**，无法用本 change 自身验证触发面。做法：在**隔离副本**（`rm -f .git && git init -q` 复制一份，别在被审 worktree 上操作）造一个改 `agent/**` 的探针 diff，分别用**定制 policy** 与**出厂 policy** 跑 `check`，确认前者两条 stage 判定出现、后者消失；把两次输出并列记入报告（这是「定制 policy 必要」的**证伪证据**，不是推理）。

### A.4 本地交互层（不进 PR）

- [ ] A.4.1 从 witnessloop 仓的 `plugin/` 装 Claude Code plugin（`commands/` 下的 `grill` / `review-loop` + `hooks/` 的 guard hook）。
- [ ] A.4.2 确认安装是**本地动作**：`.claude/` 被 `.gitignore:9` 忽略 ⇒ 不进任何 diff、不产生 PR。
- [ ] A.4.3 把安装/卸载/升级步骤写进 `docs/development-guide.md`，使这个「没有评审记录」的本地动作至少有**版本控制内的书面记录**（R5 的缓解）。
- [ ] A.4.4 确认本地层与 CI 层**互不依赖**：不装 plugin 时 CI 门禁照跑；装 plugin 也不会自动勾 required。
- [ ] A.4.5 **双守卫并存实测**（Decision 8 / R9，判据 ⑥）：装好 plugin 后，对一条 `agent/**` 路径触发一次 `Write`（该 change 没有 `stage=grill` 的 manifest），记录三件事——① 本仓 `scripts/workflow_guard.py`（matcher `Write|Edit|Bash`）与 plugin 的 guard（matcher `Write|Edit`）是否**都**执行、串行还是并行；② 被拦时提示归属哪个守卫（两个都出还是只出一个）；③ plugin 的 `grill` / `review-loop` 命令与仓内 `.claude/commands/` 下同名命令是否命名空间冲突。三项**全部实测**，不得由推理代替。

### A.5 验收与回归确认

- [ ] A.5.1 开本分支的 PR，确认 CI 里**新增** `gate / check` job 并跑出结果（判据 ②）。
- [ ] A.5.2 确认本 job **未进 required**（`gh api …/protection` 的 `contexts` 仍为 `["validate", "benchmark-gate"]`）。
- [ ] A.5.3 与 A.1.2 的基线逐项比对 `validate` / `benchmark-gate` 的行为与 branch protection 四项实况，确认未变（判据 ⑤）。
- [ ] A.5.4 在 `docs/development-guide.md` 新增「witnessloop 影子接入」一节：明确写「阶段 A 不 required、只跑不拦」，给出本地跑 `check` / `guard` 的命令，以及卸载路径（R1 的缓解）。
- [ ] A.5.5 把 A 阶段验收报告落盘：findings 原始输出、触发面验证与负向对照的两次输出、基线比对表、双守卫实测三项结论、**已知红清单（K1 `add-minimal-tui-runtime-view` + K2 本 change 自己）**。
- [ ] A.5.6 **本 change 自己补一份 witnessloop 形态的 grill manifest 当样板**（Decision 7 的推荐处置）：跑 `uv run witnessloop manifest build --change witnessloop-adoption --stage grill --report reviews/grill-design.md`，产出 `reviews/grill.manifest.json`。**目的**：让阶段 A 的验收里**第一次有「绿」的一侧**（否则整条验收只有红，分不清「配置没生效」与「本来就缺证据」）；同时它就是阶段 B 的流程样板。**注意**：本 change 的 diff 不触 `code_hits` ⇒ `building` / `grill-adversarial` 两条**本就不要求**，**不要伪造**它们。

## 阶段 B：用一个真实小需求跑一遍

**B 的出口判据**：产出验收报告，含 findings 清单、与本地 checker 的**分叉清单**、已知红清单、体验摩擦清单，以及「值不值得真打开」的判断依据。

- [ ] B.1 选定真实小需求，标准：**必须触达 `require_change_for`**（否则 `code_hits` 为空、两条核心门禁不触发，跑不出东西）；**必须能产生 spec delta 或受保护写入**（否则测不到解释事件那一面）；规模一到两个文件。把选择理由记入报告。
- [ ] B.2 在新流程上跑完整链路：本地 `guard` 拦（Write/Edit 路径）→ 写码 → 本仓 `/review-loop` 产出 grill / grill-adversarial / building 三份审阅证据（**asterwynd 形态**）→ **额外跑 `uv run witnessloop manifest build --change <id> --stage <stage> --report reviews/<stage>-review.md` 产出三份 witnessloop 形态 manifest（`reviews/<stage>.manifest.json`）** → `witnessloop check` 核证据 → 测试执行点在 CI 的 `gate / check` 里实际跑起来。**这一步的额外动作就是「两套 manifest 并存」的真实成本，须如实记入报告**（Decision 2 / R11：不补这一步，阶段 B 结构上跑不绿、拿不到「绿」的对照）。
- [ ] B.3 **如实记录已知红**：K1 `add-minimal-tui-runtime-view`（无 `reviews/`）在 witnessloop 契约下的报错原文；K2 本 change 自己（缺 witnessloop 形态 manifest、`code_hits` 为空）；**不放宽判据、不给它们开豁免**（Decision 7）。
- [ ] B.4 列出**分叉清单**：同一段 diff 下，本地 checker 判绿而 witnessloop 判红的项、以及反过来判的项，逐条给出 `文件:行号` 级依据（这是后续「逐项下掉」迁移清单的输入，R7）。
- [ ] B.5 评估本地守卫的行为变化，**两件事分开记**（Decision 8 的 Scenario）：① **退步**——本地守卫不再覆盖 Bash 写文件，实测一次「用 Bash 写受管路径」是否确实绕过 witnessloop `guard`；② **新增面**——witnessloop `guard` 会在「缺 grill 证据」这一**本仓现有守卫不管的维度**上新增拦截。两者不得互相抵消成一句「影响不大」。
- [ ] B.6 写「值不值得真打开」的判断依据：findings 的可读性与可行动性、误报率、与本地 checker 的重复劳动量、对 in-flight change 的影响面、**两套 manifest 并存的额外劳动量**。
- [ ] B.7 记录 Q4 决定带来的**已知边界**：witnessloop 测试执行点覆盖到什么、覆盖不到什么（浏览器用例、编码 warn-as-error 门、`openspec validate`、artifact checker 四条是否在执行点内），以及它们在本仓 `validate` job 里**仍然照跑**的事实。

## 阶段 C：真打开（**不在本 change 内执行**）

- [ ] C.1 依据 B.6 的结论决定是否推进；若推进，**另立 change/PR** 做：合入 caller、把 `gate / check` 勾成 required、改写 `AGENTS.md` 的流程段（含守卫退步的如实记载）、收尾 `add-minimal-tui-runtime-view` 这条已知红。
- [ ] C.2 决定 `validate` 里与 witnessloop 重合的那一半什么时候下掉（**必须等 witnessloop 侧证据齐**，不是勾完 required 就下）。

## 收尾（本 change 的归档前必须完成）

> **两条硬约束**：① 归档 move 必须**独立纯 rename 提交**（Z.5）；② 当前规格必须**覆盖重写**而不是只合并 ADDED（Z.2）。两条都由 grill 实测得出，踩了都会让 witnessloop 判红。

- [ ] Z.1 检查文档影响面：`docs/development-guide.md`（A.5.4 新增节）、`docs/openspec-change-backlog.md`（本 change 的登记与状态）、`AGENTS.md`（**本 change 不改流程段**，但要确认没有因接入产生的事实性出入——若有，记入阶段 C 的任务而不是就地改）。
- [ ] Z.2 **覆盖重写**当前规格（不是只合并 ADDED）：按 `platform-gate` 先例（实现 commit `f7e912b`「同步 current spec（覆盖占位，SHALL 目标语言）」）重写 `openspec/specs/dev-workflow-gate/spec.md`——① 删除「当前为预留能力域」这条被阶段 A 实现**直接证伪**的占位 Requirement（本 delta 已用 `## REMOVED Requirements` 登记）；② Purpose 段从「尚未接入」改写为接入后的实际承载形态；③ 合并本 delta 的 ADDED Requirements；④ 追加 `current_spec_synced` 解释事件。
- [ ] Z.3 跑 `/review-loop witnessloop-adoption` 完成实现后独立审阅闭环，产出 `reviews/building-review.md` + review manifest。
- [ ] Z.4 跑 `uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`，把原始输出要点写进 PR 描述。
- [ ] Z.5 归档到 `openspec/changes/archive/2026-10-13-witnessloop-adoption/`，从 `docs/openspec-change-backlog.md` 移除，并在 issue #305 回链阶段进展。**硬约束：归档 move 必须是独立的纯 rename 提交**——grill 实测，`git mv` 与同一 commit 内的内容改动并用会被 git 记作 `A`/`D`（非 `R100`）⇒ witnessloop 的 `is_archive_move` 为假（`contract.py:38-55`）⇒ 出 3 条红（`change 目录不存在` + `缺少 review manifest` + `无 stage=grill 的 manifest`）。⇒ **先单独提交归档 move，再在后续提交里改 backlog/issue 回链**。
- [ ] Z.6 (post-merge) PR 合入后：确认 active change 目录不存在、backlog 干净、本地 `master` 已快进；在 issue #305 补阶段 A 的完成说明（**不关闭 issue**——它是多阶段跟踪入口）。

## 后续候选（**不属本 change**，登记以便不丢失）

- [ ] N.1 **退役状态机残留清理**：`handoff.json`（122 个归档里只有 5 个有）+ `check_openspec_artifacts.py` 的 `_check_handoff_json` / `_check_archived_projectable` / `_check_new_archived_completion_gates`（issue #305 盘点：相关测试 6+6+5 条）。**不混进阶段 A**（Decision 6）——混进来会污染影子接入的 diff 可评估性。建议另立 change。
- [ ] N.2 **上游 `@v1` 移动 tag 的固化评估**（R6）：是否用 `--gate-ref` 钉 commit sha。建议先观察一个迁移周期再定。
- [ ] N.3 **`benchmarks/**` 的窄模式**（若 Q2 选 (a) 但 `benchmarks/` 下有需保护的运行时代码）：立 witnessloop issue 或另立 change 讨论 `benchmarks/**/*.py` 之类的窄模式。
- [ ] N.4 **manifest schema 统一**（阶段 C 之后的独立 change）：改 `agent/workflow/review_manifest.py`，让它输出 witnessloop 的必填字段（`stage` / `author_run_id` / `report_path`），并连带改它的 2874 行测试体量与 `/review-loop` 的产出路径。**这是 Decision 2 显式推迟的那件事**——阶段 A/B 用「两套 manifest 并存」绕过它。
- [ ] N.5 **（债项，非本 change 引入）checker 的 Open Questions 抽取只认列表项**：`scripts/check_openspec_artifacts.py` 的 `_extract_open_question_indexes` 只认行首 `Q<n>`/数字，`### Q<n>:` 小标题式条目抽取结果为 **0 条** ⇒ grill 的「停轮确认门」在那种写法下**静默失效**。grill 实测：归档 `2026-10-07-grill-flow-hardening/reviews/grill-design.md`（用 `### Q2:`/`### Q3:`）抽取为 0 条，而同期的 `2026-10-03-tool-result-lifecycle`（用 `- **Q1**…` 列表项）正确抽出 8 条。⇒ 二选一：收紧 checker 兼容小标题形式，或在 `docs/development-guide.md` 明写「Open Questions 必须用列表项」。**别在本 change 内改**（本 change 明确不改 `scripts/**`）。
