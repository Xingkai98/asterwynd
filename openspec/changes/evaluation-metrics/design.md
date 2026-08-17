# Design: evaluation-metrics（C2）

## Context

C1 `evaluation-task-spec` 已合入并归档（PR #155）：`openspec/specs/benchmark/spec.md` 已含 M1–M11 指标/方法 Requirement（带「实现归 C2 evaluation-metrics」注记）。本 change 实现指标层，使 C3（结果页披露/运行协议）有真实统计可渲染。

实测现状（2026-08-17 主仓库 master `3be9dae`）：

- `benchmarks/statistics.py`：`mean_std`/`bootstrap_ci`（seed=0, 2000 次重采样）/`pass_at_k`（Chen 2021 组合计数，k=n 时坍缩为「≥1 成功」）/`layer_pass_rate`。**无 pass^k 聚合**（全部 k 轮成功）。
- `benchmarks/models.py`：`TaskResult`（task_id/agent/model/status/input_tokens/output_tokens/reason/category/run_round/task_family 等）、`RunMetadata`（run_id/agent/model/计数）。**无 cache tokens/temperature/seed/fault_owner/task_set_hash**。
- `agent/cost_tracker.py`：`MODEL_PRICES` 只有 sonnet-4/opus-4 两档，`compute_cost(model, input, output)` 只按 input/output 计价（无 cache 档）；**5 系/Flash 返回 unknown**。
- `benchmarks/adapters.py`：SwebenchAdapter 只取 `report.json` 的 `resolved` 布尔，**丢弃 f2p_rate/p2p_rate/reward**。
- `benchmarks/compare.py`：`build_summary`/`build_html` 只做点估计对比（任务表/summary/延迟百分位/成本估算），**无配对统计**。
- `agent/main.py`：benchmark CLI 有 `--repeat`（默认 1，`r1..rN`）、`--provider`/`--model`/`--agent`；**无 `--seeds`/`--temperature`/`--model-version`**。
- 结果页 `benchmarks/report.py`：按层聚合、bootstrap CI、pass_at_k、延迟/成本估算；无 pass^k/cost@pass/fault_owner 交叉表/小 N 声明。

## Goals / Non-Goals

**Goals:**

- 数据模型扩展（TaskResult/RunMetadata 新字段，向后兼容）。
- pass^k 新增聚合（区分 pass@1/pass@k/pass^k，无效轮次不进分母）。
- cache-aware 四档定价 + $/resolved-task + cache hit rate + 5 系定价表。
- fault_owner 正交 + reason×fault_owner 交叉表 + 标注来源声明。
- 配对比较统计（per-task delta + 差异 CI + win-rate）。
- f2p/p2p 部分成功保留。
- 小 N 统计声明。
- 采样显式化 CLI（--seeds/--temperature/--model-version）+ run 记录采样参数。
- spec 注记清理（REVISED 去掉「实现归 C2」）。

**Non-Goals:**

- **不做结果页披露渲染**（报告元组/污染注记/反作弊披露的渲染、`--budget-cap`/`--preflight`/`self_check.py` 五门禁）→ 归 C3 `evaluation-protocol-reporting`（本 change 只在数据模型/统计层把字段和口径准备好）。
- **不做 T1 协议文档**（`docs/` 运行协议文档）→ 归 C3。
- **不做面试叙事** → 归 C4。
- **不引入 numpy/scipy**（延续 bootstrap 纯 Python 风格；McNemar 用精确二项 / 超几何实现）。
- **不重写既有单次运行语义**与既有 artifact 结构（全部向后兼容扩展）。

## Decisions

### Decision D1: 数据模型新增可选字段，from_dict 向后兼容

**方案**：`TaskResult` 新增 `cache_read_tokens`/`cache_write_tokens`/`temperature`/`seed`/`fault_owner`（均 `int|float|str|None = None`）；`RunMetadata` 新增 `task_set_hash`/`max_iterations`/`timeout_seconds`/`network`/`adapter_version`/`prompt_version`/`pricing_table_version`。`from_dict` 保持「未知 key 忽略、缺失走默认」逻辑不变；`to_dict` 保持「None 省略」。

**备选**：新建独立 `EvaluationMeta` 结构。被拒：与既有 `TaskResult`/`RunMetadata` 同生命周期，拆分增加关联成本。

