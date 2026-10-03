# Grill 设计追问：foreach 预算截断可见性（change foreach-budget-truncation-visibility）

- 执行者：独立零记忆设计评审 subagent（/grill 等价流程）
- 分支：foreach-budget-truncation-visibility/2026-10-03
- 评审对象：openspec/changes/foreach-budget-truncation-visibility/ 的 design.md（D1–D6）/ proposal.md / tasks.md / delta spec
- 方法：逐行走读被改代码（行号已核）+ 实测探针（`/tmp/fbtv/probe_*.py`，真跑 `WorkflowScheduler.run` / `DryRunWorkflow` / `GetWorkflow`，并用 pytest plugin 把拟议 D3 helper 打补丁后跑整套 `tests/agent/subagent/`）
- 结论摘要：**方向成立、地基扎实**——`_resolve_items` 切片到剩余预算「刚好合身」使 `_check_foreach_budget` 不触发（安静丢弃），两出口（dry run + `GetWorkflow`）经共享 helper 扩展后确实能报出「声明 60 / 展开 24 / 省略 36 + 成因 `budget`」，静态路径值不变、零噪声成立、套装 842 测试全绿。**但有三处承重事实必须修**：(1) proposal/design 的「非 terminal 会响亮报」是**错的**——非 terminal 在切片 ≤ `max_fan_in` 时**同样静默**（实测 `fan→collect` `max_runs=10` 静默、`max_runs=11` 才响亮），静默窗口比文档说的宽；(2) 模型**直接**跑 `RunWorkflow` 拿到的结果信封 `nodes` **连 #279 的静态字段都没有**（实测 `items` 之外无任何可见性字段），本 change 若只对齐 #279 两出口，**模型最常看的那个出口仍然静默**；(3) design D3「静态路径逐字节不变」与它自己的代码（新增 `items_omitted_cause`）**自相矛盾**。另坐实 5 个设计候选 OQ 并新增 2 个。

---

## Confirmed Decisions

- **决策**: 预算截断的**机制**是「`_resolve_items` 把集合切到 `_remaining_expansion_capacity()` 恰好合身 ⇒ `_check_foreach_budget` 的 `runs+delta>limit` 刚好不触发」，不是「delta≤0 跳过」。**理由/证据**: 实测探针 `probe_core.py`（source 60 → planner 占 1 run、`max_runs=25`，`fan.items=24/items_declared=60`，`status=completed`、`diagnostics={}`、信封无 `items_omitted`）；`probe_oq3.py` instrument `_remaining_expansion_capacity` 打印各项：`max_runs used=1 lim=25 → 24`、`max_nodes expanded=2 lim=200 → 198`、`min=24`。行号：切片 `agent/subagent/scheduler.py:2677`、判定 `:2180`/`:2192`、容量 `:2726-2741`。此结论与 #279 对抗报告（`archive/2026-10-03-foreach-truncation-visibility/reviews/grill-adversarial.md:60-70`）一致，**推翻**了 #279 grill 原稿的「delta≤0」误述。

- **决策**: 拟议的 **D3 扩展（去 `max_items>0` 前置、按 `max_items` 值发 `items_omitted_cause`）在功能上正确且两出口都成立**。**理由/证据**: 用 pytest plugin（`/tmp/fbtv/patch_plugin.py`）把拟议 helper 打补丁后实测：dry-run 字面 60/`max_items=0`/`max_runs=25` → `items_declared=60 / items_expanded=25 / items_omitted=35 / items_omitted_cause=budget`；dry-run source(script 60) → `60/24/36/budget`；运行期 `GetWorkflow(detail='nodes')` 字面 → `items=25 / items_declared=60 / items_omitted=35 / cause=budget`；运行期 source → `items=24 / declared=60 / omitted=36 / cause=budget`。既有字段 `items_total`（=展开数）与 `items` 未被覆盖、共存。helper 落点 `agent/tools/builtin/subagents.py:1122`（分支 `:1153`）、后写入口 `:1159`（在 `parent_envelope()` 之后，`GetWorkflow` 路径 `:1081→:1095`）。

