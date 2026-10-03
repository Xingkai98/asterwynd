# 对抗验证：foreach 预算截断可见性 grill 报告（change foreach-budget-truncation-visibility）

- 执行者：独立零记忆**对抗验证** subagent（角色：证伪 reviews/grill-design.md，不复述、不背书）
- 分支：foreach-budget-truncation-visibility/2026-10-03
- 被验证对象：openspec/changes/foreach-budget-truncation-visibility/reviews/grill-design.md（6 Confirmed Decisions + Q1–Q7 + 风险表 + 走读索引）
- 方法：对每条承重结论**先跑实测证伪**（探针落 `/tmp/fbtv_adversarial/probe_*.py`，真跑 `RunWorkflow` / `DryRunWorkflow` / `GetWorkflow` / `WorkflowScheduler.run`，合成 LLM，隔离 workspace）。凡标「实测」均真跑（`.venv/bin/python`，HEAD `ecd98ff`）。
- 一句话结论：**grill 的地基顶得住——6 条 Confirmed Decisions 全部 survives，Q4「≤ max_fan_in 静默 / > 响亮」的机制与阈值被实测精确证实（config 改 `max_fan_in` 阈值随之移动），Q2 甚至被证到更强的形态。唯一需修正的是 Q5 的一处推荐不精确（「更稳的 T1 用字面 60 项」拿不到 spec 声明的 24），以及我另找到的 3 处 grill 未提的静默出口/更强事实。无翻案。**

---

## 对 grill 结论的裁决

### Confirmed Decisions

| # | 结论 | 裁决 | 证据 |
|---|---|---|---|
| C1 | 静默机制 = 「`_resolve_items` 切到 `_remaining_expansion_capacity()` 恰好合身 ⇒ `_check_foreach_budget` 的 `runs+delta>limit` 刚好不触发」 | **survives** | 实测 `probe_c1b.py`（instrument 两方法）：source 60 / planner 占 1 / `max_runs=25` → `[_cap] cap=24`，随后 `[_check] count=24 charged=0 delta=24 runs_before=1 limit=25 sum=25` ⇒ `25>25` 为假、**不 raise**。两出口实测皆静默（`probe_c1.py`）：`RunWorkflow` 信封 `status=completed`、`diagnostics={}`、fan 无任何 omitted 字段；`GetWorkflow(detail='nodes')` 只有 `items_total/item_refs_omitted`，无 `items_omitted`。delta=24 **不是** ≤0——grill 对 #279 原稿「delta≤0」的推翻成立。 |
| C2 | 拟议 D3（去 `max_items>0` 前置 + `items_omitted_cause`）两出口都成立 | **survives** | 实测 `probe_c2.py`（monkeypatch 拟议 helper，**未提交**）：dry-run 字面 60/`mi=0`/`mr=25` → `items_declared=60/items_expanded=25/items_omitted=35/cause=budget`；dry-run source(script 60) → `60/24/36/budget`；运行期 `GetWorkflow(detail='nodes')` 字面 → `items=25/declared=60/omitted=35/cause=budget`；source → `24/60/36/budget`。**无一出口漏**（两出口都写）。既有 `items_total`（=展开数）、`item_refs_omitted` 未被覆盖、共存。 |
| C3 | `items_omitted_cause` 零撞名 | **survives** | 实测 grep：`grep -rn '"cause"' agent/` **零命中**；`grep -rn 'cause=' agent/` 零命中；全仓 `.py` 内裸 `cause` 只出现在 `tests/test_openspec_artifact_checker.py:80` 的一句英文注释。运行期节点键集（`probe_c2.py`）含 `reason`、无 `cause`；dry-run 条目键集含 `reason`（经 `_terminal_reason`）、无 `cause`。故与 `reason` 同 dict 不碰撞。 |
| C4 | 静态路径「值不变但非逐字节不变」 | **survives** | 实测 `probe_c4.py`（**两个独立进程** baseline vs patched，7 例矩阵：static 30/60/100/1000-of-60、static source 20of60、empty literal、mi0 plenty）：`diff` 唯一差异 = 4 处**新增** `items_omitted_cause: "max_items"` 行；把新增键滤掉后与基线**逐字节相同**（`diff` 空）。`declared==expanded`（`max_items=1000`）与 `max_items=0` 充足预算两例**未新增任何键**，无误伤。design.md:72「逐字节不变」措辞确实被证伪（见 M4/R3）。 |
| C5 | 零噪声（T4） | **survives** | 实测 `probe_c4.py`/`probe_q5.py`：字面 5/`mi=0`/`mr=25` → dry-run 条目仅 `{items_expanded:5}`；字面 60/`mi=0` 默认充足预算 → 仅 `{items_expanded:60}`；运行期同。无 `declared==expanded>0` 被误报。source 无 script 时发 `items_declared=0+items_declared_simulated=True`，但那是 #279 既有行为（且 delta spec 只禁「截断省略数/成因」），非本 change 噪声。 |
| C6 | 不触门禁 | **survives** | 实测：`PYTHONPATH=. .venv/bin/python scripts/check_openspec_artifacts.py` → `OpenSpec artifact checks passed`（exit 0）；`npx @fission-ai/openspec@1.4.1 validate --all --strict` → `29 passed, 0 failed`；打补丁后 `pytest tests/agent/subagent/ -q` → **842 passed**（与 grill 报数逐位一致，我复跑）。 |

