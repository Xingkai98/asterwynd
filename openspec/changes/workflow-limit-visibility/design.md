# Design: 工作流闸门可见性 — 让模型在撞闸前看见生效上限与余量

## Context

#273 的 `DryRunWorkflow` 让模型能零成本预演拓扑与数据流。本 change 扩展同一个报告，把**闸门**（结构闸的生效值、声明图展开后的规模、离闸多远、撞闸了是哪个闸）也摊开。

### 已实测的机制事实（本设计的地基）

1. **机制早已存在，只是 dry run 没接**：`scheduler.py:456` 的 `limits_report(spec, ceiling)` 产出 `{declared, applied, clamped}` 三段式，已接进**三个**出口——`status()`（`scheduler.py:2866`）、`_envelope()`（`scheduler.py:3077`）、资产加载（`subagents.py:2275`）。`DryRunWorkflow` 是**第四个**出口，未接（`research/gap_probe.py` 实测 `G1_report_has_limits_key: false`）。
2. **生效值读取的唯一入口已存在**：`WorkflowScheduler._eff_limit(field)`（`scheduler.py:601`）是结构闸的**唯一**读取入口，`clamp_limit(declared, ceiling)` 是共用钳制函数。
3. **执行计划天然带「声明 vs 展开」**：`ExecutionPlan.declared_nodes`（原始声明）/ `.inserted_nodes`（`__auto_agg__` 自动插层）/ `.nodes`（展开后全集）（`aggregation.py:177-186`）。实测：声明 3 → 展开 5（自动插层 2）（`research/gap_probe.py` 的 `G2_*`）。
4. **撞闸诊断已结构化**：`GraphRecursionError.to_dict()`（`scheduler.py:186`）给出 `reason` / `limit` / `steps` / `current_nodes`；`_truncation_diagnostics()` 补 `declared_max_rounds` / `rounds_actually_run` / `limit_source`。真实运行的 `_envelope()` **有条件**携带 `diagnostics`（`scheduler.py:3107`，`if self._diagnostics`）。**dry run 报告不携带**（`research/gate_trip_probe.py` 实测 `T2_trip_has_diagnostics: false`）。
5. **dry run 的 scheduler 不传 ceiling**：`WorkflowScheduler(sim_manager)`（`subagents.py:1789`）→ `_limit_ceiling` 为空 → `clamp_limit(declared, None) == declared`。**dry run 里 `applied == declared` 恒成立**（钳制只发生在资产加载路径）。
6. **route 的闸门计数已存在**：`_route_counts[node.id]`（`scheduler.py:529` / 增于 `:1891` / 判于 `:1672`）就是 `max_routes` 判定的实际计数。
7. **描述披露现状**：`DeclareWorkflow` 描述（4109 字符，守卫上界 6000）**不提**图级三闸；只披露路由 `max_routes` 默认 1（`subagents.py:782`）。`DryRunWorkflow` 提闸门**名字**不提**值**。

### 已实测的**缺口**（本 change 要消除的东西）

`research/gap_probe.py` / `research/gate_trip_probe.py` 输出（本目录 `research/`）：

| 缺口 | 实测证据 |
|---|---|
| **G1 顶层无生效上限** | dry run 报告键集无任何 `limits`/`cap` 字段。 |
| **G2 无「声明 vs 展开」汇总** | 声明 3 / 展开 5 / 自动插层 2，但顶层无 `count`/`expand` 字段，只有逐节点 `auto_inserted` 布尔。 |
| **G3 route 无 `max_routes`** | route 条目键集不含 `max_routes`。 |
| **G4 描述不披露图级三闸值** | `DeclareWorkflow` 描述不含 `max_nodes` / `recursion_limit` / `200`。 |
| **G5 撞闸非结构化** | dry run 撞 `max_nodes` 时无 `limits` 无 `diagnostics`；原因只在 `warnings[]` 散文里（`...exceeding max_nodes 3 (2 already declared)`）。而真实运行的 `status()`/`_envelope()` 两者都有——**dry run 是唯一漏的出口**。 |

## Goals / Non-Goals

### Goals

- 让模型在 dry run 报告里看见：结构闸的生效值（三段式）、声明图展开后的规模与离上限的距离、route 的 `max_routes` 与已用计数、撞闸时的结构化诊断。
- 让模型在**声明前**（工具描述）就知道图级三闸的默认值。
- 消除「dry run 是唯一不报生效值的出口」这一不一致——**这条是本 change 最强的设计论证**：同一批值在三个出口都报，唯独第四个不报，是无理由的漂移。

### Non-Goals

- **不改任何闸门默认值**（属 #276）。
- **不改闸门判定逻辑**（`_check_declared_limits` / `_drive` / `_route_verdict`）。
- **不引入第二个真相源**（见 D6）。
- **不做静态「是否撞闸」预测**——dry run 真跑了调度器，撞不撞是既成事实，本 change 只把结果结构化。

