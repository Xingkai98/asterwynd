# Design: foreach 截断可见性

## Context

`foreach` 的 `max_items`（默认 20）静默截断 `items`（`scheduler.py:2669` `items[:node.max_items]`），是全仓**唯一**不报告的截断点（其余三处：`nodes_omitted`/`warnings_omitted`/`item_refs_omitted`）。本 design 把截断在**三条模型可见出口**如实报告。

### 已核实的事实（本设计的地基）

1. **截断点**：`_resolve_items`（`agent/subagent/scheduler.py:2665-2669`）：`max_items==0` → `items[:remaining_expansion_capacity()]`（预算截断）；`>0` → `items[:node.max_items]`（**静态截断，本 change 的主角**）。
2. **两条声明入口共用 warnings helper**：`DeclareWorkflow`（`subagents.py:841`）与 `RunWorkflow(spec=...)`（`:1284`）都调 `_route_task_warnings(spec)`（`:710`，纯声明期、只读 spec、不运行）。
3. **dry run 的 foreach 条目**：`subagents.py:1584` `entry["items_expanded"] = state.items`（只有展开数，无 decline/omitted）。
4. **已有同名字段，语义不同**：`item_refs_omitted`（`subagents.py:1132`）= `items_total - len(item_refs)`——那是**结果投影里 ref 列表**被 `_PARENT_NODES_LIMIT` 截断的条数，**不是** `max_items` 丢弃的项数。两件事 SHALL NOT 混。
5. **先例形态**：`nodes_omitted = max(total - limit, 0)`（`scheduler.py:3163`）+ 一个 `total`。本 change 的字段直接沿用。
6. **`items` 字段**：`WorkflowNode.items: list | None`（`workflow.py`）；`source` 驱动时 `items is None`、集合在运行期经 `_source_collection` 解析。

## Goals / Non-Goals

### Goals

- 三条出口（声明 warnings / dry run / 运行期投影）如实报告「声明 N / 展开 M / 省略 K」。
- 零噪声：不截断时不报；`max_items=0` 不报静态截断。
- 与既有 `item_refs_omitted` 不混。

### Non-Goals

- 不改 `max_items` 默认值（#276）。
- 不改 `max_items=0` 语义。
- 不预测/提示 `source` 驱动 foreach 的声明期展开数（对抗否决弱提示，见 D3）。
- **不报告 `max_items=0` 的预算截断静默**（另立 follow-up，见边界节 Q3）。
- **字段名不复用 `items_total`**（D2）。

## Decisions

### D1 — **三出口一致**：声明期 / dry run / 运行期各报告其所知

| 出口 | 何时可知 | 报告什么 |
|---|---|---|
| **声明期 warnings**（`DeclareWorkflow` + `RunWorkflow(spec=)`） | 仅**字面 `items`** 可知（`len(node.items)`）；`source` 驱动不可知 | 「node {id} declares {N} items but max_items={M}; only the first {M} run」+ 行动指引 |
| **dry run**（`DryRunWorkflow` foreach 条目） | dry run 会**解析**集合（含 source 驱动） | 补 `items_declared` / `items_omitted`（与既有 `items_expanded` 三者齐）；source 驱动的 `items_declared` 标**模拟、不可信**（见 Q5） |
| **运行期投影**（`GetWorkflow` foreach 节点） | 运行期解析后 | 静态截断信号（`items_omitted`）——**须后写**（见 D3） |

**为什么声明期只报字面 `items`**：`DeclareWorkflow` 是**纯声明、不运行**（`:710` helper 只读 spec）；`source` 驱动的集合数要到运行期才解析得出，声明期**无从可知**。**已定（对抗否决 grill 的弱提示）**：声明期对 source 驱动**完全静默**——delta spec 的「source 驱动在声明期不猜」Scenario 把 source 截断报告**独家路由**到 dry-run/运行期；且 source+默认 `max_items` 是**最常见**配置，声明期提示会**无条件触发**成噪声、行动性弱。若要一条提示，它该落在 **dry-run**（同本 change 既有出口）。

### D2 — 字段名：**扁平 `items_declared` / `items_omitted`**（弃用 `items_total`）

