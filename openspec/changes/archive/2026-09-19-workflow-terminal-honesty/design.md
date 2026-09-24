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

**`completed_count` 的口径**：`state.status == "completed"` 的**节点**数。**不含** `skipped`——`skipped` 是「未选中」，不等于「跑成功了」。

> **口径澄清（grill Q2 用户确认，2026-09-19）**：本判据的数**不是**快照的 `completed` 计数。快照的 `completed` 来自 `_unit_counts()['completed_units']`，是 `_logical_units` 口径（`foreach` 容器按展开项数计，见 `scheduler.py:2469`）；本判据数的是**节点**。二者**不同源**，实现时 SHALL NOT 复用 `_unit_counts()`，否则 `foreach` 图上两口径会给出不同结论。
>
> **已接受的语义**（用户拍板）：`route` / `collect` 聚合节点完成即计入 `completed_count`。因此「只有一个空 route 完成、真正干活的节点全被挡」的图会报 `completed` —— 这是**有意接受**的（「至少有一个节点成功即算跑起来了」），不额外排除「零产出节点」（加排除会引入新的边条件，让判据更脆）。

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

> **前端可见性（grill Q4 用户确认，2026-09-19 — 本 change 范围扩大）**：只改 `state.reason` **不足以**让用户看到真因。前端 `explainNode()`（`web/static/workflow_graph.js:836-846`）对 `blocked` 节点的取因顺序是：① 图级停止固定句（`GRAPH_STOP_REASONS`：`budget_exceeded`/`cancelled`/`graph_recursion_exceeded`，见 `:773-777`）→ ② 沿数据入边穿透找上游（「被上游 X 挡住，未执行」）→ ③ 才用 `node.reason`。实测：`max_routes` 图的三个节点在 UI 上全渲染成「流程因图超限被停止，该节点没来得及执行」，`max_routes` 与上限值一个字都不出现；`stalled` 图渲染成「被上游 body 挡住，未执行」。
>
> 故本 change **必须同时改前端 `explainNode()`**：当 `node.reason` 携带**具体闸门信息 / 「入边互等」**时，它 SHALL 优先于泛化文案（优先级 ①/②）。`drawerWhy()`（`workflow.js:1087`）与节点小字（`workflow.js:848/867`）都走同一函数，改一处即全覆盖。**验收口径**：spec 的 Scenario 要看「用户实际看到的那句话」，不是 `state.reason` 字段本身。
>
> **截断口径**：节点投影在 `_SUMMARY_LIMIT`(400) 处切，前端 `truncateText` 在 160 处再切。注入 `state.reason` 时 SHALL 按**前端展示预算**压缩（形如 `图级闸门 max_routes 触发（超过上限 2），本节点未派发`），SHALL NOT 直接塞入整段异常文本（否则关键信息会被 160 字符切掉）。

### D4 — `_reset_subtree` 发起者豁免 **+ `_is_skipped` 选中判据修正（方案 D，组合修）**

> **grill Q1 用户拍板：方案 D（组合修）**（2026-09-19）。原 D4 单独实施会制造**新假话**（实测见下），必须与 `_is_skipped` 的判据修正一起做。

**改动 A：`_reset_subtree(state, *, origin)` 沿 `data_outgoing` 递归时跳过 `origin`**

**为什么是豁免而不是停止传播**：回边场景下，`origin` 的下游里既包含「需要重跑的下游」（正常语义，G11 的立项目的），也包含「origin 自己」（回边造成）。只豁免 origin 一个节点，既不破坏 G11 的重跑语义，又避免清空刚写完的结果。

**调用点**（共 3 处，`scheduler.py:1509/1535/1626`）都要透传 origin：
- `_execute_route` 的派发循环（`:1626`）：`origin = state.node.id`（route 自己）——**这一处是修复生效的关键**，只改 `_on_node_finished` 那处不会有任何效果
- `_on_node_finished`（`:1509`）：`origin = state.node.id`（刚完成的那个节点）
- `_reset_subtree` 自身的递归（`:1535`）：透传 `origin`——豁免只发生在递归链上

**改动 B：`_is_skipped()` 的「是否被选中」判据增加条件 2**

原判据只有「`activations <= 0` + 控制入边源头 route 已 completed」。但 `activations` 会被 `_reset_subtree` 清零，而回边场景下 route **已经选中并派发过**该节点 —— 仅凭 `activations <= 0` 会把「选过、也跑过」的节点报成 `route did not select this branch`。

**实测证据（主 session 复核，2026-09-19）**：同一空转环 spec（`max_routes=3`、case 与 default 都指向 `body`、回边 `required:false`、`body` 为 subagent）：