**理由**：向后兼容（旧 artifact 读取不受影响），字段落在既有数据模型上，C3 结果页可直接消费。

### Decision D2: pass^k 新增独立聚合，不复用 pass_at_k

**方案**：`statistics.py` 新增 `pass_k_success_rate(task_rounds: Sequence[bool]) -> float`：任务级「全部有效轮通过」布尔 → 跨任务均值（通过任务数 / 有效任务数）；无效轮次（unsupported/approval-unavailable/docker_unavailable）在输入聚合前即被排除（不进分母）。`pass@1` = 有效轮经验通过率（现有 `layer_pass_rate` 语义）；`pass@k` 保留现有组合计数（能力上限）；`pass^k` = 新增（可靠性）。三者在结果页并列标注语义。

**备选**：复用 `pass_at_k` 传 k=n。被拒：k=n 时 `1 - C(n-c,n)/C(n,n)` 坍缩为「≥1 成功」，不是「全部成功」，语义错误（C1 spec delta 已明确此陷阱）。

**理由**：τ-bench pass^k 事实标准；独立聚合避免与 pass_at_k 混淆；无效轮次排除逻辑显式（G3 M2）。

### Decision D3: cache-aware 四档定价 + 5 系定价表

**方案**：`agent/cost_tracker.py` 的 `MODEL_PRICES` 扩展为四档结构 `{model: (in_price, cache_read_price, cache_write_price, out_price)}`（USD/1M tokens）；新增 `compute_cost_cached(model, input_tokens, cache_read_tokens, cache_write_tokens, output_tokens)` 与 `cache_hit_rate(cache_read, cache_write, total)`。补 5 系定价（claude-sonnet-5/opus-5/haiku-4.5 等）+ deepseek-v4-flash（本地近零成本档，标注 self-hosted 口径）。定价表带 `PRICING_TABLE_VERSION`/日期。

**备选**：沿用两档 input/output 近似。被拒：API 前沿对照会返回 unknown、无法核算 cache 收益（G3 M3 硬要求）。

**理由**：cache-aware 四档是 G3 M3 与 T1 协议的成本口径；`$/resolved-task` 与 cache hit rate 都依赖它。

### Decision D4: $/resolved-task 口径实现

**方案**：`statistics.py` 或独立成本聚合函数 `cost_per_resolved(results: Sequence[TaskResult], total_cost: float) -> float`：层内**全部 run 总成本（含失败 run）** / resolved 数（`passed` + `passed_with_warnings`，SWE-bench 严格 resolved 由 adapter 透传）。未标注 `cost_per_resolved` 时（self-hosted 不计费）输出估算口径标注。口径声明「仅 LLM token 计费、不含沙箱/CI/计算」。

**理由**：G3 M3 分子分母显式定义；`passed_with_warnings` 是否计入分子在本 change 默认计入并在结果标注（C3 渲染时可配置展示）。

### Decision D5: fault_owner 数据模型 + 交叉表

**方案**：`TaskResult.fault_owner ∈ {agent, task, environment, unknown}`（字符串可选字段，未标注默认 None → 聚合时归 unknown）。`statistics.py` 新增 `fault_owner_cross(reason, fault_owner)` 交叉表聚合（reason × fault_owner 计数）。标注来源在结果页披露段声明（人审抽样 κ / 强 judge，C3 渲染时承接；本 change 只提供字段 + 聚合函数 + 默认 unknown 归并）。

**备选**：reason→owner 查表自动推导。被拒：G3 M4 明确「避免 AutoTriage 偏差复发」，fault_owner 绑定 (task, round) 标注，不做查表。

**理由**：字段 + 聚合先行，标注流程（人审/强 judge）作为数据生产方式由使用者执行，本 change 提供容器。

### Decision D6: 配对比较统计（compare.py 新增）

**方案**：`compare.py` 新增 `paired_comparison(run_a, run_b) -> dict`：per-task delta（同任务通过率差）、差异 CI（paired bootstrap，seed 固定可复现）、win-rate（A 胜/B 胜/平）。对二值通过结果用 McNemar（精确二项）做显著性检验。

**备选**：只给两个点估计。被拒：G3 M8 硬要求「面试卖点不能只给两个点估计」。

