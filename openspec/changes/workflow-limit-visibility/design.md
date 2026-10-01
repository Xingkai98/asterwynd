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

> **grill 结论（round-1）**：保留三段式与 `clamped` 字段 **确认**（它是结构性事实：dry run 构造 scheduler 不传 `limit_ceiling`）。**条件**：报告 `notes` 必须补口径说明句，否则 `clamped:false` 会被读成「永远不会被钳」。

### D2 — 新增 `node_budget`：声明 vs **展开** vs 上限，**headroom 只对 `max_nodes` 给**

报告顶层增 `node_budget: {declared, graph_nodes, expanded_nodes, auto_inserted, limit, headroom}`。

**grill 发现并实测钉死的口径错误（本 design 原稿是错的，已改）**：

1. **`max_nodes` 闸门按「foreach 每项各计一个节点」计费**，而非只数图节点。依据：`workflow.py` 明写「`max_nodes` 数节点（**含 foreach 展开**）」；`_check_foreach_budget`（`scheduler.py:2146`）以 `count = state.items` 计费。
2. **原稿用 `len(plan.nodes)` 作 `expanded` 是错的**：它完全不计 foreach 展开项。实测（`max_nodes=200`、20 项）：`len(plan.nodes)=4` 但闸门口径 = 24。
3. **改用 `_expanded_nodes` 仍不够**（本 change 的探针 `research/node_budget_probe.py` 实测，比 grill 的推荐更进一层）：闸门在 `self._expanded_nodes += delta` **之前** raise，故**撞闸图上 `_expanded_nodes` 也不含被拒的那次展开**。

实测对照（`research/node_budget_probe.py` 输出）：

| 场景 | `run_status` | `len(plan.nodes)` | `_expanded_nodes` | 真值 |
|---|---|---|---|---|
| 20 项，`max_nodes=200` | 完成 | 4（余 196） | 24（余 176） | 24 |
| 20 项，`max_nodes=**5**` | **撞闸** | 4（**余 1**） | 4（**余 1**） | 24 |
| 20 项，`max_nodes=24` | 完成 | 4（余 20） | 24（**余 0**） | 24 |
| 20 项，`max_nodes=**23**` | **撞闸** | 4（**余 19**） | 4（**余 19**） | 24 |
| 2 项，`max_nodes=200` | 完成 | 2（余 198） | 4（余 196） | 4 |

**结论**：**两个既有计数在撞闸图上都报正余量**——正是本 change 要消灭的「假面」在报告自己身上复现。若照原稿实现，一张**已经撞闸**的图会显示 `headroom: 1`。这与 #273 D6「不臆造」直接冲突。

> **`expanded` 的定义（改后）**：`node_budget.expanded_nodes` = **闸门等价投影** = `len(plan.nodes) + Σ foreach 展开项数`，即「这张图若展开完，闸门会数到多少」。上表「真值」列即此值。
>
> **实现取向（待用户 Q1 拍板）**：投影值**不应在报告层重算**（违反 D6）。推荐**让闸门自己记录**：在 `_check_foreach_budget` 计算 `count` 后、**做超限判定之前**，把 `self._expanded_nodes + delta` 记入一个新字段（如 `self._projected_expanded_nodes`，取历史最大）。这样报告的 `expanded_nodes` 与闸门**同源**，且撞闸时也如实（`max_nodes=5` → `expanded_nodes=24` → `headroom=-19`，负值即「超了」）。**此取向需要一处 `scheduler.py` 改动**（记录投影值，**不改任何判定逻辑**），故须回写 Impact Analysis（见下）。
>
> **字段拆分**：另保留 `graph_nodes = len(plan.nodes)`（图规模，**只含自动插层、不含 foreach 项**）——它与既有 `workflow_graph_snapshot` 的「图规模权威值」口径一致（`scheduler.py:2840` 注释）。两个数讲两件事：`graph_nodes` 是「图有多大」，`expanded_nodes` 是「闸门数到多少」。`notes` 需点明二者差别。
>
> **`auto_inserted` 不再是 `expanded - declared`**：改用 `expanded_nodes` 后，`expanded_nodes - declared` 含 foreach 项，不再等于自动插层数。`auto_inserted` 改**直接取 `len(plan.inserted_nodes)`**（只数自动插层），与 `expanded_nodes` 是**独立**字段。原稿的 `auto_inserted == expanded - declared` 断言作废。

**`headroom` 的口径必须限定在 `max_nodes`**：`max_nodes` 是**静态**的（展开完的节点总数在展开后即确定），`limit - expanded_nodes` 是一个**确定的**距离（可为负）。而 `max_runs` / `recursion_limit` 是**动态**的（取决于 route 实际走了几轮），dry run 的展开数**不构成**它们的上界——若也报 `max_runs` 的 headroom，会给出一个**看似精确实则下界**的数字，正是 #273 D6「不臆造」要防的。

