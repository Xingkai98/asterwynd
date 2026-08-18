# Design: evaluation-narrative（C4）

## Context

T2 叙事改动清单（`docs/research/narrative-changes-2026-08-17.md`，map #144 已确认，2026-08-17）是精确编辑清单：总原则 + 每文件编辑表 + 关键段落草案。本 change 按它落进 4 份面试文档。实测现状（2026-08-17 主仓库 master `88ed98a`，C2 合入后）：

- `docs/resume-description.md`：L9/L104「23 个」、L87「34 个」、L23/L116「450+」、L9/L89/L105/L125-126/L132 多处 `claw-swe-bench/` 目录表述。
- `Q13-benchmark.md`：L7 任务两类、L11 指标层（无 pass^k/cost@pass/fault_owner）、L13 对比层（无配对比较）、L15 面试重点（无污染披露）、L64 Claw 表述。
- `W07-observability-benchmark.md`：L3/L98 36+ 保留、L104-109 加分点 4 条。
- `FINAL-master-script.md`：L111 130/~1691、L112 38 工具、L117 36 任务、bullet 7 L96、速查表 L106-127。

**数字口径基线**（grill 2026-08-17 实测 master）：本地任务 27（A 轨 26 含 readme-title + B 轨 1 b01）；测试 148 文件/~1997 函数；内置工具 38（KNOWN_BUILTIN_TOOL_NAMES）；37 = 27 本地 + 10 swebench。README/README_EN 已同步 27/37（C1 已改），面试材料是唯一旧口径残留源。

## Goals / Non-Goals

**Goals:**

- 5 份文档按 T2 编辑清单 + grill 实测修正现状口径（resume/Q13/W07/FINAL/walkthrough-README；任务数 27/37、测试 148/~1997、Claw 重锚）。
- 升级叙事段写入 Q13/W07/FINAL（升级目标 ~90/pass^k/cost@pass/fault_owner/配对比较/污染披露/预算，双要素标注「当前已落 37」），全部标「设计已定、C1–C3 实现中」。
- 简历 bullet 7 改后草案落地（展开版 §6，L87 行）。

**Non-Goals:**

- **不把未实现写成已实现**（升级数字不伪装成当前能力）。
- **不改 benchmark 代码/spec**（归 C1/C2/C3）。
- **不改 T1 协议文档**（归 C3，本 change 只引用）。
- **不重跑 comparison.md**（C3 按协议产出后替换；本 change 不引用其数字）。
- **不改 README/README_EN 中与任务数无关的内容**（如涉及任务数才同步）。

## Decisions

### Decision D1: 现状口径修正（resume + FINAL 速查表 + walkthrough/README）

**方案**（用户 2026-08-17 确认：数字以 grill 实测 master 为准，即 27/37/148/~1997）：
- resume：L9/L104「23 个」→「27 个（26 A 轨回归基线 + 1 B 轨当前演进）」；L87「34 个本地」行由 D3 草案整体替换；L23/L116「450+」→「~1997」；L9/L89/L105/L125-126/L132 Claw-SWE-Bench 目录表述 → 统一 harness 口径（SwebenchAdapter + 多 runner）。
- FINAL：L111「130/~1691」→「148/~1997」；L112 38 保留 + 口径注明「38 内置（KNOWN_BUILTIN_TOOL_NAMES 已知名数，含默认关闭的浏览器工具）」；L117「36（26 本地 + 10 SWE-bench）」→「37（27 本地 + 10 SWE-bench）」；L11/L27/L96「36+」→「37」。
- walkthrough/README（第 5 份目标文档，Q4 确认纳入）：L27「36+ 任务（26 本地 + 10 SWE-bench）→ 26 + 10 = 36」→「37 任务（27 本地 + 10 SWE-bench）→ 27 + 10 = 37」；L28「1700+ 自动化测试 → 130 文件 / ~1691 函数」→「148 文件 / ~1997 函数」。