**理由**：与 C1 task_set 对齐（同任务集）；paired bootstrap 纯 Python 延续现有风格。

### Decision D7: f2p/p2p 部分成功保留

**方案**：`adapters.py` SwebenchAdapter 在 Verdict `detail` 中透传 `f2p_rate`/`p2p_rate`/`reward`（从 report.json 读取）；`TaskResult` 新增可选 `partial` 字段（dict）或在 `detail` 承载。C2 至少保证字段不丢、可回查。

**备选**：只取 resolved。被拒：G3 M9 低成本保留更细粒度信息，失败归因建立在更细数据上。

**理由**：report.json 已含字段，透传成本极低；C3 结果页可展示部分成功档。

### Decision D8: 小 N 统计声明

**方案**：统计/渲染层对 N=3–5 的 per-task CI 附「小样本声明」（N 值 + 区间如实展示为证据强度）；layer/aggregate 层级 CI 权重优先展示。

**理由**：G3 M10；避免面试引用 N=3 的窄区间误导。

### Decision D9: 采样显式化 CLI

**方案**：`agent/main.py` benchmark CLI 新增 `--seeds`（`list[int]`，默认 `0..N-1` 由 `--repeat` 推导）、`--temperature`（float，默认 0.2）、`--model-version`（str，报告元组字段）；每轮 run 记录 (temperature, seed, model version) 进 run artifact/result。

**grill 补充（Q11/Q12）**：`RunMetadata` 新增 `temperature`/`seed`/`model_version`（轮级共享，run.json 可读），`TaskResult` 保留 `temperature`/`seed` 便于 (task, round) 回查。`--seeds` 与 `--repeat` 长度不一致时**报错**（防静默丢弃）；`--repeat` 上限 5、N<3 时警告；C2 只记录不接线，结果页声明「temperature/seed 为记录值，部分 provider 不承诺 seed 语义」。

**备选**：仅 `--repeat`。被拒：G3 M2 要求显式采样参数 + 每轮记录，可复现声明限定在 (model, provider, harness) 内。

**理由**：T1 协议命令面直接落地；C3 的 `--budget-cap`/`--preflight` 不在本 change。

### Decision D10: 过程效率指标（trace 采集，渲染归 C3）

**方案**：从 trace 采集 `time-to-first-successful-edit`（首次 status 成功的 Edit 事件时间戳 − run 开始时间）与 `exploration fraction`（探索占比）。exploration fraction 口径定义为：非 Edit 工具调用耗时占比 =（全部工具调用总耗时 − Edit 工具总耗时）/ 全部工具调用总耗时（无工具调用时为 0）。统计层提供 `process_efficiency(trace_events) -> dict`，输出两项 + 可空标记；结果页可选展示归 C3。

**备选**：只落字段不采集。被拒：spec delta「过程效率指标」带「实现归 C2」注记，只落字段无法诚实 REVISED 去注记。

**理由**：grill Q13；trace 已有事件序列（`agent/trace_recorder.py`），纯 Python 采集成本低。

### Decision D11: SWE-bench 污染披露数据层

**方案**：`RunMetadata` 新增 `swebench_dataset_version`/`swebench_package_version`（可选字段）；SwebenchAdapter 运行时用 `importlib.metadata.version("swebench")` 采集包版本、从 task/dataset 元数据采集数据集版本，写入 run metadata。披露渲染（污染注记/子集过滤信息）归 C3。

**备选**：不记录。被拒：spec「run metadata SHALL 记录 swebench 数据集版本与 swebench 包版本，供披露引用」是数据层工作，不记录则 C3 无数据可渲染。

**理由**：grill Q13；C3 渲染「数据集版本与 swebench 包版本钉住」注记时 run.json 有数据可引用。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 指标口径需对照业界主流（同 proposal 4 项）。
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录不可用）。替代依据为 G3 决议（#150，4 独立审阅 agent 对照 2025-2026 业界验证定稿）与 R1（#145）：pass^k 为 τ-bench 事实标准（M1）、cost@pass 为 Claw-SWE-Bench 等统一 harness 披露口径（M3）、fault_owner 对齐 TRAIL/AutoTriage（M4）、配对比较为标准统计方法（M8）。口径细节已固化为 C1 spec delta 的 Requirement 文本，本 design 按其实现。
- design impact: M1–M11 Requirement 文本为 D1–D9 输入；无新增调研依赖。