- **决策**: **成因判别字段名 `items_omitted_cause` 零撞名**——全仓 `agent/` 下不存在裸 `cause` 键；运行期节点 dict（`NodeState.to_dict`）与 dry-run 条目各自的键集里都只有 `reason`（终态原因），无 `cause`。**理由/证据**: `grep -rn '"cause"\|cause=' agent/` 零命中；实测 dry-run 条目键集 `['auto_inserted','id','items_declared','items_declared_simulated','items_expanded','kind','produced','produced_kind','received','runs','status']`（无 `cause`）；运行期节点键集 `['id','item_refs','item_refs_omitted','items','items_total','kind','reason','runs','status','subagent_id','summary']`（有 `reason`、无 `cause`）。故 `items_omitted_cause` 与 `reason` 同 dict 不碰撞（若取裸 `reason` 会重蹈 #279 D2 的 `items_total` 覆辙）。

- **决策**: **静态路径（`max_items>0`）的既有字段值不变**（`items_declared`/`items_omitted` 数对不上回归），但**并非「逐字节不变」**——新增 `items_omitted_cause='max_items'`。**理由/证据**: 打补丁前后对比（`probe_static_diff.py`）：`max_items=30` 时基线 dry-run 键 = `[items_declared, items_expanded, items_omitted]`，打补丁后 = 上述 + `items_omitted_cause`；`items_declared=60`、`items_omitted=30` 数值逐位不变。这印证 proposal T5「值不变」，但**证伪** design.md:72 的「逐字节不变」措辞（见风险表 R3）。

- **决策**: **零噪声成立**（T4）。`max_items=0` 且预算充足（`declared==expanded`）⇒ 不产生任何 `items_omitted`/`items_omitted_cause`。**理由/证据**: 打补丁后 `probe_d3b.py`：字面 5 项/`max_items=0`/`max_runs=25` → dry-run 条目仅 `{'items_expanded': 5}`，无 `items_declared`/`items_omitted`/`empty_collection`。逻辑上 `expanded = len(items[:cap]) = min(declared, cap)`，`max_items==0` 时 `expanded<declared` 当且仅当 `cap<declared`（即真预算截断），故不会误报。

- **决策**: **不触门禁**。本 change 只改报告面（reports-only），不改任何 gate/checker 判定逻辑。**理由/证据**: `PYTHONPATH=. .venv/bin/python scripts/check_openspec_artifacts.py` → `OpenSpec artifact checks passed`（exit 0）；`npx @fission-ai/openspec@1.4.1 validate --all --strict` → `29 passed, 0 failed`（含 `change/foreach-budget-truncation-visibility`）。打补丁后整套 `tests/agent/subagent/` → **842 passed**，零回归。

---

## Open Questions

### Q1（成因字段命名 —— 坐实推荐 `items_omitted_cause`）

**核实结论**：`items_omitted_cause` 安全（无 `cause` 键、不与 `reason` 碰撞，见 Confirmed Decision 3）。候选 `items_truncation_cause` 同样安全但**语义更窄**（它描述「截断成因」，而本 change 已有 `items_declared`/`items_omitted` 一对，`items_omitted_cause` 与之并排读更自洽）。

**推荐答案**：`items_omitted_cause`，取值 `"max_items"` / `"budget"`。**具体例子**（本 change 真实参数）：`{"id":"fan","kind":"foreach","source":"planner","max_items":0}`，planner 产出 60 项、`max_runs=25`：
- 运行期 `GetWorkflow(detail='nodes')` 的 fan 节点 → `{"items":24, "items_total":24, "items_declared":60, "items_omitted":36, "items_omitted_cause":"budget", "reason":null, ...}`。`reason` 仍是节点终态原因（此处 `null`），`items_omitted_cause` 独立表达「谁把 60 砍成 24」。

若改叫 `items_truncation_cause` 亦无硬伤，仅命名口味；**不要**叫 `reason`、`items_reason`（后者与节点 dict 的 `reason` 近形，易误读）。

### Q2（出口范围 —— **必须升级为显式 OQ，倾向扩范围或至少显式声明缺口**）