**`node_budget` 只服务 `max_nodes` 一闸**（grill 确认 D2-a）：不泛化成 `gates: {...}` 映射，命名即边界，避免诱导实现方给动态闸也填「余量」。

### D3 — route 条目增 `max_routes`（生效值）与**闸门计数**（字段名 `gate_count`）

route 条目的 `max_routes` 取 `state.node.max_routes`；闸门计数取 `scheduler._route_counts.get(node.id, 0)`。

**grill 发现并实测钉死的事实错误（本 design 原稿的理由是错的，已改）**：原稿称「`state.runs` 对 route 是『route 被求值的次数』」——**错**。`state.runs` 对 route **结构性恒为 0**：唯一递增点是 `_apply_run_status`（`scheduler.py:2328`），只有 `_execute_subagent` / `_execute_aggregate` 调它；`_execute_route`（`:1866`）从不调。实测：gate 被判定一次 → `_route_counts={'gate':1}` 而 `state.runs=0`。

**字段名定为 `gate_count`（不是 `used`）**（grill Q3 推荐）：报告的 route 条目**已经**有一个既有 `runs` 字段（恒 0）。若新增字段叫 `used`，模型会读到 `runs: 0` 与 `used: 1` 并列为**表观矛盾**。命名为 `gate_count` 并在 `notes` 说明「route 的 `runs` 恒 0 是既有事实（route 不跑模型），`gate_count` 才是 `max_routes` 判定的计数」，把矛盾消解为解释。**`runs` 字段本身不在本 change 改**（属既有字段语义）。

**为什么读私有 `_route_counts`**（grill 确认 D3-a）：它是 `max_routes` 超限判定**唯一**实际使用的计数（定义 `:529`、递增 `:1891`、判定 `:1672`）；`_build_dry_run_report` 已在读 `scheduler._plan` / `_states`，同包私有同类读取，不新增耦合面。替代方案（报告层重算 route 次数）会引入第二真相源，违反 D6。

### D4 — `diagnostics` 字段：**无条件挂载**，与**模型可见出口**（`parent_envelope`）同形

报告增 `diagnostics`，取 `dict(scheduler._diagnostics)`，**无条件挂载**（未撞闸时为 `{}`）。

**grill 发现并实测钉死的事实错误（本设计原稿是错的，已改）**：原稿称「`_envelope()` 有条件携带 diagnostics（`scheduler.py:3107`，`if self._diagnostics`）」——**错**。`scheduler.py:3107` 是 `"diagnostics": dict(self._diagnostics),`，**无条件**写在 payload 字面量里；`if self._diagnostics` 出现在 **`status()`** 的 `scheduler.py:2886`（另一条出口）。实测：`parent_envelope()`（= `RunWorkflow` 交给模型的返回体，`_envelope` 的 bounded 投影）**始终带 `diagnostics` 键**，值为 `{}`。

**因此挂载条件取「无条件 `{}`」**：模型在 `RunWorkflow` 学到的是「`diagnostics` 恒在」，dry run 保持同形才符合「一处学会处处可用」。用 `status()` 的条件口径会与模型最常打交道的 `RunWorkflow` 分叉。

**`_diagnostics` 会被非闸门诊断填充**（实测：一张**未撞闸**但有 `$ref` 槽未命中的图得到 `{"route_ref_misses": [...]}`）。故 `notes` 必须说明「**`diagnostics` 非空 ≠ 一定撞了闸**——看 `reason` 键」（与 `scheduler.py:1476` 既有纪律一致）。

**spec delta 需同步**：原 delta 的 Scenario「未撞闸时不产出现实不存在的诊断」要求 dry run **不挂空诊断**，与「与真实运行的同一诊断出口一致」在 `parent_envelope` 口径下**不可兼得**。**改 delta**：删「SHALL NOT 因此挂一个空诊断」，改为「诊断字段与真实运行**模型可见出口**形状一致（未撞闸时为空对象）」。

### D5 — 工具描述披露图级三闸**默认值**（值，SHALL NOT 是示例）

`DeclareWorkflow` 描述补一句（~140 字符）：

> `Graph-level gates default to recursion_limit=100 / max_nodes=200 / max_runs=300 — these are module defaults; a deployment may override them (and an asset loaded under a smaller config is clamped), so trust the effective values DryRunWorkflow reports.`

**为什么是「值」不是「示例」**：#248 实测教训——示例是模型学错的地方（照抄错示例）；而**默认值本身是事实**，模型知道 200 就能规划图规模，不会误导。这与 #248「schema 管域、示例管形」同精神：**值是域的一部分**。

