# Tasks: 阶段 C 翻开关的记录与规格对账（stage-c-required-switch）

> **本 change 无代码面**（见 `design.md` Decision 5）：diff 只落在 `openspec/**` 与 `docs/**`。因此**没有「测试先行」一节**（没有可测对象）。**benchmark smoke 仍然排了（2.4b）**——不是因为本 change 有 code 面，而是 checker 的触发启发式被本 change 正文里的「不影响」清单命中了（**一次假阳性**，如实记录在该任务行与 `design.md` Decision 5 里）。
>
> **前置门（第 0 节）不完成不得开工**：grill 由独立零记忆 subagent 执行（`/grill`），产出 `reviews/grill-design.md`；随后按 issue #298 跑设计阶段对抗闭环，产出 `reviews/grill-adversarial.md`。
>
> **停轮口径**：本 change 记录的是**已经拍过板且已经落地**的决定（issue #305 阶段 C）。设计里**不应有需要用户拍板的 Open Question**；被挑战出来的待定项必须用仓库内事实（`gh api` 输出、`--verify` 输出、规格行号）当场判掉。**若确实冒出一个只有用户能拍的问题，就停下来写清楚留给他，绝不代拟答案、也不用占位文本糊过去。**

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 `grilling` skill（独立零记忆 subagent）对 `design.md` 做设计追问，产出结构化决策记录到 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含**决策 / 理由 / 来源**三字段）。
- [x] 0.2 逐项核对 grill 的 7 个维度，**重点是第 7 条（触发与门禁）**：本 change 自身的写操作会不会被 witnessloop 的 `building` / 受保护写入门禁拦下（它只改 `openspec/**` 与 `docs/**`，不触达 `require_change_for`）；以及它建立 change 目录后能否让 `gate / check` 判绿。
- [x] 0.3 跑**设计阶段对抗闭环**（与 `/review-loop` 同构但审设计而非代码）→ `reviews/grill-adversarial.md`；对 Decision 1（`process` 的档位选择——**初稿是 `exempt`，对抗轮 I-6 后已改 `light`**）与 Decision 3（REMOVED 的爆炸半径）做专门挑战，能由仓库事实判定的当场判掉、移出停轮队列。
- [x] 0.4 **停轮检查**：确认 `design.md` 没有需要用户拍板的 Open Question。若无 ⇒ 直接进入实现；若有 ⇒ **停下来报告**，不开 PR。
- [x] 0.5 把 grill 与对抗闭环的结论回填 `design.md` 的 `## Pre-Implementation Review`。
- [x] 0.6 **grill 记录的格式契约**（`design.md` Decision 11，v1.7.0 实测）：`reviews/grill-design.md` SHALL 含 `## Confirmed Decisions`（每条决策块内有**同行裸** `来源:`）、`## User Confirmation`（**无条件存在**，零 Open Question 也要有）、以及与逐字标题一致的 Open Questions 小节。用 v1.7.0 的 `grill_evidence_findings` 实测应为 **0 findings**。

## 1. 规格同步（本 change 的实质改动）

