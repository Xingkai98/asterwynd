# Design: evaluation-narrative（C4）

## Context

T2 叙事改动清单（`docs/research/narrative-changes-2026-08-17.md`，map #144 已确认，2026-08-17）是精确编辑清单：总原则 + 每文件编辑表 + 关键段落草案。本 change 按它落进 4 份面试文档。实测现状（2026-08-17 主仓库 master `88ed98a`，C2 合入后）：

- `docs/resume-description.md`：L9/L104「23 个」、L87「34 个」、L23/L116「450+」、L9/L89/L105/L125-126/L132 多处 `claw-swe-bench/` 目录表述。
- `Q13-benchmark.md`：L7 任务两类、L11 指标层（无 pass^k/cost@pass/fault_owner）、L13 对比层（无配对比较）、L15 面试重点（无污染披露）、L64 Claw 表述。
- `W07-observability-benchmark.md`：L3/L98 36+ 保留、L104-109 加分点 4 条。
- `FINAL-master-script.md`：L111 130/~1691、L112 38 工具、L117 36 任务、bullet 7 L96、速查表 L106-127。

**数字口径基线**（已核实）：本地任务 26（C1 新增 b01 后 27，A 轨 26 + B 轨 1）；测试 135 文件/1700+ 函数；内置工具 38；36 = 26 本地 + 10 swebench。

## Goals / Non-Goals

**Goals:**

- 4 份文档按 T2 编辑清单修正现状口径（resume 任务数/测试数/Claw 重锚、FINAL 速查表 135/1700+）。
- 升级叙事段写入 Q13/W07/FINAL（场景化 ~90/pass^k/cost@pass/fault_owner/配对比较/污染披露/预算），全部标「设计已定、C1–C3 实现中」。
- 简历 bullet 7 改后草案落地。

**Non-Goals:**

- **不把未实现写成已实现**（升级数字不伪装成当前能力）。
- **不改 benchmark 代码/spec**（归 C1/C2/C3）。
- **不改 T1 协议文档**（归 C3，本 change 只引用）。
- **不重跑 comparison.md**（C3 按协议产出后替换；本 change 不引用其数字）。
- **不改 README/README_EN 中与任务数无关的内容**（如涉及任务数才同步）。

## Decisions

### Decision D1: 现状口径修正（resume + FINAL 速查表）

**方案**：按 T2 编辑表逐行修正：
- resume L9/L104 23→26、L87 34→26、L23/L116 450+→1700+；L9/L89/L105/L125-126/L132 Claw-SWE-Bench 目录表述 → 统一 harness 口径（SwebenchAdapter + 多 runner）。
- FINAL L111 130/~1691→135/1700+；L112 38 保留 + 口径注明「38 内置（KNOWN_BUILTIN_TOOL_NAMES 已知名数，含默认关闭的浏览器工具）」；L117 36 保留 + 追加升级行。

**理由**：T2 总原则 1「现状口径与升级方向分层」；resume 内部 23 与 34 自相矛盾必须统一（R3 发现）。

### Decision D2: 升级叙事段（Q13/W07/FINAL）

**方案**：
- Q13 L7 加场景×难度分层 + 三来源（带过渡句区分「两类=执行类型轴」）；L11 指标层加 pass^k/cost@pass/fault_owner；L13 对比层加配对比较；L15 面试重点加污染披露 + pass@1/pass^k 口径 + 内联 Claw 重锚。
- W07 L104-109 追加 4 条升级加分点（场景化 ~90/pass^k、污染披露、反作弊诚实边界、预算可配置可取消——标 C2/C3 交付）。
- FINAL bullet 7 L96 追加升级句 + 速查表新增升级数字行（~90/pass^k/cost@pass/fault_owner/预算，标「设计已定/实现中」）。

**理由**：T2 各文件编辑表 + 段落草案直接落地；升级全部标实现中，不穿帮。

### Decision D3: 简历 bullet 7 改后草案

**方案**：T2 给的改后草案落地：
> "内置 26 个本地 coding-agent 任务 + SWE-bench Verified 子集，git worktree 隔离 + hidden test patch 确定性验证，bootstrap 95% CI（固定 seed）统计，pass@1/pass@k 指标，支持跨 agent 统一 harness 对比和 CI 回归门禁。"

升级方向（~90/pass^k/cost@pass）**不上简历**（未实现），面试讲稿讲路线。

**理由**：T2 §1 bullet 7 草案；升级不上简历原则。

### Decision D4: C3 并行边界与校准

