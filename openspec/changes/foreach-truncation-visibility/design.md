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
- 不预测 `source` 驱动 foreach 的声明期展开数。

## Decisions

### D1 — **三出口一致**：声明期 / dry run / 运行期各报告其所知

| 出口 | 何时可知 | 报告什么 |
|---|---|---|
| **声明期 warnings**（`DeclareWorkflow` + `RunWorkflow(spec=)`） | 仅**字面 `items`** 可知（`len(node.items)`）；`source` 驱动不可知 | 「node {id} declares {N} items but max_items={M}; only the first {M} run」+ 行动指引 |
| **dry run**（`DryRunWorkflow` foreach 条目） | dry run 会**解析**集合（含 source 驱动） | 补 `items_total` / `items_omitted`（与既有 `items_expanded` 三者齐） |
| **运行期投影**（`GetWorkflow` foreach 节点） | 运行期解析后 | 静态截断信号（`max_items` 丢弃数） |

**为什么声明期只报字面 `items`**：`DeclareWorkflow` 是**纯声明、不运行**（`:710` helper 只读 spec）；`source` 驱动的集合数要到运行期才解析得出，声明期**无从可知**。声明期硬报会需要运行语义、且可能与实际不符——**SHALL NOT** 在声明期猜测 `source` 驱动的展开数（见 Non-Goals）。

> **待 grill 确认**：声明期对 `source` 驱动且 `max_items>0` 的 foreach，要不要给一条**弱提示**（「此 foreach 由 source 驱动，运行时可能被 max_items=N 截断，无法在声明期确定」）？还是**完全静默**、只在 dry-run/运行期报？（推荐：**完全静默**——声明期不知就不说，避免噪声；dry-run 会报。）

### D2 — 字段名沿用先例：`items_total` / `items_omitted`

`items_total` = 本轮应展开的集合大小（dry-run：解析后的集合长；运行期：`_resolve_items` 收到的集合长）；`items_omitted = max(items_total - items_expanded, 0)`。**沿用 `nodes_omitted` 的 `max(total - shown, 0)` 形态**（事实 5），不新造词表。

> **待 grill 确认**：`items_total` 与 **`item_refs_omitted` 的 `items_total`** 同名——后者（`subagents.py:1098-1099`）定义是 `len(state.item_runs)`（**本轮展开项数含空槽**），**不是**集合大小！两处 `items_total` 语义不同会撞名。**这是本设计最大的风险**：要么本 change 用**不同名**（如 `items_declared` / `collection_size`），要么统一语义。**须 grill 裁定。**

### D3 — 声明期 vs 运行期可知性边界

- **字面 `items`**：`len(node.items)` 声明期可知 → 声明期 warnings 可报。
- **`source` 驱动**：声明期不可知 → 声明期不报，dry-run / 运行期报。
- **`max_items=0`**：无静态截断 → 三条出口都**不报静态截断**（预算截断是另一层，本 change 不报、也不与静态截断混）。

### D4 — 与 `item_refs_omitted` 划清（SHALL NOT 混）

`item_refs_omitted` = ref **列表界**（投影数组有界）；本 change 的 `items_omitted` = `max_items`/预算 **丢弃的项数**。两者**独立共存**：一个 foreach 可以 `item_refs_omitted>0` 而 `items_omitted==0`（展开了全部、但 ref 列表被界截），或反之。测试 SHALL 显式覆盖「两者不同」。

### D5 — 措辞可行动（沿用 #248 纪律）

声明期警告 SHALL 同时给「哪里」与「怎么改」：`node {id}: declares {N} foreach items but max_items={M} defaults to 20 — only the first {M} will run. Reduce items, raise max_items, or set max_items: 0 to run all.`（确切措辞实现期定，须含行动项）。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| **`items_total` 与 `item_refs_omitted` 的 `items_total` 撞名异义**（D2） | **grill 裁定字段名**；测试锁语义 |
| **声明期对 source 驱动报错/误报** | D1/D3：声明期只报字面 items；source 驱动声明期静默 |
| **`max_items=0` 误报静态截断** | D3：三出口都排除 `max_items=0` |
| **噪声**（不截断也报） | T5：`items ≤ max_items` 时不产生任何字段/警告 |
| **把 ref 列表界与 items 截断混报** | D4：`item_refs_omitted` 独立保留；测试覆盖两者不同 |
| **声明期 warnings 条数上界**（`warnings_omitted`） | 新 warning 走既有 `warnings` 列表，受既有 `warnings_limit`/`warnings_omitted` 约束（无需新增界） |

## Testing Strategy

- **新增**（并入既有 workflow 测试或新文件）：
  - T1/T2：60 项 literal foreach + 默认 max_items ⇒ `DeclareWorkflow` 与 `RunWorkflow(spec=)` warnings 含截断提示（含行动指引）；
  - T3：dry run foreach 条目 `items_total=60 / items_expanded=20 / items_omitted=40`；
  - T4：运行期 `GetWorkflow` 暴露静态截断信号；
  - T5：`items ≤ max_items` ⇒ 无截断字段/warning；
  - T6：`max_items=0` ⇒ 不报静态截断；
  - T7：`item_refs_omitted` 与 `items_omitted` 独立（构造两者不同的图）；
  - source 驱动 foreach：声明期不报、dry-run 报（D3）。
- **回归**：workflow declare/dry-run/run 既有测试；全量 `uv run pytest -q`。

## Pre-Implementation Review

grill 阶段填写（`reviews/grill-design.md`）。**按流程纪律：grill 结论须先走独立对抗验证（`reviews/grill-adversarial.md`）再拍板。**

## Impact Analysis（design 视角的补充）

见 `proposal.md`。补充：**最敏感处是 D2 的字段名撞名**（`items_total` 与 `item_refs_omitted` 那处的 `items_total`）——实现前必须由 grill/对抗钉死命名，否则两个不同语义的 `items_total` 会让读回方混淆。
