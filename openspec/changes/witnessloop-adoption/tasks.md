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

- [ ] A.1.1 写下阶段 A 的验收判据（5 条）：① `init --dry-run` 待建文件 = 4 个且零冲突；② 本分支 PR CI 出现 `gate / check` 并跑出结果；③ 本分支 diff 下 `check` **确实触发** `building` 与 `grill-adversarial` 两条 stage 判定；④ **负向对照**：出厂 policy 下这两条判定**消失**；⑤ `validate` / `benchmark-gate` 与本 change 前逐字节一致、branch protection 的 `contexts` 未变。
- [ ] A.1.2 记录基线：本分支起点 `gh api repos/Xingkai98/asterwynd/branches/master/protection` 的 `contexts` / `strict` / `required_approving_review_count` / `required_conversation_resolution.enabled` 四项实况，写进阶段 A 验收报告（供 A.5.3 复比对）。

### A.2 定制 policy seed（仓外临时文件，不入库）

- [ ] A.2.1 按 0.5 定稿的字段值，在仓外临时路径（如 `/tmp/witnessloop-asterwynd-policy.json`）写**完整** policy：`changes_root` / `protected_paths` / `require_change_for` / `required_artifacts` / `evidence.review_manifest_glob` / `evidence.events_file` / `evidence.protected_write_event_types`（基线形态见 `design.md` Decision 1；三个待定值按 0.3 的答复填）。
- [ ] A.2.2 自查 seed：`protected_paths` **不含** `openspec/changes/archive/**`（Decision 3）；`review_manifest_glob` 为 `reviews/*-manifest.json`（Decision 2）；`required_artifacts` 与 asterwynd 现有 change 目录必需件同形。
- [ ] A.2.3 确认 seed **不进 PR**（`git status` 干净、仓外路径），产物 `.witnessloop/policy.json` 才入库。

### A.3 落接入产物

- [ ] A.3.1 在 building worktree 跑 `witnessloop init --root . --policy <seed> --test-command "<asterwynd 测试命令>"`；`--test-command` 的值取本仓现有 CI 的测试口径（对应 `.github/workflows/ci.yml` 的 `validate` 里那一步），**必须是真实可跑的命令**、不得留哨兵 `<<REPLACE-ME>>`。
- [ ] A.3.2 核对产物 = 4 个文件（`.witnessloop/policy.json` / `.witnessloop/init-manifest.json` / `.github/workflows/witnessloop.yml` / `.github/witnessloop-tests.txt`），且 `.github/workflows/ci.yml` **未被触碰**。
- [ ] A.3.3 本地跑一次 `witnessloop check`（`uv run witnessloop check --root .`，用 worktree 里的补丁版本、**不用**全局安装的那份），逐条读 findings 并把原始输出粘进阶段 A 验收报告。
- [ ] A.3.4 执行 A.1.1 的负向对照 ④：临时用出厂 policy 再跑一次 `check`，确认 `building` / `grill-adversarial` 两条判定**消失**；把两次输出并列记入报告（这是「定制 policy 必要」的证伪证据，不是推理）。

### A.4 本地交互层（不进 PR）

- [ ] A.4.1 从 witnessloop 仓的 `plugin/` 装 Claude Code plugin（`commands/` 下的 `grill` / `review-loop` + `hooks/` 的 guard hook）。
- [ ] A.4.2 确认安装是**本地动作**：`.claude/` 被 `.gitignore:9` 忽略 ⇒ 不进任何 diff、不产生 PR。
- [ ] A.4.3 把安装/卸载/升级步骤写进 `docs/development-guide.md`，使这个「没有评审记录」的本地动作至少有**版本控制内的书面记录**（R5 的缓解）。
- [ ] A.4.4 确认本地层与 CI 层**互不依赖**：不装 plugin 时 CI 门禁照跑；装 plugin 也不会自动勾 required。

### A.5 验收与回归确认

- [ ] A.5.1 开本分支的 PR，确认 CI 里**新增** `gate / check` job 并跑出结果（判据 ②）。
- [ ] A.5.2 确认本 job **未进 required**（`gh api …/protection` 的 `contexts` 仍为 `["validate", "benchmark-gate"]`）。
- [ ] A.5.3 与 A.1.2 的基线逐项比对 `validate` / `benchmark-gate` 的行为与 branch protection 四项实况，确认未变（判据 ⑤）。
- [ ] A.5.4 在 `docs/development-guide.md` 新增「witnessloop 影子接入」一节：明确写「阶段 A 不 required、只跑不拦」，给出本地跑 `check` / `guard` 的命令，以及卸载路径（R1 的缓解）。
- [ ] A.5.5 把 A 阶段验收报告落盘（findings 原始输出、负向对照两次输出、基线比对表）。

