# Design: evaluation-protocol-reporting（C3）

## Context

C2 已实现指标层数据/统计/CLI（`benchmarks/statistics.py` pass^k/cost/fault_owner/paired_comparison、`benchmarks/models.py` 新字段、`agent/main.py` `--seeds/--temperature/--model-version`）。spec 顶部有渲染边界注记：「结果页渲染义务（`$/resolved-task`/cache hit rate/定价表版本展示、reason × fault_owner 交叉表、报告元组、SWE-bench 污染注记、部分成功档、采样参数、小样本声明、过程效率展示）归 C3」。

实测现状：
- `benchmarks/report.py`：`TaskAggregate`/`AggregateRun`、`render_report`（markdown）、`_render`（按层聚合/CI/延迟/成本估算）、`collect_run_results`/`aggregate_results`。**未渲染**：报告元组、污染注记、反作弊披露、fault_owner 交叉表、$/resolved-task、部分成功档、采样参数、小样本声明、过程效率。
- `benchmarks/compare.py`：`build_summary`/`build_html` 点估计对比表（任务表/summary/延迟百分位/成本估算），读 run.json 的 `agent`/`model`。**未接入** `paired_comparison`（C2 已实现于 statistics.py）。
- `agent/main.py`：benchmark CLI 有 `--repeat/--provider/--model/--agent/--seeds/--temperature/--model-version`。**无** `--budget-cap`/`--no-cap`/`--preflight`。
- **无** `scripts/self_check.py`、**无** `docs/benchmark-run-protocol.md`。
- T1 协议文档在 wayfinder-research worktree（`.gitignore` 调研区），未转正。

## Goals / Non-Goals

**Goals:**

- 运行协议文档转正（`docs/benchmark-run-protocol.md`）。
- 结果页披露渲染（spec 边界注记 10 项落地）。
- compare 配对渲染 + run 元数据补齐。
- CLI `--budget-cap`/`--no-cap`/`--preflight`。
- `scripts/self_check.py` 五门禁。
- spec 边界注记→已实现（MODIFIED）。

**Non-Goals:**

- **不改指标计算**（pass^k/cost/fault_owner/配对函数本体归 C2，本 change 只消费渲染）。
- **不改面试叙事** → 归 C4（并行，本 change 不碰 docs/interview-script）。
- **不做任务集扩展** → 归 C1 follow-up（#156 B 轨扩展）。
- **不跑真实评测烧钱**（用户定：只定协议不跑；数字由实现阶段按协议产出）。
- **不实现反作弊加固**（shallow/mirror 截断）→ 归后续项。
- **不引入前端框架**：结果页 markdown/HTML 沿用现有纯 Python 渲染。

## Decisions

### Decision D1: 运行协议文档转正为 `docs/benchmark-run-protocol.md`

**方案**：T1 `eval-run-protocol-2026-08-17.md` 内容转正为仓库正式文档 `docs/benchmark-run-protocol.md`（中文），清理 wayfinder-research 引用、落真实命令（`uv run asterwynd benchmark --repeat 5 --seeds 0 1 2 3 4 --temperature 0.2 --budget-cap 50`）。含任务集 82–90 口径、模型（本地 deepseek-v4-flash + API 前沿对照）、采样（repeat 5 + seed 0..4 + temp 0.2）、预算（`--budget-cap`/`--budget-cap 0` 取消）、对照（换 agent/换 model 分开）、artifact 布局、自洽五门禁、reproduction。

**理由**：T1 已按 map 决策定稿；转正使协议成为仓库可引用资产，C4 叙事引用它。

### Decision D2: 结果页披露渲染清单（10 项）

**方案**：`benchmarks/report.py` 渲染以下披露段（在既有按层聚合/CI/延迟/成本基础上追加）：
1. 报告元组（model/harness/task_set_hash/grader/成本口径，读 RunMetadata 新字段）
2. SWE-bench 污染注记（保留条件域：OpenAI 2026-02 弃用 + 138 实例 59.4% 缺陷 + 子集过滤/版本钉住）
3. 反作弊泄漏披露（A 轨回归基线定位 + 来源/时间范围）
4. reason × fault_owner 交叉表（读 TaskResult.fault_owner）
5. $/resolved-task + cache hit rate + 定价表版本
6. f2p/p2p 部分成功档（读 TaskResult.partial）
7. 采样参数（temperature/seed/model version）
8. 小样本声明（N=3–5 附声明）
9. 过程效率（time-to-first-successful-edit / exploration fraction）
10. 能力覆盖矩阵（C1 manifest，套件级展示）

**备选**：只加元组 + 污染注记。被拒：spec 边界注记明确 10 项渲染义务，缺项会留下"实现了但结果页不可引用"。

**理由**：C2 已备好全部数据/统计字段，渲染是纯消费层；golden 测试锁片段。

### Decision D3: compare 配对渲染 + 元数据补齐

**方案**：`compare.py` 接入 `statistics.paired_comparison`（C2 已实现），`build_summary`/`build_html` 对成对 run 输出 per-task delta 表 + 差异 CI + win-rate + McNemar p 值；run 元数据补齐（model version/date/cost 口径读 run.json 新字段）。

**理由**：G3 M8 面试卖点"同任务同 harness 换 agent 对比不能只给两个点估计"；C2 已实现统计函数，本 change 只接线渲染。

