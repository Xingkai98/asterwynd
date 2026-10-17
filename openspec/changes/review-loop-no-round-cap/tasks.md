# Tasks: 审阅闭环去掉轮数上限，改为「无收敛才停」（review-loop-no-round-cap）

> **本 change 无运行时行为改动**（见 `design.md` Decision 5）：只改**规则文档**、**规格**与 `scripts/check_openspec_artifacts.py` 的**两处提示字符串**。因此没有要新增的单元测试——但**有**机械验收（T6/T7 的 grep 与 diff 检查）。
>
> **前置门（第 0 节）不完成不得开工**：grill 由独立零记忆 subagent 执行（`/grill`），产出 `reviews/grill-design.md`；随后按 issue #298 跑设计阶段对抗闭环，产出 `reviews/grill-adversarial.md`。
>
> **停轮口径**：本 change 的语义**已由用户拍板**（去掉上限、修到收敛）。设计里**不应有需要用户拍板的 Open Question**；被挑战出来的待定项必须用仓库内事实（grep 结果、规格行号、先例文档）当场判掉。**若确实冒出一个只有用户能拍的问题，就停下来写清楚留给他，不代拟答案。**

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [ ] 0.1 用 `grilling` skill（独立零记忆 subagent）对 `design.md` 做设计追问，产出结构化决策记录到 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含**决策 / 理由 / 来源**三字段）。
- [ ] 0.2 逐项核对 grill 的 7 个维度，**重点是第 7 条（触发与门禁）**：本 change 改 `scripts/**` ⇒ 会触发 witnessloop 的 `building` 与 `grill-adversarial` 两个 stage 判定；确认本 change 建立 change 目录 + 三份 manifest 后能判绿。
- [ ] 0.3 跑**设计阶段对抗闭环**（与 `/review-loop` 同构但审设计而非代码）→ `reviews/grill-adversarial.md`；对 Decision 3（对齐到哪一层：只对齐「停的条件」不搬机制）与 Decision 2（不写任何数值阈值）做专门挑战。
- [ ] 0.4 **停轮检查**：确认 `design.md` 没有需要用户拍板的 Open Question。若无 ⇒ 进入实现；若有 ⇒ **停下来报告**，不开 PR。
- [ ] 0.5 把 grill 与对抗闭环的结论回填 `design.md` 的 `## Pre-Implementation Review`。
- [ ] 0.6 **grill 记录的格式契约**：`reviews/grill-design.md` SHALL 含 `## Confirmed Decisions`（≥ 3 条、每条决策块内有**同行裸** `来源:`）、`## User Confirmation`（**无条件存在**，零 Open Question 也要有）、以及与逐字标题一致的 Open Questions 小节。用 v1.7.0 的 `grill_evidence_findings` 实测应为 **0 findings**。

## 1. 规则与文案改动

- [ ] 1.1 `AGENTS.md:18`（设计阶段闭环的「直到 PASS 或轮数封顶」）改为收敛口径。
- [ ] 1.2 `AGENTS.md:104`（实现后闭环的「直到 PASS 或 3 轮封顶」）改为收敛口径，并补上「无法收敛 ⇒ 报告阻塞 / 不以轮数为停止理由」。
- [ ] 1.3 `README.md:148` + `README_EN.md:148`（流水线图里的同一句，**必须同改**）。
- [ ] 1.4 `docs/requirements-process.md:45`（实现后闭环）与 `:189`（设计阶段闭环）改为收敛口径。
- [ ] 1.5 `docs/interview-script/questions/Q14-dev-process.md:13`（讲稿正文）与 `:56`（要点「3 轮封顶：审阅不会无限循环…」）改为收敛口径；**`:17` 的 #99 历史案例（「3 轮审阅」）保留原文**——它记录的是当时的经过，不是规则。
- [ ] 1.6 `scripts/check_openspec_artifacts.py:1139` 与 `:1623` 的提示字符串改为收敛口径。**只改字符串，判定逻辑一行不改。**

## 2. 规格

- [ ] 2.1 `openspec/changes/review-loop-no-round-cap/specs/dev-workflow-state-machine/spec.md`：写 delta——`## ADDED Requirements` 新增 `### Requirement: 审阅闭环的终止条件为收敛，而非轮数上限`（含「没有轮数上限」「收敛即停」「无法收敛时报告阻塞」三个 Scenario）。
- [ ] 2.2 **把 delta 施加进当前规格** `openspec/specs/dev-workflow-state-machine/spec.md`；核对 Requirement 条数前后计数如实记入 `workflow-events.jsonl` 的 `current_spec_synced` 事件；**现有条目逐条保留且逐字节不变**（只追加）。

