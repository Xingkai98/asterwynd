# Design: workflow 终态与因由如实表达（workflow-terminal-honesty）

## Context

三个 bug 同源：**图的终态与因由没有如实反映「实际发生了什么」**。它们的共同触发场景是**回边环**（route + 回边），而回边环恰是本项目 `patterns.py` 的 `review_loop` 形态——不是边角场景。

排查中确认的两个关键事实（决定了改动面）：

1. **`_reset_subtree` 只在「回边是数据边」时走回发起者**。官方 `review_loop` 的回边是 `gate`(route) → `producer`，属**控制边**；而 `data_outgoing` **不含控制边**，递归永远不会走回 gate。所以官方 pattern 天然免疫，只有「回边从非 route 节点出发」才触发——**而那正是按「回边」直觉会写出来的形状**。
2. **`stalled` 与 `failed` 必须分开**。`failed` 已被「节点执行失败」占用（`completed_with_failures` 依赖它）。若把「零节点成功」也记成 `failed`，则「有节点失败」与「图没跑起来」不可分辨——而这两者对用户的行动指引完全不同（去看哪个节点失败 / 去查为什么一个都没跑）。

## Goals / Non-Goals

**Goals**

- 图级终态在「零节点成功」时不再报 `completed`
- 节点因由指向真实成因（图级闸门 / 入边互等），不用一句兜底文案覆盖
- 回边重跑不清空发起者状态
- **契约同步**：新档进入 `TERMINAL_STATUSES` 的两个副本 + 前端配色/图例/文案

**Non-Goals**

- 不修空转环本身（它在语义上就该撞 `max_routes`）
- 不做 #219 的模型面提示与声明期校验（另立 change）
- 不改 `max_routes` 语义

## Decisions

### D1 — 新增图级终态 `stalled`，判据为「零 completed 且零 failed」

`_terminal_converged_status()` 的判据从二档扩为四档（**优先级即语义，先命中先返回**）：

| 条件 | 终态 | 含义 |
|---|---|---|
| `completed_count > 0` 且 `failed_count > 0` | `completed_with_failures` | 跑了，但有节点失败（既有） |
| `completed_count > 0` 且 `failed_count == 0` | `completed` | 跑了，全成功（**含义收窄**） |
| `completed_count == 0` 且 `failed_count > 0` | `failed` | 全挂，没一个成功 |
| `completed_count == 0` 且 `failed_count == 0` | **`stalled`** | 压根没跑起来（死锁 / 全被挡） |

**为什么新增独立档而不是复用 `failed`**：业界 Airflow/Prefect 把「无成功」并入 FAILED 是因为它们的 `failed` 语义本就宽（含 `upstream_failed`）。本项目 `failed` 的语义已被节点级占用且 `completed_with_failures` 依赖它，混用会造成不可分辨。新增 `stalled` 与 `completed_with_failures` 形成对称（「跑了但有失败」/「压根没跑」）。

**`completed_count` 的口径**：`state.status == "completed"` 的**节点**数（与快照 `completed` 计数同源）。**不含** `skipped`——`skipped` 是「未选中」，不等于「跑成功了」。

**`budget_exceeded` / `cancelled` / `graph_recursion_exceeded` 优先级不变**（既有权衡：预算停与取消是更强的停止原因），仍先于本表的四个档。

> **实现顺序硬要求**：`_terminal_converged_status()` 只在既有 `if self._budget_stop: ... else: ...` 的 **else 分支**里被调用（`scheduler.py:884`），四个档的判定必须都在其中，不得上移。

### D2 — 零完成且零失败时的「有没有 blocked」不影响档位

`stalled` 的判据**不要求**存在 `blocked` 节点。理由：零 `completed` + 零 `failed` 的收敛，其成员只可能是 `blocked` / `skipped` / `pending`（收敛后应无 pending），无论哪种组合都满足「图没跑起来」这一事实。加「必须存在 blocked」只会引入一个**在某些图形态下不成立的边条件**，让判据更脆。

### D3 — 节点因由分档：图级闸门穿透 + 入边互等说明

`_resolve_pending_status()`（`scheduler.py:1295` 附近）的兜底文案改为**按真实成因分档**：

| 成因 | 因由文案 |
|---|---|
| 图级闸门触发（`self._diagnostics` 非空） | `图级闸门 {reason} 触发（{diagnostics.message}），本节点未派发` |
| 入边互相等待（无图级闸门） | `入边互相等待（{上游 id 列表}），本节点永远未就绪` |
| 其它兜底 | 保留原文案 |

