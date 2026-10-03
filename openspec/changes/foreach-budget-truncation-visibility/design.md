# Design: foreach 预算截断可见性

## Context

`foreach` 的 `max_items=0` 时，`_resolve_items`（`agent/subagent/scheduler.py:2676-2677`）返回 `items[:self._remaining_expansion_capacity()]`——切片先把集合切到「恰好等于剩余预算」的长度，使后续 `_check_foreach_budget`（`:2167`）的 `runs + delta > limit` 判定**刚好不触发**（等号不通过）⇒ **不 raise、无 omitted 报告**、超预算项**静默丢弃**（实测：60 声明 / 24 展开 / 36 静默丢，`status=completed`、`diagnostics={}`）。本 design 把这条**预算**截断在**模型可见出口**如实报告，与 #279 的**静态**截断报告**同形态**。

### 已核实的事实（本设计的地基）

1. **截断点**：`_resolve_items`（`agent/subagent/scheduler.py:2654-2678`）：`max_items==0` → `items[:remaining_expansion_capacity()]`（**预算截断，本 change 的主角**）；`>0` → `items[:node.max_items]`（静态截断，#279 已治）。**两条路径都先记 `state.items_declared = len(items)`（`:2675`，切片之前）**——故预算截断路径的 `declared` **已被记录**，本 change 无需改 `_resolve_items`。
2. **静默机制**：切片使 `count` = 剩余容量 ⇒ `_check_foreach_budget`（`:2180-2183`）`delta = count - charged`、`runs + delta == limit`（等号）⇒ 不 raise（`:2192`/`:2204` 的 `>` 不成立）。**terminal 且切片后预算够下游**时无人报（非 terminal 会在 `_expand_plan` 撞 `max_nodes` 响亮 raise，见边界）。
3. **两出口共用 helper**：`_foreach_visibility_fields`（`agent/tools/builtin/subagents.py:1122`）是**纯函数**，dry-run（`:1693`）与运行期（经 `_attach_foreach_visibility`，`:1159`）**共用**——本 change 扩展它即天然覆盖两出口。
4. **运行期出口须「后写」**：新字段必须在 `parent_envelope()` **之后**补写（`_attach_foreach_visibility` 已在正确位置，`:1097`），否则被 `_bounded_node` 白名单 `_PARENT_NODE_FIELDS`（`scheduler.py:389`，仅 `id/kind/status/runs/subagent_id/items`）**静默丢弃**（#279 D3 已钉死）。
5. **`reason` 键已占用**：运行期节点 dict（`NodeState.to_dict`，`scheduler.py:187`）与 dry-run 条目（`subagents.py:1684`）**均有 `reason` 键**（终态原因）——成因判别字段 SHALL NOT 叫 `reason`（同 dict 同键覆盖，与 #279 D2 的 `items_total` 覆辙同类）。
6. **`items_declared` 已被 #279 使用**：`state.items_declared`（`scheduler.py:254`）+ dry-run/运行期已投影该字段（`max_items=0` 时 #279 也报 `items_declared`，只是**不带** `items_omitted`——见 `_foreach_visibility_fields` 的 `elif max_items > 0 and declared > expanded` 分支，`:1153`）。

## Goals / Non-Goals

### Goals

- 两出口（dry run / 运行期投影）如实报告 `max_items=0` 预算截断的「声明 N / 展开 M / 省略 K」。
- `items_omitted` 与**成因判别字段**配对，静态 vs 预算两种成因不歧义。
- 零噪声：不截断（declared == expanded）时不报。
- 不退化 #279 的静态截断面；不冲突 #279 的「`max_items=0` 不报**静态**截断」。

### Non-Goals

- 不改 `max_items` 默认值（#276）。
- 不改 `max_items=0` 语义。
- 声明期不适用（预算截断是运行期现象）。
- 成因判别字段不复用 `reason`（D2）。

## Decisions

### D1 — **两出口一致**：dry run / 运行期各报告其所知

