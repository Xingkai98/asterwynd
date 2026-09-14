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

### D5 — reducer 声明（抄 LangGraph）

并行分支写同一结果槽必须声明 reducer（无损合并）；校验阶段对「多入边写同字段」无 reducer 时报 schema 错。join 节点显式声明「等几条臂 + 只执行一次」（防 LangGraph 非 END merge 每路径执行一次的坑）。

### D6 — 图级 recursion_limit

图级步数上限（默认 25），超限 GraphRecursionError；图级而非节点级（否则单分支死循环饿死其他分支）。

### D7 — 4 pattern → DSL 模板

```
orchestrator-worker → foreach + aggregate(all_required)
peer-review         → subagent + subagent + route + 有限循环(max_rounds)
hierarchical        → subagent(manager, 可嵌套) + foreach
bidding             → foreach + aggregate(selector)
```

`run_pattern()` 保留兼容 adapter，内部编译成 WorkflowSpec；返回字段兼容 + 新增 workflow_id/spec_hash/critical_path_s/peak_active/total_cost。

### D8 — 前置项:每 orchestration 复位 + root_run_id 计数桶

C1 的累计 spawn 计数取 manager 生命周期保守语义；本 change 引入 workflow/orchestration 身份后，改为「每 orchestration 复位 + `root_run_id` 计数桶」——每个顶层 workflow run 有自己的计数桶，子 run 通过 `root_run_id` 归因，防 #69206 式单次展开爆炸的同时不误伤长会话。

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