**方案**：本 change 与 C3 并行。升级叙事段标「C1–C3 实现中」不依赖 C3 合入即可落；C3 合入后如有数字变化（如任务数、协议细节），本 change 收尾时校准。不碰 `docs/benchmark-run-protocol.md`（C3 专属）。

**理由**：G4 C3/C4 并行决策；现状口径修正零依赖，升级叙事段措辞稳定（标实现中）。

### Decision D5: 不引用 comparison.md

**方案**：面试材料不引用 `benchmarks/reports/comparison.md` 的 myagent 旧数字（R3 确认其为 2026-06 一次性产物、与当前任务集/agent 名不符）；C3 重跑后替换。

**理由**：T2 总原则 4；避免面试引用过时能力证据。

## Reference Implementation Research

- status: enabled
- research_tier: exempt
- reason: docs-only + 数字均已核实 + 编辑清单来自已确认 T2 交付物（#153 已关闭）；引用已关闭决策路径，无待定设计项。
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录）。数字口径来源：R3（#147）实测 + C1 合入后任务数 27；编辑位置与草案来自 T2（#153）。
- design impact: D1–D5 直接承接 T2 编辑清单；无新增调研依赖。

## Risks / Trade-offs

- **[升级叙事误写成已实现] → 全部升级段标「设计已定、C1–C3 实现中」；简历不上升级数字（D3）。**
- **[数字口径漂移（C1 后 27 vs 26）] → 以 C1 合入后实测为准（A 轨 26 + B 轨 1 = 27）；T2 原文 26 为 C1 前口径，落稿时用当前 master 核实。**
- **[C3 合入后数字变化] → 本 change 收尾时校准升级段；C3 协议文档是契约点（D4）。**
- **[Claw 重锚误伤历史] → 只改失效目录表述，不动历史口径说明。**
- **[README 同步遗漏] → tasks 明确「如涉及任务数同步 README/README_EN」。**

## Pre-Implementation Review

（2026-08-17 由独立零记忆 grill subagent 完成，产出 `reviews/grill-design.md`，run id `f1c9210c-1fd3-47f2-9358-09b84b483d5a`。）

**已确认（6 条，详见 grill-design.md）**：D3 升级不上简历；D4 C3 并行边界不碰 `docs/benchmark-run-protocol.md`；D5 不引用 `comparison.md`；38 内置工具口径（含默认关闭浏览器工具）；污染披露数字 138/59.4% 有 spec 依据；Change Type 保持 `process`（docs 主类型会放宽门禁，保持 process 门禁更严）。

**grill 发现的核心矛盾（须用户确认后修正 D1/D3 目标数字）**：design 落稿目标（resume 26、FINAL 36、测试 135/1700+）与当前 master 实测（本地任务 27 = 26 A 轨 + b01、总任务 37 = 27 + 10 swebench、测试 148 文件/1997 函数）不一致；直接按 D1/D3 落稿会把旧口径换成另一版旧口径。

**Open Questions（8 条，待用户确认后记录进 grill-design.md `## User Confirmation`）**：
- Q1: FINAL 速查表「评测任务 36（26+10）」写 36 还是 37（含 L11/L27/L96 三处 36+ 联动）？
- Q2: resume 本地任务数用 27（含 b01）还是 26（仅 A 轨）？连带 L9/L104/L87 目标数与 D3 草案逐字。
- Q3: FINAL「自动化测试」写 148/~1997 还是 135/1700+？连带 resume 450+→1700+ 或 ~1997。
- Q4: `docs/interview-script/walkthrough/README.md` L27-L28（26+10=36 / 130/~1691）是否纳入本 change（第 5 份文档）+ 6.1 grep 词表扩展？
- Q5: D3「简历 bullet 7 草案」落点：推荐写法 L9 / 选项 A / 展开版 §6？
- Q6: W07 L98 核实表「26+10=36 ✅」与 L3 顶部引用句是否同步（与 Q1 联动）？
- Q7: 升级叙事「~90」是否统一「目标 ~90 + 当前已落 37」双要素标注？
- Q8: 缺失的逐字段落草案来源：design 内补齐（停轮覆盖）还是用户提供外部 T2 路径（`docs/research/narrative-changes-2026-08-17.md` 在所有 git 分支不存在）？

**停轮状态**：Open Questions 未确认前不落稿 4 份目标文档（grill-confirmation-gate，issue #95）。

## Testing Strategy

- docs-only change：无新增功能测试。
- 一致性校验：落稿后 grep 确认无残留「23 个/34 个/450+/claw-swe-bench/」错误口径（README 同步）；数字与 C1 合入后 master 一致。
- 若存在文档检查脚本则跑过；跑 `npx openspec validate` + artifact checker。