| 出口 | 何时可知 | 报告什么 |
|---|---|---|
| **dry run**（`DryRunWorkflow` foreach 条目） | dry run 会**解析**集合并**模拟**预算消耗 | 补 `items_declared` / `items_omitted` + 成因（与既有 `items_expanded` 三元齐） |
| **运行期投影**（`GetWorkflow(detail='nodes')` foreach 节点） | 运行期解析 + 实际预算消耗后 | 同三元 + 成因；**须后写**（D3） |

**为什么声明期不适用**：`DeclareWorkflow` 是纯声明、不运行，而预算截断取决于**运行期已用预算**与**source 解析出的集合大小**——声明期两者皆不知。故本 change **无声明期出口**（与 #279 不同——#279 至少字面 `items` 声明期可知，预算截断连字面 `items` 也要运行到才知道用掉多少预算）。

**dry run 是否会真撞预算截断**：dry-run 的 scheduler 用 spec 声明的 `max_runs`/`max_nodes`，`_resolve_items` 走**同一条**预算切片路径——只要 dry-run 里 source 产出足够大（脚本化假 LLM），就会撞。实现期须用测试确认 dry-run 真能复现（见 Testing Strategy）。

### D2 — 字段名：**复用扁平 `items_omitted` + 新增扁平成因判别字段**（绝不复用 `reason`）

- **复用 `items_declared`/`items_omitted`**：与 #279 同名字段、同一「声明数 / 被丢弃数」语义。`items_declared` 已由 `_resolve_items:2675` 记录、两出口已投影；本 change 让 `items_omitted` 在 `max_items == 0` 且 `declared > expanded` 时**也发**（#279 仅 `max_items > 0` 时发）。
- **新增成因判别字段**（拟名 `items_omitted_cause`，取值 `"max_items"` / `"budget"`）：**绝不能**叫 `reason`——运行期节点 dict 与 dry-run 条目**均已有 `reason` 键**（终态原因），同名会**同 dict 同键覆盖、无报错**（#279 D2 实测 `items_total` 覆辙）。
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

**关键差异**：原 #279 是 `elif max_items > 0 and declared > expanded`；本 change 去掉 `max_items > 0` 前置，改为按 `max_items` 值选成因。静态路径（`max_items > 0`）的输出**逐字节不变**（T5 回归锁）。

### D4 — 零噪声：不截断不发字段

`max_items=0` 且预算充足 ⇒ `declared == expanded` ⇒ 不发 `items_omitted`/`items_omitted_cause`（仅可能发 `items_declared`，与 #279 现状一致）。与 #279 的「无截断不报」纪律一致。

### D5 — 与 #279 的「`max_items=0` 不报**静态**截断」不冲突（ADDED 新 Requirement，非改判定）

#279 的 spec Scenario「max_items=0 不报静态截断」说的是：`max_items=0` **不静态截断**，故 SHALL NOT 报**静态**截断。#286 报的是**预算**截断——**不同现象**。二者不冲突：新 Requirement 独立声明「预算截断 SHALL 报」，既有 Scenario 仍成立（没有静态截断可报）。delta 用 **ADDED** 新 Requirement，并对既有 Requirement 做 **MODIFIED**（仅把 `items_omitted` 的表述收敛为「与成因判别字段配对」，语义不放松）。

### D6 — 成因判别的**可行动性**：是否细化到预算维度？