| | 图级 | `cycle_gate.targets` | `body` 终态 | skipped 假话 |
|---|---|---|---|---|
| 基线 | `graph_recursion_exceeded` | `[]` | `completed`（runs=2） | 无 |
| **仅改动 A** | `completed` | `['body']` | **`skipped`（runs=1）** | **有**（说没选，实际选了且跑过） |
| **方案 D（A+B）** | `completed` | `['body']` | `blocked`（runs=1） | 无 |

两补丁逐行 diff 确认**只差 `_is_skipped` 一处**（新增 `if node_id in source.targets: return False`）。

**否决「只调顺序」的替代方案**（曾被建议，实测无效）：单独把 `_execute_route` 派发循环改成「先 `_reset_subtree` 再 `activations += 1`」，结果与基线**逐字相同**（`graph_recursion_exceeded`、`targets=[]`）——因为 `_on_node_finished` 传的 origin 是刚完成的节点（`body`），豁免的是 `body`、**不保护 route**。更进一步：在方案 D 之上再加该顺序调整，route 派发次数从 2 回到 3、#220 的 `targets=[]` **复发**。故**不采用**顺序调整——起作用的是 origin 的**取值语义**，不是语句顺序。

**条件 2 的写法**：对每条控制入边，源头 route 已 `completed` 时，若 `node_id in source.targets` → **不是 skipped**（route 确实选中了它）。`targets` 是权威信号：它受发起者豁免（改动 A）保护，不被回边复位清空；且已成为对外契约（`web-ui` spec 的 route 选中出口、edge `passed` 判定都依赖它）。**只读既有字段，不引入新记账。**

**G11 回归红线**：`_reset_subtree` 必须仍然清 `reason`/`error`/`summary`/`finished_at`/`status`/`activations`/`verdict`/`targets`（否则「重跑时显示上一轮失败因由」与「负耗时」会回归）。改动 A **只加豁免**，不减任何清理项。

**残余项（记录，不在本 change 修复）**：方案 D 下该环节点最终落 `blocked` + 兜底因由 `workflow ended before the node became ready`，而它实际上跑过（`runs>0`）。这条因由由 D3 的分档覆盖（`blocked` 的因由解释为「被结构性原因挡住未派发」在语义上仍不精确）。它的**端到端归属**是「节点在环里重跑后的终态语义」，属 #219 的循环契约面，本 change 只消灭「说没选中」这条最直接的假话。

### D5 — 图级终态集合的三副本同步（硬要求）

> **表述修正（grill 风险 5 + 主 session grep 复核，2026-09-19）**：原文说「scheduler 侧 `TERMINAL_STATUSES`」——**该对象不存在**。`scheduler.py:83` 的 `TERMINAL_NODE_STATUSES` 是**节点**级集合（`{completed, failed, cancelled, blocked, budget_exceeded, skipped}`），与图级终态无关。真实图级副本是下面三个。

新增 `stalled` 必须同时进入：

| # | 副本 | 位置 | 消费方 |
|---|---|---|---|
| 1 | `_SNAPSHOT_TERMINAL_STATUSES` | `agent/subagent/scheduler.py:111` | 快照是否带计数 + `web/session.py` 的终态立即发送（`_is_terminal_snapshot`） |
| 2 | `TERMINAL_STATUSES`（数组） | `web/static/workflow.js:21` | `pruneGraphs` 的 tab 淘汰池 + `isRunning` |
| 3 | `isGraphTerminal()`（函数） | `web/static/workflow_graph.js:983` | `graphTabMeta` 的「已跑 N 秒 / N 分钟前」耗时判据 |

**漏同步的后果**（#197 已踩过同类坑）：该图被当成 running → 永不进入 tab 淘汰池 → 每次 ws 重连都补发。

**机械保障**：补一条测试断言三个副本的集合相等（而非各自断言「包含 stalled」）——前者能防未来新增档时再次漂移。

> **副本 3 的可断言性**：`isGraphTerminal` **未导出**到 `window.AsterwyndWorkflowGraph`（`workflow_graph.js:1075-1116`），而副本 2 是 IIFE 内的数组、只在 `window.AsterwyndWorkflow` 暴露。跨文件集合等价断言 SHALL 走**正则抽取源文本**（既有范式：`tests/web_tests/test_workflow_graph_ux_js.py:444-455` 抽取 `workflow.js` 的 `TERMINAL_STATUSES`），**不新增导出**——理由：导出会把内部判据变成对外 API，扩大契约面；而源文本断言与既有测试同构，成本更低且已证明可用。

### D6 — 前端编码：`stalled` 的视觉与文案

`stalled` 是**异常终态**（非良性），视觉上须与 `completed` 明确区分：

- 配色：区别于 `completed` 绿与 `failed` 红——取**深琥珀/暗橙**（既有 `budget_exceeded` 的橙**不可复用**，二者会混淆）
- tab 徽标文案：`停滞（无节点完成）`
- 图例：说明「图收敛时没有任何节点成功执行」

