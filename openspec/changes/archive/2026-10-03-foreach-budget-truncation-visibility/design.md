# Design: foreach 预算截断可见性

## Context

`foreach` 的 `max_items=0` 时，`_resolve_items`（`agent/subagent/scheduler.py:2676-2677`）返回 `items[:self._remaining_expansion_capacity()]`——切片先把集合切到「恰好等于剩余预算」的长度，使后续 `_check_foreach_budget`（`:2167`）的 `runs + delta > limit` 判定**刚好不触发**（等号不通过）⇒ **不 raise、无 omitted 报告**、超预算项**静默丢弃**（实测：60 声明 / 24 展开 / 36 静默丢，`status=completed`、`diagnostics={}`）。本 design 把这条**预算**截断在**模型可见出口**如实报告，与 #279 的**静态**截断报告**同形态**。

### 已核实的事实（本设计的地基）

1. **截断点**：`_resolve_items`（`agent/subagent/scheduler.py:2654-2678`）：`max_items==0` → `items[:remaining_expansion_capacity()]`（**预算截断，本 change 的主角**）；`>0` → `items[:node.max_items]`（静态截断，#279 已治）。**两条路径都先记 `state.items_declared = len(items)`（`:2675`，切片之前）**——故预算截断路径的 `declared` **已被记录**，本 change 无需改 `_resolve_items`。
2. **静默机制**：切片使 `count` = 剩余容量 ⇒ `_check_foreach_budget`（`:2180-2183`）`delta = count - charged`、`runs + delta == limit`（等号）⇒ 不 raise（`:2192`/`:2204` 的 `>` 不成立）。**静默窗口 = 切片后预算仍够整张图跑完**（terminal；或非 terminal 但下游不新增吃预算的节点）——**已由对抗实测修正**：非 terminal（`fan → root(strategy=collect)`）在切片 ≤ `max_fan_in`(=10) 时**同样静默**（不插 auto-agg 层、下游 collect 不跑模型），切片 > `max_fan_in` 才响亮 `graph_recursion_exceeded`（详见「边界」节与 `reviews/grill-adversarial.md` Q4）。原文「非 terminal 一律响亮」**是错的**。
3. **两出口共用 helper**：`_foreach_visibility_fields`（`agent/tools/builtin/subagents.py:1122`）是**纯函数**，dry-run（`:1693`）与运行期（经 `_attach_foreach_visibility`，`:1159`）**共用**——本 change 扩展它即天然覆盖两出口。
4. **运行期出口须「后写」**：新字段必须在 `parent_envelope()` **之后**补写（`_attach_foreach_visibility` 已在正确位置，`:1097`），否则被 `_bounded_node` 白名单 `_PARENT_NODE_FIELDS`（`scheduler.py:389`，仅 `id/kind/status/runs/subagent_id/items`）**静默丢弃**（#279 D3 已钉死）。
5. **`reason` 键已占用**：运行期节点 dict（`NodeState.to_dict`，`scheduler.py:187`）与 dry-run 条目（`subagents.py:1684`）**均有 `reason` 键**（终态原因）——成因判别字段 SHALL NOT 叫 `reason`（同 dict 同键覆盖，与 #279 D2 的 `items_total` 覆辙同类）。
6. **`items_declared` 已被 #279 使用**：`state.items_declared`（`scheduler.py:254`）+ dry-run/运行期已投影该字段（`max_items=0` 时 #279 也报 `items_declared`，只是**不带** `items_omitted`——见 `_foreach_visibility_fields` 的 `elif max_items > 0 and declared > expanded` 分支，`:1153`）。

## Goals / Non-Goals

### Goals

- **三出口**（dry run / `RunWorkflow` 结果信封 / `GetWorkflow(detail='nodes')` 投影）如实报告 `max_items=0` 预算截断的「声明 N / 展开 M / 省略 K」。
  > **用户 2026-10-03 拍板（OQ2 = (b)，有意扩范围）**：原设计只对齐 #279 的**两出口**（dry run + `GetWorkflow(detail='nodes')`），但实测 `RunWorkflow` 的**结果信封** `nodes`（`_bounded_node` 白名单过滤）**连 #279 的静态字段都没有**——模型跑完图**最自然的读法**（直接读返回信封）会全静默。故本 change **顺带把后写挂到 `RunWorkflow` 信封路径**，把 #279 的静态字段也一并补上。
  > **如实记录的边界（M1）**：`GetWorkflow` 的**默认** `detail='summary'`（`subagents.py:1071`）**也不带**这些字段——字段只在**显式** `detail='nodes'`（`:1083`）出现。本 change **不**动 `summary` 出口（最小改动；`summary` 是总览档、本就不展开 per-node 可见性字段），此事实**如实记录**于本 design 与 proposal。
