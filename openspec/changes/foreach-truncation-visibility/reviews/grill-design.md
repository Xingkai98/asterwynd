# Grill 设计追问：foreach 截断可见性（issue #279）

- 执行者：独立零记忆设计评审 subagent（`/grill` 等价流程）
- 分支：`foreach-truncation-visibility/2026-10-03`
- 评审对象：`openspec/changes/foreach-truncation-visibility/` 的 `design.md`（D1–D5）/ `proposal.md` / `tasks.md` / delta spec
- 方法：逐行走读被改代码（行号已核）+ 全仓 sweep 找设计未覆盖的静默丢弃路径。所有结论带 `文件:行号`。
- 结论摘要：设计方向成立（三出口报告截断是真缺陷、真修复）；**但 D2 字段名撞名是真实且更严重的事故——它不只是「同名异义」，而是 `GetWorkflow` 同一个 dict 里同键互相覆盖，且会让「三出口一致」的主张自我矛盾**（见 Q1，必改）。另有 3 处 grill 未覆盖的静默丢弃路径（见 Q3/Q4）。

---

## Confirmed Decisions

- **决策**: 截断点与「唯一不报」判定成立。`_resolve_items` 在 `max_items>0` 时执行 `items[:node.max_items]`（`agent/subagent/scheduler.py:2669`），`max_items==0` 时走预算切片 `items[:self._remaining_expansion_capacity()]`（`:2668`）。其余三处截断（`nodes_omitted` `scheduler.py:3163`、`warnings_omitted` `subagents.py:1661`、`item_refs_omitted` `subagents.py:1132`）都显式报告，`max_items` 静态截断是唯一静默点。**理由**: 逐行核实，proposal 的对照表属实。

- **决策**: 声明期入口**确实能拿到字面 `items`**，D1/D3 的「声明期只报字面列表」在技术上可行。`DeclareWorkflow.execute` 调 `parse_spec_for_manager` 得到 `WorkflowSpec`，`_route_task_warnings(spec)`（`subagents.py:710`）已在遍历 `spec.nodes` 读 `node.kind`/`node.task`；与它并列的 `_foreach_truncation_warnings(spec)` 可同样读 `node.items`（`tuple|None`，`workflow.py:165`）与 `node.max_items`（默认 20，`workflow.py:168`）。两条入口（`DeclareWorkflow` `subagents.py:841`、`RunWorkflow(spec=)` `subagents.py:1284`）共用同一 helper 的模式已存在（`_route_task_warnings`），新 helper 并列天然覆盖两条入口。**理由**: 代码路径核实。

- **决策**: D4（与 `item_refs_omitted` 划清）成立，两者是**独立可共存的量**。`item_refs_omitted = items_total - len(item_refs)`（`subagents.py:1132`）是「展开项 ref 列表被 200 上限截断的条数」；本 change 的「被 max_items 丢弃的项数」= 声明集合 − 展开数。可构造：字面 **500 项 / `max_items:250`** ⇒ 声明 500、展开 250、静态省略 250；`item_refs` 上限 200 ⇒ `item_refs_omitted = 250-200 = 50`。**两者同时 >0**，但语义不同、互不决定。**理由**: `_attach_item_refs`（`subagents.py:1110-1132`）与 `_resolve_items`（`:2669`）计算源不同。

- **决策**: 「声明期报字面 N = dry-run 报的 N」不会打架——**同一节点不可能同时有 `items` 和 `source`**。`parse_workflow_spec` 校验 `has_items == has_source` 即拒绝（`workflow.py:540-542`，报 `needs exactly one of items/source`）。因此任务里假设的「声明期说 60、dry-run 因 source 解析出别的数」在同一节点上**结构上不可能**：字面节点 declare 与 dry-run 都取 `len(node.items)`，一致；source 节点 declare 静默。**理由**: 校验期互斥约束核实。

- **决策（实现约束，design 未写）**: 「运行期出口暴露」**不是免费的**——`GetWorkflow` 的节点经 `parent_envelope()`（`scheduler.py:3142`）→ `_bounded_node()`（`:389`），后者只保留白名单 `_PARENT_NODE_FIELDS = ("id","kind","status","runs","subagent_id","items")`（`scheduler.py:384`）。**任何新字段除非加进该白名单、或像 `_attach_item_refs` 那样在 bounded 之后补写，否则会被静默丢弃**。注意 `items`（=展开数 M）**已经在**该白名单里（`:2943`/`_bounded_node`），所以运行期 foreach 节点上其实已有一个 `items:20`——design 的 T4 必须决定新字段与这个既有 `items` 的关系。**理由**: `_bounded_node`/`_PARENT_NODE_FIELDS` 逐行核实。tasks 3.4 需据此细化。