**为什么「入边互等」要单独一档**：实测确认（issue #218 的「补充实测」）——**无任何图级闸门、`diagnostics` 为空**的死锁场景下，节点因由**依然是**那句 `workflow ended before the node became ready`。所以这不是「有闸门时没穿透」的单点问题，而是**兜底文案不区分成因**的系统性问题。只修「闸门穿透」会漏掉死锁形态。

**穿透的 bounded 要求**：`diagnostics.message` 可能较长，注入 `state.reason` 时必须**截断**（复用 `_SUMMARY_LIMIT` 同口径）。`state.reason` 是 `_envelope` 的字段，**本体语义不得改变**（既有 spec 已有此约束，见 `web-ui` 的 workflow 快照 Requirement）。

### D4 — `_reset_subtree` 增加「发起者豁免」

`_reset_subtree(state, *, origin)` 沿 `data_outgoing` 递归时**跳过 `origin`**（本次派发的发起节点）。

**为什么是豁免而不是停止传播**：回边场景下，`origin` 的下游里既包含「需要重跑的下游」（正常语义，G11 的立项目的），也包含「origin 自己」（回边造成）。只豁免 origin 一个节点，既不破坏 G11 的重跑语义，又避免清空刚写完的结果。

**调用点**（共 3 处，`scheduler.py:1509/1626` 及自身递归）都要透传 origin：
- `_execute_route` 的派发循环：`origin = state.node.id`（route 自己）
- 其它调用点：`origin` 为发起重跑的那个节点

**G11 回归红线**：`_reset_subtree` 必须仍然清 `reason`/`error`/`summary`/`finished_at`/`status`/`activations`/`verdict`/`targets`（否则「重跑时显示上一轮失败因由」与「负耗时」会回归）。本改动**只加豁免**，不减任何清理项。

### D5 — `TERMINAL_STATUSES` 双副本同步（硬要求）

新增 `stalled` 必须同时进入：
- scheduler 侧 `TERMINAL_STATUSES`（`scheduler.py`）
- 快照补发池 `_SNAPSHOT_TERMINAL_STATUSES`
- 前端 `web/static/workflow_graph.js` 的 `TERMINAL_STATUSES`

**漏同步的后果**（#197 已踩过同类坑）：该图被当成 running → 永不进入 tab 淘汰池 → 每次 ws 重连都补发。

**机械保障**：补一条测试断言三个副本的集合相等（而非各自断言「包含 stalled」）——前者能防未来新增档时再次漂移。

### D6 — 前端编码：`stalled` 的视觉与文案

`stalled` 是**异常终态**（非良性），视觉上须与 `completed` 明确区分：

- 配色：区别于 `completed` 绿与 `failed` 红——取**深琥珀/暗橙**（既有 `budget_exceeded` 的橙**不可复用**，二者会混淆）
- tab 徽标文案：`停滞（无节点完成）`
- 图例：说明「图收敛时没有任何节点成功执行」

**与 `budget_exceeded` 的区分**：`budget_exceeded` 是「预算耗尽而停」，`stalled` 是「结构性停（互等/全被挡）」。二者可能同时成立——按 D1，**预算优先**（既有口径），即 `stalled` 不会覆盖 `budget_exceeded`。

## Pre-Implementation Review

> 本 change 含 `feature`（spec 可见：图级终态词表扩档 + 节点因由分档），实现前须由**独立零记忆
> subagent** 审视本 design 的 D1–D6，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions +
> Open Questions 停轮确认）。实际 review 记录以该文件为准。
>
> 三个 bug 的实证与复现见 `diagnosis.md`。

## Testing Strategy

### 后端（`tests/agent/subagent/`）

**三个 bug 的确定性回归**（本 change 的复现脚本可直接作基础）：

- **#217**：`route` 回边 `required=true` 的入口互等 → 图级 status **SHALL NOT** 为 `completed`
- **#218 形态 A**：`max_routes` 撞线 → 被牵连节点 `reason` **含** `max_routes` 与上限值；**不含**仅有兜底文案
- **#218 形态 B**：无图级闸门的死锁（`diagnostics` 为空）→ 节点 `reason` 说明「入边互等」；**不含** `workflow ended before`
- **#220**：回边为数据边 → `_reset_subtree(body)` 后 `cycle_gate` 的 `status`/`targets`/`summary` **保持**；选中的控制边判 `passed` 而非 `inactive`