**核实结论（实测证伪「对齐 #279 两出口就够」）**：`RunWorkflow` 的结果信封 `nodes` 是 `parent_envelope()` → `_bounded_node()` 白名单（`scheduler.py:389` 仅 `id/kind/status/runs/subagent_id/items`）过滤的，**连 #279 的静态字段（`items_declared`/`items_omitted`/`empty_collection`）都没有**。`_drive_scheduler`（`subagents.py:934`）返回的就是 `parent_envelope()`，`RunWorkflowTool.execute`（`:1402`）原样回它——**后写只发生在 `GetWorkflow(detail='nodes')` 分支（`subagents.py:1095`），不在 RunWorkflow 路径**。实测（`probe_core.py` / `probe_d3b.py`）：`RunWorkflow` 信封 fan 节点键 = `['id','items','kind','reason','runs','status','subagent_id','summary']`，静态 `max_items=20` 场景也只有 `{'items':20}`，无任何截断字段。

**这是本 change 最值得用户拍板的一点**：模型跑一张图，**最自然的读法就是直接读 `RunWorkflow` 的返回信封**；本 change 若只对齐 #279 两出口，则「60 声明 / 24 展开 / 36 省略」**在模型最常看的出口仍然全静默**——模型必须**额外**调 `GetWorkflow(detail='nodes')` 才看得到。

**推荐答案（两选一，需用户定）**：
- **(a) 对齐 #279，两出口（dry run + GetWorkflow），并把「RunWorkflow 信封缺可见性字段」作为 #279 遗留缺口显式记录 + 另开 follow-up**。代价小、爆炸半径小；缺点是 #286 的主诉场景（模型跑图后看返回）未被根除。
- **(b) 本 change 顺带把 `_attach_foreach_visibility` 也挂到 `_drive_scheduler`/`RunWorkflow` 的信封路径**（同一后写位置，`RunWorkflow` 与 `GetWorkflow` 都调 `parent_envelope()`）。代价：多一个出口分支 + 一条测试；**且这会同时补上 #279 的静态字段**（把 #279 的缺口一并关掉，scope 扩大但更彻底）。

**具体例子**：`{"id":"fan","kind":"foreach","source":"planner","source_field":"items","max_items":0}` + planner 60 项 + `max_runs=25`。
- 选 (a)：`RunWorkflow` 返回 `nodes:[{id:"fan", items:24, runs:24, status:"completed"}]` —— **模型看到「24」，以为就 24 个**；须再调 `GetWorkflow` 才知道共 60 省 36。
- 选 (b)：`RunWorkflow` 返回同一节点即带 `items_declared:60 / items_omitted:36 / items_omitted_cause:"budget"`，一步到位。

**建议**：(b) 更贴合「消灭静默、模型看不见」的立项动机；若判 (b) 超 #286 边界，则 (a) 必须**在 proposal 的 Non-Goals 里显式写明**「RunWorkflow 结果信封不报，含 #279 静态字段同为遗留」。

### Q3（成因粒度 —— 坐实「粗粒度 `"budget"` 够用」，细化可选）

**核实结论**：`_remaining_expansion_capacity`（`scheduler.py:2726-2741`）取 `min(C4 max_total_runs 剩余, C2 max_runs 剩余, C2 max_nodes 剩余)`。**实测哪个维度绑定**（`probe_oq3.py`/`probe_oq3b.py`）：
- source 60 / `max_runs=25`（planner 占 1）→ 绑定 **`max_runs`**（cap=24）。
- source 60 / `max_nodes=25` → 绑定 **`max_nodes`**（cap=23）。
- source 60 / 配置 `subagents.workflow.budget.max_total_runs=12`、spec `max_runs=200`/`max_nodes=400` → 绑定 **`max_total_runs`**（cap=12）。

即绑定维度是**运行期 min 的结果**，随配置/图而变，**当前未在任何字段回传**。

**推荐答案**：**v1 用粗粒度 `"budget"`**。理由：三个维度的剩余值**已在同一信封的 `budget.dimensions.{runs,...}`（`_budget_summary`）与 `limits`（`_limits_report`）里可见**，模型已能自行判断「调 `max_runs` 还是 `max_total_runs`」；细化到 `"budget:max_runs"` 需在切片点 `_resolve_items` 回传「绑定维度」（proposal 的 Non-Goal 边界里允许「如需暴露成因/生效上限再加只读字段」，但那是**新增 `NodeState` 字段 + 一个新的 argmin 计算**，扩大测试面）。若用户要更可行动，可选细化，但**非本 change 必需**。