### Open Questions 裁决

#### Q1（成因字段命名）— survives
`items_omitted_cause` 无撞名（同 C3 证据）。取值 `"max_items"`/`"budget"` 与既有 `reason` 同 dict 不覆盖。

#### Q2（出口范围 —— 最高价值）— **survives，且被证到更强的形态**
**实测 `probe_q2.py` / `probe_detail.py`：**
- `RunWorkflow(spec=...)` 信封的 fan 节点键集（**三种场景全同**）=
  `['id','items','kind','reason','runs','status','subagent_id','summary']`。
  - 静态字面 60/`max_items=20`：`items=20`，**无** `items_declared/items_omitted/empty_collection`。
  - 预算 source 60/`mi=0`：`items=24`，**无**任何截断字段。
  - 预算字面 60/`mi=0`：`items=25`，**无**任何截断字段。
  ⇒ grill 的「连 #279 静态字段都没有」**逐字为真**。
- **比 grill 更强的一条（grill 未提）**：`RunWorkflow(spec=)` 顶层 `warnings` 对**静态字面**截断**有**报告（我实测拿到 `"node 'fan': declares 60 foreach items but max_items=20 …"`），对**预算截断**是 **`[]`**（两种预算场景顶层 `warnings` 都空）。即**预算截断在 RunWorkflow 返回路径上：既无节点字段、又无 warning——比静态截断更彻底地静默**。
- **第二条更强的（grill 未提）**：`GetWorkflow` 的**默认** `detail='summary'`（schema 默认，`subagents.py:1071`）**也不带**这些字段——fan 键集与 RunWorkflow 信封同形。字段只在显式 `detail='nodes'`（`subagents.py:1083`）才出现。故所谓「运行期出口」严格等于「`GetWorkflow(detail='nodes')`」，模型若按默认调 `GetWorkflow(workflow_id=...)` 仍看不到。见 M1。

**裁定**：Q2 的证伪成立且结论方向正确。R1（高）成立并应升级描述。

#### Q3（成因粒度）— survives
实测 `probe_q36.py`（instrument `_remaining_expansion_capacity`）：
- source 60/`max_nodes=25`（无 `max_runs`）→ `[cap] max_runs_left=299 max_nodes_left=23 -> 23`，`fan.items=23`（绑定 **max_nodes**）。
- source 60/`max_runs=25` → `max_runs_left=24 max_nodes_left=198 -> 24`，`fan.items=24`（绑定 **max_runs**）。
- config `budget.max_total_runs=12` + spec `max_runs=200/max_nodes=400` → `budget_max_runs_left=11 -> 11`，`fan.items=11`（绑定 **max_total_runs**）。
绑定维度 = 三者运行期 min，随图/配置而变，grill 说法准确。粗粒度 `"budget"` 够用（各维度已见 `limits`/`budget`）的推荐成立。

