# Design: evaluation-btrack-expansion

## Context

C1 已交付：B 轨 5 条（4 陈旧重写 002-sandbox-executor/004-benchmark-cli/005-bash-workspace/021-lsp-diagnostics → B 轨当前 HEAD + 1 新增 `asterwynd-b01-report-family-summary`，scenario=integration/difficulty=hard/track=B）、manifest coverage 矩阵（7 能力列 × 5 场景列机械校验 ≥1）、`task_schema` 的 scenario/difficulty/track 字段。C1 grill OQ-B1（2026-08-17 用户按推荐确认）给出了 CP-1~CP-4 context-planning 候选 + long-term-memory scope 隔离 + long-context 大读取形态。

当前覆盖矩阵（manifest）能力列现状：tool-usage ✅ / context-planning ⚠️（仅 010/022，无 B 轨）/ multi-step-solving ✅ / error-recovery ✅ / safety-boundary ✅（002/005 重写）/ long-term-memory ⚠️（2 条 A 轨）/ long-context ⚠️（仅 b01）。场景列：bug-fix/feature-dev/refactor/debug/integration 需每场景 ≥1–2。

## Goals / Non-Goals

**Goals:**

- B 轨 5 → 12–16 条（新增 7–11）。
- context-planning 补 3–5 条 B 轨任务（面试亮点）。
- long-term-memory +1（scope 隔离）、long-context +1–2（大读取 + 小改动）。
- 每场景 ≥1–2；含 2–3 条 hard。
- 每任务测试先行（issue.md 不给路径 + 确定性验证 + 覆盖矩阵登记）。
- manifest coverage 矩阵扩展；C4 任务数数字校准。

**Non-Goals:**

- **不改 A 轨**（22 条保持，grill 实测口径；C1 重打标后 A=22/B=5/verified=10/总 37）。
- **不改既有 B 轨 5 条**（002/004/005/021/b01 保持）。
- **不做 Verified 40**（归并行的 evaluation-verified-subset）。
- **不引入外部任务集**（B 轨全为本地真实模块构造）。
- **不改 benchmark 运行逻辑**（只加任务 + manifest + 校验器小改：Q6 确认扩展 `validate_coverage` per-track B 能力列校验）。

## Decisions

### Decision D1: 任务清单（CP-1~CP-4 + LT-MEM-1 + LC-1 + BF-1）

**方案**（来自 C1 grill OQ-B1 候选 + 本 change grill OQ-1~7 用户确认，2026-08-18）：
- **CP-1**（feature-dev / multi-step-solving / tool-usage / context-planning）：新增工具 `ListRunningBenchmarks`（类名按惯例 `ListRunningBenchmarksTool`），注册进 `agent/tools/registry.py` 并经 `agent/tools/factory.py` 装配、在 `agent/loop.py` AgentLoop 主循环可调用，补 contract 测试。验证：`pytest tests/...` 断言工具已注册且经 `run()` 可调用。难度：hard。
- **CP-2**（refactor / context-planning）：`flow/statechart.json` 新增 awaiting 态 `awaiting_grill_confirmation`，**触面 6 处**（grill OQ-5 确认）：①`flow/statechart.json` 新增态；②`agent/workflow/event_log.py` 的 `AWAITING_SUB_STATES` 镜像常量；③`scripts/workflow_state.py` 的 `args.awaiting` 校验（~L576）；④`scripts/workflow_state.py` 的 `_AWAITING_RECOVERY_DEFAULTS`（`flow confirm` recovery 目标）；⑤`scripts/workflow_methods.json` 方法映射；⑥parity 测试 `tests/test_declarative_flow_engine.py`。难点：先理解 statechart↔engine↔event_log↔workflow_state↔parity 五者关系。难度：hard。
- **CP-3**（integration / context-planning / multi-step-solving）：`benchmarks/report.py` 结果页新增按 `track`（A/B/verified）分组数量与占比（spec「任务集由三来源组成」Scenario）。grill 核验：`benchmarks/models.py` 的 `TaskResult` 现只有 `task_family`/`category` 无 `track`，需 models+runner+statistics+report 管道改造（5 处 `TaskResult(...)` 构造点），触面写进 issue.md。需读 report.py + run.json schema + statistics.py。难度：medium。
- **CP-4**（debug / context-planning / error-recovery）：**合成回归**（grill OQ-2 确认，原「未转义 bug」前提与 HEAD 不符）：base 人为去掉 `benchmarks/adapters.py` 的 `model_name.replace("/","__")` 转义（合成回归制造缺陷），gold 加回 + 单测断言「路径转义后与 harness 目录命名一致」。若判别力弱则换本地可确定性验证的其它 debug 任务。难度：medium。
- **LT-MEM-1**（feature-dev / long-term-memory）：project 身份双端闭合（grill OQ-7 确认）：`SaveMemoryTool` 新增 `--project <hash>` 参数（`agent/tools/builtin/memory.py`）+ `agent/context/sources.py` 的 `MemoryIndexSource` 按当前 session project 过滤注入。验证：先写 A 项目记忆、切 B 项目确认不可见、切回 A 复用（测试构造两个 project 实例断言隔离）。难度：medium。
- **LC-1**（refactor / long-context）：拆分目标钉具体（grill OQ-4 确认）：把 `agent/context/sources.py` 里 memory 注入逻辑下沉到 `agent/memory/` 的明确归属（如 `agent/memory/context_source.py` 或同类），`MemoryIndexSource` 保留在 context 层但渲染逻辑调 memory 层 API；base 红用「行为保持断言 + 新模块路径可用」双断言，避免纯符号搬家。保持现有测试全绿。难度：hard。
- **BF-1**（bug-fix / error-recovery，第 7 条，grill OQ-1 确认 B=12）：从 command_guard/sandbox 等真实模块挑一个本地可确定性验证的缺陷形态（红绿可复现）。