**具体例子**：source 60 / `max_runs=25` → 建议 `items_omitted_cause:"budget"`；细化版为 `"budget:max_runs"`。两者都能让模型知道「被预算砍了」；后者多告诉它「砍你的是 `max_runs`」。

### Q4（非 terminal 响亮路径 —— **design/proposal 的边界描述被实测证伪，必须改**）

**核实结论**：proposal.md:50 与 design.md 称「**非 terminal**（如 `fan → collect` root）切片后剩余预算不够下游 auto-agg 节点 ⇒ **响亮报** `graph_recursion_exceeded` + `diagnostics` + `blocked`，**不静默**」。**实测证伪其普遍性**（`probe_window2.py`/`probe_window3.py`，`fan→collect`，`max_fan_in=10`，60 项，`max_items=0`）：
- `max_runs=8/9/10` → `status=completed`、`diagnostics={}`、`fan.items=8/9/10`（<60）→ **静默**。
- `max_runs=11+` → `status=graph_recursion_exceeded`、`diag.reason=max_runs` → 响亮。
- `max_nodes=8..12` → 静默；`max_nodes=13+` → 响亮。

**机制**：切片 `≤ max_fan_in`（10）时**不插入 auto-agg 层**（`_expand_plan`，`scheduler.py:2090`；层插入逻辑 `aggregation.py:242`+`plan_layer_insertions`），下游 `collect` 聚合**不跑模型**（0 run）⇒ 图在预算内**安静完成**；切片 `> max_fan_in` 才插 llm auto-agg 层（`aggregation.py:389` strategy=`llm`）⇒ 该层要吃一个 run ⇒ 撞 `max_runs` 响亮。故**响亮与否取决于「切片后是否还够下游（含 auto-agg 层）发完」**，「terminal vs 非 terminal」只是其中一种特例。

**推荐答案**：**仍然无条件发 `items_omitted` + 成因**（`state.items_declared`/`state.items` 在响亮路径上也已就绪，读取 O(1)），**不抑制**。且 **proposal/design 的边界文字必须改成**：「静默窗口 = 切片后预算仍够图跑完（terminal，或非 terminal 但下游不新增吃预算的节点）；非 terminal 仅在插入 auto-agg 层并撞闸后才响亮」，别把会响亮的形态也算进静默、也别声称非 terminal 一律响亮。

**具体例子**：`fan → collect`、60 项、`max_runs=10`、`max_fan_in=10` → 实测**全静默**（`fan.items=10`、`status=completed`、`diag={}`），与 terminal 完全相同；而 `max_runs=11` 才响亮。这正是 design 边界写错的反例。

### Q5（dry-run 可行性 —— **坐实「可行，但 T1 必须带 `script`」**）

**核实结论**：dry-run **结构性**能撞预算截断（复用同一 `_resolve_items` 预算切片路径）。
- **字面 `items`**：dry-run 完全确定——60 字面 / `max_items=0` / `max_runs=25` → dry-run 条目 `items_expanded=25 / items_declared=60 / items_omitted=35 / cause=budget`（实测）。**无假 LLM 依赖。**
- **source 驱动**：dry-run 需 `script` 注入 JSON（`_DryRunLLM._output_for`，`subagents.py:1481`；`DryRunWorkflowTool.execute(script=...)`，`:2107`）。**不带 script 时 source 驱动的 dry-run 兄弟节点只回显任务文本、`extract_collection` 取 `source_field` 落空 ⇒ `declared=0`**（`{"items_expanded":0,"items_declared":0,"items_declared_simulated":True}`，实测），**撞不到截断**。带 `script={"planner":[ '{"items":[...60...]}' ]}` 才得 `60/24/36/budget`。

**推荐答案**：dry-run 出口**保留**（不是「只剩运行期出口」）。但 **T1 的构造必须显式带 `script`**——design 的 T1 措辞「`max_items=0` + source 60 项」若不写 script，dry-run 会得 declared=0、测试拿不到 60/24/36。**更稳的 T1 用字面 60 项**（确定性最强，无需假 LLM 脚本），或 source 版**显式喂 script**。