- **决策**: 措辞**不得声称 `max_items=20` 是「默认值」**。`WorkflowNode.max_items: int = 20`（`workflow.py:168`）是 dataclass 默认，解析后**无法区分**模型显式写 `max_items: 20` 还是省略。D5 的示例句 `max_items={M} defaults to 20` 应改为中性表述（如 `max_items={M}`），否则可能在模型显式声明 20 时给出错误归因。**理由**: `_parse_max_items(data.get("max_items", 20) ...)`（`workflow.py:529`）不保留「是否显式」信息。

---

## Open Questions

> 说明：每条含推荐答案 + 用本 change 真实场景构造的具体例子。**均需用户拍板**，主 session 转达。

### Q1（D2 字段名撞名 —— **必攻项，必改**）「声明集合大小」该用什么字段名？

**核实结论：撞名真实存在，且比 design 描述的更严重——是同一 dict 内的同键覆盖，不是「两处不同出口的异义」。**

事实链：
1. 现有 `items_total` 由 `_attach_item_refs` 写在 `GetWorkflow(detail='nodes')` 的 foreach 节点投影上：`projection["items_total"] = len(state.item_runs)`（`subagents.py:1131`），其值 = **本节点已展开的项数（截断后）**，因为 `state.item_runs` 在 `_execute_foreach` 里被初始化为解析后（已截断）列表的长度（`scheduler.py:1921` `state.items = len(items)`、`:1929` `state.item_runs = [_ItemRunSlot() for _ in items]`）。
2. 该值被 spec **钉死**：`openspec/specs/multi-agent-collaboration/spec.md:858` 定义 `items_total = len(state.item_runs)`，且 `item_refs_omitted = items_total - len(item_refs)` 依赖它；`tests/agent/subagent/test_foreach_item_refs.py:121` 对其有硬断言。
3. design 的 D1 表格把**运行期出口定在同一个 `GetWorkflow` foreach 节点**上；而 design D2 提议把 `items_total` 定义为「本轮应展开的集合大小（截断前）」。
4. **冲突点**：design 的新 `items_total` 与既有 `items_total` 会写进**同一 dict、同一个键、不同值**。模型声明 60 项、`max_items` 默认 20 时：既有字段想写 `20`，design 想写 `60`——**后写者覆盖先写者**，且无任何报错。这不是「两处同名」的观感问题，是数据被静默吞掉。

**推荐答案：本 change 任何出口都 SHALL NOT 复用 `items_total` 这个词。**采用**独立命名**，三出口统一用同一个新名。推荐形态二选一（命名最终由用户裁定）：

- **首选（零撞名、零近似）**：一个**命名空间对象**，如
  `items_truncation: {"declared": 60, "expanded": 20, "omitted": 40, "limit": 20, "reason": "max_items"}`
  —— 新键在独立子 dict 内，与 `items_total`/`item_refs_omitted` 结构上不可能相撞；且天然承载 D3/Q3 需要的 `reason`（`max_items` vs `budget`）判别子。
- **次选（沿用扁平先例）**：`items_declared`（声明集合大小）+ `items_omitted`（被 max_items 丢弃数）。**必须避免 `items_total`**。

**为什么不采用「统一语义」这一选项**：把既有 `items_total` 改成「声明集合」会改 spec:858 + `test_foreach_item_refs.py` 的钉死断言，且 `item_refs_omitted` 的定义式随之失效——爆炸半径远大于本 change，且会让「ref 列表界」这个既有语义漂移。**不推荐**。

**残留风险（次选方案才有）**：扁平网格下 `items_omitted` 与既有 `item_refs_omitted` 只差 `s` / `_refs`，且**会同时出现在同一个 foreach 节点 dict 上**——正是本 change 要消灭的「读混两类省略」的隐患。若担心这点，选首选的对象形态。

**具体例子（60/20/40）**：模型声明 `{"id":"fan","kind":"foreach","items":[60 项字面],"task":"{item}"}`，不写 `max_items`。
- 若按 design D2 现状：`GetWorkflow(detail='nodes')` 的 `fan` 节点上，`items_total` 到底是 20 还是 60，取决于 `_attach_item_refs` 与本 change 新投影谁后写——**不可预测**。
- 按推荐首选：节点上出现 `items_truncation.declared=60 / expanded=20 / omitted=40`，且既有 `items_total=20`（=展开数，语义不变）、`item_refs_omitted=0`（20≤200）原样保留，三者各自自洽、互不覆盖。