## 3. 验证（判据见 `design.md` 的 Testing Strategy）

- [ ] 3.1 **T1**：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → 记原始输出。
- [ ] 3.2 **T2/T3**：两条 checker 命令 → exit 0（**时序**：产证据前是「内容同步正确」的读数；`building-review.md` 落盘后、manifest 产出前会转 exit 1；以 3.1 产 manifest 之后的读数为最终记录）。
- [ ] 3.3 **T4**：`uv run python scripts/platform_gate.py --verify` → `全部一致`（exit 0）。本 change 不改平台配置，合入后**不需要**再 `--apply`。
- [ ] 3.4 **T6**：`git grep -n "3 轮封顶\|轮数封顶" -- ':!openspec/changes/archive'` → **无命中**（exit 1）。这是「改齐了」的机械证明。
- [ ] 3.5 **T7**：`git diff --stat origin/master...HEAD -- openspec/changes/archive/` → 只出现本 change 自己的归档路径（历史归档未被回填）。
- [ ] 3.6 **内容真实性抽查**：规格与文档里每条关于「终止条件」的断言，逐条与 Decision 2 的四要素对上（无上限 / 收敛定义 / 无法收敛出口 / 不以轮数为理由）。

## 4. 实现后独立审阅闭环

- [ ] 4.1 跑 `/review-loop review-loop-no-round-cap`，产出 `reviews/building-review.md` + `reviews/building-review-manifest.json`（**asterwynd 形态**）。CHANGES_REQUESTED 则修复并再审，**直到收敛**（本 change 自己的规则：无轮数上限）。
- [ ] 4.2 收敛后**清理中间轮产物**（如 `building-review-r1.md`），避免孤儿报告。

## 5. witnessloop 证据与出口判据

- [ ] 5.1 在**所有内容提交之后**（含 1.1–1.6、2.2 与 backlog 清理），用 `witnessloop manifest build` 产三份 witnessloop 形态 manifest（`grill` / `grill-adversarial` / `building`），`report_path` 覆盖 `reviews/` 下每一份 `.md`。
- [ ] 5.2 **T5**：`/home/happy/wl170/bin/witnessloop check --root . --base origin/master --head HEAD` → `check：通过 ✓`（0 项）。必须锚定 v1.7.0；必须在内容提交之后跑（提交前是假绿）。
- [ ] 5.3 CI 侧复核：PR 的 `gate / check` 判绿；`validate` / `benchmark-gate` / `windows-platform` 照跑。

## 6. 收尾（归档前必须完成）

- [ ] 6.1 `docs/openspec-change-backlog.md`：登记本 change，随后在**证据产出之前**结算/移除（backlog 一致性规则要求不得引用已归档 change）。配 `backlog_updated` 解释事件。
- [ ] 6.2 写 `workflow-events.jsonl`：`change_created` / `backlog_updated` / `current_spec_synced` / `change_archived`，`approved_by` 非空。
- [ ] 6.3 结算 `tasks.md`：勾掉全部已完成项；closeout 类未完成项标 `(post-merge)`。**未勾且未标 `(post-merge)` 的任务必须为 0 条**。
- [ ] 6.4 归档 move：**手工 `git mv`** 到 `openspec/changes/archive/2026-10-17-review-loop-no-round-cap/`，**独立纯 rename 提交**（**SHALL NOT 跑 `openspec archive`**：1.4.1 的日期取 UTC、且它把规格同步与 move 合成一次提交）。
- [ ] 6.5 归档后，在归档目录上用**归档目录名**重建两套 manifest（asterwynd 形态 + witnessloop 三份）。
- [ ] 6.6 **合入方式**：本 PR **SHALL 用 `--merge` 合入，SHALL NOT squash**（否则 manifest 的 `head_sha` 不再是祖先，日后触及本 change 目录的 PR 会判红）。

## 7. 合入之后（结构上无法在本 PR 内完成）

- [ ] (post-merge) 7.1 在 issue #305 追加 comment：审阅闭环的轮数上限已从规则与门禁文案中移除，规格已补上终止条件。**issue 保持 OPEN**。
- [ ] (post-merge) 7.2 合入后确认：active change 目录不再存在、backlog 干净、本地 `master` 已快进；并复核 `master` 的 required 仍为 `["gate / check"]`（本 change 不该改变平台实况）。
