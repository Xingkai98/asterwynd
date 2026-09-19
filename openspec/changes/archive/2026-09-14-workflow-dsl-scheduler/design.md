# Design: Workflow DSL 调度器

## Context

C1（已合入）交付了队列化并发 + 父子身份字段。本 change 在其上落地「可选 Workflow DSL + 统一调度器」：模型可一次性声明复杂协作拓扑（并行/汇合/条件分支/有限循环），也可退回逐工具调用。4 个内置 pattern 降级为 DSL 模板。决策来自 wayfinder #170 的 G1 #172（架构方向）+ G3 #174（DSL schema）+ R1 #171（业界调研）。

## Goals / Non-Goals

**Goals**

1. 分离式工具入口：DeclareWorkflow / StartWorkflow / GetWorkflow / CancelWorkflow + RunWorkflow 便捷语法。
2. 4 种节点（subagent / aggregate / route / foreach）+ 2 种汇合（all_required / best_effort）。
3. DAG 调度器：ready 队列 + 依赖门控，复用 C1 的 max_active/许可绑执行。
4. reducer 声明 + 图级 recursion_limit（默认 25）。
5. 4 个内置 pattern 降级为 DSL 模板，`run_pattern()` 兼容 adapter。
6. bus 非权威（关键结果走 result_ref/artifact）。
7. 前置项：D5 累计 spawn 计数改「每 orchestration 复位 + root_run_id 计数桶」。

**Non-Goals**

- 不做结果引用落盘 / 分层汇聚（C3）。
- 不做 workflow 级总预算 / 成本归因（C4）。
- 不做 benchmark replay（C5）。
- 不做每个 subagent 单独设模型（wayfinder #170 Out of scope）。
- 不做 web 端编排可视化（wayfinder #170 Out of scope）。

## Decisions

### D1 — 分离式工具入口

`DeclareWorkflow(spec) → workflow_id`；`StartWorkflow(id, wait) → status`；`GetWorkflow(id) → bounded status`；`CancelWorkflow(id)`。`RunWorkflow(spec, wait=true)` 内部走 Declare+Start。理由：可中途查/取消；spec 可保存 + 哈希用于 benchmark replay（C5）。

### D2 — WorkflowSpec 数据结构

```json
{
  "schema_version": "workflow.v1",
  "goal": "...",
  "nodes": [
    {"id": "...", "kind": "subagent|aggregate|route|foreach", "task": "...", "mode": "...", "...kind-specific fields..."}
  ],
  "edges": [{"from": "...", "to": "...", "channel": "result_ref|summary|artifact|bus", "required": true}],
  "entry": ["..."],
  "terminal": ["..."]
}
```

节点 kind-specific：
- `subagent`: task/mode/name。
- `aggregate`: strategy(llm)、join 语义(all_required|best_effort)、输入 token 预算。
- `route`: cases[{when, to}]、default、max_routes。
- `foreach`: 集合来源(上游节点 id + 字段)、max 展开数、模板化子任务。

### D3 — DAG 调度器

ready 队列 + 依赖门控：节点只有「所有 required 上游完成」才进 ready。复用 C1 的 `max_active`/`max_queued_runs`/许可绑执行。调度器内部状态：node_queued/node_started/node_blocked/node_completed/node_failed。

### D4 — 2 种汇合语义

`all_required`（全等齐才汇合）+ `best_effort`（等截止时间，消费已完成结果，保留失败记录）。「失败不 fail-fast」只在 aggregate 层，不进底层 scheduler。

- `best_effort` 的截止时间载体 = aggregate 节点字段 `deadline_s`（从 aggregate 开始等算起，Q3）。
- 超时臂处置 = `CancelSubagentRun`（写 checkpoint 供后续 resume），标 `status: cancelled`，**不**放任后台跑完（避免占 max_active 名额 + 结果无人消费）。需把 `cancelled` 纳入 TERMINAL_RUN_STATUSES。

### D5 — reducer 声明（抄 LangGraph）

节点加 `outputs: ["<槽名>"]` 声明写哪些槽（Q4）。并行分支写同一结果槽必须声明 reducer；reducer 用受限枚举 `concat` / `merge_dict` / `first_non_empty` / `last`（不执行模型生成代码）。校验阶段对「多入边写同槽」无 reducer 时报 schema 错。join 节点显式声明「等几条臂 + 只执行一次」（防 LangGraph 非 END merge 每路径执行一次的坑）。