#### Q4（非 terminal 响亮路径）— **survives（阈值与机制被精确证实；未翻案）**
**实测 `probe_q4.py` / `probe_q4b.py`（三组扫描）：**
- **字面 60 / `mi=0` / `fan→collect`（无 planner）**：`max_runs=1..10` → 全 `completed`、`diag={}`、`fan.items` 随 mr 增长；`max_runs=11+` → `graph_recursion_exceeded`（`diag.reason=max_runs`）。**边界恰在 10/11**——与 grill「`8/9/10` 静默、`11+` 响亮」一致（grill 的 8/9/10 含 10 静默，为真的子集）。
- **`max_nodes` 扫描**：`max_nodes=5..12` 静默（`fan.items=3..10`）；`13+` 响亮（`fan.items=11`）。
- **决定性一击（改 config `max_fan_in=4`）**：source 60，`max_runs=5` → completed/`fan.items=4`；`max_runs=6+` → 响亮/`fan.items=5`。**阈值随 `max_fan_in` 从 10 位移到 4**（静默当且仅当切片 ≤ `max_fan_in`）。⇒ grill 的机制「切片 ≤ max_fan_in 不插 auto-agg 层 ⇒ 静默」**成立且可配置复现**。
- **非 terminal 静默的普遍性**：`fan→collect`（**非 terminal**）`max_runs=10` 实测 `status=completed`、`diag={}`——**确实静默**。proposal.md:50 的「非 terminal（如 `fan→collect` root）⇒ 响亮报…不静默」作为**无条件普遍陈述是错的**（见 R2）。

**裁定**：Q4 的证伪（proposal/design 边界描述被实测推翻）**成立**。grill 建议改文字为「切片后预算仍够图跑完即静默」正确。（唯一细节：grill 通篇用 source+planner，其 8/9/10 阈值与我的字面扫描一致；若带 planner 需 +1，但那是能耗预算的口径差，不改变阈值=max_fan_in 的结论。）

#### Q5（dry-run 可行性）— **needs-revision（一处推荐不精确）**
**实测 `probe_q5.py` / `probe_literal24.py`：**
- 字面 60/`mi=0`/`mr=25`（无 planner）→ dry-run `25/60/35/budget`（与 grill「字面 60 给 25/35」一致）。
- source 无 script → `items_expanded=0, items_declared=0, items_declared_simulated=True`（撞不到截断）——**grill 的 script 必要性主张成立**。
- source+script(60) → `24/60/36/budget`（成立）。
- **grill 漏掉的确定性路径**：**字面 60 + 上游 planner（占 1 run）/`mi=0`/`mr=25`** → dry-run `24/60/36/budget`，运行期 `24/60/36/budget`。**完全确定性、零假 LLM 脚本**，且**同时满足 spec Scenario 的 60/24/36**。

**裁定**：grill 的「T1 必须带 `script`（source）或改字面」——其中「改字面」**不精确**：**裸字面 60 给的是 25/35，不是 spec 声明的 24**（grill 自己在同一段也承认 25/35，却又在推荐里写「更稳的 T1 用字面 60 项」，自相矛盾）。要字面拿 24 必须**再加一个吃 1 run 的上游节点**（我实测成立）。T1 的最佳形态 = 字面 60 + 上游 planner，而非 grill 建议的裸字面或 source+script。

#### Q6（`declared_is_simulated` 与新分支交互）— survives
实测 `probe_q36.py`：source+script dry-run → `{'items_declared':60,'items_declared_simulated':True,'items_omitted':36,'items_omitted_cause':'budget'}` 共存、无 `empty_collection`。source 无 script（`declared=0`）走 `declared==0` 分支，**不**发 `items_omitted`（无假报）。grill 的「接受现状 + 测试锁共存」成立。**补充**：`items_omitted` 自身无 `_simulated` 标记（见 M3）。

#### Q7（`items_omitted = declared - expanded` 无碰撞）— survives
实测 `probe_q7.py`：
- source 60/`mr=1`（planner 占满）→ 运行期 `items=0/declared=60/omitted=60/cause=budget`，**无** `empty_collection`；dry-run 同（`items_expanded=0/declared=60/omitted=60/budget`）。
- 字面 60/`mr=1` → `items=1/declared=60/omitted=59/budget`。
两信号正确分离。

---

