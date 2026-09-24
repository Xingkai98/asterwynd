# Proposal: benchmark 三模式与 workflow 可重放（benchmark-workflow-replay）

关联跟踪 issue：[#187](https://github.com/Xingkai98/asterwynd/issues/187)。wayfinder 地图：[#170](https://github.com/Xingkai98/asterwynd/issues/170)。决策票：G6 [#177](https://github.com/Xingkai98/asterwynd/issues/177)。依赖 C2 [#181](https://github.com/Xingkai98/asterwynd/issues/181)（已合入，spec 可哈希）+ C4 [#185](https://github.com/Xingkai98/asterwynd/issues/185)（已合入，预算归因数据）。

## Change Type

- primary: feature
- secondary:
  - benchmark
  - subagent

## Why

C1–C4 已经把「模型自由构建几十~上百个 subagent 协作」做成了产品能力（队列化并发 → Workflow DSL → 结果聚合 → 预算归因），但**缺一个可重放的验收闭环**：

- 现在的 benchmark 只能测「单个 agent 解决单个任务」（`benchmarks/runner.py` 的 `AsterwyndRunner`），测不到 subagent 编排本身的**质量**（拓扑合理吗、fan-out 冗余吗、被护栏拒绝了几次）。
- 「模型自由」与「可重放」有根本矛盾：dynamic 模式里模型每次生成的 workflow 都不同，没法复现、没法对比。G6 #177 已定稿三模式调和：`template`（固定 baseline）/ `dynamic-record`（自由生成 + 保存规范化 spec）/ `dynamic-replay`（不重跑规划模型，离线重放已保存 spec）。
- 之前推迟的**端到端真实 LLM fan-out 验证**（C1 subagent 端到端验证延后）随本 change 落地——用真实 LLM 跑 dynamic-record 再 replay，验证「同一 spec 两次跑结果可比」。

业界依据（R1 #171 调研）：LangGraph 用图级 `recursion_limit` + 确定性 `spec_hash` 支持 replay（`agent/subagent/workflow.py:287-291` 的 `spec_hash` 已是 C5 的锚点）；Claude Code #68110/#69206 教训（无累计 spawn 上限烧 1.5M tokens）要落成「拒绝降级计数」指标。

## What Changes

- **benchmark 三模式**：`template` / `dynamic-record` / `dynamic-replay`。dynamic-record 保存规范化 workflow_record.json + spec_hash + scheduler_version + budget_config + seed/model/temperature；dynamic-replay 不重跑规划模型、离线重放。
- **报告新增字段**：workflow_mode / workflow_spec_hash / scheduler_version / node_count / run_count / peak_active / queue_wait_s / critical_path_s / workflow_cost_usd。
- **新增指标**：冗余度（有用产出 / spawn）、图级步数、拒绝降级计数。
- **比较口径扩展**：完成率 + 总 token + $/resolved-task + wall time + 节点数 + 峰值并发 + 关键路径 + 失败原因（不只比 pass rate）。
- **端到端 fan-out 验证**：真实 LLM 跑 dynamic-record → dynamic-replay 对比。

## Capabilities

### New Capabilities

无新能力域；在既有 `benchmark` 能力域上深化。

### Modified Capabilities

- `benchmark`: 从「单 agent 任务」扩展到「workflow 编排可重放验收」——三模式 + workflow 报告字段 + 编排指标。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 架构级改造（benchmark 运行模型扩展 + 可重放协议），走 grill 的非平凡 change，命中 `full` 判据。
- research questions:
  1. 业界 benchmark 如何调和「模型自由」vs「可重放」（record/replay 模式怎么设计）？
  2. 编排质量指标（冗余度/图级步数/拒绝计数）怎么定才有区分度？
  3. workflow 报告字段与既有 benchmark 报告怎么对齐？
- findings: 见 wayfinder R1 #171 决议（已关闭）+ G6 #177 决议（已关闭）。核心结论——
  - **record/replay 分离**（G6）：dynamic-record 把「规划」与「执行」拆开——规划模型生成的 spec 落成 artifact，replay 只重放 spec 不重跑规划模型，这是 LangGraph `spec_hash` 复用的关键（`agent/subagent/workflow.py:287-291`）。
  - **编排指标**（G6 + #68110 教训）：冗余度 = 有用产出 / spawn（吸收「无上限 spawn 烧钱」）；图级步数、拒绝降级计数（护栏拒绝 / queue_full / 深度撤工具都算）反映编排是否健康。
  - **对照臂**（G6）：须含「小 k 高质量 vs 大 N 暴力」，否则指标没有区分度。
- design impact: 见 design.md D1–D6；三模式与报告字段直接来自 G6 #177 决议。

## Impact Analysis

- **能力域**: `benchmark`（可重放三模式 + workflow 报告字段 + 编排指标）。
- **代码**: 改 `benchmarks/runner.py`（BenchmarkRunner 增 workflow 模式分派 + 报告字段收集；3 处 `TaskResult(...)` 完整重建点须同步带上新字段，`runner.py:377-398`/`:446-468`/`:530-552`）、`benchmarks/models.py`（`TaskResult` **与 `AgentRunResult` 成对**增 workflow_* 字段，全部默认 None）、`benchmarks/report.py`（渲染 workflow 字段 + 编排指标）、`benchmarks/compare.py`（比较口径扩展，新增读法按 raw-dict 宽松风格）、`benchmarks/agent_runner.py`（AsterwyndRunner 暴露 workflow 生命周期钩子 **+ 注入 CostLedger**）、新增 `benchmarks/workflow_replay.py`（dynamic-record/replay 的 spec 落盘/重放）。改 `agent/subagent/scheduler.py`（暴露 run_count / workflow 级 spawn_count 快照 / queue_wait_s / 拒绝计数给 benchmark 采集）、`agent/subagent/manager.py`（新增 spawn 拒绝与 depth 撤工具计数器）、`agent/main.py`（benchmark 命令加 `--workflow-mode` / `--workflow-record` 并透传 AsterwyndRunner）。
- **测试**: 新增三模式 round-trip 测试、报告字段渲染测试、冗余度/拒绝计数指标测试、replay 确定性测试（同 spec 两次跑结果可比）。
- **文档**: `docs/openspec-change-backlog.md`（C5 状态）、wayfinder #170（引用）、`docs/benchmark-plan.md`（如有关联段落）。
- **流程（process）**: 本 change 是 C5（终点）；完成后 wayfinder #170 的「subagent 编排自由度」目的地全部落地。

## 端到端验证说明

本 change 含之前推迟的端到端真实 LLM fan-out 验证：用真实 LLM（非 fake）跑一个 dynamic-record benchmark 任务，保存 spec，再 dynamic-replay，验证「同 spec 两次跑的可比性」与「拒绝降级计数」真实产生。此验证在本地 LLM 可用时执行（`deepseek-v4-flash` 本地配置，见记忆），不可用时记录缺口并按 C5 完成标准降级为 fake + 记录未验证事实。

可比性断言口径按 grill Q6：fake 场景硬断言 `spec_hash`/`node_count`/`run_count`/`status` 全等；真实 LLM 场景只硬断言 `spec_hash` 相等 + 两侧无异常完成，其余字段只报不判（wall-clock 与 token 噪声会 flaky）。降级事实按 grill Q7 落进每个任务的 `result.json`（机器可读 `e2e_llm_verified` 等字段，字段本体加在 `TaskResult` 上）。