## Decisions

### D1 — 新增 `limits` 字段：复用 `limits_report()`，三段式，不强加 ceiling

报告顶层增 `limits: {recursion_limit: {declared, applied, clamped}, max_nodes: {...}, max_runs: {...}}`，直接调 `limits_report(spec, {})`。

**为什么不扁平化成 `{recursion_limit: 100}`**：既有三个出口都是三段式（`limits_clamped` 从它派生），扁平化会引入**第二种形状**，正是要消灭的漂移。模型读到的 `limits` 与 `RunWorkflow` 返回体**逐字段同形**，一处学会处处可用。

**口径（必须写进报告/描述，否则模型会误读）**：dry run 的 scheduler 不传 ceiling（Context #5），所以 `applied == declared` 恒成立、`clamped` 恒为 `false`。这**不是 bug，是如实**——dry run 模拟的是模型**当前声明的 spec**，而钳制只在**资产加载路径**发生。报告须说明：这个 `limits` 是「你这张图在当前会话直接运行时会生效的值」；若这张图将来存成资产再加载，可能被配置钳制（届时 `RunWorkflow` 返回体的 `limits_clamped` 会报出来）。

> **待 grill 确认**：`clamped` 在 dry run 恒 `false` 是否该保留？保留=与另外三出口同形（推荐）；去掉=更诚实但引入形状差异。**倾向保留 + 报告说明句。**

### D2 — 新增 `node_budget`：声明 vs 展开 vs 上限，**headroom 只对 `max_nodes` 给**

报告顶层增 `node_budget: {declared, expanded, auto_inserted, limit, headroom}`，来源是 `ExecutionPlan.declared_nodes` / `.inserted_nodes` / `.nodes` 与 `_eff_limit("max_nodes")`。

**`headroom` 的口径必须限定在 `max_nodes`**：`max_nodes` 是**静态**的（声明 + 自动插层的节点总数在执行计划构建后即确定），`limit - expanded` 是一个**确定的**距离。而 `max_runs` / `recursion_limit` 是**动态**的（取决于 route 实际走了几轮），dry run 的展开数**不构成**它们的上界——若也报 `max_runs` 的 headroom，会给出一个**看似精确实则下界**的数字，正是 #273 D6「不臆造」要防的。

> **待 grill 确认**：`node_budget` 是否只服务 `max_nodes` 一闸（推荐），还是改成通用结构 `gates: {max_nodes: {..., headroom}, max_runs: {...}}` 但只对 max_nodes 填 headroom？**倾向：`node_budget` 只讲 max_nodes 一件事，命名即边界。**

### D3 — route 条目增 `max_routes`（生效值）与已用计数

route 条目的 `max_routes` 取 `state.node.max_routes`；已用计数取 `scheduler._route_counts.get(node.id, 0)`。

**为什么不复用条目已有的 `runs`**：`state.runs` 对 route 是「route 被求值的次数」，`_route_counts` 是「闸门判定的计数」——两者**未必相等**（闸门在计数达到 `max_routes` 时拒绝，route 可能多求值一次或提前走 default）。报告必须报**闸门实际用的那个计数**，否则又是一处「看起来对、口径不同」的假面。

> **待 grill 确认**：`_route_counts` 是私有状态，读它是否可接受？**论证**：`_build_dry_run_report` 已读 `scheduler._plan` / `scheduler._states`，读 `_route_counts` 属同一类（同包私有），且这是**唯一**与闸门同源的计数。替代方案（重算 route 次数）会引入第二真相源（违反 D6）。**倾向：读，并在测试里锁 `route.used == _route_counts` 同源。**

### D4 — 撞闸时报告带 `diagnostics`，与 `_envelope()` **同条件同形**

报告增 `diagnostics`，取 `dict(scheduler._diagnostics)`，**条件与 `_envelope()` 一致**（`if self._diagnostics`）。

**为什么镜像而非新造**：`_envelope()` 已有「诊断只在非空时挂载」的纪律，且 `_diagnostics` 会被**非闸门**诊断填充（`route_ref_misses`，见 `scheduler.py:1476` 注释）。镜像它的条件，保证 dry run 与真实运行**对同一张图给出同一份诊断**——这是「一处学会处处可用」的又一例。

**注意**：dry run 撞闸时 `_diagnostics` **已有**内容（`_mark_graph_recursion_exceeded` 写入），只是报告没读。所以这是纯「接出口」。

### D5 — 工具描述披露图级三闸**默认值**（值，SHALL NOT 是示例）

`DeclareWorkflow` 描述补一句（~120 字符）：

> `Graph-level gates default to recursion_limit=100 / max_nodes=200 / max_runs=300 (declare them in the spec to override; an asset loaded under a smaller config is clamped to the config value).`