- [x] 1.1 `openspec/changes/stage-c-required-switch/specs/platform-gate/spec.md`：写 delta——`## MODIFIED Requirements` 覆盖重写 `### Requirement: 合入平台闸门`（required 由两项改为唯一 `gate / check`，Scenario 由「benchmark-gate 为 required check」改为 witnessloop `gate / check` 为唯一 required + 三 job 照跑）与 `### Requirement: 平台闸门复用 GitHub branch protection 语义`（Scenario「平台配置走 PR review」里的 CI 列举）；`## ADDED Requirements` 增 `### Requirement: 降级为非必过的检查仍须运行`。
- [x] 1.2 `openspec/changes/stage-c-required-switch/specs/dev-workflow-gate/spec.md`：写 delta——`## REMOVED Requirements` 登记 `### Requirement: 影子接入阶段不改变任何既有强制`（带 Reason / Migration）；`## MODIFIED Requirements` 覆盖两条（`grill 报告正文判据的已知不兼容` 补记 v1.7.0 的四条契约并订正「结构性不可能判绿」；`已知红如实记录且不放宽判据` 补记阶段 C 后的**状态迁移**）；`## ADDED Requirements` 增**两条**（`阶段 C 翻开关后的 required 形态`；`翻开关这一动作自身必须具备 change 记录`，见 Decision 9）。
- [ ] 1.3 **把 change 的 spec delta 同步进当前规格**：`openspec/specs/platform-gate/spec.md` 与 `openspec/specs/dev-workflow-gate/spec.md` 就地覆盖（Purpose 段一并按阶段 C 实况改写）。同步后核对：Requirement 条数前后计数如实记入 `workflow-events.jsonl` 的 `current_spec_synced` 事件；**`dev-workflow-gate` 的其余 10 条 Requirement 逐条保留**（Decision 3 的爆炸半径约束）。
- [x] 1.4 `docs/development-guide.md`：订正 witnessloop 节里阶段 A 遗留的两条 bullet（「已知红…② 本 change 自己」与「`reviews/` 的一致状态…2 条拉到 14/16 条」），使它们指向已归档的 `witnessloop-adoption` 而不是一个不存在的「本 change」。
- [ ] 1.5 **Purpose / 「阶段划分」段的人手就地改写**（`design.md` Decision 10）：两份规格的 `## Purpose` 段与 `dev-workflow-gate` 的「阶段划分」段按阶段 C 实况改写；**顺带修掉 `openspec/specs/dev-workflow-gate/spec.md` Purpose 段内的死链**（`openspec/changes/witnessloop-adoption/reviews/acceptance-stage-a.md` → 归档路径）。改写前后的差异记入 `current_spec_synced` 事件（该段**无 delta 载体**，只能就地改）。
- [x] 1.6 `README.md` + `README_EN.md`：「用 Agent 开发 Agent」流水线图里「CI 门禁（… + benchmark-gate）」一行改为反映阶段 C 的实况（required 只有 `gate / check`，其余照跑不拦）。**两条必须同改**（AGENTS.md 的 README 同步规则）。
- [x] 1.7 讲稿面按阶段 C 实况订正（**位置以下列为准**：`docs/interview-script/questions/Q12-ci-testing.md`（job 数量 + 树图）、`Q13-benchmark.md:13/:15/:51/:63`、`Q09-observability.md:15/:61`、`docs/interview-bullets/walkthrough.md:3895`）。**不写「共 N 处」这种总数口径**——第二轮对抗复核 N-4 实测该口径会被自己证伪（初稿写「6 处」而清单列了 7 项），按位置列举才是可核对的写法。**订正口径统一为「判失败/报警，阶段 C 之后不再拦合并」**——不要只改一处而让同文件自相矛盾（设计阶段对抗闭环 I-2 实测：初稿只改了 `Q13:15`，同文件 `:63` 仍是旧口径）。

## 2. 验证（判据见 `design.md` 的 Testing Strategy）

- [ ] 2.1 **T1**：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → 记原始输出。
- [ ] 2.2 **T2**：`uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` → exit 0。**base 必须显式绑 `origin/master`**：checker 默认 base 是 `master`，而本 worktree 的本地 `master` ≠ 上游 ⇒ 用默认值会去校验**另一个变更集**（实测 `git diff --name-only master --` 列出的是 PR #311 的整份 diff）。
- [ ] 2.3 **T3**：`uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` → exit 0。
- [ ] 2.4 **T4**：`uv run python scripts/platform_gate.py --verify` → `全部一致`（exit 0）。**必须带 `uv run`**——本环境没有裸 `python`（`command not found`、exit 127）。**本 change 不改平台配置，合入后 SHALL NOT 再跑 `--apply`**（Decision R7）。
- [x] 2.4b **benchmark smoke**（**已跑，PASS**）：实际执行的命令与原始输出——
  ```
  $ uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke --source-repo . \
      --runs-dir /tmp/benchmark-gate-runs-sc --baseline benchmarks/baseline.json \
      --require-baseline --skip-p95
  BENCHMARK GATE
    success_rate: baseline=1.0000 current=1.0000 delta=+0.0000
    p95_latency_s: SKIPPED (deterministic task set)
    result: PASS
  EXIT=0
  ```
  （与本仓 `ci.yml` 的 `benchmark-gate` job 同形；`--runs-dir` 用了 change 专属目录 `/tmp/benchmark-gate-runs-sc`，避免与本机既有的 `/tmp/benchmark-gate-runs` 混淆——第二轮对抗复核 N-5 指出初稿的命令行与真实产出目录不一致，此处已改为**实际执行的那一条**。）
  **为什么本 change 明明无代码面却要跑**（如实记录）：checker 的 `_requires_benchmark_smoke` 是一条**对 proposal 正文的正则启发式**（`benchmarks/` 等四个模式），而本 change 在「不影响」清单里逐项列出了 `.github/workflows/ci.yml`、`scripts/**`、`agent/**`、`benchmarks/**` 等路径 ⇒ **命中了该正则**。这是一次**假阳性**：本 change 的 diff 里没有任何 benchmark 代码。**但它不靠改措辞绕开**——触发面命中就跑，跑出来的是真结论；同时把这条假阳性如实记进 `design.md`（供将来决定是否收窄该启发式）。**放权判据的做法是「跑它」，不是「改一句话让正则不命中」。**