- `items_omitted` 与**成因判别字段**（`items_omitted_cause`）配对，静态 vs 预算两种成因不歧义。
- 零噪声：不截断（declared == expanded）时不报。
- 不退化 #279 的静态截断面；不冲突 #279 的「`max_items=0` 不报**静态**截断」。

### Non-Goals

- 不改 `max_items` 默认值（#276）。
- 不改 `max_items=0` 语义。
- 声明期不适用（预算截断是运行期现象）。
- 成因判别字段不复用 `reason`（D2）。

## Decisions

### D1 — **三出口一致**：dry run / `RunWorkflow` 信封 / `GetWorkflow(detail='nodes')` 各报告其所知

| 出口 | 何时可知 | 报告什么 |
|---|---|---|
| **dry run**（`DryRunWorkflow` foreach 条目） | dry run 会**解析**集合并**模拟**预算消耗 | 补 `items_declared` / `items_omitted` + 成因（与既有 `items_expanded` 三元齐） |
| **`RunWorkflow` 结果信封**（`_drive_scheduler` 返回的 `parent_envelope()` 的 `nodes`，foreach 节点） | 运行期解析 + 实际预算消耗后；**须后写**（D3） | 同三元 + 成因（**用户拍板 OQ2=(b) 新增出口**；一并补 #279 静态字段） |
| **`GetWorkflow(detail='nodes')` 投影**（foreach 节点） | 同上；**须后写**（D3） | 同三元 + 成因 |

**为什么声明期不适用**：`DeclareWorkflow` 是纯声明、不运行，而预算截断取决于**运行期已用预算**与**source 解析出的集合大小**——声明期两者皆不知。故本 change **无声明期出口**（与 #279 不同——#279 至少字面 `items` 声明期可知，预算截断连字面 `items` 也要运行到才知道用掉多少预算）。

**M1（如实记录的边界）**：`GetWorkflow` 的**默认** `detail='summary'` 只有 bounded 节点、不带这些可见性字段；字段只在**显式** `detail='nodes'` 出现。本 change 不改 `summary` 出口（`summary` 是总览档，本就不承载 per-node 可见性字段）。

**dry run 是否会真撞预算截断**：dry-run 的 scheduler 用 spec 声明的 `max_runs`/`max_nodes`，`_resolve_items` 走**同一条**预算切片路径——只要 dry-run 里 source 产出足够大（脚本化假 LLM），就会撞。实现期须用测试确认 dry-run 真能复现（见 Testing Strategy）。

### D2 — 字段名：**复用扁平 `items_omitted` + 新增扁平成因判别字段**（绝不复用 `reason`）

- **复用 `items_declared`/`items_omitted`**：与 #279 同名字段、同一「声明数 / 被丢弃数」语义。`items_declared` 已由 `_resolve_items:2675` 记录、dry-run 已投影；本 change 让 `items_omitted` 在 `max_items == 0` 且 `declared > expanded` 时**也发**（#279 仅 `max_items > 0` 时发）。
- **新增成因判别字段**（**用户 2026-10-03 拍板 OQ1 = `items_omitted_cause`**，取值 `"max_items"` / `"budget"`）：**绝不能**叫 `reason`——运行期节点 dict 与 dry-run 条目**均已有 `reason` 键**（终态原因），同名会**同 dict 同键覆盖、无报错**（#279 D2 实测 `items_total` 覆辙）。实测 `agent/` 全仓无裸 `cause` 键，`items_omitted_cause` 零撞名。
- **扁平不用嵌套**：#279 对抗已否决嵌套对象（违背项目扁平先例，见 RIR finding 1）——本 change 沿用扁平，**不新造** `items_truncation{...}` 对象。
- **只在真截断时发**：`items_omitted_cause` 仅随 `items_omitted` 一起出现（`declared > expanded`）；不截断时**零噪声**（T4）。

### D3 — 复用 `_foreach_visibility_fields` 共享 helper，扩展一个成因参数

扩展 `_foreach_visibility_fields`（`subagents.py:1122`）逻辑：

```
if declared is None or expanded is None: return {}
fields = {}
if declared_is_simulated:                       # 沿用 #279 Q5
    fields["items_declared"] = declared
    fields["items_declared_simulated"] = True
if declared == 0:
    if not declared_is_simulated:
        fields["empty_collection"] = True       # 沿用 #279 Q4
elif declared > expanded:                        # #286 扩展点：不分 max_items 值
    fields["items_declared"] = declared
    fields["items_omitted"] = declared - expanded
    fields["items_omitted_cause"] = "max_items" if max_items > 0 else "budget"
return fields
```