---

### Q2（D1/D3 残留）声明期对 `source` 驱动且 `max_items>0` 的 foreach，完全静默还是给「弱提示」？

design D1 的 `> 待 grill 确认` 项，推荐「完全静默」。**我倾向推翻这个推荐，给一条不含量值的可行动弱提示。**

**理由**：(a) 本 change 的整条立项动机是「消灭静默、模型看不见」（proposal Why 节），而 source 驱动 + `max_items>0` 恰恰是**截断风险最高**的组合——集合可能远超 20，模型却拿到空 `warnings`，与「没截断」在返回体上**无从区分**；(b) 弱提示**不违反 delta spec**——delta 的 `source 驱动在声明期不猜` 场景只禁止「报告其展开数或截断数（**数值**）」（delta spec:39-40、design D3）；一句「此节点由 source 驱动，运行时可能被 max_items=N 截断，dry-run 可预演」**不含任何数值**，不构成「猜测」；(c) 与既有 `_route_task_warnings`（`:710`）「无条件对可疑声明报警」的先例一致。

**具体例子**：`{"id":"fan","kind":"foreach","source":"planner","source_field":"tasks","max_items":20}`，`planner` 产出 60 行。
- 现状（完全静默）：`DeclareWorkflow` 返回 `warnings: []`。模型以为 planner 的产出会被完整消费。
- 弱提示：`warnings: ["node 'fan' is source-driven (source='planner'); max_items=20 may truncate the runtime collection — run DryRunWorkflow to see the resolved count."]`。模型据此可在零成本下预演，或主动改 `max_items: 0`。

---

### Q3（新发现）`max_items=0` 的**预算截断**（`_remaining_expansion_capacity`）要不要一并报告？

design D3 明说「不报静态截断（预算截断是另一层，本 change 不报）」。**这个切法可接受，但必须显式写成 Non-Goal，并开一个 follow-up issue——因为它与本 change 属同一缺陷类，且当前完全静默。**

**核实**：`max_items==0` 时 `_resolve_items` 返回 `items[:self._remaining_expansion_capacity()]`（`scheduler.py:2668`；capacity 见 `:2717-2732`）。切片后 `state.items` 已是缩小值，于是随后的 `_check_foreach_budget`（`:2162`）算 `delta = count - charged ≤ 0`，**不会 raise**——即超预算的项被静默丢弃，**没有任何 GraphRecursionError、也没有 omitted 报告**。

**具体例子**：`{"id":"fan","kind":"foreach","source":"planner","max_items":0}`，planner 产出 60 行；图级 `max_runs=25`（已用 0）。`_remaining_expansion_capacity()` = min(25, …) = 25 ⇒ `_resolve_items` 返回 25 项，**35 项静默丢弃**；dry-run `items_expanded:25`、无 omitted，运行期无任何信号。这正是 issue #279 描述的同型缺陷，只是闸门换成预算而非 `max_items`。

**推荐答案**：本 change **保持 Non-Goal 边界（只修 `max_items` 静态截断）**，但：
1. 在 `proposal.md` 的 Non-Goals 里**显式**写「`max_items=0` 路径下的预算截断静默，不在本 change 范围」，避免日后被读成「已全面消灭 foreach 静默丢弃」；
2. 开一个 follow-up issue（可挂在 #279 下），并在 delta spec / 本 change 的 Impact 里引用其号。
若用户希望**一次做干净**：因本 change 已在建报告面，把预算截断用同一报告结构 + `reason:"budget"` 判别子承载，边际成本很小——但这会扩大验收面，需用户明示。

---

### Q4（新发现）`source` 解析为空 / 集合为空时，foreach 展开 **0 项且完全静默**——要不要报告？

**这是 grill 未触及、全仓 sweep 找到的第 3 条静默路径。**

**核实**：`extract_collection` 在值为 `None` 时直接 `return []`（`scheduler.py:353`）；`_source_collection` 在 source 节点无 state / 多入边歧义时返回 `None`（`:2696-2715`）。于是 `_resolve_items` 得 `items=[]`，`_execute_foreach` 以 0 项运行（`state.items=0`、`item_runs=[]`），**无 warning、无 error**；dry-run 只显示 `items_expanded:0`。

**具体例子**：`{"id":"fan","kind":"foreach","source":"planner","source_field":"tasks"}`，而 planner 的 `result` 槽为空（模型没按预期输出 JSON/行），或 planner 被 `blocked` 从未产出。⇒ `fan` 展开 0 个 worker，aggregate 拿到空输入，**模型看不到任何「为什么没跑」的信号**——与 #279「模型以为跑了 60 个」同型的「以为跑了 N 个、实际 0 个」。

