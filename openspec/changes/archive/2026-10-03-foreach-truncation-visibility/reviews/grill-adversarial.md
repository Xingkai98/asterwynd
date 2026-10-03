# 对抗验证：foreach 截断可见性 grill 报告（issue #279）

- 执行者：独立零记忆**对抗验证** subagent（角色：证伪 `reviews/grill-design.md`，不复述、不背书）
- 分支：`foreach-truncation-visibility/2026-10-03`
- 被验证对象：`openspec/changes/foreach-truncation-visibility/reviews/grill-design.md`（6 Confirmed Decisions + Q1–Q5 + 风险表 + 走读索引）
- 方法：对每条承重结论**先跑实测证伪**（探针落 `/tmp/probe_ftv.py`、`/tmp/probe_q5*.py`、`/tmp/probe_q3*.py`、`/tmp/probe_q4b.py`、`/tmp/ftv_adv_final.py`），跑不动才退到逐行走读。凡标「实测」均真跑（`uv run python` + 合成 LLM，隔离 workspace）。
- 一句话结论：**grill 的方向与多数 Confirmed Decisions 顶得住；但它自己新提的 Q3/Q5 的「机制」都错了（结论侥幸对），Q1 的「首选方案」与仓库既有范式相悖，Q2 推荐与 delta spec 的设计意图冲突。另有 1 条 grill 与 design 共同写错的缓解声明（M1）。**

---

## 对 grill 结论的裁决

### Confirmed Decisions

| # | 结论 | 裁决 | 证据 |
|---|---|---|---|
| C1 | 截断点与「唯一不报」判定成立（`max_items` 静态截断是唯一静默点） | **survives** | 实测：`_resolve_items` 在 `max_items>0` 走 `items[:node.max_items]`（`scheduler.py:2669`）；另三处截断 `nodes_omitted`（`:3163`）、`warnings_omitted`（`subagents.py:1661`）、`item_refs_omitted`（`:1132`）均显式报告——confirmed 属实 |
| C2 | 声明期入口确能拿到字面 `items`，D1/D3 技术可行 | **survives** | `_route_task_warnings`（`subagents.py:710-724`）遍历 `spec.nodes` 读 `node.kind`/`node.task`；并列 helper 读 `node.items`（`workflow.py:165`）同构。两条入口（`:841`/`:1284`）共用 helper 模式属实 |
| C3 | D4：`items_omitted` 与 `item_refs_omitted` 独立共存 | **survives** | 实测（210 项 / `max_items:205`）：`items=205`、静态省略=5、`item_refs_omitted=5`、`len(item_refs)=200` ⇒ **两者同 >0**，互不决定，可共存。grill 的算术方向正确（其 500/250 例与我的 210/205 例均成立） |
| C4 | 同一节点不可能同时有 `items` 和 `source` | **survives** | `workflow.py:540-542` `has_items == has_source` 即拒（`needs exactly one of items/source`）。grill 引 `:540-542` 准确 |
| C5 | 运行期新字段会被 `_bounded_node` 白名单静默丢弃 | **survives** | `_PARENT_NODE_FIELDS = ("id","kind","status","runs","subagent_id","items")`（`scheduler.py:384`），`_bounded_node`（`:389-405`）只留白名单。**且第二缓解路径已有活先例**：`GetWorkflow(detail='nodes')` 先 `parent_envelope()`（`subagents.py:1046`）**再** `_attach_item_refs`（`:1058`）往 bounded 后的 node dict 补写 `item_refs`/`items_total`/`item_refs_omitted`——新字段按此模式补写即不被丢。grill 指的出口正确 |
| C6 | 措辞不得声称 `max_items=20` 是「默认值」 | **survives** | `max_items=_parse_max_items(data.get("max_items", 20), …)`（`workflow.py:529`）——显式写 20 与省略**同值不可分**，无法归因。属实 |

**小结论**：6 条 Confirmed Decisions **全部 survives**，grill 的走读地基扎实。

---

### Q1（字段撞名）— `needs-revision`

**拆成三个可独立证伪的子命题：**

**(a) 撞名机制（同 dict 同键覆盖）——survives。** 实测：60 项字面 foreach（默认 `max_items`）跑完后 `GetWorkflow(detail='nodes')` 的 `fan` 节点键集 = `['id','item_refs','item_refs_omitted','items','items_total','kind','reason','runs','status','subagent_id','summary']`，`items_total=20`（=展开数）。`items_total` 由 `_attach_item_refs` 在 `subagents.py:1131` 写进**该节点 dict**。若本 change 在同一出口用同名键，后写者覆盖先写者、无报错——**grill 说「同一 dict 同键覆盖，不是异义观感」属实**。