**具体例子**：T1 断言 dry-run 条目 `items_declared==60 and items_expanded==24 and items_omitted==36 and items_omitted_cause=="budget"`——只有 `script={"planner":[60 项 JSON]}` 的 source 规格才同时满足 24 与 36（planner 占 1 run）；字面 60 规格给的是 25/35（无 planner）。**测试必须与选定的 spec 形态对齐**，否则断言数值对不上。

### Q6（新增 —— `declared_is_simulated` 与新 `declared > expanded` 分支的交互）

**核实结论**：拟议 D3 代码里，`declared_is_simulated=True` 与新增 `declared > expanded` 分支**不互斥**，可同时触发。**实测**：source 驱动 dry-run + script（60）→ 条目同时含 `items_declared=60`、`items_declared_simulated=True`、`items_omitted=36`、`items_omitted_cause="budget"`。语义上自洽（declared 是模拟值、标记已给，omitted 由模拟 declared 推出、模型可据 `_simulated` 打折理解）。**无假报**：不带 script 时 `declared=0` 走 `declared==0` 分支（非 simulated 才标 `empty_collection`），不发 `items_omitted`。

**推荐答案**：接受现状（无需特判），但**在测试里显式锁**「source+script 时 `items_omitted` 与 `items_declared_simulated` 共存、且 `empty_collection` 不出现」。**具体例子**：`{"items_declared":60,"items_declared_simulated":true,"items_omitted":36,"items_omitted_cause":"budget"}`——不得额外出现 `empty_collection`。

### Q7（新增 —— `items_omitted` 语义在预算路径的取值确认）

**核实结论**：`items_omitted = declared - expanded`，其中 `expanded = state.items`（切片后长度）。`max_items==0` 时 `expanded = len(items[:cap]) = min(declared, cap)`，故 `declared>expanded` 当且仅当 `cap<declared`（真预算截断），语义正确。**边界**：`max_runs=1`（planner 占满）→ `expanded=0 / declared=60` → `items_omitted=60 / cause=budget`（实测 `probe_cap0.py`），**不是** `empty_collection`（`declared!=0`）——两信号正确分离，无碰撞。

**推荐答案**：`items_omitted = declared - expanded` 无需 clamp（预算路径下 `declared>=expanded` 恒成立）；可加 `max(...,0)` 防御但非必需。

---

## 风险

| # | 风险 | 定级 | 缓解 |
|---|---|---|---|
| **R1** | **两出口不覆盖模型最常看的 `RunWorkflow` 结果信封**（Q2）：模型跑完图直接读返回信封，`nodes` 里无任何截断信号 → 本 change 上线后该出口仍静默 | **高** | 用户拍板 Q2：选 (b) 扩到 `_drive_scheduler`/`RunWorkflow` 信封；或选 (a) 并在 proposal Non-Goals **显式写明**该缺口（含 #279 静态字段同缺） |
| **R2** | **「非 terminal 会响亮报」边界描述错误**（Q4，`proposal.md:50`/design）：非 terminal 切片 ≤ `max_fan_in` 时**同样静默**（实测） | **中-高** | 改文字为「切片后预算仍够图跑完即静默」；字段无条件发（不依赖响亮路径） |
| **R3** | **design D3:72 声称静态路径「逐字节不变」，但代码新增 `items_omitted_cause` 使其字节变化**（自相矛盾） | **中** | 措辞改为「既有字段（`items_declared`/`items_omitted`）值不变 + 新增 `items_omitted_cause`」；T5 按「值不变 + 新增键」锁，不锁「逐字节」 |
| **R4** | **T1 若按 design 字面「source 60 项」构造但 dry-run 不带 `script`，得 declared=0、断言拿不到 60/24/36**（Q5） | **中** | T1 改用确定性的字面 60 项，或 source 版显式 `script`；测试数值与 spec 形态对齐 |
| **R5** | **`items_omitted` ↔ 既有 `item_refs_omitted` 近形** 同节点同现 | **低** | 名称已由 #279 对抗裁决为可接受（命名+测试缓解）；本 change 沿用，不新增辨析负担 |
| **R6** | **细化成因粒度需新增 `NodeState` 只读字段 + argmin**（Q3） | **低** | v1 用粗粒度 `"budget"`；细化是可选增强（proposal Non-Goal 边界内允许） |
| **R7** | **去 `max_items>0` 前置后误改静态输出** | **低** | 已实测（`probe_static_diff.py`）：`max_items>0` 的 `items_declared`/`items_omitted` 值逐位不变；整套 842 测试绿 |