**grill 发现的分叉风险（已改）**：`DeclareWorkflowTool.description` 是**静态类属性**，而运行期默认来自配置（`_spec_bounds()`，`subagents.py:442`，随 config 变化——实测配置 `max_nodes=777` 时 `bounds` 为 777，但描述恒为静态串）。若描述把 200 说成「你当前的默认值」，一个覆盖了配置的部署会出现「描述说 200、报告说 777」的分叉，正违反 D6。**故措辞明确限定为「模块默认值」，并加「以 `DryRunWorkflow` 报告的生效值为准」。**

**长度预算**：`DeclareWorkflow` 描述 4109 字符，补 ~140 后 ~4249，仍在 6000 守卫内（grill 确认 D5-a）。

**放 `DeclareWorkflow`**（grill 倾向）：模型在那里动笔声明，最需要；`DryRunWorkflow` 描述已提闸门名字，可另加一句「the report tells you the effective values」（是否两处都加见 Open Questions Q6 之邻项）。

### D6 — 唯一数据源纪律（本 change 的核心不变量）

报告里**每一个**闸门值都 SHALL 经既有函数/同源字段取得：`limits_report()` / `_eff_limit()` / `ExecutionPlan` 字段 / `_route_counts` / `_diagnostics` / **闸门记录的投影展开值（D2）**。**SHALL NOT** 在报告层基于 spec 重算任何闸值。

**理由**：spec 已有条款要求「所有对外报出限制值的出口都报**实际生效值**而非声明值」。如果在 dry run 报告层重算，钳制逻辑一旦演进（如新增一种 ceiling 来源），dry run 就会与其他三出口**静默分叉**——这正是「对内钳、对外报声明值」假面的同型问题。

**grill 发现原稿的测试锁是假保护（已改）**：原稿写 `report["limits"] == limits_report(spec, {})`——这是**输出值相等**，报告层若自行重算、在无 ceiling 时数值恰好相同（`min(declared, None) == declared`），测试照样绿。**改为调用级同源锁**：monkeypatch `limits_report` / `_eff_limit`（或报告实际依赖的函数）返回**哨兵值**，断言报告字段反映哨兵——证明它**确实调用了**该函数，而非巧合相等。`node_budget` 同理：断言 `expanded_nodes` 来自闸门记录的投影字段（哨兵/同对象读取），**不**用「值相等」锁。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| **`headroom` 在撞闸图上报正数（假余量）** | **已由 D2 修正**：`expanded_nodes` 取闸门记录的投影值，撞闸时为负数。测试须含「撞闸图 headroom < 0」断言（`research/node_budget_probe.py` 的 `max_nodes=5` / `=23` 两例作回归基线）。 |
| **新增字段被模型误读**（把 `declared` 当 `applied`、把 `headroom` 当动态闸余量、把 `gate_count` 与 `runs` 当矛盾） | D1/D2/D3 的口径说明句进报告 `notes`；调用级同源锁；验收 L3 专查新误读。 |
| **报告体积增大** | 新字段是**定长小对象**（不随图规模增长）；报告已有 `max_report_chars` 有界纪律。 |
| **`clamped` 恒 false 让模型以为「永远不会被钳」** | D1 说明句点明「资产加载路径可能钳」；`RunWorkflow` 的 `limits_clamped` 仍是权威。 |
| **D2 需改 `scheduler.py`（记录投影展开）** | 只**增**一个只读字段（不改判定逻辑、不改异常路径）；实现时若发现波及判定路径，SHALL 先停轮回写。已在 Impact Analysis 标注。 |
| **`diagnostics` 非空被误当「撞闸」** | D4 `notes` 说明；delta 措辞覆盖该情形。 |
| **描述默认值与运行期配置分叉** | D5 措辞限定为「模块默认值 + 以报告为准」。 |
| **描述 +140 字符挤压既有条款** | 实测余量 ~1891 字符；测试锁描述长度 < 6000。 |
| **本 change 与 #276 重叠** | 硬边界：本 change **只报值**，#276 才**改值**；#276 blocked-by 本 change。 |

## Testing Strategy