**覆盖矩阵目标**：context-planning 由 CP-1/2/3/4 覆盖、long-term-memory 由 LT-MEM-1、long-context 由 LC-1 + b01；每场景 ≥1–2（bug-fix 由既有 005/004-harden/011/017/020 + 新 BF-1、feature-dev CP-1/LT-MEM-1、refactor CP-2/LC-1、debug CP-4、integration CP-3/b01）。B 轨总数 = 5 + 7 = 12，达 proposal/C1「B 轨 12–16」下限。

**备选**：只补 3 条 context-planning / 接受 B=11 收敛。被拒：C1 grill 用户确认的形态（CP-1~4 + LT-MEM + LC + BF-1）覆盖全部能力列目标且 B=12 达下限。

**理由**：全部来自已确认候选 + grill OQ-1~7 用户确认；每任务测试先行 + 覆盖矩阵登记；难度梯度 hard×3（CP-1/CP-2/LC-1）。任务数口径实测 A=22/B=5/verified=10/总 37（grill 事实基线）。

### Decision D2: 任务设计规范（issue.md 不给路径）

**方案**：每个新任务 issue.md 只给行为症状/目标 + 业务背景，**不给目标文件路径**（迫使 agent 先 repo-map 定位再规划）；task.json 用 `scenario`/`difficulty`/`track=B`；gold.patch = 参考实现（实现 agent 先写验证再写任务）；test_command 确定性断言。

**理由**：B 轨定位"面试核心"（G2），不给路径才能测 context-planning 能力；与 C1 B 轨既有任务（b01 同规范）一致。

### Decision D3: 覆盖矩阵校验（含 per-track B 扩展）

**方案**：manifest coverage 登记新任务后，跑 `validate_coverage`（C1 交付）确认 7 能力列 × 5 场景列 ≥1。grill OQ-6 确认扩展：`benchmarks/task_set.py` 的 `validate_coverage` 增加 per-track B 能力列要求——`required_track_coverage = {"context-planning": {"B"}, "long-term-memory": {"B"}, "long-context": {"B"}}`，只对声明的缺口列生效（A+B 聚合校验保留；新任务若引入新能力列需小改校验器）。

**理由**：覆盖矩阵是"场景×能力"的可引用证据（G1），机械校验防漂移；per-track B 校验让 spec delta「context-planning 列 SHALL 有 B 轨任务登记」有机械强制（否则交付 0 条新任务门禁也绿，grill R3）。

### Decision D4: 面试叙事数字校准（grill OQ-3 全套清单）

**方案**：B 轨合入后任务数 37+7=44（27 本地 → 34 本地，总 → 44；A=22/B=12/verified=10）。A 轨以实测 22 为准（不延续「26 A 轨」错误口径）。change 内更新 C4 引用的数字，**全套清单**（grill OQ-3 确认）：
- `docs/interview-script/FINAL-master-script.md`：L11「37 任务评测闭环」、L27「37 任务（27 本地 + 10 SWE-bench）」、L96「评测 37 任务…从 37 扩到 ~90」、L117「评测任务 37（27 本地 + 10 SWE-bench）」、L118「~90（…当前已落 37）」→ 按实测新数字；升级行「当前已落 37」→ 新数字。
- `docs/interview-script/walkthrough/README.md` L27：同步。
- `docs/resume-description.md` L9/L87/L104：写「27 本地（26 A + 1 B）」→「34 本地（22 A + 12 B）」。
- `README.md` L36/L178/L373、`README_EN.md` L36/L178：同步（README 修改须同变更同步 README_EN，AGENTS.md 维护规则）。
数字口径以 change 实现时实测为准（C4 教训：按 master 实测而非预定数字）。

**理由**：C4 合入后 B 轨扩展改变任务数，面试材料必须同步避免穿帮（C4 review-loop 对数字一致性是 PASS 项）；D4 原「26 A 轨 + N B 轨」会延续错误口径（grill R4）。

### Decision D5: 与 Verified-subset 并行——manifest 错开合入

**方案**：本 change 只改 manifest 的 coverage 矩阵段（新任务登记 + 能力列）；verified-subset 改 verified 条目段。错开合入，后合者 rebase。

**理由**：G4 系列并行模式；两 change 各改 manifest 不同段，冲突面最小。

### Decision D6: 每任务红绿可复现

