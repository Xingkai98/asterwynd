# Design: 纯门控边的独立状态

## Context

`workflow_graph_snapshot()` 的边状态是**五档**（`inactive` / `ready` / `active` / `passed` / `blocked`，`agent/subagent/scheduler.py::_edge_status`），由 #190 定型、#197 补过 `passed` 的 per-edge 记账。

用户 #197 实测发现：`scan→fan`（`fan` 用**字面 items**，从不读 scan 产出）跑完**显示为灰色**，而 `scan→fragile`（读了）是绿的——尽管两条边在「执行顺序」上完全一样（都是 `required`，都门控了下游派发）。

根因是 `inactive` 这个**兜底档**同时承载两种语义：真·无关边，与「起了门控作用但没传数据」的边。后者永远命中不了 `passed`（需要 `_consumed_edges` 记账），只能落兜底。

## Goals / Non-Goals

**Goals**

1. 让「依赖已满足但产出未被读取」的边**不再看起来像死线**。
2. 与 `passed`（数据确实流过去了）**视觉可分辨**、且不丢后者承载的观测信号。
3. 图例自动跟随（不新增手工维护的文案分支）。

**Non-Goals**

- **不改 `passed` 的语义**（仍是「上游产出被下游读走」）——C5 的冗余度指标依赖它。
- **不追求覆盖所有「曾起门控作用」的组合**（见 D4 的边界）。
- 不做边捆绑 / 力导向等几何层方案（#197 已排除）。
- 不改 `_consumed_edges` / `_mark_consumed` / `_consumed_run_ids`（C5 口径零漂移）。

## Decisions

### D1 — 判据与优先级位置

**新档 `satisfied`**，判据（四个条件同时成立）：

```python
# source/target 的 None 是**防御性分支**：真实图不可达
# （_states 由 plan.nodes 构造，边端点已在解析期校验），但省掉它一旦发生
# 就是 AttributeError 打断整张图的快照推送。grill 决策 2。
source is not None and target is not None
    and edge.required and source.status == "completed" and target.status != "pending"
```
（外加「未被消费」——由优先级链保证：`passed` 的判据在本档**之前**，命中即返回。**不需要**再写显式的 `not in _consumed_edges`——那会制造两处真相；能执行到本档本身就是「不在该集合」的证明（grill 决策 6）。）

**放哪**：优先级链的**第 5 档之后、兜底之前**（即 `ready` 之后、`inactive` 之前）。

```
1. 控制边（route）                    → passed / inactive（提前返回，本档不涉及）
2. 被消费过（_consumed_edges）        → passed
3. 目标 blocked/budget_exceeded，
   或源 failed/cancelled              → blocked
4. 源或目标在跑                       → active
5. 源 completed 且目标 pending        → ready
6. 【新】required + 源 completed
   + 目标越过 pending                 → satisfied
7. 兜底                               → inactive
```

**为什么必须在 `ready` 之后**：目标仍 `pending` 时是 `ready`（「上游已就绪、**等待**下游消费」）——那是**进行中**的等待态，不是「已定局的未消费」。两者语义不同，不能合并。

**为什么 `required` 是必要条件**：非 required 边（`required=False`）从不门控派发——它没起过作用，「未消费」就是真的无关，应保持 `inactive`。

### D2 — 视觉编码：同色系靠**明度 + 粗细**拉开

| 档 | 色 | 明度/透明度 | 线宽 | 语义 |
|---|---|---|---|---|
| `passed` | `#4ade80` 绿 | 0.9 | 2.2 | 数据**流过去了** |
| **`satisfied`** | `#86efac` **淡绿** | 0.55 | 1.6 | **依赖满足了，但没流数据** |
| `inactive` | `#475569` 暗灰 | 0.28 | 1.4 | 真的没参与 |

**为什么同色系**：`passed` 与 `satisfied` 都是「这条边起了作用」，同色系让用户先归为一类；再用**明度 + 线宽**区分「有没有数据流」。与 `inactive`（暗灰、最细、最低透明度）拉开距离，不再像死线。

**为什么靠明度而不只靠色相**：#197 已确立「不得仅靠颜色承载语义」的口径（节点侧用角标 + 边框形状做了四重编码）。边侧没有角标位，所以用**明度差 + 线宽差**——转灰度后仍可分辨。

### D2b — 无箭头是**第三重编码**（grill 实测补充，非缺陷）

`renderEdge` 只给 `edge.status === 'passed' || 'active'` 的数据边挂实心箭头（`web/static/workflow.js:685-687`），控制边另挂空心箭头（`:682-684`），其余一律无箭头。所以按 D2/D3 的最小改落地后，**`satisfied` 天然无箭头、`passed` 有箭头**——语义上正好是「有没有数据流过去」。