**逐字 before/after**（resume，Q2/Q3/Q5 确认版）：
- L9：「内置 23 个 coding-agent 本地任务」→「内置 27 个本地 coding-agent 任务（26 A 轨回归基线 + 1 B 轨当前演进）」。
- L9 末：「并接入 Claw-SWE-Bench 统一对比框架」→「并以统一 harness（SwebenchAdapter + 多 runner）对比 Aider/OpenCode」。
- L23：「当前测试集中约 450+ 个测试函数」→「当前测试集约 ~1997 个测试函数」。
- L87：「内置 `benchmarks/` runner：34 个本地 coding-agent 任务，支持 worktree 隔离、hidden `test.patch`、fake/shell/Asterwynd runner、结构化 artifact。」→ D3 草案整行替换（含 27 个本地任务口径）。
- L89：「Claw-SWE-Bench 集成：`claw-swe-bench/` 注册 Asterwynd、Aider、OpenCode adapter，通过独立 harness 在目标容器内运行 headless solver。」→「统一 harness 对比：SwebenchAdapter + 多 runner（Asterwynd/ClaudeCode/Shell）在同一批任务上对比。」
- L104：「内置 23 个本地 coding-agent benchmark 任务」→「内置 27 个本地 coding-agent benchmark 任务（26 A 轨回归基线 + 1 B 轨当前演进）」。
- L105：「并接入 Claw-SWE-Bench 对比 Asterwynd / Aider / OpenCode 等 agent 的解题表现」→「并以统一 harness（SwebenchAdapter + 多 runner）对比 Asterwynd / Aider / OpenCode 等 agent 的解题表现」。
- L116：「用约 450+ 回归测试覆盖…」→「用约 ~1997 个回归测试覆盖…」。
- L125-126：「集成 Claw-SWE-Bench，新增 Asterwynd headless solver 与 Asterwynd/Aider/OpenCode adapter…」→「统一 harness 对比：SwebenchAdapter + 多 runner（Asterwynd/ClaudeCode/Shell）在同一批任务上对比…」。
- L132：「并接入 SWE-bench / Claw-SWE-Bench 做可复现评测」→「并以 SWE-bench / 统一 harness 做可复现评测」。

**理由**：T2 总原则 1「现状口径与升级方向分层」；resume 内部 23 与 34 自相矛盾必须统一（R3 发现）；grill 实测 master 后用户确认 27/37/148/~1997 为准，避免引入另一版旧口径。

### Decision D2: 升级叙事段（Q13/W07/FINAL）

**方案**（用户 2026-08-17 确认 Q7：升级「~90」统一双要素标注「升级目标 ~90（设计已定：A 轨 20–24 + B 轨 12–16 + Verified 50；当前已落 37）」，标「C1–C3 实现中」）：
- Q13 L7 任务层加场景×难度分层 + 三来源（带过渡句区分「两类=执行类型轴」）；L11 指标层加 pass^k/cost@pass/fault_owner；L13 对比层加配对比较；L15 面试重点加污染披露 + pass@1/pass^k 口径 + 内联 Claw 重锚；L64 Claw 表述重锚。
- W07 L104-109 追加 4 条升级加分点（场景化 ~90 分层、污染披露、反作弊诚实边界、预算可配置可取消——标 C1–C3 交付）。
- FINAL bullet 7 L96 追加升级句 + 速查表新增升级数字行（~90/pass^k/cost@pass/fault_owner/预算，标「设计已定/实现中」）。

**逐字草案**（Q13，T2 §2 + Q7 双要素标注）：
- L7 任务层追加（过渡句区分两类=执行类型轴）：「在此基础上，评测任务按 **场景×难度** 分层组织（5 场景枚举 × easy/medium/hard），能力层用套件级覆盖矩阵表达（OpenHands 式）；任务集三来源：历史重建回归基线 + 当前 HEAD 真实缺陷/增强 + 开源测试集精选子集（升级目标 ~90 = A 轨 20–24 + B 轨 12–16 + Verified 50，设计已定、C1 实现中；当前已落 37 = 27 本地 + 10 Verified 子集）。」
- L11 指标层追加：「指标不止 pass 率——pass@1（用户实际获得）/ pass@k（能力上限）/ pass^k（可靠性，全部 k 次成功）；成本看 $/resolved-task（cache-aware 定价）；失败带 11 类 reason + fault_owner 归因（升级方向，C1–C3 实现中）。」
- L13 对比层追加：「对比不止点估计——per-task delta + 差异 CI + win-rate（paired bootstrap / McNemar）（升级方向）。」
- L15 面试重点追加：「引用 SWE-bench 数字**带污染披露**（OpenAI 2026-02 已弃用：审计 138 题中 59.4% 有实质缺陷 + 训练污染，当对照参考不当金标准）」；「pass@1 是用户实际拿到的质量，pass^k 是能不能 shipped——两个口径分开讲」；内联「Claw-SWE-Bench 统一 harness」→「对标 Claw-SWE-Bench 的统一 harness 口径（SwebenchAdapter + 多 runner）」。
- L64：「Claw-SWE-Bench 统一 harness」→「对标 Claw-SWE-Bench 的统一 harness 口径（SwebenchAdapter + 多 runner 对比 Aider/OpenCode），同一任务同一 grading 仅换 agent runtime」。