**grill + 对抗两轮证实**：**绝不能复用 `items_total`**——`GetWorkflow(detail='nodes')` 的 foreach 节点 dict 上**已有** `items_total`（`subagents.py:1131`，`= len(state.item_runs)` = **展开后项数**，被 spec:858 钉死 + `test_foreach_item_refs.py:121` 硬断言）。本 change 的「声明集合大小」若也叫 `items_total`，会写**同一 dict、同键、后写者覆盖先写者、无报错**（实测该节点同时带既有 `items_total=20` 与 `items=20`）。

**采纳对抗结论**：用**扁平** `items_declared`（声明集合大小）/ `items_omitted`（被 `max_items` 丢弃数 = `max(items_declared - items_expanded, 0)`），**不用** grill 提的嵌套对象 `items_truncation{...}`——那违背 proposal 自证的 RIR finding 1（「统一是 `X_omitted = max(total-shown,0)` + `X_total`，不新造词表」）与全仓节点投影的扁平范式（`_graph_node_projection`/`_attach_item_refs` 全扁平）。测试锁「既有 `items_total`/`item_refs_omitted` 语义不变 + 新字段独立共存」。

### D3 — 三出口可知性边界 + **运行期出口须走「后写」**

- **字面 `items`**：`len(node.items)` 声明期可知 → 声明期 warnings 可报。
- **`source` 驱动**：声明期**不可知 → 声明期完全静默**（对抗否决了 grill 的「弱提示」：delta spec 的「source 驱动在声明期不猜」Scenario 把 source 截断报告**独家路由**到 dry-run/运行期；且 source+默认 `max_items` 是**最常见**配置，声明期提示会**无条件触发**成噪声、行动性弱）。截断由 dry-run / 运行期报。
- **`max_items=0`**：无静态截断 → 三出口都**不报静态截断**。
- **运行期出口实现约束（grill 未写、对抗确认）**：新字段加在 `GetWorkflow(detail='nodes')` 的 foreach 节点上，**必须像 `_attach_item_refs` 那样在 `parent_envelope()` 之后补写**（`subagents.py:1046` → `:1058` 的既有顺序）——否则会被 `_bounded_node` 的白名单 `_PARENT_NODE_FIELDS`（`scheduler.py:384`）**静默丢弃**（该白名单只有 `id/kind/status/runs/subagent_id/items`）。tasks 3.4 据此落点。

### D4 — 与 `item_refs_omitted` 划清（SHALL NOT 混）

`item_refs_omitted` = ref **列表界**（投影数组超 200 的条数，`subagents.py:1132`）；本 change 的 `items_omitted` = `max_items` **丢弃的项数**。两者**独立共存**（对抗实测：210 项 / `max_items:205` ⇒ `items_omitted=5` 且 `item_refs_omitted=5` **同 >0**，互不决定）。测试 SHALL 显式覆盖「两者不同」。

### D5 — 措辞可行动且**不误称「默认值」**（沿用 #248 纪律）

声明期警告 SHALL 同时给「哪里」与「怎么改」，**且 SHALL NOT 声称 `max_items=20` 是「默认值」**——`_parse_max_items`（`workflow.py:529`）不保留「是否显式声明」，显式写 `max_items: 20` 与省略**同值不可分**，误称会给出错误归因。示例：`node {id}: declares {N} foreach items but max_items={M} — only the first {M} will run. Reduce items, raise max_items, or set max_items: 0 to run all.`

### D6 — 声明期 warnings **条数的界**（grill 与 design 原稿的假缓解，对抗修正）

**原稿风险表称「新 warning 受既有 `warnings_limit`/`warnings_omitted` 约束」是错的**：那两个界**只存在于 dry-run 报告构造器**（`subagents.py:1660-1662`）；`DeclareWorkflow`（`:841`）与 `RunWorkflow`（`:1294`/`:1299`）的 `warnings` **直接来自 helper、无任何切片**（实测 300 个截断节点 ⇒ 300 条警告、无 omitted）。