- [ ] 2.5 **内容真实性抽查**：规格里每条涉及 required 集合 / job 是否运行 / `--apply` 是否已执行的断言，逐条与 `gh api repos/Xingkai98/asterwynd/branches/master/protection` 的原始 JSON 对上。

## 3. 实现后独立审阅闭环

- [ ] 3.1 跑 `/review-loop stage-c-required-switch`，产出 `reviews/building-review.md` + `reviews/building-review-manifest.json`（**asterwynd 形态**）。CHANGES_REQUESTED 则修复并再审，直到 PASS 或 3 轮封顶。
- [ ] 3.2 收敛后**清理中间轮产物**（如 `building-review-r1.md`）——它们不在任何 manifest 的 `report_path` 上，一旦建了 witnessloop 形态 manifest 就会成孤儿报告。

## 4. witnessloop 证据与出口判据

- [ ] 4.1 在**所有内容提交之后**（含 1.4 与 backlog 清理），用 `witnessloop manifest build` 产三份 witnessloop 形态 manifest（`grill` / `grill-adversarial` / `building`），**绑定的 `report_path` 覆盖 `reviews/` 下每一份 `.md`**（`grill-design.md` / `grill-adversarial.md` / `building-review.md`），否则孤儿规则被激活。
- [ ] 4.2 **T5**：`/home/happy/wl170/bin/witnessloop check --root . --base origin/master --head HEAD` → `check：通过 ✓`（0 项）。**必须锚定 v1.7.0**：PATH 上那份是 0.1.0、`/home/happy/witnessloop` 克隆检出在 tag `v1`，两者都不是 CI 实际用的 `v1.7.0`（`00192ab`）。**必须在内容提交之后跑**——内容提交前它会报「0 个变更文件」并「通过 ✓」，那是**假绿**（untracked 文件不进 `git diff`）。这是本 change 的出口判据。
- [ ] 4.3 CI 侧复核：PR 的 `gate / check` 判绿；`validate` / `benchmark-gate` / `windows-platform` **照跑**（记录它们的结论，用于佐证 Decision 4 的不变量）。

## 5. 收尾（归档前必须完成，且必须按此顺序）

- [ ] 5.1 `docs/openspec-change-backlog.md`：登记本 change，随后在**证据产出之前**把它结算/移除（backlog 一致性规则机械要求不得引用已归档 change；`docs/` 不属 witnessloop 的 stale 豁免路径）。配 `backlog_updated` 解释事件。
- [ ] 5.2 写 `workflow-events.jsonl`：`change_created` / `backlog_updated` / `current_spec_synced`（两份规格各一条）/ `change_archived`，`approved_by` 非空。
- [ ] 5.3 结算 `tasks.md`：勾掉全部已完成项；closeout 类未完成项标 `(post-merge)`。**未勾且未标 `(post-merge)` 的任务必须为 0 条**。
- [ ] 5.4 归档 move：**手工 `git mv`** 到 `openspec/changes/archive/2026-10-17-stage-c-required-switch/`，**独立纯 rename 提交**（Decision 6）。**SHALL NOT 跑 `openspec archive`**：`openspec` 1.4.1 的 `getArchiveDate()` 用 `new Date().toISOString()`（**UTC**），本机实测会产出**前一天**的目录名 `2026-10-16-…`；且它把「规格同步 + move」原子合成一次提交，破坏本条的「独立纯 rename」要求。
- [ ] 5.5 **归档后**在归档目录上用**归档目录名**重建 witnessloop 三份 manifest 与 asterwynd 形态 manifest（Decision 6 的第 ④ 步）。
- [ ] 5.6 **合入方式**：本 PR **SHALL 用 `--merge`（merge commit）合入，SHALL NOT squash**（Design 的 R8）。理由：witnessloop v1.7.0 的 `_check_git_span` 要求 manifest 的 `head_sha` 是本次被检 head 的**祖先**；squash 会把该 sha 从 `master` 历史里抹掉，日后任何触及本 change 目录的 PR 都会因此判红（阶段 A 有实测先例）。

## 6. 合入之后（结构上无法在本 PR 内完成）

- [ ] (post-merge) 6.1 在 issue #305 追加 comment：阶段 C 的 change 记录已归档、规格已同步、`gate / check` 在本 change 的 PR 上判绿。**issue 保持 OPEN**（继续跟踪「逐项下掉旧件」）。
- [ ] (post-merge) 6.2 合入后确认：active change 目录不再存在、backlog 干净、本地 `master` 已快进到 `origin/master`；**并复核 `master` 的 required 仍为 `["gate / check"]`**（本 change 不该改变平台实况——这是 R7 的复核动作）。