**四档判据的边界矩阵**（每格一条）：

| completed | failed | 期望 |
|---|---|---|
| >0 | >0 | `completed_with_failures` |
| >0 | 0 | `completed` |
| 0 | >0 | `failed` |
| 0 | 0 | `stalled` |
| 0 | 0 且 `budget_stop` | `budget_exceeded`（优先） |

**契约同步**：三副本（scheduler `TERMINAL_STATUSES` / `_SNAPSHOT_TERMINAL_STATUSES` / 前端）**集合相等**断言。

**G11 回归红线**：陈旧因由 / 负耗时两条既有测试必须保持绿。

### 前端（`tests/web_tests/`）

- `stalled` 的配色 / tab 文案 / 图例与 `completed`、`budget_exceeded` 可分辨
- 既有前端断言若因新增档位而红（精确集合相等式），按新档位更新并加注释

### 变异验证（硬要求）

每个新测试都要能被「改坏实现」杀死，至少覆盖：四档判据（逐档去掉该分支）、因由三档（逐档回退成兜底文案）、origin 豁免（去掉跳过）、三副本同步（从某一副本移除 `stalled`）。

### 全量

- `uv run pytest tests/agent/subagent/ tests/web_tests/ -q`
- `uv run pytest -q`（仓库全量）

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| `completed` 含义收窄破坏既有断言 | 中 | 全量跑 `tests/agent/subagent/`；既有测试若断言「零完成图报 completed」，按新语义更新并加注释说明 |
| `stalled` 漏同步到某个消费方 | **高** | D5 的三副本等价测试 + 全量回归 |
| `_reset_subtree` 改动破坏 G11 | **高** | G11 的既有回归测试必须保持绿；本改动只加豁免不减清理项（D4） |
| 因由文案变更破坏既有断言 | 中 | 因由是 bounded 字符串，测试多为「含关键词」，逐条核对 |
| 新增档位被误用为「失败的委婉说法」 | 低 | `stalled` 是异常终态，前端文案明确「图没跑起来」，不给「一切正常」的暗示 |

**Trade-off（明确记录）**：新增一个对外状态词的成本，换来「有节点失败」与「图没跑起来」可分辨。若选「并入 `failed`」，成本更低但会永久失去这个区分——而用户当前的核心诉求恰恰是**分清「哪里出问题了」**。

## Impact Analysis

（与 `proposal.md` 的同名章节同源；此处补充实现层的具体落点）

**改动落点**

| 落点 | 文件:符号 | 说明 |
|---|---|---|
| 图级档位 | `scheduler.py:_terminal_converged_status` | 二档 → 四档 |
| 因由分档 | `scheduler.py:_resolve_pending_status` | 兜底文案 → 三档 |
| 重跑豁免 | `scheduler.py:_reset_subtree` + 3 处调用点 | 加 `origin` 参数 |
| 终态集合 | `scheduler.py:TERMINAL_STATUSES` / `_SNAPSHOT_TERMINAL_STATUSES` | 同步 |
| 前端集合 | `workflow_graph.js:TERMINAL_STATUSES` | 同步 |
| 前端视觉 | `workflow_graph.js` 的 `GRAPH_STATUS_COLORS` / `NODE_COLORS` 附近 | `stalled` 配色 + 文案 |

**测试影响**

- 新增：三个 bug 各一条确定性回归 + 四档判据的边界矩阵 + 三副本等价断言 + 因由分档
- 既有：`tests/agent/subagent/` 全量；重点看断言图级 status 的用例
- **变异验证**：每个新测试都要能被「改坏实现」杀死（本 change 的复现脚本可直接作变异基线）

**文档影响**

- `openspec/specs/web-ui/spec.md`：图级终态 Requirement（MODIFIED，扩为四档）+ 节点因由 Requirement
- `docs/openspec-change-backlog.md`：登记本 change；完成后移除
- 关键词扫描 `docs/`、`AGENTS.md`、`CONTEXT.md` 中涉及图级状态词的段落

**受保护路径**

- `docs/openspec-change-backlog.md`、`openspec/specs/**`、`openspec/changes/archive/**` 的改动需 `workflow-events.jsonl` 结构化解释事件。