**关键差异**：原 #279 是 `elif max_items > 0 and declared > expanded`；本 change 去掉 `max_items > 0` 前置，改为按 `max_items` 值选成因。静态路径（`max_items > 0`）的**既有字段值不变**（`items_declared`/`items_omitted` 数值逐位不变），但**新增一个键 `items_omitted_cause="max_items"`**——故**并非「逐字节不变」**（原文措辞已被对抗字节 diff 证伪，见 `grill-adversarial.md` C4/M4）。T5 按「值不变 + 新增键」锁，不锁「逐字节」。

### D4 — 零噪声：不截断不发字段

`max_items=0` 且预算充足 ⇒ `declared == expanded` ⇒ 不发 `items_omitted`/`items_omitted_cause`（仅可能发 `items_declared`，与 #279 现状一致）。与 #279 的「无截断不报」纪律一致。

### D5 — 与 #279 的「`max_items=0` 不报**静态**截断」不冲突（ADDED 新 Requirement，非改判定）

#279 的 spec Scenario「max_items=0 不报静态截断」说的是：`max_items=0` **不静态截断**，故 SHALL NOT 报**静态**截断。#286 报的是**预算**截断——**不同现象**。二者不冲突：新 Requirement 独立声明「预算截断 SHALL 报」，既有 Scenario 仍成立（没有静态截断可报）。delta 用 **ADDED** 新 Requirement，并对既有 Requirement 做 **MODIFIED**（仅把 `items_omitted` 的表述收敛为「与成因判别字段配对」，语义不放松）。

### D6 — 成因判别的**粒度**：粗粒度 `"budget"`（**用户拍板 OQ3**）

`_remaining_expansion_capacity`（`scheduler.py:2726`）取 `min(C4 max_total_runs 剩余, C2 max_runs 剩余, C2 max_nodes 剩余)`——**哪个维度绑定**截断对「如何调参」有价值（调 `max_runs` 还是 `max_total_runs`）。实测绑定维度随图/配置而变：source 60 + `max_runs=25` 绑 **max_runs**（cap=24）；`max_nodes=25` 绑 **max_nodes**（cap=23）；配置 `budget.max_total_runs=12` 绑 **max_total_runs**（cap=11）。**用户 2026-10-03 拍板 OQ3 = 粗粒度 `"budget"`**（不细化到 `"budget:max_runs"`）：三个维度的剩余值**已在同一信封的 `limits`/`budget`**（`_limits_report`/`_budget_summary`）里可见，模型已能自行判断调哪个；细化需在切片点回传「绑定维度」（新增 `NodeState` 只读字段 + argmin），扩大测试面，非本 change 必需。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| **成因字段撞 `reason` 键**（D2） | 用独立扁平名 `items_omitted_cause`；测试断言运行期 `reason`（终态原因）不被覆盖 |
| **运行期新字段被 `_bounded_node` 白名单丢弃**（D3） | 复用 `_attach_foreach_visibility` 的**后写**位置（`parent_envelope()` 之后）；`RunWorkflow` 与 `GetWorkflow(detail='nodes')` **两条**路径都在 `parent_envelope()` 之后补写；测试断言两个出口**都**真能看到 |
| **`RunWorkflow` 信封出口是新增路径**（OQ2=(b)） | `_drive_scheduler`（`subagents.py:934`）返回 `scheduler.parent_envelope()`——与 `GetWorkflow(detail='nodes')` 同源；后写挂到**返回值**上（`RunWorkflowTool.execute` 拿到 envelope 后补 `_attach_foreach_visibility`）；一条专门回归测试断言 `RunWorkflow(spec=...)` 返回的 fan 节点带三元 + 成因 |
| **静态路径回归**（去 `max_items>0` 前置误改） | T5 回归：`max_items>0` 的 `items_declared`/`items_omitted` **值**不变（`items_omitted_cause="max_items"` 为**新增键**，非值改） |
| **`max_items=0` 且不截断时误报** | D4：`declared == expanded` 不发；T4 锁零噪声 |
| **dry run 实际撞不到预算截断**（假 LLM 产出太小） | **已实测可行**（`grill-design.md` C2/Q5）：字面 60 + 上游 planner（占 1 run）确定性得 60/24/36；source 驱动需 `script`。T1 按此构造 |
| **非 terminal 时图已响亮 raise，字段冗余** | **用户拍板 OQ4 = 无条件发**（不抑制）；响亮路径上读同两份 state、O(1)、无害 |
| **`items_declared` 在 dry-run source 驱动下是模拟值**（#279 Q5） | 沿用 `items_declared_simulated` 标记（D3 代码保留该分支）；**用户拍板 OQ6 = 接受** `items_omitted` 自身不加 simulated 标记 |
| **`GetWorkflow` 默认 `detail='summary'` 不带字段**（M1，如实记录） | 本 change 不改 `summary` 出口（总览档，本不承载 per-node 可见性字段）；字段只在显式 `detail='nodes'` 出现，文档写明 |

