# Proposal: 评测指标层实现（evaluation-metrics，C2）

关联跟踪 issue：[#157](https://github.com/Xingkai98/asterwynd/issues/157)（【feature】evaluation-metrics：评测指标层实现）。系列父级：[#144](https://github.com/Xingkai98/asterwynd/issues/144)（Wayfinder: Agent 评测升级）｜ follow-up：[#156](https://github.com/Xingkai98/asterwynd/issues/156)。

## Change Type

- primary: feature
- secondary: []

## Why

C1 `evaluation-task-spec`（#154，PR #155）已把 G3 M1–M11 的指标/方法 Requirement 全部落进 `openspec/specs/benchmark/spec.md`（带「实现归 C2 evaluation-metrics」注记）。当前指标层存在真实缺口（实测）：

- `statistics.py` 只有 pass@k 组合计数（`pass_at_k`，Chen 2021），**无 pass^k 聚合**（任务级「全部有效轮通过」布尔 → 跨任务均值）。
- `models.py` 的 `TaskResult`/`RunMetadata` **缺 cache tokens/temperature/seed/fault_owner/task_set_hash 等字段**（T1 §G3 M5 数据模型缺口）。
- `agent/cost_tracker.py` 定价表**只有 sonnet-4/opus-4 两档**、无 cache-aware 四档、无 5 系模型（API 前沿对照会返回 unknown）。
- `adapters.py` 的 SwebenchAdapter **只提取 `resolved` 布尔，丢弃 f2p_rate/p2p_rate/reward**。
- `compare.py` 只有点估计对比表，**无配对比较统计**（per-task delta + 差异 CI + win-rate）。
- CLI 无 `--seeds`/`--temperature`/`--model-version`（采样不可显式控制、每轮不记录采样参数）。

面试被追问「评测怎么做的统计/成本/归因」时，这些缺口会让讲稿停在「有 pass@k + bootstrap CI」的旧口径。本 change 把 C1 落定的 M1–M11 Requirement 实现为可跑的指标层，并清理 spec 中的「实现归 C2」注记。

## What Changes

- **数据模型扩展**（`benchmarks/models.py`）：`TaskResult` 新增 `cache_read_tokens`/`cache_write_tokens`/`temperature`/`seed`/`fault_owner`；`RunMetadata` 新增 `task_set_hash`/`max_iterations`/`timeout_seconds`/`network`/`adapter_version`/`prompt_version`/`pricing_table_version`。全部可选字段、`from_dict` 向后兼容（未知 key 忽略、缺失走默认）。
- **pass^k 新增聚合**（`benchmarks/statistics.py`）：任务级「全部有效轮通过」布尔 → 跨任务均值；区分 pass@1（经验通过率）/ pass@k（组合计数，能力上限）/ pass^k（全 k 轮成功，可靠性）；无效轮次（unsupported/approval-unavailable/docker_unavailable）不进分母；n>>k 有效性声明。
- **cost@pass cache-aware**（`agent/cost_tracker.py` + `benchmarks/statistics.py`）：四档定价（fresh input / cache read / cache write / output）+ 补 5 系模型定价（claude-sonnet-5/opus-5/haiku-4.5 等，deepseek-v4-flash 本地近零成本档）；`$/resolved-task` = 层内全部 run 总成本（含失败）/ resolved 数；cache hit rate；定价表版本/日期。
- **fault_owner 正交**（`benchmarks/models.py` + 统计）：`{agent, task, environment, unknown}`；标注来源声明（人审抽样 κ / 强 judge）；未标注归 unknown；reason × fault_owner 交叉表（按层聚合）。
- **配对比较统计**（`benchmarks/compare.py`）：per-task delta + 差异 CI（paired bootstrap / McNemar）+ win-rate。
- **f2p/p2p 部分成功保留**（`benchmarks/adapters.py`）：SwebenchAdapter 透传 `f2p_rate`/`p2p_rate`/`reward` 到 Verdict detail。
- **小 N 统计声明**：统计层/渲染层对 N=3–5 的 per-task CI 附小样本声明。
- **采样显式化**（`agent/main.py` benchmark CLI）：`--seeds`（固定集合，默认 seed 0..N-1）、`--temperature`（默认 0.2）、`--model-version`；每轮 run 记录 (temperature, seed, model version)。
- **spec 注记清理**：C1 落进正式 spec 的带「实现归 C2」注记 Requirement 在实现后改为 REVISED（去掉注记、补充具体化细节），保持规格与实现一致。

## Capabilities

### New Capabilities

无。全部为既有 `benchmark` 能力域的指标层实现。

### Modified Capabilities

- `benchmark`: M1–M11 Requirement 中归 C2 的部分从「已落规格文本（待实现）」变为「已实现」，spec delta 以 REVISED 方式去掉「实现归 C2」注记并补充具体化细节；数据模型/统计/成本/适配器/CLI 字段扩展全部向后兼容。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 非平凡 change（走 grill），指标口径（pass^k/cost@pass/fault_owner/配对比较）需对照业界主流确认，避免自造不可引用的统计口径。
- research questions:
  1. pass^k（τ-bench 可靠性指标）的标准定义与聚合方式？
  2. cost per resolved task（$/resolved-task）的业界口径与 cache-aware 定价？
  3. 失败归因 fault_owner 的标注来源与校准证据（AutoTriage κ）？
  4. 配对比较（paired bootstrap / McNemar）统计方法？
- findings: 本地 `.dev/reference-repos.txt` 不存在，本地参考仓库不可用，已在 findings 记录。替代依据为 map 调研结论：G3 决议（[#150](https://github.com/Xingkai98/asterwynd/issues/150)）经 4 个独立零记忆审阅 agent 对照业界最佳实践验证定稿（CHANGES_REQUESTED → 采纳全部修正）；R1（[#145](https://github.com/Xingkai98/asterwynd/issues/145)）确认 pass^k 为 τ-bench 事实标准、cost@pass 为 Claw-SWE-Bench 等统一 harness 的披露口径、fault_owner 为 TRAIL/AutoTriage 失败归因方向。具体口径（M1–M11）已在 C1 spec delta 落为 Requirement 文本，本 change 按文本实现。
- design impact: M1–M11 Requirement 文本为设计输入；实现方案见 design.md D1–D9。

## Impact Analysis

- **能力域**: `benchmark`（指标层实现）。
- **代码**: `benchmarks/models.py`（TaskResult/RunMetadata 可选字段：cache tokens/temperature/seed/fault_owner/partial + report tuple 12 字段，向后兼容）、`benchmarks/statistics.py`（pass^k 聚合、无效轮排除、$/resolved-task、fault_owner 交叉表、κ、配对比较 + McNemar、小 N 样本量、过程效率、swebench 版本）、`agent/cost_tracker.py`（cache-aware 四档 + 5 系定价 + self-hosted 零成本档）、`benchmarks/adapters.py`（Verdict resolved/partial 透传）、`benchmarks/compare.py`（配对比较渲染）、`agent/main.py`（benchmark CLI `--seeds`/`--temperature`/`--model-version` + `benchmark-annotate`）、cache token 采集链（`agent/llm.py` Usage → anthropic_llm → loop → RunResult → AgentRunResult → TaskResult）、`benchmarks/runner.py`（partial/采样参数/swebench 版本透传）。
- **测试**: 新增 `tests/benchmark/` 指标层测试（pass^k 聚合、cache-aware 成本、$/resolved-task、fault_owner 归因 + 交叉表、κ、配对比较、f2p/p2p 透传、数据模型向后兼容、CLI 采样参数、annotate、过程效率、swebench 版本、runner 集成）；涉及 benchmark 路径已覆盖 benchmark 层级测试；全部基准测试通过。
- **文档**: `openspec/specs/benchmark/spec.md` 已同步（9 条 REVISED 去掉「实现归 C2」注记）、`docs/openspec-change-backlog.md` 更新（收尾阶段）。
- **基准**: 不改变既有单次运行语义与既有 artifact 结构；新增字段全部可选，旧 result/run.json 读取兼容（向后兼容测试锁定）。
- **流程（process）**: 指标口径约定落地——pass@1/pass@k/pass^k 语义、无效轮次排除谓词、成本口径（仅 LLM token、cache-aware 四档、self-hosted 不计费）、fault_owner 标注来源（annotate 工具 + κ）、配对比较统计方法（paired bootstrap + 精确二项 McNemar）、采样参数记录（temperature/seed/model-version，只记录不接线），供后续评测与 C3 结果页引用。