**(b) 「必改」定级——survives（但要精确）。** 只要本 change 在该出口（`GetWorkflow` foreach 节点）写 `items_total`，就与既有键相撞。既有键被 spec 钉死（`openspec/specs/multi-agent-collaboration/spec.md:858`：`items_total = len(state.item_runs)`）并有硬断言（`tests/agent/subagent/test_foreach_item_refs.py:121`）。故「本 change 三个出口 SHALL NOT 复用 `items_total`」**成立**。但注意：design D1 的运行期字段是**被丢弃数 K**（不是 `items_total`）——是否真会写 `items_total` 取决于实现，grill 把一个**有条件**的撞名（改叫别的名即无冲突）讲成了必然事故。**「必避免该名」对；「必改」的严重程度依赖实现选择。**

**(c) grill 的「首选」（命名空间对象 `items_truncation{...}`）——refuted。** 这条我推翻：
- proposal 自身的 RIR finding 1（`proposal.md:81`）明确钉死本 change 的形态是「**统一是 `X_omitted = max(total - shown, 0)` + 一个 `X_total`**，不新造词表」。grill 的「首选」= 一个**嵌套子 dict**，**恰恰是新造词表/新形态**，与 proposal 自证的先例相悖。
- 全仓节点投影**无任何嵌套子 dict**：`_graph_node_projection`（`scheduler.py:2920-2952`）与 `_attach_item_refs`（`subagents.py:1113-1132`）全是扁平标量/短列表。引入嵌套对象是形态漂移，还给读回方增加一层解析负担（模型要读 `items_truncation.declared` 而非扁平 `items_declared`）。
- grill 的「次选」扁平 `items_declared`/`items_omitted` 反而**与代码库先例一致**；grill 以「`items_omitted` 与 `item_refs_omitted` 近形混淆」为由把它降级——那是**可读性**风险（可用测试与命名缓解），远轻于引入新形态。
- 实测确认扁平次选可共存：既有键 `items_total`/`item_refs_omitted` 与新增 `items_declared`/`items_omitted` **不同名**，无覆盖。

**裁决：`needs-revision`。** 「避免复用 `items_total`」采信；**「首选嵌套对象」不采信，推荐扁平 `items_declared`（声明数）/ `items_omitted`（丢弃数），并用测试锁「既有 `items_total`/`item_refs_omitted` 语义不变 + 新字段共存」**（这正是 grill「次选」+ design D4 测试项）。

---

### Q2（source 弱提示）— `needs-revision`（倾向否决 grill，回到 design 的「完全静默」）

grill 推翻 design 的「完全静默」，主张**声明期**给一条不含量值的弱提示。**我不采信**：

1. **与 delta spec 的设计意图冲突**（grill 只做了「字面合规」检查）。delta spec 的 Scenario「source 驱动在声明期不猜」原文：`THEN SHALL NOT 报告该节点的展开数或截断数; AND 其截断情况 SHALL 由 dry run 与运行期出口报告`。这条**把 source 驱动的截断报告独家路由到 dry-run/运行期**。声明期报「运行时**可能**被截断」是在**声明期谈论截断**——grill 论证「不含数值故不违反字面」，但该 Scenario 的结构意图正是「声明期对 source 保持沉默」。grill 用「字面没说数字」绕过了 Scenario 的**目的**，属过度自信的文字主义。
2. **噪声是结构性的，不是边缘**。source 驱动 + 默认 `max_items=20` 是**最常见**配置；集合大小声明期**永不可知**，所以该提示**无条件触发**（每个 source 驱动 foreach 都报）。grill 的缓解「`max_items>0` 才报」不解决问题——`max_items>0` 恰是常态。这正是 design 担心的「每个 source 驱动 foreach 都报」的噪声。
3. **行动性弱**：提示的行动项是「跑 dry-run」——而模型本来就能跑 dry-run（工具描述已引导）。对照既有 `_route_task_warnings`（`subagents.py:719-724`）报的是**确定可行动**的错（route 的 task 永不执行、该挪到 `cases[].when`）；source 弱提示没有等价的确定行动。

**裁决：`needs-revision`。** 推荐**维持 design 的「声明期完全静默」**；若要一条提示，它该落在 **dry-run**（与本 change 既有的 dry-run 出口同面），**不该**落在声明期。

---

### Q3（`max_items=0` 预算截断静默）— `needs-revision`（结论窄口径下 survives；**所述机制 refuted**）