**方案**：每个新增任务验证「base 红 + gold 绿」：task 加载 → 应用 gold.patch → test_command 过；不加 gold.patch → test_command 红（证明任务有判别力）。全部红绿验证通过才提交。

**理由**：C1 教训（弱评估 022 用 grep 关键词打分、2 gold.patch 空）；B 轨任务必须真判别力，防"看起来有任务实则没验证"。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 常规任务设计（C1 已调研 G1/G2 + OQ-B1 候选确认）；本 change 是候选落地实现。
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录）。C1 归档 change grill-design.md OQ-B1 含 CP-1~CP-4 候选具体设计；manifest/validate_coverage/task_schema 已就绪。
- design impact: D1–D6 直接承接 C1 已确认候选；无新增调研依赖。

## Risks / Trade-offs

- **[任务设计超出手工可验证范围] → D6 红绿可复现硬性；任一任务红绿不成立则不提交（宁可收敛条数）。**
- **[context-planning 任务设计难（不给路径 vs 模型能力）] → issue.md 症状描述 + hints_text 给线索但给不给路径由实现 agent 定（C1 b01 先例）。**
- **[C4 数字校准滞后/口径错] → D4 实现时实测 + 全套清单（FINAL 5 行/walkthrough/resume/README/README_EN）+ A 轨以实测 22 为准（grill OQ-3）。**
- **[manifest 与 verified-subset 冲突] → 只改 coverage 段 + 错开合入（D5）；前提 verified-subset 用独立顶层段（grill R6）。**
- **[任务数目标 12–16 可能达不到] → 7 条候选 B=12 达下限；若某候选做不出判别力，如实记录收敛 + 在 #156 标注（C1 先例：5 条收敛）。**
- **[CP-4 合成回归判别力弱] → base 人为去掉转义 + gold 加回 + 单测断言路径转义一致性；判别力不足则换本地确定性 debug 任务（grill OQ-2）。**
- **[LC-1 弱判别力（重构不改行为）] → base 红用「行为保持断言 + 新模块路径可用」双断言，避免纯符号搬家重演 C1 022 教训（grill OQ-4）。**
- **[CP-2 触面低估] → 6 处清单写进 issue.md（statechart/event_log/workflow_state×2/methods/parity），避免 agent 只改 statechart 卡死（grill OQ-5）。**
- **[per-track B 机械校验缺口] → validate_coverage 扩展 required_track_coverage，防「0 新任务也过门禁」（grill OQ-6）。**

## Pre-Implementation Review

独立零记忆 grill（`reviews/grill-design.md`，2026-08-18）已完成，结论如下：

**已确认（5）**：D2 不给路径、D6 红绿硬性、D1 能力补缺方向（CP-1/CP-2/CP-3/LT-MEM-1 候选实测可构造）、D5 只改 coverage 段（前提 verified-subset 用独立顶层段）、D3 校验方向（需扩展 per-track B）。grill 门禁自检无死锁；`reviews/**` 写豁免成立；tasks 1.3 停轮确认有机械强制。

**需修改（待用户确认后整合进 D1/D3/D4 与 tasks）**：
- D1：任务数口径——实测 A=22（非 26）、B=5、verified=10、总 37；6 条候选落地后 B=11，低于 proposal/C1「B 轨 12–16」下限 12，需补第 7 条 bug-fix 或明确收敛（OQ-1）。
- CP-4：前提与 HEAD 不符——`benchmarks/adapters.py:125` 已做 `model_name.replace("/","__")`，「未转义 bug」不存在，按现描述不可构造（OQ-2）。
- D4：校准范围与数字——`walkthrough/README.md` 实际在 `docs/interview-script/walkthrough/`；resume 在 `docs/resume-description.md`（L9/L87/L104 写「26 A + 1 B」与实测 22 A + 5 B 不符）；校准范围漏 FINAL L27/L96/L118、README L36/L178/L373、README_EN L36/L178（OQ-3）。
- CP-2 触面：真实为 6 处（补 `agent/workflow/event_log.py` AWAITING_SUB_STATES + `scripts/workflow_state.py` _AWAITING_RECOVERY_DEFAULTS），非「跨 4 处」（OQ-5）。

**Open Questions（Q1–Q7，停轮等用户确认后写入 `## User Confirmation`）**：Q1 B 轨下限 12 vs 11；Q2 CP-4 前提与红绿构造；Q3 D4 校准范围与 22/26；Q4 LC-1 拆分方向与 base 红判别力；Q5 CP-2 六处触面；Q6 validate_coverage per-track B 机械校验；Q7 LT-MEM-1 project 身份来源。详见 `reviews/grill-design.md`。

## Testing Strategy

- 单元测试：新增任务各一条（加载 + base 红 + gold 绿断言）；覆盖矩阵 validate_coverage 全过。
- 集成测试：`--tasks <glob>` 单任务 smoke（fake runner 发现/执行新 B 轨任务）。
- 回归测试：既有 A 轨/B 轨任务 + benchmark 全量不回归。
- 面试数字校准：grep 确认 4 处文档任务数一致（FINAL/walkthrough/resume/README）。
- 每个 bug fix 新增回归测试；涉及 benchmark 路径必须覆盖 benchmark 层级测试。