**推荐答案**：**报告**。至少 dry-run 条目与运行期投影应能区分「集合为空（source 未产出/解析为空）」与「正常展开 0 项」；声明期对字面 `items: []` 亦应可警示（若允许空列表）。这条比 Q3 更贴近本 change 的「可见性」主题，建议**纳入范围或与用户确认边界**。若判定超出 #279，同样须写 Non-Goal + follow-up issue。

---

### Q5（D1 一致性补充）dry-run 对 `source` 驱动报出的 `declared` 数，是**模拟值**，不得被读成「真实运行会展开这么多」——design 需显式声明该信任边界。

**核实**：dry-run 复用调度路径 + 假 LLM（`_DryRunLLM`，`subagents.py:1377`），`source` 节点在 dry-run 里产出的是**回显/注入文本**，`extract_collection` 对这段文本切行得到的 N 是**模拟产物**，与真实 provider 输出无关。design D1 只说「dry run 会解析集合（含 source 驱动）」，未标注该数对 source 驱动**不具预测性**（对字面 `items` 则精确）。

**具体例子**：`source="planner"` 的 foreach，dry-run 里 planner 回显任务文本 `"调研 X"`（1 行）⇒ `declared=1`；真实运行 planner 产出 60 行 ⇒ 实际 declared=60。若模型据 dry-run 的 `declared=1` 判断「不会截断」，就被误导。

**推荐答案**：dry-run 条目的 `declared`（或对象内的 `declared`）**对 source 驱动须带模拟标记**（dry-run 已有「模拟结果」的既有纪律，spec「模拟结果 SHALL 声明其可信边界」）。字面 `items` 的 `declared` 精确、可不标；source 驱动的须可区分。**具体形态实现期定**，但设计须写明这条边界，否则与既有「模拟不预测真实输出」的 spec 承诺打架。

---

## 风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| **D2 `items_total` 同 dict 同键覆盖**（Q1）：运行期 `GetWorkflow` foreach 节点上，既有 `items_total`(展开数) 与本 change 新 `items_total`(声明数) 后写者覆盖先写者，静默吞值 | **高** | 本 change 全面弃用 `items_total`，改独立名（推荐命名空间对象 `items_truncation{...}`）；测试锁「既有 `items_total`/`item_refs_omitted` 语义不变 + 新字段独立共存」 |
| **运行期字段被 `_bounded_node` 静默丢弃**（Confirmed Decision）：新字段未进 `_PARENT_NODE_FIELDS`（`scheduler.py:384`）就永不出现 | 中 | tasks 3.4 明确：或加白名单、或像 `_attach_item_refs` 在 bounded 后补写；测试断言 `GetWorkflow(detail='nodes')` 真能看到该字段 |
| **`max_items=0` 预算截断静默**（Q3）：`_check_foreach_budget` 因先切片而不 raise，超预算项无声丢弃 | 中 | 显式 Non-Goal + follow-up issue；或纳入范围用 `reason:"budget"` 判别子 |
| **空集合/解析为空静默跑 0 项**（Q4）：「以为跑了 N、实际 0」 | 中 | 报告「集合为空」状态，与「展开 0 项」区分 |
| **`items_omitted` ↔ `item_refs_omitted` 近形混淆**（Q1 次选方案的残留）：同节点同现、只差 `s`/`_refs` | 中 | 采用命名空间对象（首选方案）规避；否则测试显式覆盖两者不同 |
| **source 驱动弱提示的噪声**（Q2）：若采纳弱提示，`max_items=0` 的 source 节点不该再提示（无静态截断风险） | 低 | 弱提示仅限 `max_items>0`；`max_items=0` 时三出口都不报静态截断（与 D3/T6 一致） |
| **声明期措辞误称「默认值」**（Confirmed Decision）：显式 `max_items:20` 被说成默认 | 低 | 措辞改中性（`max_items={M}`），不给「默认」归因 |
| **声明期警告对「不会运行」的节点**：节点可能 `blocked`/`skipped` 却仍报截断 | 低 | 与既有 `_route_task_warnings` 同口径（声明期只看声明），可接受；无需处理 |

---

## 附：走读证据索引