**与 `budget_exceeded` 的区分**：`budget_exceeded` 是「预算耗尽而停」，`stalled` 是「结构性停（互等/全被挡）」。二者可能同时成立——按 D1，**预算优先**（既有口径），即 `stalled` 不会覆盖 `budget_exceeded`。

> **配色可判定性（grill 风险 8，2026-09-19）**：原设计只写「深琥珀/暗橙、不复用 budget_exceeded 的橙」，**没有可机械断言的阈值**，`validate` 与测试都无法验证「可分辨」。实测现有调色板最接近的一对是 `completed_with_failures #fbbf24` ↔ `budget_exceeded #fb923c`（RGB 欧氏距离 51.0）。
>
> 因此本 change SHALL 把「可分辨」写成**可断言门槛**：`stalled` 到**每一个既有图级档**（尤其 `budget_exceeded`、`completed_with_failures`、`completed`）的 RGB 欧氏距离 SHALL ≥ **100**，并补一条测试锁定。候选色实测：`#b45309`（到 `budget_exceeded` Δ=107.8）、`#92400e`（Δ=140.9）满足；`#d97706`（Δ=69.3）、`#a16207` 不满足（仍在橙/卡其带内）。具体取值在实现时以「满足门槛 + 视觉可读」定，测试按门槛断言。

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
  - **复现 spec 以 `diagnosis.md` 的 Evidence 块为准**（`cycle_gate` 的 `default` 必须是 `body`，即回边分支被选中、环真的转起来）。`default: end` 的写法 route 只派发 1 次、`_reset_subtree` 从不被调用，#220 复现不出（会得到永远为绿的假测试）。
- **方案 D 的组合回归**：同一张含数据边回边的图，断言 **(a)** `route` 保持 `completed` 且 `targets` 含被派发节点；**(b)** 该被派发节点**不是** `skipped`、其 `reason` 不含 `route did not select this branch`。两条必须一起断言——只断 (a) 会让「仅改动 A」的中间态（制造 `skipped` 假话）通过。

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
- **配色门槛断言**：`stalled` 到每个既有图级档的 RGB 欧氏距离 ≥ 100（D6）
- **`explainNode()` 优先级回归（Q4 新增）**：喂入一张 `max_routes` 撞线的真实快照（节点 `reason` 含闸门信息）→ 断言用户可见文案**含** `max_routes`；喂入一张 `stalled` 死锁快照 → 断言文案说明「入边互等」而非「被上游 X 挡住」。这两条是 Q4 的验收口径（「用户实际看到的那句话」）。
- 既有前端断言若因新增档位而红（精确集合相等式），按新档位更新并加注释

### 变异验证（硬要求）

每个新测试都要能被「改坏实现」杀死，至少覆盖：四档判据（逐档去掉该分支）、因由三档（逐档回退成兜底文案）、origin 豁免（去掉跳过）、**`_is_skipped` 条件 2（去掉 `targets` 判据 → 方案 D 的组合回归测试必须变红）**、三副本同步（从某一副本移除 `stalled`）、前端 `explainNode()` 优先级（回退成泛化文案 → Q4 的两条前端断言必须变红）。

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
| 图级档位 | `scheduler.py:_terminal_converged_status`（`:1234`） | 二档 → 四档 |
| 因由分档 | `scheduler.py:_resolve_pending_status`（`:1281`） | 兜底文案 → 三档 |
| 重跑豁免 | `scheduler.py:_reset_subtree`（`:1511`）+ 3 处调用点（`:1509`/`:1535`/`:1626`） | 加 `origin` 参数 |
| **选中判据** | `scheduler.py:_is_skipped`（`:1298`） | **新增条件 2**：`node_id in source.targets` → 非 skipped（方案 D） |
| 终态集合 (1) | `scheduler.py:_SNAPSHOT_TERMINAL_STATUSES`（`:111`） | 同步（**无** `TERMINAL_STATUSES`，原表述有误） |
| 终态集合 (2) | `web/static/workflow.js:21` 的 `TERMINAL_STATUSES` 数组 | 同步 |
| 终态集合 (3) | `web/static/workflow_graph.js:983` 的 `isGraphTerminal()` | 同步 |
| 前端视觉 | `workflow_graph.js` 的 `GRAPH_STATUS_COLORS`(`:98`)/`GRAPH_STATUS_LABELS`(`:109`)/图例 | `stalled` 配色（RGB 距离门槛）+ 文案 + 图例 |
| **前端因由优先级** | `workflow_graph.js:explainNode()`（`:836-846`）+ `GRAPH_STOP_REASONS`（`:773`） | **Q4：具体因由优先于泛化文案**（节点小字 + 详情面板同一函数） |

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