---

## 走读索引

| 事实 | 文件:行号 |
|---|---|
| `_resolve_items` 定义（记 `items_declared` 于切片前） | `agent/subagent/scheduler.py:2654` / `:2675` |
| `max_items==0` 预算切片 `items[:remaining_capacity]` | `agent/subagent/scheduler.py:2677` |
| `max_items>0` 静态切片 `items[:node.max_items]` | `agent/subagent/scheduler.py:2678` |
| `_remaining_expansion_capacity`（min of max_total_runs/max_runs/max_nodes） | `agent/subagent/scheduler.py:2726-2741` |
| `_check_foreach_budget`（切片后不 raise） | `agent/subagent/scheduler.py:2167`（raise `:2193`/`:2205`） |
| `NodeState.items_declared` | `agent/subagent/scheduler.py:254` |
| `_expand_plan`（auto-agg 层插入 / max_nodes 复检，响亮路径） | `agent/subagent/scheduler.py:2090`（raise `:2133`） |
| `_PARENT_NODE_FIELDS` 白名单 / `_bounded_node` | `agent/subagent/scheduler.py:389` / `:394` |
| `parent_envelope()`（bounded，丢弃白名单外字段） | `agent/subagent/scheduler.py:3151` |
| `_foreach_visibility_fields`（共享纯函数，分支 `:1153`） | `agent/tools/builtin/subagents.py:1122` |
| `_attach_foreach_visibility`（后写，绕白名单） | `agent/tools/builtin/subagents.py:1159` |
| `_attach_item_refs`（既有 `items_total`/`item_refs_omitted` 写入点） | `agent/tools/builtin/subagents.py:1183` |
| dry-run foreach 条目 `items_expanded` + `entry.update(...)` | `agent/tools/builtin/subagents.py:1688` / `:1693` |
| `GetWorkflow` `detail=nodes` 后写（`parent_envelope` → `_attach_*`） | `agent/tools/builtin/subagents.py:1081` / `:1095` |
| `_drive_scheduler`（RunWorkflow 返回 parent_envelope，**无后写**） | `agent/tools/builtin/subagents.py:934` |
| `_foreach_truncation_warnings`（声明期，`max_items>0` 且字面 items） | `agent/tools/builtin/subagents.py:727` |
| dry-run 假 LLM / `script` 注入 | `agent/tools/builtin/subagents.py:1481` / `:1549` / `:2107` |
| auto-agg 插层（`MAX_FAN_IN`=10，strategy=`llm`） | `agent/subagent/aggregation.py:37` / `:242` / `:389` |
| 运行期预算账本（四维度 `max_total_runs` 等） | `agent/subagent/workflow_budget.py`；config `agent/config.py:335` |
| spec 钉死 `max_items=0` 语义 / 静态截断可见性 | `openspec/specs/multi-agent-collaboration/spec.md:315` / `:324` / `:333` / `:343` / `:345` |
| 上游 #279 对抗报告的机制修正（「切片合身」非「delta≤0」） | `openspec/changes/archive/2026-10-03-foreach-truncation-visibility/reviews/grill-adversarial.md:60-70` |

探针脚本（`/tmp/fbtv/`，实现期可复跑）：`probe_core.py`（两出口基线）、`probe_d3b.py`（拟议 D3 全 T1–T5）、`probe_dry_script.py`（source+script dry-run）、`probe_window2.py`/`probe_window3.py`（静默窗口矩阵）、`probe_oq3.py`/`probe_oq3b.py`（绑定维度）、`probe_static_diff.py`（静态路径前后对比）、`patch_plugin.py`（拟议 helper 的 pytest 补丁，跑出 842 passed）。

行号基于本 worktree 当前 HEAD；实现期若改动上游文件，行号可能漂移，以符号名为准。
