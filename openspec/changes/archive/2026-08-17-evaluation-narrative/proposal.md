# Proposal: 面试叙事改动（evaluation-narrative，C4）

关联跟踪 issue：[#160](https://github.com/Xingkai98/asterwynd/issues/160)（【feature】evaluation-narrative）。系列父级：[#144](https://github.com/Xingkai98/asterwynd/issues/144)。

## Change Type

- primary: process
- secondary: []

## Why

评测升级的 C1（任务集 + spec）/C2（指标层）/C3（协议 + 披露，并行中）已让评测体系从"布尔结论"升级为"场景×难度分层 + 可引用数字"，但**面试材料还停留在旧口径**：

- `docs/resume-description.md`：写「23 个本地任务」（实为 26，C1 后 27）、「34 个本地任务」（自相矛盾）、「450+ 测试函数」（实为 1700+）、`claw-swe-bench/` 目录（已不在 tree）。
- `docs/interview-script/questions/Q13-benchmark.md`：指标层只讲 pass 率/pass@k，无 pass^k/cost@pass/fault_owner/配对比较；无 SWE-bench 污染披露。
- `docs/interview-script/walkthrough/W07-observability-benchmark.md`：36+ 保留但无升级加分点。
- `docs/interview-script/FINAL-master-script.md`：速查表「130 测试文件/~1691 函数」（实为 135/1700+）、36 保留但无升级行。

T2 叙事改动清单（2026-08-17，map #144 已确认）是精确编辑清单；本 change 落进 4 份文档，让面试叙事与评测升级后的现状/升级方向一致。

## What Changes

- **`docs/resume-description.md`**：23→26（C1 后 27）本地任务、450+→1700+ 测试、Claw-SWE-Bench 目录表述重锚为统一 harness 口径（SwebenchAdapter + 多 runner）；简历 bullet 7 改后草案。
- **`docs/interview-script/questions/Q13-benchmark.md`**：任务层加场景×难度分层 + 三来源任务集；指标层加 pass^k/cost@pass/fault_owner；对比层加配对比较；面试重点加污染披露 + pass@1/pass^k 口径；内联 Claw 表述重锚。
- **`docs/interview-script/walkthrough/W07-observability-benchmark.md`**：36+ 保留 + 4 条升级加分点（场景化 ~90/pass^k、污染披露、反作弊诚实边界、预算可配置可取消标 C2/C3 交付）。
- **`docs/interview-script/FINAL-master-script.md`**：速查表 130/~1691→135/1700+、36 保留 + 升级行、bullet 7 追加句、速查表新增升级数字行（~90/pass^k/cost@pass/fault_owner/预算）。
- **总原则**：现状口径与升级方向分层（不把未实现写成已实现）；数字口径统一（26/1700+/38）；`comparison.md` 历史产物不引用；README/README_EN 如涉及同步。

## Capabilities

### New Capabilities

无（docs-only）。

### Modified Capabilities

- `interview-script`（docs）：面试材料数字口径修正 + 升级叙事；不新增 benchmark capability。

## Reference Implementation Research

- status: enabled
- research_tier: exempt
- reason: docs-only 变更（无新增能力面），数字口径均已核实（R3 资产盘点 #147 + grill 2026-08-17 实测 master），编辑清单来自已确认的 T2 交付物（#153 已关闭；T2 文件实体在 `wayfinder-research` worktree `docs/research/narrative-changes-2026-08-17.md` 可读，2026-08-17 用户确认草案来源）。无待定设计项。
- research questions: 无（exempt）。
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录）。数字口径：grill 2026-08-17 实测 master 为本地任务 27（26 A 轨 + 1 B 轨 b01）+ 10 swebench = 37、测试 148 文件/~1997 函数、38 内置工具（KNOWN_BUILTIN_TOOL_NAMES）；用户确认以该实测为准（T2 原文 26/36/135/1700+ 为 C1/C2 合入前口径，不采用）。编辑清单为 T2（#153）交付物。
- design impact: 5 份文档的编辑位置与段落草案由 T2 交付物 + grill 实测给出，design.md 承接并已补齐逐字 before/after。

## Impact Analysis

- **能力域**: `interview-script`（docs）——面试材料口径修正与升级叙事。
- **代码**: 无。
- **测试**: 无新增测试（docs-only）；一致性校验用扩展词表 grep（`23 个`/`34 个`/`450+`/`claw-swe-bench`/`26 + 10`/`130 文件`/`~1691`/`36（26`）确认 5 份目标文档清零。
- **文档**: `docs/resume-description.md`、`docs/interview-script/questions/Q13-benchmark.md`、`docs/interview-script/walkthrough/W07-observability-benchmark.md`、`docs/interview-script/FINAL-master-script.md`、`docs/interview-script/walkthrough/README.md`（用户 Q4 确认纳入第 5 份）五份修改；`docs/openspec-change-backlog.md` 更新；README/README_EN 实测已为 27/37（C1 同步），无待改。
- **基准**: 无行为影响（纯文档）。
- **流程（process）**: 面试叙事与评测现状对齐——升级方向标「设计已定、C1–C3 实现中」+ 双要素标注（升级目标 ~90 + 当前已落 37），不把未实现写成已实现。
- **已知债务（2026-08-17 用户确认，不扩 scope）**: `docs/architecture.md`/`docs/development-guide.md`/`docs/testing-guide.md`/`docs/benchmark-plan.md`/`docs/coding-agent-roadmap.md` 的 `claw-swe-bench/` 失效目录引用记录于 design.md `## Known Debt`，后续专项清理。
- **状态**: 实现完成（tasks 2.x–6.x 已勾选），进入同步与审阅收尾。
