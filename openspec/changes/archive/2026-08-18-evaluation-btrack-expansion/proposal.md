# Proposal: B 轨扩展到 12–16（evaluation-btrack-expansion）

关联跟踪 issue：[#164](https://github.com/Xingkai98/asterwynd/issues/164)。系列 follow-up：[#156](https://github.com/Xingkai98/asterwynd/issues/156)（C1 后续项 2）。

## Change Type

- primary: feature
- secondary: []

## Why

C1 `evaluation-task-spec`（#154）的 B 轨目标 12–16 条，实际交付 5 条（4 陈旧重写 002/004/005/021 + 1 新增 `asterwynd-b01`）。能力缺口（C1 grill OQ-B1 已列候选，用户按推荐确认方向，2026-08-17）：

- **context-planning 0 新增**（当前由 A 轨 010/022 覆盖矩阵兜底）——目标补 3–5 条，这是面试最想展示的"规划"能力。
- long-term-memory 补 1 条（scope 隔离形态）。
- long-context 补 1–2 条（大读取 + 小改动形态）。
- safety-boundary 靠 002/005 重写已覆盖。
- 每场景（bug-fix/feature-dev/refactor/debug/integration）至少 1–2 条；含 2–3 条 hard。

当前任务集 37 条（27 本地 + 10 swebench），面试叙事（C4 已合入）写「升级目标 ~90（设计已定：A 轨 20–24 + B 轨 12–16 + Verified 50；当前已落 37）」——B 轨扩展是朝目标收敛的关键一步。

## What Changes

- **B 轨新增 7–11 条**（5 → 12–16）：context-planning 3–5（CP-1 工具装配链 / CP-2 statechart 跨 4 处 / CP-3 结果页 track 分组 / CP-4 debug 形态）、long-term-memory scope 隔离、long-context 大读取任务、每场景 ≥1–2、2–3 条 hard。
- **每任务测试先行**：issue.md（问题描述不给文件路径，迫 agent 先 repo-map 再规划）+ 确定性 test_command/gold patch + 覆盖矩阵校验（7 能力列 × 5 场景列 ≥1）。
- **manifest 更新**：`benchmarks/tasks/manifest.json` 的 coverage 矩阵登记新任务（与 verified-subset 并行，只改 coverage 段）。
- **面试叙事数字校准**：C4 写「当前已落 37」，B 轨扩展合入后任务数变（37+N），change 内更新或标注校准。

## Capabilities

### New Capabilities

无。全部为既有 `benchmark` 能力域的任务集扩展。

### Modified Capabilities

- `benchmark`: B 轨任务补齐（context-planning 等能力空白）；无 spec delta（C1 已落任务集组成/能力覆盖 Requirement，本 change 是实现与扩展）。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 常规功能增强（C1 已调研 G1 分层 #148 / G2 任务集 #149，B 轨补缺目标与候选已在 C1 grill OQ-B1 确认）；本 change 是任务设计实现，无新方法论。
- research questions: 无（light）。
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录）。C1 归档 change 的 grill-design.md（OQ-B1）含 CP-1~CP-4 候选的具体任务设计（问题描述/验证方式/gold patch 来源）；manifest 覆盖矩阵结构（7 能力列 × 5 场景列）已由 C1 交付。
- design impact: 任务清单与覆盖矩阵实现见 design.md D1–D6。
- 最终结论: 7 条候选按 design D1 + grill OQ-1~7 用户确认全部落地（CP-1~4 + LT-MEM-1 + LC-1 + BF-1），B 轨 5→12 达下限；每条任务 base 红 + gold 绿验证通过；CP-4 因原「未转义 bug」与 HEAD 不符改为合成回归（base 6baa26c bug 态 + gold 恢复转义），BF-1 从 command_guard 实测发现真实绕过缺陷（绝对路径 shell 管道拦截）并修复。`validate_coverage` 扩展 per-track B 能力列校验（Q6）。任务数实测 44（34 本地 = 22 A + 12 B + 10 verified）。

## Impact Analysis

- **能力域**: `benchmark`（B 轨任务扩展）。
- **代码**: `benchmarks/tasks/`（新增 7 条 asterwynd-b02~b08 任务目录，每个含 issue.md/task.json/gold.patch/test.patch）、`benchmarks/tasks/manifest.json`（coverage 矩阵登记 7 条）、`benchmarks/task_set.py`（validate_coverage 扩展 per-track B 能力列校验 + 测试）。
- **测试**: 7 条任务全部「base 红 + gold 绿」红绿可复现验证通过（每条 test_command 确定性）；覆盖矩阵 `validate_coverage` 7 能力列 × 5 场景列 ≥1 + per-track B 全过；既有 benchmark/agent 测试无回归。
- **文档**: `docs/openspec-change-backlog.md`（#156 后续项 2 状态，见 7.3）；面试叙事数字校准全套：FINAL-master-script（L11/L27/L96/L117/L118）+ Q13 + walkthrough/README + W07 + resume-description（L9/L87/L104）+ README + README_EN（37→44，22 A + 12 B）。
- **基准**: 新增任务是纯增量；既有 A 轨（22 条）/既有 B 轨 5 条不动；任务 schema/manifest 结构不变（manifest 只改 coverage 段，与 verified-subset 错开）。
- **流程（process）**: B 轨任务设计约定（issue.md 不给路径 + 确定性验证 + 覆盖矩阵 + 红绿可复现）延续 C1 规范；CP-4 采用合成回归（base 为 6baa26c bug 态，gold 恢复转义）。