## 已决 Open Questions（grill + 对抗 + 用户停轮确认，**已闭环**）

详见 `reviews/grill-design.md` 的 `## Open Questions`（7 条）与 `## User Confirmation`（Q1–Q6 逐条答复）。

- **OQ1（成因字段命名）** = `items_omitted_cause`（取值 `"max_items"` / `"budget"`）。
- **OQ2（出口范围）** = **(b) 扩到 `RunWorkflow` 结果信封**（有意扩范围，一并补 #279 静态字段）；三出口清单见 D1；`GetWorkflow` 默认 `detail='summary'` 不带字段（M1，如实记录，不改）。
- **OQ3（成因粒度）** = 粗粒度 `"budget"`（不细化到绑定维度）。
- **OQ4（非 terminal 响亮路径）** = 无条件发字段（不抑制）；边界文字修正见 Context 节。
- **OQ5（dry run 可行性）** = 可行；T1 用「字面 60 + 上游 planner」构造（确定性 60/24/36）。
- **OQ6（`items_omitted` 无 simulated 标记）** = 接受现状（模型据 `items_declared_simulated` 打折理解）。

## Testing Strategy

- **新增**（并入既有 `tests/agent/subagent/test_foreach_truncation_visibility.py`）：
  - **T1**：`max_items=0` + **字面 60 项 + 上游 planner（占 1 run）** + `max_runs=25` ⇒ dry-run 条目 `items_declared=60 / items_expanded=24 / items_omitted=36` + `items_omitted_cause="budget"`（用户拍板 OQ5 的确定性构造；零 script）；
  - **T2**：同图**运行期** `GetWorkflow(detail='nodes')` 同三元 + 成因；
  - **T2b（新增出口）**：同图 `RunWorkflow(spec=...)` 的**结果信封** fan 节点带同三元 + 成因（OQ2=(b) 的专门回归）；
  - **T3**：`max_items>0` 静态 ⇒ `items_omitted_cause="max_items"`；`max_items=0` 预算 ⇒ `"budget"`；
  - **T4**：`max_items=0` + 预算充足 ⇒ 无 `items_omitted`/`items_omitted_cause`；
  - **T5**：`max_items>0` 静态路径**值**不变（`items_declared`/`items_omitted` 不变，新增 `items_omitted_cause`）。
- **回归**：`test_foreach_truncation_visibility.py`（#279，18 条）、`test_dynamic_foreach.py`（Q9 口径）；全量 `uv run pytest -q`。

## Pre-Implementation Review

**已完成**（`reviews/grill-design.md` + `reviews/grill-adversarial.md`）：

- grill（独立零记忆 subagent）产出 6 条 Confirmed Decisions（全部带探针证据）+ 7 条 Open Questions。
- 对抗验证（独立零记忆 subagent）逐条证伪：**6 条 Confirmed Decisions 全部 survives，无承重结论被翻案**；坐实两处文档文字错误（非 terminal 边界、静态路径「逐字节不变」），发现 `RunWorkflow` 信封缺口（M1/M2）。
- 用户 2026-10-03 停轮确认 OQ1–OQ6（记录于 `grill-design.md` 的 `## User Confirmation`）。
- 本 design 已按上述结论回写（D1 三出口 / D2 字段名 / D3 措辞 / D6 粒度 / 风险表 / 边界文字）。

## Impact Analysis（design 视角的补充）

见 `proposal.md`。补充：**本 change 是 #279 共享 helper 的扩展**（`_foreach_visibility_fields` 去 `max_items > 0` 前置、加成因），静态路径**值**不变（T5，新增键除外）；预算路径的 `items_declared` 已由 `_resolve_items:2675` 记录，**不改 `_resolve_items`**；新字段须**后写**——`GetWorkflow(detail='nodes')`（既有位置）与 **`RunWorkflow` 结果信封**（OQ2=(b) 新增路径）两处都在 `parent_envelope()` 之后补写，绕过 `_bounded_node` 白名单。**出口从两增到三**（+`RunWorkflow` 信封）；`GetWorkflow` 默认 `detail='summary'` 不带字段（M1，如实记录，不改）。