grill 的「机制」链：`max_items==0` → `_resolve_items` 先切片 → `_check_foreach_budget` 因 `delta = count - charged ≤ 0` 不 raise。**这条被实测证伪**：

- 探针 instrument `_check_foreach_budget`（`scheduler.py:2162`）入参：terminal foreach、`max_items=0`、`items=60`、`max_runs=30` ⇒ **`count=30, charged=0, delta=30`**（**>0，不是 ≤0**）。
- 真实机制不是「delta≤0」，而是**「切片正好装进预算」**：`_remaining_expansion_capacity()`（`:2717-2732`）= `min(max_runs-used, max_nodes-expanded, …)`，`_resolve_items` 用 `items[:capacity]`（`:2668`）先切成**恰好等于预算**的长度 ⇒ 随后 `_check_foreach_budget` 的 `runs+delta > limit` 判定**刚好不触发**（`30 > 30` 为假）⇒ 不 raise。是「**切到刚好合身**」而非「delta≤0 跳过」。

**结论的成立范围比 grill 说的窄**（实测）：
- **terminal foreach**（无下游）且切片装进预算：`completed`、`fan.items=30/60`、`diagnostics={}` ⇒ **真静默**（这是 Q3 唯一站得住的窗口）。
- **非 terminal**（fan→collect root）：切片后剩余预算不够下游 auto-agg 节点 ⇒ **响亮触发** `graph_recursion_exceeded` + `diagnostics` + 多条 `blocked` 警告。**不静默**。
- grill 举的例子（fan→root、`max_runs=25`）**并不精确**——它落在会**响亮报错**的形态，与 grill 声称的「dry-run `items_expanded:25`、无 omitted、运行期无任何信号」矛盾。

**裁决：`needs-revision`。** 该路径**确是缺陷类**、建议 Non-Goal + follow-up（grill 的处置对），但（i）**机制描述必须改**（不是 delta≤0，是「切到合身」）；（ii）**静默窗口要缩到「terminal foreach / 切片后预算仍够下游」**，别把会响亮报错的形态也算进「静默」。

---

### Q4（空集合 / source 无产出 → 跑 0 项）— `survives`（且比 grill 说的更强）

- 实测（planner 产出非 JSON 文本、successful）：`planner.status=completed`、`result` 槽 `None`、`fan.items=0`、`fan.status=completed`、**无任何 warning**、`item_refs_omitted=0` ⇒ **完全静默**，属实。
- **比 grill 更强的一条**（grill 未测）：**planner FAILED** 时同样 `fan.status=completed, items=0`——source 从未产出（失败/空/歧义）⇒ foreach 静默跑 0 项并报 completed。
- **一处 grill 过度**：grill 说「模型看不到任何『为什么没跑』的信号」。对 **failed** 情形，`planner` 节点的 `status=failed`/`reason` **在投影里可见**（`scheduler.py:2923-2926`）——信号在**上游**节点、不在 `fan`。真正「无信号」的是 **successful-but-empty** 那个子情形（探针证实无处可看）。

**裁决：`survives`**（口径修正为「fan 节点本身无因由；successful-but-empty 才是全静默」）。建议纳入范围或显式 Non-Goal + issue（与 grill 一致）。

---

### Q5（dry-run 对 source 的 `declared` 是模拟值）— `needs-revision`（**所述机制 refuted**；广义结论 survives 且更糟）

grill 的例子：source 驱动在 dry-run 里 planner 回显任务文本 `"调研 X"`（1 行）⇒ `declared=1`。**实测证伪**：
- planner **无 script**：`items_expanded=0`（不是 1）。
- planner scripted 为 **3 行纯文本**：`items_expanded=0`。
- 只有 planner scripted 为 **JSON `{"tasks":[...]}`**：才得到真实条数（2/3）。
- 原因：`extract_collection`（`scheduler.py:343-366`）对 source 驱动**应用 `source_field`**（JSON 键查找，`:345-347`）；dry-run 假 LLM（`subagents.py:1377`）回显的是**任务文本**（非该 JSON 形状）⇒ 取字段得 `None` ⇒ `[]`（`:353`）。**不是「回显文本被切行」，是「字段名查找在非 JSON 回显上落空」。**

**grill 的广义结论 survives，且实际更糟**：source 驱动的 dry-run `declared` 通常是 **0**（除非 script 恰好产出正确 JSON 形状），这个 0 **读起来像「集合为空」**，与 Q4 的空集合**无从区分**。所以任何对 source 驱动报的 `declared` 数字都是**模拟产物**、且常是误导性的 0。