**修法（二选一，实现期定，倾向 (b)）**：(a) 给两条声明入口的 `warnings` 也加 `warnings_limit`（复用 dry-run 口径 + `warnings_omitted`）；(b) 如实写「声明期警告条数上界 = foreach 节点数（受 `max_nodes` 间接约束），不漏项」——因声明期 warnings 是对**声明**的忠实反映，截断它反而可能漏掉某个节点。**无论哪个，SHALL NOT 引用不存在的 `warnings_omitted` 界。**

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| **`items_total` 同 dict 同键覆盖**（D2） | 弃用该名，改扁平 `items_declared`/`items_omitted`；测试锁共存 |
| **运行期新字段被 `_bounded_node` 白名单丢弃**（D3） | 走 `_attach_item_refs` 式**后写**（`parent_envelope()` 之后补写）；测试断言 `GetWorkflow(detail='nodes')` 真能看到 |
| **声明期对 source 误报/漏报** | D3：声明期只报字面 items；source 驱动声明期**完全静默** |
| **`max_items=0` 误报静态截断** | D3：三出口都排除 `max_items=0` |
| **噪声**（不截断也报） | T5：`items ≤ max_items` 时不产生任何字段/警告 |
| **把 ref 列表界与 items 截断混报** | D4：`item_refs_omitted` 独立保留；测试覆盖两者不同 |
| **声明期 warnings 条数无界**（M1，实测假缓解） | D6：补界 或 如实写「上界=节点数」；SHALL NOT 引用不存在的 `warnings_omitted` |
| **dry-run 对 source 的 `items_declared` 无预测性**（Q5） | source 驱动 dry-run 的 declared 是**模拟值**（常为 0，与空集合同形），须标**不可信/模拟**；与 Q4 的「空集合」合并处理（见下） |

## 边界（Q3/Q4，对抗定级）

- **Q3 `max_items=0` 预算截断静默**：机制是 **`_resolve_items` 切到 `_remaining_expansion_capacity()` 刚好合身**（`scheduler.py:2668`）⇒ 后续 `_check_foreach_budget`（`:2162`）`runs+delta>limit` **刚好不触发**（非「delta≤0 跳过」——实测 delta>0）。静默窗口**窄**（仅 **terminal foreach 且切片后预算仍够下游**；非 terminal 会**响亮报** `graph_recursion_exceeded`）。**本轮 Non-Goal**（#279 原文只点 `max_items` 静态截断），**须显式写 Non-Goal + 开 follow-up issue**。
- **Q4 空集合 / source 无产出 ⇒ foreach 跑 0 项**：`extract_collection(None)→[]`（`scheduler.py:353`）⇒ `fan` 以 0 项运行、`status=completed`、**无信号**（对抗上调至中-高：含 **failed-source** 子情形；successful-but-empty 是全静默）。**范围决策 —— 见停轮确认项。**

## Testing Strategy

- **新增**（并入既有 workflow 测试或新文件）：
  - T1/T2：60 项 literal foreach + 默认 max_items ⇒ `DeclareWorkflow` 与 `RunWorkflow(spec=)` warnings 含截断提示（含行动指引）；
  - T3：dry run foreach 条目 `items_declared=60 / items_expanded=20 / items_omitted=40`；
  - T4：运行期 `GetWorkflow` 暴露静态截断信号；
  - T5：`items ≤ max_items` ⇒ 无截断字段/warning；
  - T6：`max_items=0` ⇒ 不报静态截断；
  - T7：`item_refs_omitted` 与 `items_omitted` 独立（构造两者不同的图）；
  - source 驱动 foreach：声明期不报、dry-run 报（D3）。
- **回归**：workflow declare/dry-run/run 既有测试；全量 `uv run pytest -q`。

## Pre-Implementation Review

grill 阶段填写（`reviews/grill-design.md`）。**按流程纪律：grill 结论须先走独立对抗验证（`reviews/grill-adversarial.md`）再拍板。**

## Impact Analysis（design 视角的补充）

见 `proposal.md`。补充：**D2 字段名已由对抗钉死**——本 change 用扁平 `items_declared`/`items_omitted`，**绝不复用**既有 `items_total`（同 dict 同键会覆盖）；运行期新字段须**后写**（绕过 `_bounded_node` 白名单）。