**为什么是「值」不是「示例」**：#248 实测教训——示例是模型学错的地方（照抄错示例）；而**默认值本身是事实**，模型知道 200 就能规划图规模，不会误导。这与 #248「schema 管域、示例管形」同精神：**值是域的一部分**。

**长度预算**：`DeclareWorkflow` 描述 4109 字符，补 ~120 字符后 4229，仍在 6000 守卫内（`test_workflow_tool_discoverability.py`）。

> **待 grill 确认**：三闸默认值放 `DeclareWorkflow` 还是 `DryRunWorkflow` 描述？**倾向 `DeclareWorkflow`**（模型在那里动笔声明，最需要）；`DryRunWorkflow` 描述已有闸门名字，可加一句「the report tells you the effective values」。两者都加 vs 只加一处，见 Open Questions。

### D6 — 唯一数据源纪律（本 change 的核心不变量）

报告里**每一个**闸门值都 SHALL 经既有函数取得：`limits_report()` / `_eff_limit()` / `ExecutionPlan` 字段 / `_route_counts` / `_diagnostics`。**SHALL NOT** 在报告层基于 spec 重算任何闸值。

**理由**：spec 已有条款要求「所有对外报出限制值的出口都报**实际生效值**而非声明值」。如果在 dry run 报告层重算，钳制逻辑一旦演进（如新增一种 ceiling 来源），dry run 就会与其他三出口**静默分叉**——这正是「对内钳、对外报声明值」假面的同型问题。

**测试锁**：同一 spec + 同一 ceiling 下，`report["limits"] == limits_report(spec, ceiling)` 逐字段相等（变异验证：把报告层改成重算，测试须变红）。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| **新增字段被模型误读**（把 `declared` 当 `applied`、把 `headroom` 当精确值用在动态闸上） | D1/D2 的口径说明句进报告 `notes`；不变量测试锁同源；验收 L3 专查新误读。 |
| **报告体积增大** | 新字段是**定长小对象**（不随图规模增长）；报告已有 `max_report_chars` 有界纪律。 |
| **`clamped` 恒 false 让模型以为「永远不会被钳」** | D1 说明句点明「资产加载路径可能钳」；`RunWorkflow` 的 `limits_clamped` 仍是权威。 |
| **读 `_route_counts` 与 `state.runs` 口径不同，模型困惑** | D3 只报闸门计数并在字段名上标明（如 `used`），不报第二个计数；测试锁同源。 |
| **描述 +120 字符挤压既有条款** | 实测余量 ~1900 字符；测试锁描述长度 < 6000。 |
| **本 change 与 #276 重叠** | 硬边界：本 change **只报值**，#276 才**改值**；#276 blocked-by 本 change。 |

## Testing Strategy

- **新增** `tests/agent/subagent/test_workflow_limit_visibility.py`：
  - `limits` 三段式存在；**钳制场景**（配置 `max_runs` 小于 spec 声明）下断言 `applied != declared`、`clamped is True`——**注意**：dry run 不传 ceiling，钳制场景须走**资产加载**出口或直接构造带 ceiling 的 scheduler 才能触发；dry run 路径断言 `applied == declared`。
  - `node_budget`：宽扇入图（`items > MAX_FAN_IN=10`）断言 `expanded > declared`、`auto_inserted == expanded - declared`、`headroom == limit - expanded`；窄扇入图断言 `expanded == declared`。
  - route 条目含 `max_routes` 与 `used`；断言 `used == scheduler._route_counts[node]`（同源锁）。
  - 撞闸图（配小 `max_nodes`）报告含 `diagnostics`，`diagnostics["reason"] == "max_nodes"`；**未撞闸**图报告**不含** `diagnostics`（镜像 `_envelope()` 条件）。
  - **不变量**：`report["limits"] == limits_report(spec, {})` 逐字段相等（变异验证）。
- **扩展** `tests/agent/subagent/test_workflow_tool_discoverability.py`：`DeclareWorkflow` 描述含三闸默认值；描述长度 < 6000。
- **回归** `tests/agent/subagent/test_workflow_dry_run.py`：新增字段是**增**，既有断言不失效。
- **全量** `uv run pytest -q`。

## Pre-Implementation Review

**grill 阶段填写**：`reviews/grill-design.md`（独立零记忆 subagent 逐轮追问产出的决策记录 + `## User Confirmation` 用户答复）。

## Impact Analysis（design 视角的补充）

见 `proposal.md` 的 `## Impact Analysis`。design 视角的两个补充：

1. **`scheduler.py` 预期零改动**——本 change 只读既有私有状态（`_plan`/`_states`/`_route_counts`/`_diagnostics`/`_eff_limit`）。若实现中发现需改 scheduler，SHALL 先停轮回写（与 #273 的「不改调度器」不变量同精神）。
2. **`limits_report()` 的 `ceiling` 参数**：dry run 传 `{}`（无钳制）。若将来要让 dry run 反映某个 ceiling，须先回写本 design（属新增能力面）。