## grill 漏掉的

**M1（新出口缺口，放大 Q2）——`GetWorkflow` 默认 `detail='summary'` 也不带字段。** grill 与 design 都只说「运行期 = `GetWorkflow` 的 foreach 节点投影」，但字段只在**显式** `detail='nodes'` 出现（`subagents.py:1083` 的 `if detail == "nodes":`）；默认 `detail='summary'`（`:1071`）的 fan 节点键集与 RunWorkflow 信封同形、**无任何截断字段**（`probe_detail.py` 实测）。模型最省事的两条读法（RunWorkflow 返回、`GetWorkflow()` 默认）**都看不到**。

**M2（stark 对比，放大 Q2）——预算截断在 RunWorkflow 路径上比静态更静默。** 静态字面截断至少有顶层 `warnings`（`_foreach_truncation_warnings`，实测非空）；预算截断 `warnings` 恒 `[]` **且**节点无字段。即本 change 若不扩 RunWorkflow 信封，预算截断在「跑图拿返回」这条最自然路径上是**双重静默**。

**M3（新字段缺模拟标记）——source 驱动的 dry-run `items_omitted` 无自带 `_simulated` 标记。** source+script dry-run 里 `items_declared` 标了 `items_declared_simulated=True`，但 `items_omitted`（= 模拟 declared − 模拟 expanded）**自身无标记**；模型可能把 `items_omitted=36 / cause=budget` 读成「真会省 36 个」而非模拟产物。grill Q6 承认共存但未点出这个缺失标记。属可读性/可行动性风险，非硬缺陷。

**M4（口径核对，非缺陷）——design D3:72「逐字节不变」与其自身 T5 措辞（`design.md:113`「值不变」）自相矛盾。** 我的字节 diff（C4）坐实：静态输出**是**新增了 `items_omitted_cause` 键，故 D3:72 的「逐字节不变」为假，T5/`:113` 的「值不变」为真。grill 已在 C4/R3 指出，此处补精确证据：**恰 4 个静态例各新增 1 行 `items_omitted_cause`，其余逐字节相同**。

---

## 严重度复核

| grill 风险项 | grill 定级 | 我的复核 | 理由 |
|---|---|---|---|
| **R1** 两出口不覆盖 `RunWorkflow` 结果信封 | 高 | **高（维持，且应加 M1/M2）** | 实测坐实，且比 grill 说的更强：预算截断在 RunWorkflow 路径「无字段 + 无 warning」双静默，`GetWorkflow` 默认 detail 亦静默 |
| **R2** 非 terminal 边界描述错误 | 中-高 | **中-高（维持）** | 实测坐实：`fan→collect` 非 terminal 在切片 ≤ `max_fan_in` 时静默；proposal.md:50 的无条件陈述错 |
| **R3** design D3:72「逐字节不变」自相矛盾 | 中 | **中（维持）** | 字节 diff 坐实：静态仅新增 `items_omitted_cause` 键，非逐字节不变 |
| **R4** T1 source 无 script 得 declared=0 | 中 | **中（维持，但推荐需修）** | 实测坐实；**但 grill 的「改用字面 60」拿不到 24**——最佳 T1 = 字面 60 + 上游 planner（M3） |
| **R5** `items_omitted` ↔ `item_refs_omitted` 近形 | 低 | **低（维持）** | 可读性风险，命名/测试可缓解；#279 对抗已裁决可接受 |
| **R6** 细化成因粒度需新字段+argmin | 低 | **低（维持）** | Q3 实测坐实绑定维度随图/配置变，v1 粗粒度合理 |
| **R7** 去前置误改静态输出 | 低 | **低（维持）** | 字节 diff 坐实静态值不变；842 测试绿 |

---

## 总体

### 可据此拍板（顶得住对抗）
- **6 条 Confirmed Decisions 全部 survives**（C1–C6 逐条实测复现，含 C2 两出口、C4 字节级静态 diff、C6 门禁与 842 测试）。
- **Q3（绑定维度 = 三者 min，随配置变）、Q6（simulated+omitted 共存）、Q7（`mr=1` → omitted=60 不误标 empty_collection）** 均实测坐实。
- **Q4 的机制与阈值（静默当且仅当切片 ≤ `max_fan_in`）被精确证实**，连 config 改 `max_fan_in` 阈值随之移动都复现——**这是本 change 最需要的「proposal.md:50 必须改」的证据，顶得住**。
- **Q2 坐实并加强**（RunWorkflow 信封无字段；静态靠 warnings 兜底、预算双重静默）。