- **新增** `tests/agent/subagent/test_workflow_limit_visibility.py`：
  - `limits` 三段式存在；dry run 路径断言 `applied == declared`、`clamped is False`；**钳制场景**（走资产加载出口或直接构造带 ceiling 的 scheduler）断言 `applied != declared`、`clamped is True`。
  - **`node_budget`（按 D2 改后口径）**：
    - 宽扇入图（20 项 foreach）：`expanded_nodes == len(plan.nodes) + 20`、`graph_nodes == len(plan.nodes)`、`auto_inserted == len(plan.inserted_nodes)`、`headroom == limit - expanded_nodes`；
    - **撞闸图（`max_nodes` 配成 5 与 23）**：`expanded_nodes` 仍为 24、**`headroom < 0`**（回归 `research/node_budget_probe.py` 的两个撞闸例）；
    - 窄扇入图（2 项）：`expanded_nodes == len(plan.nodes) + 2`（**不等于** `graph_nodes`，除非无 foreach）。
  - route 条目含 `max_routes` 与 `gate_count`；断言 `gate_count == scheduler._route_counts[node]`（同源锁），并断言**撞过一次的 route** `gate_count > 0` 而 `runs == 0`（锁住 R3 的事实）。
  - **`diagnostics`**：撞闸图 `diagnostics["reason"] == "max_nodes"`；**未撞闸**图 `diagnostics == {}`（**无条件挂载**，镜像 `parent_envelope`）。
  - **调用级同源锁（非值相等）**：monkeypatch `limits_report` 返回哨兵 → 断言报告反映哨兵；`node_budget.expanded_nodes` 断言取自闸门投影字段。
- **扩展** `tests/agent/subagent/test_workflow_tool_discoverability.py`：`DeclareWorkflow` 描述含三闸**名 + 数值**（宽松匹配，不绑定运行时配置）；描述长度 < 6000。
- **新增（scheduler 侧）**：若采用 D2 的「闸门记录投影展开」取向，加一条 scheduler 测试——撞闸图上 `_projected_expanded_nodes`（暂名）等于 `len(plan.nodes) + Σ items`，且**判定逻辑未变**（既有的 `max_nodes` 拒绝行为逐字不变）。
- **回归** `tests/agent/subagent/test_workflow_dry_run.py`：新增字段是**增**，既有断言不失效。
- **全量** `uv run pytest -q`。

## Pre-Implementation Review

**grill 阶段填写**：`reviews/grill-design.md`（独立零记忆 subagent 逐轮追问产出的决策记录 + `## User Confirmation` 用户答复）。

## Impact Analysis（design 视角的补充）

见 `proposal.md` 的 `## Impact Analysis`。design 视角的补充（**含 grill 后订正**）：

1. **`scheduler.py`：原计划零改动，grill 后订正为「一处只增不改」**。本 change 其余部分只读既有私有状态（`_plan`/`_states`/`_route_counts`/`_diagnostics`/`_eff_limit`）。但 **D2 的 `expanded_nodes` 口径**（撞闸图上既有 `_expanded_nodes` 不含被拒展开）要求闸门在 `_check_foreach_budget` 里**记录投影展开值**（在超限判定前记入一个新字段）——这是**新增一个只读字段**，**不改任何判定逻辑、不改异常路径、不改既有字段语义**。若实现中发现该记录会波及判定路径（如影响 `_charged_expansions`），SHALL 先停轮回写（与 #273 的「不改调度器」不变量同精神）。
2. **`limits_report()` 的 `ceiling` 参数**：dry run 传 `{}`（无钳制）。若将来要让 dry run 反映某个 ceiling，须先回写本 design（属新增能力面）。

## Pre-Implementation Review（grill 结果）

独立零记忆 grill subagent（run `grill-workflow-limit-visibility/round-1`，2026-10-01）逐条挑战 design，产出 `reviews/grill-design.md`。**4 处事实性错误被实测推翻并已改 design**：

- **D2**：原稿 `expanded = len(plan.nodes)` **完全不计 foreach 展开项**（闸门按「每项一个节点」计）。且 grill 推荐的 `_expanded_nodes` 亦不足——本 change 的 `research/node_budget_probe.py` 实测：闸门在计费前 raise，撞闸图上 `_expanded_nodes` 也不含被拒展开，**两个既有计数都报正余量**。改法：`expanded_nodes` 取闸门记录的**投影**展开值（需一处 scheduler 只增改动）。
- **D3**：原稿称 route `state.runs` 是「求值次数」——**错**，它结构性恒 0（`_execute_route` 不调 `_apply_run_status`）。字段改名 `gate_count`，`notes` 消解与 `runs:0` 的表观矛盾。
- **D4**：原稿称 `_envelope()` **有条件**挂 diagnostics（`scheduler.py:3107`）——**错**，`3107` 是**无条件**字面量，`if self._diagnostics` 在 `status()`（`:2886`）。改取**无条件挂载**（镜像模型可见的 `parent_envelope`），并同步修 delta 的「不挂空诊断」Scenario。
- **D6**：原稿的「值相等」测试锁是**假保护**（无 ceiling 时重算恰好同值）；改为**调用级同源锁**（哨兵/同对象读取）。

**已确认可保留**：D1 三段式 + `clamped`（+notes）、D2-a 只讲 `max_nodes`、D3-a 读 `_route_counts`、D6-a 复用既有函数方向、D5-a 长度预算。

**Open Questions**：Q1–Q6 见 `reviews/grill-design.md`，**待用户逐条确认后**方可进入实现（grill-confirmation-gate）。