### D6 — 图级 recursion_limit + 三闸

`recursion_limit`（默认 25）= **图级 superstep 数**（一次调度循环 = 就绪一批→派发→等一批完成 算 1 步），超限 GraphRecursionError；图级而非节点级（否则单分支死循环饿死其他分支）。

三闸（Q5）：`recursion_limit=25`（图级步数）/ `max_nodes=200`（节点数，含 foreach 展开）/ `max_runs=300`（run 总数）。三者与 C1 的 `max_spawns=200` 量纲不同、需在校验期一致性校准（避免「图还没跑完 spawn 预算先耗尽」的误伤）。

### D7 — 4 pattern → DSL 模板

```
orchestrator-worker → foreach + aggregate(all_required)
peer-review         → subagent + subagent + route + 有限循环(max_rounds)
hierarchical        → subagent(manager, 可嵌套) + foreach
bidding             → foreach(proposers) + subagent(selector) + aggregate   ← 修正：selector 是真实子 agent 节点，非 aggregate(strategy=llm) 内联
```

`run_pattern()` 保留兼容 adapter，内部编译成 WorkflowSpec；返回字段兼容 + 新增 workflow_id / workflow_spec_hash（改名，避免与 OpenSpec artifact hash 同名）/ critical_path_s / peak_active / total_cost。

- **聚合语义**：pattern 模板「每节点取最新一次 run」而非「取该节点所有 run」（peer-review 跨轮复用同一 session，取最后两次；bidding 的 completed 只数 proposers，selector 不进 workers）。

### D8 — 前置项:workflow_id 计数桶（替代 root_run_id）

C1 的累计 spawn 计数取 manager 生命周期保守语义。本 change 引入 workflow 身份后，改为**「每 workflow run 复位 + `workflow_id` 计数桶」**（Q6）：每个顶层 workflow run 一个桶（两 foreach 共享 200 上限），嵌套 workflow 各自独立桶。无 workflow 的主 loop 沿用 C1 的 manager 生命周期保守语义（每 turn 复位归后续 change）。grill 已确认 `SubagentRunRecord` 无 `root_run_id` 字段、contextvar 也无载体——桶键用既有的 `workflow_id` 而非新增 `root_run_id`。

## Pre-Implementation Review

> 本 change 为架构级改造（新增 DSL 表达面 + 调度器），实现前需按 AGENTS.md 走 `batch-grill-me`（或等价独立 subagent 设计追问）审视本 design.md 的 D1–D8，逐项确认实现细节、依赖、风险与测试策略，产出结构化决策记录到 `reviews/grill-design.md`，并经停轮确认（grill-confirmation-gate）。本节为占位声明，实际 review 记录以 `reviews/grill-design.md` 为准。

## Risks / Trade-offs

- **风险**:DSL schema 过宽会失去「受限可校验」优势 → 首版只 4 节点 + 2 汇合 + 受限 route 枚举，不执行模型生成代码。
- **风险**:foreach 动态展开 + 递归上限的交互 → foreach 展开计入 max_nodes/max_runs + 图级步数，双闸。
- **风险**:route 的条件匹配是模型生成文本 → 只匹配结构化标签/受限枚举，不执行代码。
- **Trade-off**:DSL 是「可选高级语言」,模型可退回逐工具自由调度——不牺牲自由,但 DSL 拓扑本身受 schema 约束（这是「可重放/可校验」的代价，接受）。
- **Trade-off**:`run_pattern()` 编译成 DSL 模板后,既有 pattern 的内部行为可能微调(如错误传播路径)——需兼容既有 `test_patterns.py` 的返回字段断言。

## Testing Strategy

- 新增 DSL 校验测试：非法环、未知节点、重复 id、超 max_nodes、多入边写同槽无 reducer。
- 新增调度器测试：fan-out（A/B/C 并行→D）、join（all_required 等齐 / best_effort 超时）、route（结构化标签路由）、foreach（动态展开 + max 展开数）、递归上限（图级超限报错）。
- pattern→DSL 模板映射测试：4 pattern 编译结果 + `run_pattern()` 兼容返回字段。
- 全量 `uv run pytest -q` 绿 + benchmark smoke + OpenSpec validate + artifact checker。
