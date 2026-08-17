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
- reason: docs-only 变更（无新增能力面），数字口径均已核实（R3 资产盘点 #147 + C1 实测），编辑清单来自已确认的 T2 交付物；无待定设计项，引用已关闭决策路径（#153 已关闭、`docs/research/narrative-changes-2026-08-17.md` 已定稿）。
- research questions: 无（exempt）。
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录）。数字口径来源：R3（#147）实测 26 本地 + 10 swebench、135 测试文件/1700+ 测试函数、38 内置工具（KNOWN_BUILTIN_TOOL_NAMES）；C1 合入后本地任务 27（26 + b01）。编辑清单为 T2（#153）交付物。
- design impact: 4 份文档的编辑位置与段落草案由 T2 交付物给出，design.md 承接。

## Impact Analysis

- **能力域**: `interview-script`（docs）——面试材料口径修正与升级叙事。
- **代码**: 无。
- **测试**: 无新增测试（docs-only）；若存在文档校验脚本则跑过。
- **文档**: `docs/resume-description.md`、`docs/interview-script/questions/Q13-benchmark.md`、`docs/interview-script/walkthrough/W07-observability-benchmark.md`、`docs/interview-script/FINAL-master-script.md` 四份修改；`docs/openspec-change-backlog.md` 更新；README 如涉及任务数同步（含 README_EN）。
- **基准**: 无行为影响（纯文档）。
- **流程（process）**: 面试叙事与评测现状对齐——升级方向标「设计已定、C1–C3 实现中」，不把未实现写成已实现。