`_remaining_expansion_capacity`（`scheduler.py:2726`）取 `min(C4 max_total_runs 剩余, C2 max_runs 剩余, C2 max_nodes 剩余)`——**哪个维度绑定**截断对「如何调参」有价值（调 `max_runs` 还是 `max_total_runs`）。但这需在切片处回传「绑定维度」，增复杂度。**候选**：`items_omitted_cause: "budget"` 粒度够用（既有 envelope 的 `limits`/`budget` 已报各维度）；细化到 `"budget:max_runs"` 是可选增强。**留作 Open Question**（OQ3）。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| **成因字段撞 `reason` 键**（D2） | 用独立扁平名 `items_omitted_cause`；测试断言运行期 `reason`（终态原因）不被覆盖 |
| **运行期新字段被 `_bounded_node` 白名单丢弃**（D3） | 复用 `_attach_foreach_visibility` 的**后写**位置（`parent_envelope()` 之后）；测试断言 `GetWorkflow(detail='nodes')` 真能看到 |
| **静态路径回归**（去 `max_items>0` 前置误改） | T5 回归：`max_items>0` 输出逐字段不变（含 `items_omitted_cause="max_items"` 为**新增**、`items_omitted` 值不变） |
| **`max_items=0` 且不截断时误报** | D4：`declared == expanded` 不发；T4 锁零噪声 |
| **dry run 实际撞不到预算截断**（假 LLM 产出太小） | 实现期用脚本化 source 产出 > 容量逼近；若 dry-run 结构性无法触发，如实记录并仅保留运行期出口 + 由 grill/对抗定夺（OQ2） |
| **非 terminal 时图已响亮 raise，字段冗余** | 字段在响亮路径上无害（读的是同 `state.items_declared`/`items`）；OQ4 讨论是否抑制 |
| **`items_declared` 在 dry-run source 驱动下是模拟值**（#279 Q5） | 沿用 `items_declared_simulated` 标记（D3 代码保留该分支） |

## 候选 Open Questions（交 grill 形式化 + 停轮确认）

- **OQ1（成因字段命名）**：`items_omitted_cause` / `items_truncation_cause` / 其它？`reason` 已占用不可用。
- **OQ2（出口范围）**：只 dry run + `GetWorkflow`（对齐 #279），还是**也**补 `RunWorkflow` 的**结果信封** `nodes`？（**实测：连 #279 的静态字段都没进结果信封**——`RunWorkflow` 结果 `nodes` 是 `NodeState.to_dict` + `_bounded_node`，不含后写的可见性字段。对齐 #279 = 两出口；补结果信封 = 扩范围，可能是 #279 也遗留的缺口。）
- **OQ3（成因粒度）**：`"budget"` 粗粒度，还是细化到绑定维度（`"budget:max_runs"`）？
- **OQ4（非 terminal 响亮路径）**：非 terminal 时图已 `graph_recursion_exceeded` 响亮报，是否仍发 `items_omitted`（冗余但一致）？
- **OQ5（dry run 可行性）**：若 dry-run 结构性难撞预算截断，是否接受「本 change 只有运行期出口真正覆盖预算截断」？

## Testing Strategy

- **新增**（并入既有 `tests/agent/subagent/test_foreach_truncation_visibility.py` 或新文件）：
  - T1：`max_items=0` + source 60 项 + 图级预算不足 ⇒ dry-run 条目 `items_declared=60 / items_expanded=24 / items_omitted=36` + `items_omitted_cause="budget"`；
  - T2：同图运行期 `GetWorkflow(detail='nodes')` 同三元 + 成因；
  - T3：`max_items>0` 静态 ⇒ `items_omitted_cause="max_items"`；`max_items=0` 预算 ⇒ `"budget"`；
  - T4：`max_items=0` + 预算充足 ⇒ 无 `items_omitted`/`items_omitted_cause`；
  - T5：`max_items>0` 静态路径输出不回退（值不变）。
- **回归**：`test_foreach_truncation_visibility.py`（#279，18 条）、`test_dynamic_foreach.py`（Q9 口径）；全量 `uv run pytest -q`。

## Pre-Implementation Review

grill 阶段填写（`reviews/grill-design.md`）。**按流程纪律：grill 结论须先走独立对抗验证（`reviews/grill-adversarial.md`）再拍板。**

## Impact Analysis（design 视角的补充）

见 `proposal.md`。补充：**本 change 是 #279 共享 helper 的扩展**（`_foreach_visibility_fields` 去 `max_items > 0` 前置、加成因），静态路径输出不变（T5）；预算路径的 `items_declared` 已由 `_resolve_items:2675` 记录，**不改 `_resolve_items`**；新字段须**后写**（复用 `_attach_foreach_visibility` 位置，绕过 `_bounded_node` 白名单）。