### 需修正后再拍板
- **Q5 的 T1 推荐**：改「字面 60 + 上游 planner（占 1 run）」为确定性首选（实测 60/24/36，零 script），而非 grill 的裸字面（25/35）或 source+script；或明确接受 T1 断言 25/35 而 spec Scenario 改字面。
- **design D3:72**：删「逐字节不变」，统一为「既有字段值不变 + 新增 `items_omitted_cause`」（grill R3 已提，证据见 M4）。
- **Q2/R1 描述加 M1/M2**：缺口不止 RunWorkflow 信封，还包括 `GetWorkflow` 默认 `detail='summary'`；且预算截断在 RunWorkflow 路径「无字段 + 无 warning」双静默。

### 被证伪（不可据此拍板）
- **proposal.md:50 / design 的「非 terminal ⇒ 响亮、不静默」无条件陈述**：**refuted**（`fan→collect` `max_runs=10` 实测静默）。须改为「切片后预算仍够图跑完即静默（含切片 ≤ `max_fan_in` 的非 terminal）」。
- **design.md:72「静态路径逐字节不变」**：**refuted**（字节 diff 显示新增 `items_omitted_cause` 键）。
- **grill Q5 的「更稳的 T1 用字面 60 项」**：**refuted 作为充分建议**（裸字面 60 = 25/35，非 spec 的 24；须补上游 planner 或 source+script）。

### 我如何努力证伪而未成功（顶得住攻击的结论）
1. **想证伪 C1 的「切片合身」机制**：instrument 两方法，企图让 `_check_foreach_budget` 在某参数下仍 raise。**失败**——`cap=24`、`sum=25==limit` 精确吻合，#279 对抗的机制修正顶住。
2. **想证伪 C2 的两出口覆盖**：怀疑运行期后写被 `_bounded_node` 吞掉或 dry-run 漏字段。**失败**——monkeypatch 后 dry-run 与 `GetWorkflow(detail='nodes')` **都**出 `items_omitted_cause`。
3. **想证伪 C4「值不变」**：跨 7 例（含 `max_items=1000`、`declared==expanded`）跑字节 diff。**失败**——除新增键外逐字节相同，无误伤。
4. **想证伪 Q4 的阈值机制**：以为「响亮」取决于别的因素。**失败**——改 config `max_fan_in=4`，阈值精确移到 4/5，机制无可辩驳。
5. **想证伪 Q3「绑定维度随图变」**：构造三种单维绑定。**失败**——`max_nodes`/`max_runs`/`max_total_runs` 分别绑定，cap 分别为 23/24/11。
6. **想证伪 Q7「无碰撞」**：把 `expanded` 逼到 0（`mr=1`）看是否误标 `empty_collection`。**失败**——`declared=60` 走真截断分支，正确标 `omitted=60/budget`。
7. **想证伪 C6「不触门禁」**：复跑 checker + validate + 842 测试。**失败**——全绿、报数与 grill 逐位一致。

---

### 给主 session 的一句话转达
grill 报告**可作蓝本、地基扎实，但需补三处**：**Q2/R1 的缺口比 grill 说的更宽**（RunWorkflow 信封、`GetWorkflow` 默认 `detail='summary'` 都静默；且预算截断在 RunWorkflow 路径「无字段+无 warning」双重静默——`proposal/design 若只对齐 #279 两出口，最自然的读法仍全静默`）；**proposal.md:50 与 design.md:72 两处文字被实测证伪**（非 terminal 在切片 ≤ `max_fan_in` 时同样静默；静态路径非逐字节不变）；**Q5 的 T1 推荐改用「字面 60 + 上游 planner」**（实测确定性 60/24/36，零 script；裸字面只给 25/35）。**无承重结论被翻案**——6 条 Confirmed Decisions、Q2/Q3/Q4/Q6/Q7 全部顶得住对抗。