**逐字草案**（W07 加分点追加 4 条，T2 §3 + Q7 双要素）：
> 5. **评测升级路线**（设计已定、C1–C3 实现中）：任务集从 37 扩到升级目标 ~90（A 轨 20–24 + B 轨 12–16 + Verified 50），按场景×难度分层（5 场景 × 3 档），补 context-planning 空白；指标加 pass^k（可靠性）与 cost@pass（$/resolved-task）。
> 6. **SWE-bench 污染披露**：2026-02 OpenAI 弃用 Verified（138 题 59.4% 缺陷），我们引用时带披露，不当金标准——"知道 benchmark 的失效边界"本身是加分项。
> 7. **反作弊诚实边界**：A 轨历史重建任务在完整 git 历史中跑，agent 理论上能看到后续提交——我们披露这一自评局限（回归基线定位），B 轨与 Verified 子集不受影响。
> 8. **预算可配置可取消**（设计已定，C2/C3 交付）：`--budget-cap` 设上限、`--budget-cap 0` 取消（flag 当前代码库未实现），成本口径 cache-aware 四档——"跑评测不是无脑烧钱"。

**逐字草案**（FINAL，T2 §4 + Q1/Q7 确认）：
- L96 bullet 7 现状句后追加：「评测在升级：任务集从 37 扩到升级目标 ~90（场景×难度分层，A 轨 20–24 + B 轨 12–16 + Verified 50）、指标加 pass^k 与 cost@pass、SWE-bench 引用带污染披露——设计已定，实现中。」
- 速查表新增升级行（标「设计已定/实现中」）：`| 评测任务（升级目标） | ~90（设计已定：A 轨 20–24 + B 轨 12–16 + Verified 50；当前已落 37） | C1 `evaluation-task-spec` |`；`| pass^k | 全部 k 次成功（可靠性指标） | statistics.py 新增聚合（C2） |`；`| cost@pass | $/resolved-task，cache-aware 四档定价 | cost_tracker 扩展（C2/C3） |`；`| fault_owner | {agent, task, environment, unknown} | C2 |`；`| 预算 | `--budget-cap <USD>` / 0 取消 | C2/C3 |`
- 30 秒 pitch（L11）：「1700+ 自动化测试、37 任务评测闭环」保留现状数字（升级叙事放 bullet 7，不进 pitch）。

**理由**：T2 各文件编辑表 + 段落草案直接落地；升级全部标「设计已定/实现中」，不穿帮；Q7 双要素标注防「~90」被误读为已实现。

### Decision D3: 简历 bullet 7 改后草案

**方案**（用户 2026-08-17 确认 Q5 落点 C：展开版 §6 Benchmark 闭环，替换 L87「34 个本地」行；简洁版 L9 只改数字不塞长子弹。Q2 确认本地任务数 27）：

展开版 §6 首行（L87）before：
> "- 内置 `benchmarks/` runner：34 个本地 coding-agent 任务，支持 worktree 隔离、hidden `test.patch`、fake/shell/Asterwynd runner、结构化 artifact。"

after（D3 草案整行替换，含 27 本地任务口径）：
> "- 内置 27 个本地 coding-agent 任务（26 A 轨回归基线 + 1 B 轨当前演进）+ SWE-bench Verified 子集，git worktree 隔离 + hidden test patch 确定性验证，bootstrap 95% CI（固定 seed）统计，pass@1/pass@k 指标，支持跨 agent 统一 harness 对比和 CI 回归门禁。"

