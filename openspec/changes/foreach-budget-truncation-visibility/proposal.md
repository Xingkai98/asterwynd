# Proposal: foreach 预算截断可见性 — max_items=0 路径不静默丢弃

关联跟踪 issue：[#286](https://github.com/Xingkai98/asterwynd/issues/286)。上游来源：[#279](https://github.com/Xingkai98/asterwynd/issues/279)（`foreach-truncation-visibility`，报告 `max_items > 0` 的**静态**截断）的独立对抗验证拆出的**同缺陷类、范围外**项。

## Change Type

- primary: feature
- secondary:
  - workflow
  - observability

## Why

### 问题：`max_items=0` 的**预算**截断静默丢弃 items

`foreach` 节点的 `max_items=0` 语义是「不静态截断、展开到图级预算耗尽为止」（spec `multi-agent-collaboration` 第 315 行钉死）。实现上，`_resolve_items`（`agent/subagent/scheduler.py:2676-2677`）在 `max_items == 0` 时返回 `items[:self._remaining_expansion_capacity()]`——**切片先把集合切到「恰好等于剩余预算」的长度**。

于是紧随其后的 `_check_foreach_budget`（`scheduler.py:2167`）算 `delta = count - charged`（`count` 已是**切片后**的长度）、判定 `runs + delta > limit` **刚好不触发**（等号不成立即通过）⇒ **不 raise、无任何 omitted 报告**。超预算的项被**静默丢弃**。

**实测（2026-10-03，本机复现）**：`{source: planner, source_field: items, max_items: 0}`，planner 产出 **60** 项、图级 `max_runs=25`（planner 占 1 run）。`_remaining_expansion_capacity()` = `min(25-1, …)` = **24** ⇒ `_resolve_items` 返回 `items[:24]`、**36 项静默丢弃**：

```
declared (items_declared): 60
expanded (fan state.items): 24
fan envelope keys: ['id','items','kind','reason','runs','status','subagent_id','subagent_ids','summary']   # 无 items_omitted
result status: completed
diagnostics: {}                   # 空
items_omitted in envelope: False  # 无任何信号
```

即：**模型以为「对 60 个东西各做一次」，实际只做了 24 个，`status=completed`、`diagnostics={}`、全程无人告知。**

### 为什么算 defect（按项目自己的标准）

项目在别处严格执行「不静默截断、显式报告省略数」，#279 刚补上了**静态**截断（`max_items > 0`）的报告面：

| 截断点 | 报告字段 | 状态 |
|---|---|---|
| 节点数超 `max_nodes` | `nodes_omitted` | 已报 |
| 报告的 warnings 超限 | `warnings_omitted` | 已报 |
| foreach 展开项的 result_ref 超限 | `item_refs_omitted` | 已报 |
| foreach `max_items > 0` 静态截断 | `items_declared`/`items_omitted` | **#279 已报** |
| **foreach `max_items = 0` 预算截断** | **（无）** | **本 issue** |

**唯独这一条路径不报**——与 #248/#273/#275/#279 一直在消除的「静默行为模型看不见」同型。

### 边界（如实）

- **不是 spec 违规**：spec 规定 `max_items=0` = 展开到预算耗尽（隐含有截断），**未规定预算截断须报告**。本 change 是**透明性缺陷**修复 + 报告面扩展。
- **静默窗口 = 切片后预算仍够整张图跑完**（**已由对抗实测修正**，原稿「非 terminal 一律响亮」**是错的**）。实测（`reviews/grill-adversarial.md` Q4，`fan → root(strategy='collect')` 非 terminal，60 项，`max_items=0`）：`max_runs ≤ max_fan_in(=10)` ⇒ **静默**（`status=completed`、`diagnostics={}`、`fan.items=10`，与 terminal 完全相同——切片 ≤ `max_fan_in` 不插 auto-agg 层、下游 collect 不跑模型）；`max_runs ≥ 11` 才响亮 `graph_recursion_exceeded`（插入的 auto-agg 层要吃一个 run）。改动 config 把 `max_fan_in` 改 4，阈值精确移到 4/5。故「terminal vs 非 terminal」不是判据，**「切片后预算是否仍够图跑完」才是**。
- **与 #278（OOM）无关**：那次真实运行模型恰用了 `max_items: 0`，但那是内存问题，与截断报告无关。

## What Changes

1. **dry run 报告**：`DryRunWorkflow` 的 foreach 条目在既有 `items_expanded` 旁补 `items_declared`（声明集合大小）与 `items_omitted`（被截断丢弃的项数）——**当 `max_items=0` 且 `declared > expanded`（真预算截断）时也发**（#279 只在 `max_items > 0` 时发）。使 dry run 能显示「展开 24 / 共 60 / 省略 36」。
2. **运行期报告（三出口）**：运行期**两个**模型可见出口的 foreach 节点都暴露预算截断信号（`items_omitted`），同 #279 的**后写**机制（绕过 `_bounded_node` 白名单）：
   - `GetWorkflow(detail='nodes')` 的 foreach 节点投影（#279 既有出口）；
   - **`RunWorkflow` 的结果信封** `nodes`（**用户 2026-10-03 拍板 OQ2=(b) 新增出口**——实测该信封**连 #279 的静态字段都没有**，模型跑完图**最自然的读法**会全静默；补此出口一并把 #279 静态字段补上，属**有意扩范围**）。
   - 边界（如实记录）：`GetWorkflow` 的**默认** `detail='summary'` 只有 bounded 节点、不带这些可见性字段；字段只在**显式** `detail='nodes'` 出现。本 change 不改 `summary` 出口。
3. **判别字段**：`items_omitted` 需与一个**判别字段**配对，区分截断**成因**——**用户 2026-10-03 拍板 OQ1 = `items_omitted_cause`**，取值 `"max_items"`（静态截断）/ `"budget"`（预算截断）。因运行期/dry-run 两处条目 dict **均已有 `reason` 键**（节点/条目终态原因），判别字段 SHALL NOT 用裸 `reason`（同 dict 同键覆盖，与 #279 D2 的 `items_total` 同类教训，见 D2）。**用户拍板 OQ3 = 粗粒度 `"budget"`**（不细化到绑定维度）。

**不变**：`max_items` 默认值（20）、`max_items=0` 语义（不静态截断、展开到预算耗尽）、#279 已建立的**静态**截断报告面的**字段值**（`items_declared`/`items_omitted` 在 `max_items > 0` 时数值不变；新增 `items_omitted_cause` 一个键）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `multi-agent-collaboration`：
  - **ADDED** 新 Requirement「foreach 预算截断可见」——`max_items == 0` 且 `items` 被图级预算截断时，系统 SHALL 在模型可见出口（dry run / `RunWorkflow` 结果信封 / `GetWorkflow(detail='nodes')` 投影）如实报告「声明 N / 展开 M / 省略 K」+ 成因判别，SHALL NOT 静默丢弃。
  - **MODIFIED** 既有 Requirement「foreach 静态截断可见」——明确 `items_omitted` 与**成因判别字段**配对（使静态/预算两种成因的 `items_omitted` 不歧义），并保持「`max_items=0` 不报**静态**截断」口径不变（#286 报的是**预算**截断，非静态）。

## 验收（本 change 的验收口径，**只进 proposal、不进 spec**）

| # | 指标 | 主/辅 |
|---|---|---|
| **T1** | `max_items=0` + **字面 60 项 + 上游 planner（占 1 run）** + `max_runs=25` ⇒ dry run 条目含 `items_declared=60` / `items_expanded=24` / `items_omitted=36` + `items_omitted_cause="budget"` | **主指标** |
| **T2** | 同上图**运行期** `GetWorkflow(detail='nodes')` 的 fan 节点含同样三元 + 成因判别（**后写**可见） | **主指标** |
| **T2b** | 同上图 `RunWorkflow(spec=...)` 的**结果信封** fan 节点含同样三元 + 成因（OQ2=(b) 新增出口） | **主指标** |
| **T3** | 成因判别：`max_items>0` 静态截断（`items_omitted_cause="max_items"`）与 `max_items=0` 预算截断（`"budget"`）取值不同 | **主指标** |
| T4 | 零噪声：`max_items=0` 且预算充足（declared == expanded）时不产生任何 `items_omitted`/`items_omitted_cause` 字段 | 辅 |
| T5 | #279 不退化：`max_items>0` 静态截断的既有报告面**值**不变（`items_declared`/`items_omitted` 值不变；`items_omitted_cause` 为新增键） | 辅 |
| T6 | 不退化：既有 workflow 测试全绿（含 `test_foreach_truncation_visibility.py` 18/18、`test_dynamic_foreach.py`） | 辅 |

**通过门槛**：T1 + T2 + T2b + T3 成立（三出口一致可见 + 成因可判别），T4 无假报，T5/T6 不退化。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 命中 `light` 判据「**常规功能增强；成熟模式的局部应用**」。本 change 是项目内**已有**的「不静默截断」范式（`nodes_omitted`/`warnings_omitted`/`item_refs_omitted`，及刚合入的 #279 `items_declared`/`items_omitted`）在**同一 foreach 截断点的第二条路径**（预算截断）上的局部应用，不引入新框架/新协议/新依赖。不判 `full`：非架构级改造，形态已被同仓四处先例钉死。不判 `exempt`：虽形似 bugfix，但**新增了成因判别字段（能力面）**，非「无新增能力面」。
- research questions:
  - **RQ1**：截断报告的**字段命名与出口形态**，项目内既有先例怎么做的？（对齐即可，不必新造。）
  - **RQ2**：成因判别用**扁平字段**还是**嵌套对象**？（#279 对抗已否决嵌套——违背项目扁平先例。）
- findings:
  1. **项目内四处同型先例已钉死形态**：`nodes_omitted`（`scheduler.py`，`max(total - limit, 0)`）、`warnings_omitted`（`subagents.py:1661`）、`item_refs_omitted`（`subagents.py:1187`）、`items_declared`/`items_omitted`（#279，`subagents.py:1122`）——**统一是「`X_omitted = max(total - shown, 0)`」+ 一个 `X_total`/`X_declared`**，且**全扁平**（`_graph_node_projection`/`_attach_item_refs`/`_attach_foreach_visibility` 皆扁平）。本 change 复用既有 `items_declared`/`items_omitted`、只**新增一个扁平成因判别字段**，不新造词表。
  2. **#279 已建立后写机制**：`_foreach_visibility_fields`（`subagents.py:1122`）是 dry-run 与运行期**共用**的纯函数；运行期出口经 `_attach_foreach_visibility`（`subagents.py:1159`）在 `parent_envelope()` **之后**后写（绕过 `_bounded_node` 白名单 `_PARENT_NODE_FIELDS`，`scheduler.py:389`）。本 change **扩展同一 helper**（加成因参数）而非新写，天然覆盖 dry-run 出口；运行期**两**出口（`GetWorkflow(detail='nodes')` + `RunWorkflow` 信封）共用 `_attach_foreach_visibility` 后写。
  3. **成因判别字段必须避开既有 `reason` 键**：#279 D2 的教训——运行期节点 dict（`NodeState.to_dict`，`scheduler.py:187`）与 dry-run 条目（`subagents.py:1684`）**均已有 `reason` 键**（终态原因）。判别字段若也叫 `reason` 会**同 dict 同键覆盖、无报错**（实测 `items_total` 覆辙）。故用**独立扁平名** `items_omitted_cause`（用户拍板 OQ1）。
  4. **`RunWorkflow` 结果信封是既有缺口**（对抗实测 M1/M2）：`RunWorkflow` 返回的 `parent_envelope()` 的 `nodes` 经 `_bounded_node` 过滤，**连 #279 的静态字段都没有**；模型跑完图直接读信封**最自然的读法**会全静默。用户拍板 OQ2=(b) 补此出口。
  5. **无本地参考仓库同款**（`/home/shared/agent-study/reference-repos/`）：这是本项目自有的 workflow DSL 概念（foreach/`max_items`/图级预算），业界框架无直接对应；形态依据来自**项目内先例**（finding 1–4）而非外部。本地参考仓库对本 change 非必需（`.dev/reference-repos.txt` 为工作区本地配置、不提交）；不构成 exempt 理由，此处如实记录。
- design impact: 见 design D1（三出口一致）、D2（复用 + 成因判别字段 `items_omitted_cause`，避开 `reason`）、D3（扩展共享 helper）、D4（零噪声）、D5（与 #279「不报静态截断」不冲突）、D6（成因粗粒度 `"budget"`）。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（workflow DSL 的 foreach 行为 + 报告面）。
- **代码**:
  - `agent/tools/builtin/subagents.py` — 扩展 `_foreach_visibility_fields`（`:1122`）与 `_attach_foreach_visibility`（`:1159`）：`max_items == 0` 且 `declared > expanded` 时也发 `items_omitted` + `items_omitted_cause`；dry-run foreach 条目（`:1687-1700`）与运行期后写共用。**新增**：`RunWorkflowTool.execute` 拿到 `envelope = await _drive_scheduler(scheduler)`（`:1402`）后，对 `envelope["nodes"]` 补跑 `_attach_foreach_visibility`（OQ2=(b) 新增出口，与 `GetWorkflow(detail='nodes')` 同源后写）。
  - `agent/subagent/scheduler.py` — `_resolve_items`（`:2675`）已在切片前记 `state.items_declared`，本 change **不改**（复核预算截断路径亦经此点）；成因粒度粗粒度 `"budget"` 无需回传绑定维度。
- **测试**:
  - **必须新增**：T1（dry-run）、T2（`GetWorkflow(detail='nodes')`）、**T2b（`RunWorkflow` 信封）**、T3（成因判别）、T4（零噪声）。
  - **必须回归**：`tests/agent/subagent/test_foreach_truncation_visibility.py`（#279，18 条）、`tests/agent/subagent/test_dynamic_foreach.py`（Q9 预算截断口径）；全量 `uv run pytest -q`。
- **文档**:
  - `openspec/specs/multi-agent-collaboration/spec.md`（ADDED 1 + MODIFIED 1；受保护路径）。
  - `docs/openspec-change-backlog.md`（受保护路径）。
  - `README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描（预计无需改——内部 DSL 报告面）。
- **流程（process）**: 触及受保护路径，需结构化事件 + grill + building review；实现须独立 worktree、`foreach-budget-truncation-visibility/2026-10-03` 分支。**change type = feature → 实现前必须走 `batch-grill-me` + 停轮确认 Open Questions**；**grill 结论须先走独立对抗验证**（`reviews/grill-adversarial.md`）。
- **与既有 change / issue 的边界**:
  - **#279**（静态截断可见）：本 change 是**同缺陷类第二条路径**，复用其形态与 helper；**不改**其静态行为。
  - **#276**（上限数值重估）：参数 vs 报告，独立。
  - **#248/#273/#275**（不静默截断线）：同纪律，本 change 补齐预算截断点。
  - **#283/#285**（内存）：无关。
- **代价权衡**: dry-run/运行期多点计数与一次 `declared > expanded` 比较（O(1) 级）；`_resolve_items` 已记 `items_declared`，无额外热路径开销。
- **可回滚性**: 改动集中在共享 helper 的一个分支 + 一个字段；回滚 = revert，无数据迁移。

## Non-Goals（摘要）

- **不改** `max_items` 默认值（20）——参数另议（#276）。
- **不改** `max_items=0` 语义（不静态截断、展开到预算耗尽）。
- **不把**「静态截断」与「预算截断」合并成同一个无判别字段——两者成因不同，SHALL 由判别字段区分（D2）。
- **不做**「声明期预测预算截断」——预算截断是**运行期**现象（声明期不知 source 集合大小、不知运行期已用预算），声明期本就不适用。
- **成因判别字段** SHALL NOT 复用既有 `reason` 键（同 dict 同键会覆盖，D2）。
- **不细化**成因到预算维度（`"budget"` 粗粒度，用户拍板 OQ3）——绑定维度已见 envelope 的 `limits`/`budget`。
- **不改** `GetWorkflow` 的默认 `detail='summary'` 出口（不带可见性字段；M1 如实记录，本 change 只覆盖显式 `detail='nodes'`）。
- **不改** 静态报告面的**字段值**（`max_items > 0` 时 `items_declared`/`items_omitted` 数值不变；`items_omitted_cause` 是新增键，非改动既有值）。