### Decision D4: CLI `--budget-cap`/`--no-cap` + `--preflight`

**方案**：
- `--budget-cap <USD>`：成本上限（建议默认 $50），运行中累计成本超限停止该 run 并标 `incomplete`（新增状态，C2 数据模型可承载）；`--budget-cap 0`（或 `--no-cap`）取消上限。
- `--preflight`：Docker daemon 探测 + 内存检查（可用内存 <8GiB 提示走 L1 本地路径，不强制失败）；退出码 0=可跑全量、1=需 L1 降级。
- 两者均与 C2 的 `--seeds/--temperature/--model-version` 组合使用。

**理由**：用户 2026-08-17 已定「预算可配置、可取消」；T1 协议命令面直接落地；`--preflight` 处置内存墙（R2 实测 2.5GiB < 8GiB）。

### Decision D5: `scripts/self_check.py` 五门禁

**方案**：独立 CLI `uv run python scripts/self_check.py <run_dir>`，校验五门禁：
1. 同模型同 harness 复现（report 元组存在且一致）
2. seed 复现（采样参数记录完整）
3. 失败归因闭环（fault_owner + 校准证据 + reason×owner 交叉表存在）
4. 披露段齐全（污染注记 + 严格 resolved + f2p/p2p 保留 + A 轨泄漏 + 小 N 声明）
5. 报告元组完整（model/harness/task_set_hash/grader/成本口径）
每门禁 exit 非零时输出缺失项；全部通过 exit 0。

**理由**：T1 自洽五门禁落地为可执行检查，面试数字自洽性的机械保证。

### Decision D6: spec 边界注记→已实现（MODIFIED）

**方案**：本 change 的 spec delta 以 MODIFIED 方式更新 C2 留下的渲染边界注记（`openspec/specs/benchmark/spec.md` 顶部注记 + 各 Requirement 的渲染子句），标注「渲染义务已由 C3 实现」。

**理由**：spec 与实现一致（C2 只实现数据/统计/CLI，C3 补齐渲染），清理边界注记防 overclaim。

### Decision D7: Verified 40 fixture 前置（范围外阻塞项）

**方案**：C3 的 `docs/benchmark-run-protocol.md` 在 Verified 子集节注明「40 条新 fixture 待数据可达环境执行 `build_subset` 生成（跟踪 #156）」；本 change 不实现 fixture 生成（C1 已交付工具），只做协议文档中的口径与 reproduction 步骤说明。

**理由**：huggingface 本环境不可达（C1 实测 load_dataset 超时），不阻塞协议/渲染/compare 交付；披露口径（KNOWN_BAD/偏置/版本钉住）已在 spec 与 C1 manifest 落定。

### Decision D8: C4 并行边界

**方案**：本 change 不碰 `docs/interview-script/` 与 `docs/resume-description.md`（C4 `evaluation-narrative` 并行专属）；`docs/benchmark-run-protocol.md` 是本 change 与 C4 的契约点（C4 引用协议）。

**理由**：G4 C3/C4 并行决策；避免共享 docs 文件冲突（interview docs 归 C4、benchmark 协议归 C3）。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 协议/披露口径需对照业界（同 proposal 3 项）。
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录）。替代依据为 G3 决议（#150）M5 报告元组/M6 污染披露/M7 反作弊披露、R1（#145）SWE-bench 协议、T1（#152）五门禁、T2（#153）叙事引用。披露格式与协议口径已落 C1/C2 spec，本 change 渲染/文档化。
- design impact: D1–D8 全部来自 map 已确认决策；无新增调研依赖。

## Risks / Trade-offs

- **[披露渲染 golden 测试易碎] → 用片段断言（不含时间戳/路径）锁关键披露段，避免全文件 golden。**
- **[--budget-cap 超限中断影响既有 run 语义] → 缺省不设上限保持既有行为；超限标 `incomplete` 不伪造结果（C2 数据模型可承载）。**
- **[self_check 门禁过严导致不可用] → 门禁按「缺失项报告 + 可配置跳过」设计，不全盘 FAIL。**
- **[C4 并行共享 docs 冲突] → D8 边界明确：interview docs 归 C4、benchmark 协议归 C3，不交叉。**
- **[spec 边界注记清理遗漏] → tasks 明确「MODIFIED 去渲染边界注记」清单 + validate/checker 兜底。**

## Pre-Implementation Review

（占位：由独立零记忆 grill subagent 对 design.md 逐项追问后填写结论；grill 产出 `reviews/grill-design.md`，Open Questions 停轮等用户确认。）

## Testing Strategy

- 单元测试（`tests/benchmark/`）：披露渲染 golden 片段（元组/污染注记/反作弊/fault_owner 交叉表/$/resolved-task/部分成功档/采样参数/小N/过程效率）、compare 配对渲染（delta/CI/win-rate）、CLI `--budget-cap`（超限 incomplete）/`--no-cap`/`--preflight`（内存 <8GiB）、self_check 各门禁（缺失项报告 + exit 码）。
- 回归测试：既有 report/compare/结果页测试不回归。
- benchmark 层级测试：`--repeat 3 --seeds 0 1 2` fake runner smoke，确认结果页含披露段。
- 兼容测试：旧 run.json 无新字段时结果页不崩（渲染兜底）。
- 每个 bug fix 新增回归测试；涉及 benchmark 路径必须覆盖 benchmark 层级测试。
