# Proposal: Workflow DSL 调度器（workflow-dsl-scheduler）

关联跟踪 issue：[#181](https://github.com/Xingkai98/asterwynd/issues/181)。wayfinder 地图：[#170](https://github.com/Xingkai98/asterwynd/issues/170)。决策票：G1 [#172](https://github.com/Xingkai98/asterwynd/issues/172)、G3 [#174](https://github.com/Xingkai98/asterwynd/issues/174)、R1 [#171](https://github.com/Xingkai98/asterwynd/issues/171)。

## Change Type

- primary: feature
- secondary:
  - agent-runtime
  - subagent

## Why

C1 `subagent-concurrency-queue`（#179，已合入）交付了「声明/执行解耦的队列化并发 + 父子身份字段」地基。但当前模型编排 subagent 只能 turn-by-turn 一步一调（`CreateSubagent` → `RunSubagent` → `GetSubagentRun`），**无法一次性声明复杂协作拓扑**：

```
A/B/C 并行 → 汇合给 D → D 按结构化结果选 E 或 F → E/F 再交给 G
```

这是 wayfinder #170 的 Destination 核心——「模型自由构建几十~上百个 subagent 协作流程」。G1 #172 定稿架构方向为「工具原语放开 + **可选 Workflow DSL** + 统一调度器」，G3 #174 定稿 DSL schema（分离式入口、4 节点、2 汇合、reducer、图级 recursion_limit）。本 change 落地这两个决议。

业界依据（R1 #171 调研，`full` 档已闭环）：LangGraph 的 reducer / `Send` 动态 fan-out / 图级 `recursion_limit` 三件套是 DSL 可借鉴的成熟形状；纯模型逐轮调度的反面教训是 Claude Code #68110（自由 fan-out 无结构约束 = 指数爆炸）。

## What Changes

- **分离式工具入口**：`DeclareWorkflow(spec)` → workflow_id；`StartWorkflow(id, wait)` → status；`GetWorkflow(id)` → bounded status；`CancelWorkflow(id)`。另提供 `RunWorkflow(spec, wait=true)` 便捷语法，内部走 Declare+Start（保证 spec 可保存、可哈希、可重放）。
- **4 种节点**：`subagent` / `aggregate` / `route` / `foreach`。动态并行用 `foreach` 表达（集合可来自上游产出），首版不加独立 fanout 节点。
- **2 种汇合语义**：`all_required`（全等齐才汇合）+ `best_effort`（等截止时间，消费已完成结果，保留失败记录）。「失败不 fail-fast」只在 aggregate 层实现。
- **DAG 调度器**：ready 队列 + 依赖门控；复用 C1 的 `max_active`/`max_queued_runs`/许可绑执行。
- **reducer 声明**（抄 LangGraph）：并行分支写同一结果槽必须声明 reducer，校验阶段报 schema 错。
- **图级 recursion_limit**（默认 25）：图级而非节点级，超限 GraphRecursionError。
- **4 个内置 pattern 降级为 DSL 模板**：`run_pattern()` 保留兼容 adapter，内部编译成 WorkflowSpec；返回字段兼容 + 新增 workflow_id/spec_hash/critical_path_s/peak_active/total_cost。
- **bus 非权威**：DSL 关键结果走 result_ref/artifact，禁依赖 bus 传不可丢信息。
- **前置项（C1 遗留）**：D5 累计 spawn 计数改为「每 orchestration 复位 + `root_run_id` 计数桶」——随 workflow/orchestration 身份一起落地。

## Capabilities

### New Capabilities

无新能力域；在既有 `multi-agent-collaboration` 能力域上深化。

### Modified Capabilities

- `multi-agent-collaboration`: 新增 Workflow DSL（分离式入口 + 4 节点 + 2 汇合 + reducer + 图级 recursion_limit）+ 统一 DAG 调度器；4 个内置 pattern 降级为 DSL 模板。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 架构级改造（新增 DSL 表达面 + 调度器），走 grill 的非平凡 change，命中 `full` 判据。
- research questions:
  1. LangGraph 的图编排 schema（节点/边/join/条件路由/循环上限）可借鉴什么？
  2. 动态 fan-out（编译期不知任务数）的 DSL 形状？
  3. 图级循环上限 vs 节点级上限的差异？
- findings: 见 wayfinder R1 #171 决议（已关闭）。核心结论——
  - **reducer 声明**：并行分支写同一结果槽必须无损合并（LangGraph `InvalidUpdateError` 语义）；本仓 `_aggregate`（`patterns.py:73-97`）无 reducer 概念，做 DSL 时补。
  - **`Send` 式动态 fan-out**：编译期不知任务数时用 `foreach` 表达（集合来自上游产出），对应 LangGraph 的 `Send(node, arg)`。
  - **图级 recursion_limit**（默认 25，LangGraph）：图级而非节点级，否则单分支死循环饿死其他分支；本仓只有 per-run token/time 预算（`budget.py`），无编排级步数闸。
  - **join 坑**：非 END 的 merge 节点每路径执行一次——join 节点必须显式声明「等几条臂 + 只执行一次」。
- design impact: 见 design.md D1–D7；DSL schema 直接来自 G3 #174 决议，架构方向来自 G1 #172 决议。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（Workflow DSL + 调度器）。
- **代码**: 新增 `agent/subagent/workflow.py`（WorkflowSpec、节点/边模型、校验）、`agent/subagent/scheduler.py`（DAG 调度器、ready 队列、依赖门控、递归上限）；改 `agent/subagent/patterns.py`（4 pattern 编译成 WorkflowSpec 模板）、`agent/tools/builtin/subagents.py`（DeclareWorkflow/StartWorkflow/GetWorkflow/CancelWorkflow/RunWorkflow 工具）、`agent/config.py`（workflow 相关配置，若需）。
- **测试**: 新增 DSL 校验测试（非法环/未知节点/重复 id/超 max_nodes）、调度器测试（fan-out/join/route/foreach/递归上限）、pattern→DSL 模板映射测试；既有 `test_patterns.py` 兼容（返回字段新增不改旧）。
- **文档**: `docs/openspec-change-backlog.md`（C2 状态）、wayfinder #170（引用）。
- **流程（process）**: 本 change 是 C2；C3 `workflow-result-aggregation`（结果引用 + 分层汇聚）依赖本 change 的 DAG，C4/C5 依赖本 change 的调度器 + spec 可哈希。