## Risks / Trade-offs

- **[pass^k 与 pass@k 混淆] → 独立函数 + 结果页语义标注（D2）；C1 spec 已改名防混。**
- **[cache 定价表数据不完整（新模型）] → 定价表版本化 + 未知模型返回估算/警告（不静默返回 0）；self-hosted 标不计费口径。**
- **[fault_owner 无标注来源时全是 unknown] → 默认 unknown 归并 + 披露「未归因」基数（D5）；人审/强 judge 标注流程留 C3 数据生产方式。**
- **[配对比较小样本检验力弱] → McNemar 精确检验 + 差异 CI 如实展示（D6/D8）。**
- **[数据模型字段扩散] → 全部可选、None 省略、from_dict 兼容旧 artifact（D1）。**
- **[spec 注记清理遗漏] → tasks 明确「REVISED 去注记」清单，validate + artifact checker 兜底。**
- **[C2 范围膨胀到 C3 渲染] → Non-Goals 明确边界，C3 承接渲染/协议/披露。**

## Pre-Implementation Review

独立零记忆 grill subagent（run id `grill-evaluation-metrics-20260817`）已于 2026-08-17 完成对 design.md D1–D9 的逐项追问，完整记录见 `reviews/grill-design.md`。结论摘要：

- **Confirmed Decisions**（6 条方向成立）：D2 独立 pass^k 聚合（不复用 pass_at_k(k=n)）、D5 fault_owner 不做 reason→owner 查表、D1 字段可选 + from_dict/to_dict 向后兼容机制、纯 Python 统计扩展、D7 保留 f2p/p2p/reward 方向、D3/D4 cache-aware 定价方向。
- **Open Questions**（13 条待用户确认，每条带具体例子）：Q1 pass^k 排除谓词未定义且 approval-unavailable 无生产者；Q2 pass@1「= 现有 layer_pass_rate」事实错误（现有实现把 unsupported 计入分母）；Q3 部分有效/全无效边界与 n/k 有效性声明；Q4 MODEL_PRICES 四档改造破坏 5 个消费点；Q5 cache token 采集链路全缺（D3/D4 在真实 run 退化为两档）；Q6 $/resolved-task 分子分母边界（passed_with_warnings 计入、resolved=0 除零、self-hosted 口径）；Q7 fault_owner 写入路径与非法值校验；Q8 配对比较二元定义三选一/缺对处理；Q9 f2p/p2p 承载位置（Verdict detail 是 str，「在 detail 透传」不成立）；Q10 小 N 声明挂渲染层与 Non-Goal 冲突；Q11 采样参数记录粒度 + model_version 字段遗漏；Q12 --seeds/--repeat 长度不匹配与 temperature 只记录不生效；Q13 spec delta 9 条中「过程效率指标」「SWE-bench 污染披露」两条无对应决策。

**状态：已确认**。用户 2026-08-17 答复全部 13 条 Open Questions 按 grill 推荐执行（原始答复「看晕了，代码层面且逻辑 ok 的过滤掉，按推荐就行」，主 session 审核后判定全部按推荐）。13 条确认记录见 `reviews/grill-design.md` 的 `## User Confirmation` 节。grill 补充决策 D10（过程效率指标）/D11（SWE-bench 污染披露数据层）已并入本设计；开始按 tasks 测试先行实现。

## Testing Strategy

- 单元测试（`tests/benchmark/`）：pass^k 聚合（含无效轮次排除、k=n 语义）、cache-aware 四档成本（含未知模型回退）、$/resolved-task 口径、fault_owner 交叉表（含默认 unknown）、配对比较（per-task delta/差异 CI/win-rate/McNemar）、f2p/p2p 透传、数据模型向后兼容（旧 artifact 读取）、CLI 采样参数（--seeds/--temperature/--model-version）。
- 回归测试：既有 bootstrap CI/pass@k/结果页测试不回归。
- benchmark 层级测试：`--repeat 3 --seeds 0 1 2` fake runner smoke，确认采样参数记录进 artifact。
- 兼容测试：旧 result.json/run.json 读取新模型不报错。
- 每个 bug fix 新增回归测试；涉及 benchmark 路径必须覆盖 benchmark 层级测试。