| 事实 | 文件:行号 |
|---|---|
| 静态截断点 `items[:node.max_items]` | `agent/subagent/scheduler.py:2669` |
| `max_items==0` 预算切片 `items[:remaining_capacity]` | `agent/subagent/scheduler.py:2668` |
| `_resolve_items` 定义 | `agent/subagent/scheduler.py:2649` |
| `_remaining_expansion_capacity`（min of max_runs/max_nodes/max_total_runs） | `agent/subagent/scheduler.py:2717-2732` |
| `state.items = len(items)`（截断后） | `agent/subagent/scheduler.py:1921` |
| `state.item_runs = [slot for items]`（截断后长度） | `agent/subagent/scheduler.py:1929` |
| `_check_foreach_budget`（切片后不 raise） | `agent/subagent/scheduler.py:2162-2213` |
| 既有 `items_total = len(state.item_runs)`（展开数）写入点 | `agent/tools/builtin/subagents.py:1131` |
| 既有 `item_refs_omitted` 写入点 | `agent/tools/builtin/subagents.py:1132` |
| `_attach_item_refs` 作用于 `GetWorkflow(detail='nodes')` 的 nodes | `agent/tools/builtin/subagents.py:1058` / `:1083` |
| spec 钉死 `items_total = len(state.item_runs)` | `openspec/specs/multi-agent-collaboration/spec.md:858` |
| 测试硬断言既有 `items_total` 语义 | `tests/agent/subagent/test_foreach_item_refs.py:121` |
| `_route_task_warnings`（声明期 helper，两条入口共用） | `agent/tools/builtin/subagents.py:710-724` |
| `DeclareWorkflow` warnings 出口 | `agent/tools/builtin/subagents.py:841` |
| `RunWorkflow(spec=)` warnings 出口（template 路径固定空） | `agent/tools/builtin/subagents.py:1284` / `:1299` |
| dry-run foreach 条目 `items_expanded = state.items` | `agent/tools/builtin/subagents.py:1584` |
| dry-run 假 LLM | `agent/tools/builtin/subagents.py:1377` |
| `WorkflowNode.items` / `max_items`（默认 20） | `agent/subagent/workflow.py:165` / `:168` |
| `items`/`source` 互斥校验（exactly one） | `agent/subagent/workflow.py:540-542` |
| `max_items` 默认值不保留「是否显式」 | `agent/subagent/workflow.py:529` |
| `extract_collection` 空值 → `[]` | `agent/subagent/scheduler.py:353` |
| `_source_collection` 无 state/歧义 → `None` | `agent/subagent/scheduler.py:2693-2715` |
| 父投影白名单 `_PARENT_NODE_FIELDS`（新字段会被丢） | `agent/subagent/scheduler.py:384` / `_bounded_node` `:389-405` |
| `parent_envelope` | `agent/subagent/scheduler.py:3142-3164` |
| 既有 `nodes_omitted` 先例（不静默截断） | `agent/subagent/scheduler.py:118` / `:3163` |
| foreach 节点投影带 `items`（=展开数） | `agent/subagent/scheduler.py:2941-2947` |
| 模板 fanout 上界复用 `max_items` 默认值 | `agent/subagent/patterns.py:270-271` / `:328-333` |
| issue #279 需求原文（「应补 `items_omitted`/`items_total`」） | GitHub `Xingkai98/asterwynd#279`（`gh api repo/issues/279`） |

行号基于本 worktree 当前 HEAD（分支 `foreach-truncation-visibility/2026-10-03`）；若实现期改动上游文件，以上行号可能漂移，以符号名为准。

---

## User Confirmation

- **Q1**: 用户答复：按对抗结论——字段名用扁平 `items_declared`/`items_omitted`，绝不复用既有 `items_total`（同 dict 同键会覆盖）；弃 grill 首选的嵌套对象。；确认时间: 2026-10-03
- **Q2**: 用户答复：按对抗结论——否决 grill 的 source 声明期弱提示，维持「声明期完全静默」；source 截断只在 dry-run/运行期报。；确认时间: 2026-10-03
- **Q3**: 用户答复：本轮 Non-Goal（不改 max_items=0 语义与预算截断报告），另立 follow-up issue #286 跟进。；确认时间: 2026-10-03
- **Q4**: 用户答复：纳入本轮——空集合/source 无产出致 foreach 静默跑 0 项，与本 change 同型，一并报告（区分「集合为空/无产出」与「正常展开」）。；确认时间: 2026-10-03
- **Q5**: 用户答复：采纳——dry-run 对 source 驱动的集合数标「模拟、不可信」（假 LLM 下常为 0）。；确认时间: 2026-10-03
- **M1（声明期 warning 界）**: 用户答复：采纳对抗修正——design 风险表原「受既有 warnings_omitted 约束」是假的；实现期补界或如实写「上界=节点数」。；确认时间: 2026-10-03