**裁决：`needs-revision`。** 边界主张（source 驱动 dry-run `declared` 不具预测性、须标模拟/不可区分）**采信**；但必须重写机制说明，并把它与 **Q4** 合并处理（两者在 dry-run 出口同为「0」）。

---

## grill 漏掉的

**M1（grill 与 design 共同写错的缓解声明）——「新声明期警告受既有 `warnings_limit`/`warnings_omitted` 约束」是假的。**
- `warnings_limit`/`warnings_omitted` **只存在于 dry-run 报告构造器**（`subagents.py:1660-1662`）。
- `DeclareWorkflow`（`subagents.py:841`）直接返回 `_route_task_warnings(spec)`，**无任何切片**；`RunWorkflow(spec=)` 的 `warnings`（`:1294` 非等待路径 / `:1299` 等待路径）同样**无界**。
- 实测：300 个截断 foreach 节点 ⇒ 会生成 **300 条**声明期警告，无 `warnings_omitted`。
- design 风险表写「新 warning 走既有 `warnings` 列表，受既有 `warnings_limit`/`warnings_omitted` 约束（无需新增界）」——**它在错误的出口引用了不存在的界**。grill 的 Confirmed Decision 5 与风险表**逐字复述了这条未核实的声明**。
- 严重度：**中低**——警告是「每 foreach 节点一条」，本身受 `max_nodes` 间接约束；但它违背项目「显式设界 + 报 omitted」的纪律（`nodes_omitted`/`warnings_omitted` 先例），且是**一条错误的缓解**。修法：要么给两条声明入口的 `warnings` 也加 `warnings_limit`（复用 dry-run 口径），要么在 design 里如实写「声明期警告条数上界 = 节点数（受 `max_nodes` 约束），不漏项」。

**M2（三出口设计可能制造的新不一致）——dry-run 的 source `declared=0` 与 Q4 的空集合同形。** 见 Q5 裁决：本 change 若在 dry-run 对 source 驱动无条件报 `declared`，会把「source 解析为空」（Q4）与「source 驱动的模拟回显落空」压成同一个 `0`，制造新的读混。需在字段设计上让「未知（source 驱动）」与「确认空集」可区分。

**M3（口径核对，非缺陷）——仓库有两种截断报告风格**：**计数式**（`nodes_omitted`/`warnings_omitted`/`item_refs_omitted`，`max(total-shown,0)`）与**标记式**（下游 prompt 裁剪用 `_BOUNDED_MARKER`，`aggregation.py:67/101`）。本 change 选计数式，与 `nodes_omitted` 先例一致——**正确**，非缺陷。列出以备实现期别误用标记式。

**M4（旁证，非本 change 范围）**——`_attach_item_refs` 的 `item_refs` 本身**跳过空槽 + 上限 200**（`subagents.py:1098-1099`）已是「有界 + omitted」；本 change 的「items 截断」是其**上游**（集合级）而非同层，切分正确。

---

## 严重度复核

| grill 风险项 | grill 定级 | 我的复核 | 理由 |
|---|---|---|---|
| D2 `items_total` 同 dict 同键覆盖 | 高 | **高（但口径修正）** | 覆盖机制实测属实；但仅当实现复用该名才发生——「必避免该名」高优先级对，「首选嵌套对象」错（见 Q1c，那部分应降为方案争议，非风险） |
| 运行期字段被 `_bounded_node` 丢弃 | 中 | **中** | 属实；且已有 `_attach_item_refs` 后写先例，缓解路径明确 |
| `max_items=0` 预算截断静默 | 中 | **低–中（下调）** | 机制错（非 delta≤0）；静默窗口窄（terminal / 切片合身），非 terminal 会**响亮报错**——覆盖面比 grill 说的小 |
| 空集合/解析为空跑 0 项 | 中 | **中–高（上调）** | Q4 成立且含 **failed-source** 子情形；successful-but-empty 全静默，比 grill 说的更隐蔽 |
| `items_omitted`↔`item_refs_omitted` 近形混淆 | 中 | **低（下调）** | 是**可读性**风险、非硬撞名；用命名/测试可缓解，不足以撑起「改用嵌套对象」的方案升级 |
| source 弱提示噪声 | 低 | **低（但应为「否决该提示」，非「缓解」）** | grill 把它当「采纳后的可缓解风险」；我认为**根本不该采纳**（见 Q2） |
| 声明期措辞误称默认值 | 低 | **低** | 正确 |
| 声明期警告对 blocked/skipped 节点 | 低 | **低** | 正确 |