## 阶段 B：用一个真实小需求跑一遍

**B 的出口判据**：产出验收报告，含 findings 清单、与本地 checker 的**分叉清单**、已知红清单、体验摩擦清单，以及「值不值得真打开」的判断依据。

- [ ] B.1 选定真实小需求，标准：**必须触达 `require_change_for`**（否则 `code_hits` 为空、两条核心门禁不触发，跑不出东西）；**必须能产生 spec delta 或受保护写入**（否则测不到解释事件那一面）；规模一到两个文件。把选择理由记入报告。
- [ ] B.2 在新流程上跑完整链路：本地 `guard` 拦（Write/Edit 路径）→ 写码 → grill / grill-adversarial / building 三份审阅证据 → `witnessloop check` 核证据 → 测试执行点在 CI 的 `gate / check` 里实际跑起来。
- [ ] B.3 **如实记录已知红**：`add-minimal-tui-runtime-view`（无 `reviews/`）在 witnessloop 契约下的报错原文；**不放宽判据、不给它开豁免**（Decision 7）。
- [ ] B.4 列出**分叉清单**：同一段 diff 下，本地 checker 判绿而 witnessloop 判红的项、以及反过来判的项，逐条给出 `文件:行号` 级依据（这是后续「逐项下掉」迁移清单的输入，R7）。
- [ ] B.5 评估**能力退步**的实际影响（R3）：本地守卫不再覆盖 Bash 写文件，实测一次「用 Bash 写受管路径」是否确实绕过 `guard`，把结果写入报告。
- [ ] B.6 写「值不值得真打开」的判断依据：findings 的可读性与可行动性、误报率、与本地 checker 的重复劳动量、对 in-flight change 的影响面。

## 阶段 C：真打开（**不在本 change 内执行**）

- [ ] C.1 依据 B.6 的结论决定是否推进；若推进，**另立 change/PR** 做：合入 caller、把 `gate / check` 勾成 required、改写 `AGENTS.md` 的流程段（含守卫退步的如实记载）、收尾 `add-minimal-tui-runtime-view` 这条已知红。
- [ ] C.2 决定 `validate` 里与 witnessloop 重合的那一半什么时候下掉（**必须等 witnessloop 侧证据齐**，不是勾完 required 就下）。

## 收尾（本 change 的归档前必须完成）

- [ ] Z.1 检查文档影响面：`docs/development-guide.md`（A.5.4 新增节）、`docs/openspec-change-backlog.md`（本 change 的登记与状态）、`AGENTS.md`（**本 change 不改流程段**，但要确认没有因接入产生的事实性出入——若有，记入阶段 C 的任务而不是就地改）。
- [ ] Z.2 把本 change 的 spec delta 同步进**当前规格** `openspec/specs/dev-workflow-gate/spec.md`（把 ADDED Requirements 合并进 `openspec/specs/<capability>/spec.md`，并追加 `current_spec_synced` 解释事件）。
- [ ] Z.3 跑 `/review-loop witnessloop-adoption` 完成实现后独立审阅闭环，产出 `reviews/building-review.md` + review manifest。
- [ ] Z.4 跑 `uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`，把原始输出要点写进 PR 描述。
- [ ] Z.5 归档到 `openspec/changes/archive/2026-10-13-witnessloop-adoption/`，从 `docs/openspec-change-backlog.md` 移除，并在 issue #305 回链阶段进展。
- [ ] Z.6 (post-merge) PR 合入后：确认 active change 目录不存在、backlog 干净、本地 `master` 已快进；在 issue #305 补阶段 A 的完成说明（**不关闭 issue**——它是多阶段跟踪入口）。

## 后续候选（**不属本 change**，登记以便不丢失）

- [ ] N.1 **退役状态机残留清理**：`handoff.json`（122 个归档里只有 5 个有）+ `check_openspec_artifacts.py` 的 `_check_handoff_json` / `_check_archived_projectable` / `_check_new_archived_completion_gates`（issue #305 盘点：相关测试 6+6+5 条）。**不混进阶段 A**（Decision 6）——混进来会污染影子接入的 diff 可评估性。建议另立 change。
- [ ] N.2 **上游 `@v1` 移动 tag 的固化评估**（R6）：是否用 `--gate-ref` 钉 commit sha。建议先观察一个迁移周期再定。
- [ ] N.3 **`benchmarks/**` 的窄模式**（若 Q2 选 (a) 但 `benchmarks/` 下有需保护的运行时代码）：立 witnessloop issue 或另立 change 讨论 `benchmarks/**/*.py` 之类的窄模式。