**这条要写进记录防止实现者「顺手补个箭头」把第三重编码抹掉**：`satisfied` 的「无箭头」与 D2 的「明度 + 线宽」共同构成非颜色维度的可分辨性（对应 spec delta 的「非颜色维度可分辨」口径）。

### D3 — 与 C5 指标的隔离

本档**纯读**既有信号（`edge.required` + `source.status` + `target.status`），**不引入任何新记账**：

- `_consumed_edges` 只读不写；
- `_consumed_run_ids` / `useful_runs` / `redundancy` **逐位不变**；
- `_mark_consumed` 本体不动。

这与 #190 决策 11/12 的红线一致（那条红线管的是「加记账不许污染 C5」，本档连记账都不加）。

### D4 — 边界（明确不做的事）

| 组合 | 结果 | 为什么 |
|---|---|---|
| 目标仍 `pending` | `ready`（非本档） | 「等待消费」是进行中态，语义不同（D1） |
| 边 `required=False` | `inactive` | 没门控过派发，未消费就是真无关 |
| 源 `skipped` / `blocked` / `budget_exceeded` | `inactive`（或 `blocked`，视规则 3） | 源没产出，「没数据流」是**正确**表达，不是误导 |
| 源 `failed` / `cancelled` | `blocked`（规则 3） | 既有语义已正确 |
| route 控制边 | `passed` / `inactive`（规则 1 提前返回） | 控制边不走数据语义 |
| 目标 `failed`（自身失败） | **`passed`**（**实测**，非本档） | 目标所在的 `_execute_subagent` 在启动 run **之前**先求值 `task=self._node_task_text(node)`，而后者在 `if text:` 内就记了账（`scheduler.py:1541-1546`、`:2203-2204`）——所以只要是「上游有产出且目标读了」，边早在 run 跑起来前就已是 `passed`，目标随后怎么失败都不影响。**只有**「上游产出为空」或「目标根本不读输入（如 foreach 字面 `items`）」时，目标失败才落本档 |

**明确 Non-Goal**：不追求把「源非 completed 但曾起过门控作用」的组合也标成 `satisfied`——那些组合里「没有数据」是**准确**的表达，把它们也染绿反而会稀释本档的含义。

## Pre-Implementation Review

> 本 change 为 feature（spec 可见：边词表五档 → 六档），实现前须由**独立零记忆 subagent** 审视本 design 的 D1–D4，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）。实际 review 记录以该文件为准。

## Risks / Trade-offs

- **风险**：边词表在 spec 里**明文列举**（`openspec/specs/web-ui/spec.md` 两处「五档」），改实现不改 spec 会造成 drift → **对策**：spec delta 同步 MODIFIED 两条 Requirement，收尾合入 current spec。
- **风险**：加第 6 档会红**一条**既有前端断言——`tests/web_tests/test_workflow_graph_js.py:94-96` 的 `assert set(styles) == {五档}`（**实测**加 key 后为 False）。**注意（grill 实测修正）**：图例那条**不会**红——`test_workflow_graph_ux_js.py:88-96` 的图例断言是**动态**的（`== set(call("edgeStatusStyles"))`），会随词表自动跟随；浏览器 smoke 只查 4 个文本标签。→ **对策**：更新那一条（改名 / 改断言为六档），这是 spec 变更的正常代价。
- **Trade-off**：六档比五档多一个视觉状态，图例变长一行 → 换「纯门控边不再像死线」。用户已就此拍板（方案 A）。
- **Trade-off**：`satisfied` 与 `passed` 同色系，在极小屏 + 低亮度下可能难分 → 用**线宽差**（2.2 vs 1.6）做第二重编码兜底。

## Testing Strategy

- **后端**（`tests/agent/subagent/test_workflow_graph_snapshot.py`）：
  - 新增：foreach 用字面 items 时 `scan→fan` 判 `satisfied`（复现 issue 场景，实跑）；
  - 新增：`required=False` 的未消费边仍 `inactive`；
  - 新增：目标仍 pending 时仍是 `ready`（不是 `satisfied`）；
  - 回归：既有五档判据全部不变（consumed→passed、failed→blocked、pending→inactive 等）；
  - 更新：`EDGE_STATUS_TIERS` frozenset 加 `satisfied`。
- **前端纯函数**（`tests/web_tests/test_workflow_graph_js.py` / `test_workflow_graph_ux_js.py`）：
  - `EDGE_STYLES` / 图例覆盖六档；
  - `satisfied` 与 `inactive`、`passed` 在**明度或线宽**上可分辨（转灰度可辨的第二重编码）。
- **兼容回归**：`_consumed_run_ids` / `useful_runs` / `redundancy` 逐位不变（C5 红线）。