---

## 总体

### 可据此拍板（顶得住对抗）
- **6 条 Confirmed Decisions 全部成立**：截断点定位、声明期可行性、D4 独立性（实测两者同 >0）、`items`/`source` 互斥、`_bounded_node` 白名单 + 后写先例、措辞不可称默认值。
- **Q1 的核心**：「本 change 三出口 SHALL NOT 复用 `items_total`」——采信（同名键实测会覆盖）。
- **Q4**：空集合/无产出静默跑 0 项——采信为真缺陷（且含 failed-source）。建议纳入或显式 Non-Goal+issue。
- **Q3 的处置**（Non-Goal + follow-up）：方向对，但描述要修。
- **Q5 的边界主张**（source 驱动 dry-run `declared` 非预测、须标不可信）：采信。

### 需修正后再拍板
- **Q1 的字段形态**：弃用 **grill 首选（嵌套 `items_truncation{...}`）**，改用**扁平 `items_declared`/`items_omitted`**（合 proposal RIR finding 1 与仓库扁平范式）；测试锁共存。
- **Q2**：**否决** grill 的声明期弱提示；维持 design「完全静默」，如需提示放 dry-run。
- **Q3 机制**：改成「`_resolve_items` 切到 `_remaining_expansion_capacity()` 刚好合身 ⇒ 后续 `_check_foreach_budget` 不触发」，并把静默窗口缩到 **terminal/预算合身** 形态。
- **Q5 机制**：改成「`extract_collection` 对 source 驱动应用 `source_field`，dry-run 假 LLM 回显非该 JSON 形状 ⇒ 取字段落空 ⇒ `[]`」；与 Q4 在 dry-run 出口的 `0` 合并处理。
- **M1**：design 风险表「新警告受既有界约束」是错的——要么补界，要么如实写「上界=节点数」。**(grill 未发现的错误缓解。)**

### 被证伪（不可据此拍板）
- **Q1「首选 = 命名空间对象」**：refuted（新造形态，与 proposal RIR/仓库范式相悖）。
- **Q3 的机制描述（delta≤0 跳过）**：refuted（实测 delta=30>0）。
- **Q5 的机制示例（回显文本切行得 declared=1）**：refuted（实测为 0）。
- **Q2「弱提示不违反 delta spec」**：字面真、**意图假**（Scenario 把 source 截断报告独家路由到 dry-run/运行期）——按 `needs-revision` 处理，实质应否决。

### 我如何努力证伪而未成功（顶得住攻击的结论）
1. **想证伪 C3（D4 独立性）**：构造 210 项 / `max_items:205`，企图让静态省略与 ref 界省略**不可能同 >0**。**失败**——实测 `static_omitted=5` 与 `refs_omitted=5` 同时 >0，两者正交共存。C3 顶住。
2. **想证伪 C5 的「缓解出口」**：以为白名单会连 `item_refs`/`items_total` 一起丢掉。**失败**——`subagents.py:1046`→`:1058` 的顺序证明它们是在 `parent_envelope()` **之后**补写的，绕开白名单。C5 且其缓解路径顶住。
3. **想证伪 C4（items/source 互斥）**：读 `workflow.py:540-542`，互斥是硬校验，无绕过。顶住。
4. **想证伪 Q4 的「静默」**：追 `blocked`/`skipped`/`reason` 是否已表达「为什么没跑」。**部分失败**——failed-source 情形确有上游 `status/reason` 可见（grill 那句「看不到任何信号」对此过度）；但 successful-but-empty 是**真全静默**（探针 `probe_q4`），Q4 主体顶住。
5. **想证伪 Q1(a) 的覆盖机制**：怀疑 `_attach_item_refs` 与 `_bounded_node` 不同 dict。**失败**——实测 `GetWorkflow(detail='nodes')` 的 `fan` 节点**同时**带 `items_total`(20) 与 `items`(20)，证明确在同一 dict；同名新键必覆盖。Q1(a) 顶住。

---

### 给主 session 的一句话转达
grill 报告**可作蓝本但不可照抄**：6 条 Confirmed Decisions 全部采信；**Q1 弃用「嵌套对象」改扁平 `items_declared`/`items_omitted`**；**Q2 弱提示否决、维持静默**；**Q3/Q5 的结论对但机制写错，必须重写后再进 design**；**Q4 纳入范围**；另**补 design 风险表一处假缓解（M1：声明期警告无界）**。定级上：Q3 下调（低–中）、Q4 上调（中–高）、近形混淆下调（低）。