§6 其余行（外部 swebench-* 任务 / 统一 harness 对比 / 结果状态）保留，仅 L89 Claw 目录表述按 D1 重锚。

简洁版 L9 只做 D1 数字/重锚修正，不塞 D3 长子弹。

升级方向（~90/pass^k/cost@pass）**不上简历**（未实现），面试讲稿讲路线。

**理由**：T2 §1 bullet 7 草案 + Q5 用户确认落点；升级不上简历原则（总原则 1）。

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

- **[升级叙事误写成已实现] → 全部升级段标「设计已定、C1–C3 实现中」；简历不上升级数字（D3）；「~90」统一双要素标注「升级目标 ~90 + 当前已落 37」（Q7 确认）。**
- **[数字口径漂移] → 用户 2026-08-17 确认以 grill 实测 master 为准（本地 27、总 37、测试 148/~1997）；T2 原文 26/36/135/1700+ 为 C1/C2 合入前口径，不采用。**
- **[C3 合入后数字变化] → 本 change 收尾时按 tasks 7.6 校准升级段；C3 协议文档是契约点（D4）。**
- **[Claw 重锚误伤历史] → 只改面试材料 6 处失效目录表述（resume 5 + Q13 1），不动其他文档历史口径说明。**
- **[README 同步遗漏] → tasks 明确「如涉及任务数同步 README/README_EN」；实测 README/README_EN 已为 27/37（C1 同步），无待改。**

## Known Debt（2026-08-17 用户确认，不扩 scope）

`claw-swe-bench/` 目录已从 tree 移除（`git ls-files` 无跟踪），但以下文档仍引用该目录（失效指令/失效目录表述），记为已知债务，不在本 change 处理：
- `docs/architecture.md` L105/L116
- `docs/development-guide.md` L147/L226（`cd claw-swe-bench` 失效指令）
- `docs/testing-guide.md` L144/L147（同上）
- `docs/benchmark-plan.md` L23/L84/L88/L207/L470/L471/L665
- `docs/coding-agent-roadmap.md` L301/L304

后续由专项基建债务清理或涉及这些文档的 change 一并修正。

## Pre-Implementation Review

（2026-08-17 由独立零记忆 grill subagent 完成，产出 `reviews/grill-design.md`，run id `f1c9210c-1fd3-47f2-9358-09b84b483d5a`。）

**已确认（6 条，详见 grill-design.md）**：D3 升级不上简历；D4 C3 并行边界不碰 `docs/benchmark-run-protocol.md`；D5 不引用 `comparison.md`；38 内置工具口径（含默认关闭浏览器工具）；污染披露数字 138/59.4% 有 spec 依据；Change Type 保持 `process`（docs 主类型会放宽门禁，保持 process 门禁更严）。

**grill 发现的核心矛盾（已由用户确认解决）**：grill 实测 design 落稿目标（resume 26、FINAL 36、测试 135/1700+）与 master 实测（本地 27、总 37、测试 148/~1997）不一致。用户 2026-08-17 确认**以 grill 实测 master 数字为准**（Q1–Q3），D1–D3 已按确认更新为逐字 before/after 草案。

**Open Questions（8 条）**：用户 2026-08-17 经主 session 审阅后**全部按推荐执行**，实质答复逐条记录在 `grill-design.md` 的 `## User Confirmation` 节（每条含确认时间）。T2 逐字草案来源：grill 核验 master 实测数字 + T2 内容（`wayfinder-research` worktree 可读，`docs/research/narrative-changes-2026-08-17.md`）。

**停轮状态**：已解除（grill-confirmation-gate，issue #95）。用户确认齐备，进入 tasks 2.x–5.x 落稿 5 份目标文档。

## Testing Strategy

- docs-only change：无新增功能测试。
- 一致性校验：落稿后 grep 确认无残留「23 个/34 个/450+/claw-swe-bench/」错误口径（README 同步）；数字与 C1 合入后 master 一致。
- 若存在文档检查脚本则跑过；跑 `npx openspec validate` + artifact checker。
