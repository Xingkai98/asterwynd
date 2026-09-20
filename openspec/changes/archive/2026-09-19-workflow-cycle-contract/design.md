# Design: 循环图的契约对模型可见（workflow-cycle-contract）

## Context

issue #219 的实测证明：模型按现有提示写循环图会**大概率写错**。`DeclareWorkflow` 的描述只有一句
「Cycles are only allowed through a route node」，而真正生效的契约有四条，全部只能靠踩坑发现。

**本 design 的 D1/D2 已按 `reviews/grill-design.md` 的独立审阅结论重写**（原文的「空转环 = 环内无产出节点」
与「回边死锁 = route 有同环内 required 数据入边」两条判据被实测证伪：前者误报且漏报，后者会**拒绝官方
`peer-review` pattern** 并误伤 32 条既有测试）。重写后的判据只有一个——**环必须能启动**——来自对调度器
真实派发规则的静态复刻。

关键判断（决定本 change 的形状）：**「这个环永远跑不起来」可以在声明期静态判定**，不需要运行、不需要
形式化证明。判据是调度器 `_ready_nodes` 的最小不动点：一个环里若没有任何节点能先跑起来，它就永远
不会推进。

| 现象 | 静态判据 | 为什么可判定 |
|---|---|---|
| 环永远不推进 | 环（SCC）内**无可派发节点**（不动点为空） | 派发规则是单调的：可派发集合只依赖上游可派发性与 entry/控制语义，与运行期取值无关 |

一般性的「循环可终止性」不可判定，**但「环能不能启动」可判定且实测零误报**，所以本 change 只做这一条。

## Goals / Non-Goals

**Goals**

- 模型能在 `DeclareWorkflow` 的描述里读到完整的循环契约（不再只有一句）
- 必然跑不起来的环在**声明期**被拒，而不是运行期静默收敛（图报 `completed`、环内节点全 `blocked`）
- 拒绝时给出**可操作**的原因：模型据 `reason` + `hint` 就能改对（三要素：哪个环 / 缺什么 / 怎么改）

**Non-Goals**

- 不改运行期行为（#217/#218/#220 已由 `workflow-terminal-honesty` 修复）
- 不改 `max_routes` 语义（只讲清楚）
- 不做自动修复（静默改图比报错危险）
- 不做一般性可终止性证明（不可判定）
- 不覆盖 `foreach` 的 `source` 环（既有 `_validate_foreach_source_cycles` 已处理）

## Decisions

### D1 — 环必须能启动：环内无可派发节点 → 声明期拒绝（**不动点判据**）

**判据**：对每个 SCC（复用既有 `_strongly_connected_components`，迭代式 Tarjan），若分量大小 > 1
（或自环），**且分量内没有任何节点可派发** → 拒绝。

**「可派发」的定义**（静态**过近似** `scheduler.py::_ready_nodes` + `_data_deps_satisfied`
+ `_is_entry` + `_execute_route` + `_fire_best_effort_deadlines`，取最小不动点）：

节点 `n` 可派发，当且仅当下列**任一**成立：

1. **常规路径**：全部 `required` **数据入边**源头都可派发（`required: false` 的边不参与门控——
   `_data_deps_satisfied` 对它们 `continue`）；**且**控制闸放行：`n` 是 `entry`（显式或隐式
   「无任何入边」）、**或**它没有控制入边、**或**存在一个可派发的 route 能激活它。
   「能激活」的真相源是 `_route_activators`：调度器的 `_execute_route` 按 `cases[].to` /
   `node.default` 的 **target id** 直接 `activations += 1`，**从不检查是否存在声明边**
   （`_validate_kind_specific` 也只要求目标是已知节点）——所以这两者与「route 的声明出边」
   一并计入激活来源。
2. **best_effort 截止路径**：`n` 是 `join == "best_effort"` 且声明了 `deadline_s` 的 aggregate，
   且它至少有一个数据入边源头可派发——上游一被派发就武装 `n` 的 `deadline_ref`
   （`_launch_run`），到点后 `_fire_best_effort_deadlines` 置 `deadline_fired`，而 `_ready_nodes`
   对该标志**直接放行**，连 `activations` 检查都跳过。

不动点从空集开始迭代到不再增长。

> **为什么这个方向是安全的**：判据的用途是**拒绝**（「这个环永远跑不起来」），所以可派发集合必须是
> 真实可派发节点集的**超集**——多算一个节点只会漏报（少拒一张坏图），少算一个才会误报（拒掉一张
> 能跑的图）。因此每条规则都取「有可能」的乐观口径（控制边假设「route 可能选中它」、deadline 路径
> 假设「截止会到」）。
>
> **这条安全论证必须逐条覆盖真实派发路径**——本 change 的首轮审阅正是在这里抓到两个误报：
> 漏掉 `deadline_fired` 短路（best_effort 聚合在环内时误拒）与漏掉 `cases`/`default` 激活
> （route 目标无声明边时误拒）。新增派发路径时，这里要同步。

**为什么它替换了原来的「环内无产出节点」**：产出节点（`subagent` / `aggregate(strategy="llm")` /
`foreach`）**既非必要条件也非充分条件**——实测（`reviews/grill-design.md` 的决策 4 与 Q1 场景）：

- **不充分**：环里有**两个** `subagent`（`a`、`c`）但 `b`/`c` 互相 `required` 等待时，按「有产出节点」
  通过声明，实跑 `b`/`c` **永久 `blocked`**、图级 `status = completed`、`diagnostics` 为空——
  用户在返回体里看不到任何异常。这正是 #219 要消灭的「图和人都不知道发生了什么」。
- **不必要**：`route` 其实**产出**非空 `summary`（`_node_output` 末行 `return state.summary or None`，
  route 的 summary 形如 `"default -> ['body']"`）；`aggregate(strategy="collect")` 在拼接超预算时
  也会走 `LLMSummarizer` 调 LLM。所以「环内没有任何 LLM 调用」这个论据不成立——正确的论据是
  「**环内没有任何会随轮次改变的状态**」，而那正是不动点判据刻画的东西。

**它同时覆盖了原 D2 的全部真阳性**：`route` 有同环内 `required` 数据入边时，该 route 满足不了条件 1
（它的数据源在环内、也不可派发），因而不可派发；环内其余节点又在等它——不动点为空，被拒。
实测：`#217` 那张死锁图（`cycle_gate` + `body` + 回边 `required` 默认 true）被正确拒绝。

**为什么官方 `peer-review` 不受影响**（**必须有测试锁定**）：它的 SCC 是 `{producer, reviewer, gate}`，
`producer` 是 entry（`spec.entry = ["producer"]`）且没有 `required` 数据入边 → 可派发；`reviewer` 的
required 数据源 `producer` 可派发 → 可派发；`gate` 的数据源 `reviewer` 可派发 → 可派发。不动点非空。
`gate` 的**出边是控制边**（`workflow.py::is_control_edge`）——注意这与「`gate` 的**入边**」无关，
原 D2 正是把这两件事混为一谈才误判了免疫。

### D2 — 诊断层：被拒环内若有「同环 `required` 数据入边」，在报错里点出来

**D2 不再是一条独立判据**（原判据会拒绝 `peer-review`、误伤 23 条既有测试）。它的**诊断价值**并入 D1：
拒绝时若被拒的环里存在**同环内的 `required` 数据入边**，错误信息的 `waiting on` 段落 SHALL 逐条点出
这些边，修法段落 SHALL 给出「声明 `"required": false`（或把回边改从 route 出发——route 出边是控制边，
不参与门控）」的具体动作。

**为什么保留这层**：不动点判据只报「这个环跑不起来」，粒度粗；而「你这条回边是 required 数据边」
是模型最容易改对的那一类信息。两者一起给，模型既能定位又能照做。

### D3 — 拒绝而非警告（**grill Open Question Q3，用户已拍板：拒绝**）

用户裁决：**「直接拒绝吧，这种图没意义，但是要确保给到 llm 足够的信息引导他改正」**。

- 业界先例：Airflow / Argo 对拓扑错误都是**拒绝**（`AirflowDagCycleException` / Argo 声明期拒绝环）。
- 被拒的图在语义上**必然**跑不起来（不动点为空 ⇒ 环内零节点派发），警告只会让模型带着一个坏图继续走。
- **附加要求（本 change 的关键路径）**：`_invalid_spec` 的返回体里**没有 `workflow_id`**，模型拿不到
  可运行的图，只能改 spec 重声明——所以 `reason` + `hint` 是它**唯一**的信息来源，必须自足。
  这直接抬高了 D5 的优先级：它不是措辞问题，而是本 change 能否达成目标的关键。

### D4 — 提示面：给「核心规则 + 最小正例 + 反例」，不是罗列规则

调研结论（Temporal / LangGraph 的共同做法）：**契约靠示例传达**比列规则更易被遵守。核心规则用用户
拍板的那句（Q4）：

> **环里必须有个节点先跑起来，且它不能反过来等环里的东西。**

（不用「环里必须有个会变的节点」——实测表明把 subagent 塞进环里敷衍过关也未必能让环转起来。）

`DeclareWorkflow` 描述补的循环小节包含：

1. 核心规则（上一句）+ **为什么**（否则声明期拒绝，因为图会停滞、环内节点全部 `blocked`）
2. 回边规则：**回边从 route 出发**是控制边、不参与门控；从别的节点出发是**数据边**、默认门控，
   须显式 `"required": false`
3. `max_routes`：默认 **1**、逐节点配（`workflow.py::WorkflowNode.max_routes`）、**跨轮累加不重置**
4. **最小正确示例**（entry 在环内、回边从 route 出发）与**最小反例**（route 等体、体等 route）

**为什么不用「把校验错误喂回去」代替提示**：声明期拒绝**已经**会给可操作的原因（D5），但那是**纠错**；
D4 是**预防**。两者互补。

### D5 — 报错必须可操作（**本 change 的关键路径**）

拒绝时的错误信息要能让模型**直接改对**，至少含三要素：

| 要素 | 内容 |
|---|---|
| **哪个环** | 环的成员节点 id（有界列出，超出截断并注明还有几个） |
| **缺什么** | 逐条「谁在等谁」——**只列 required 数据边**（即 `data_incoming`，**排除 route 出边**）：`'cycle_gate' waits for required data from 'body' (same cycle)`；以及 `'body' is not an entry: it can only be activated by route(s) [...], which cannot run either` |
| **怎么改** | 可照做的动作：对同环 `required` 数据边点名建议 `"required": false`；或「给环加一个能自己启动的节点（required 输入来自环外；若还有 route 指向它，要列进 `spec.entry`）」；或「把环的一条边挪到环外」 |

> **口径必须与门控真相源一致**（首轮审阅 Issue 3）：把 `route` 出边说成「required 数据等待」是
> 假话——`route` 出边是控制边、不参与门控，模型照该条去加 `"required": false` **没有任何效果**
> （实测：照做后图仍被拒）。这正是 `workflow-terminal-honesty` 立下的「答错比答不出更糟」标准
> 要消灭的那类文案，故必须排除控制边，并有反向断言锁住。

配套：`_invalid_spec` 对本类错误给**指向性 hint**（而非通用句），说明「返回体里没有 workflow_id，
请按 reason 的 how-to-fix 改 spec 后重新 Declare」。

**反面教材（必须避免）**：`cycle without a route node is not allowed` 这类**只陈述规则、不给修法**的文案。

## Pre-Implementation Review

> 本 change 含 `feature`（spec 可见：新增声明期拒绝路径 + 提示面契约），实现前已由**独立零记忆
> subagent** 审视本 design，产出 `reviews/grill-design.md`（11 条 Confirmed Decisions + 5 条 Open
> Questions 全部经用户确认）。grill 推翻了初版 D1/D2 的两条判据，本 design 已按裁决重写。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| **误伤合法图**（判据过严） | **高** | 可派发集取**过近似**（超集才安全）；每条真实派发路径都要复刻进去（首轮审阅已因此抓到 2 个误报）；官方 4 pattern 全部仍通过（测试锁定）；随机图 fuzz 交叉验证（被拒图逐个实跑，看被点名节点是否真的没跑） |
| 拒绝路径破坏既有测试里的环图 | 中 | 实测爆炸半径 6 条（全在 `test_terminal_honesty.py`，因其**故意**构造死锁图）——按 grill Q5 裁决改为绕过声明期校验、直接构造 `WorkflowSpec`，保住运行期诊断覆盖 |
| 提示面文案过长挤占工具描述预算 | 低 | grill 实测：仓库**不存在**工具描述长度上限/截断代码（`DeclareWorkflow` 现 489 字符，`GetWorkflow` 644）；仍用最小示例控制长度 |
| 模型绕过校验（直接构造 spec） | 低 | 声明期校验在 `parse_workflow_spec` 内，所有入口共用；测试里的绕过是**测试专用**的（用解析 helper 直接构造对象），不新增公开旁路 |
| 判据乐观导致漏报 | 低 | 乐观方向只漏报不误报；漏掉的形态仍由运行期诊断（`blocked` + 「入边互相等待」）如实表达 |

**Trade-off（明确记录）**：新增拒绝路径的代价是「此前能声明的图现在会报错」；换来的是「模型不会再
建出必然停滞的图」。用户已就此拍板选「拒绝」（D3）。

## Testing Strategy

### 后端（`tests/agent/subagent/test_workflow_cycle_contract.py`）

**新增判据的判定**（每条都要有正向 + 反向）：

- **#219 原始形态**（`cycle_gate`(route) + `body`(collect) + 环内 `required` 数据边）→ **拒绝**，
  报错含环成员、`waiting on` 说明与修法
- 环内 `required` 互等、环内**有** subagent（grill Q1 场景）→ **拒绝**（「有产出节点」判据会漏掉它）
- 环有能自启动的节点（entry 在环内）→ **通过**
- 环内是 `aggregate(strategy="llm")` 且能启动 → **通过**
- 环内是 `foreach` 且能启动 → **通过**
- 回边从 route 出发（控制边，peer-review 形态）→ **通过**
- 回边 `required: false` 且环能启动 → **通过**
- 环外节点 `required` 数据边喂进环、环内无 entry → **拒绝**
- **环内有 `best_effort` 聚合**（`deadline_fired` 短路会让它真被派发）→ **通过**（首轮审阅 Issue 1）
- **route 的 `cases`/`default` 指向环内节点但无声明边** → **通过**（首轮审阅 Issue 2）
- 自环 route（能自启动）→ **通过**；多个环并存、只有一个跑不起来 → **拒绝且只点名那个环**
- 报错三要素（哪个环 / 缺什么 / 怎么改）逐条断言，并用「模型视角」核对能否据此改对
- 报错**不得**把控制边说成 required 数据等待；大环的报错**必须有界**并注明 `(+N more)`

**回归红线**：

- 官方 4 个 pattern（`orchestrator-worker` / `peer-review` / `hierarchical` / `bidding`）
  **全部仍能声明通过**（`peer-review` 是本项目唯一能工作的多轮审阅循环，差点被初版 D2 误杀）
- 既有 `tests/agent/subagent/` 全量绿（`test_terminal_honesty.py` 按 Q5 裁决改造后）

### 提示面（`tests/agent/subagent/test_workflow_cycle_contract.py`）

- `DeclareWorkflow` 描述含循环契约的关键词（`max_routes` 默认值、回边 `required: false`、
  「先跑起来 / 不能反过来等」的核心规则）与正例、反例

### 变异验证（硬要求）

每条新校验都要能被「改坏实现」杀死。**注意**：初版 design 规划的「把 `data_incoming` 换成 `incoming`」
已被 grill 实测证伪——对 `peer-review` 两者结果完全相同，是**恒等变换**，杀不死任何东西。改用有
区分度的变异：

- **删掉 `required` 判断**（把 `required: false` 的边也当门控边）→ 带 `required: false` 回边的合法环
  被误拒 → 应被「回边 `required: false` 通过」这条测试抓住
- **删掉「是 entry」分支** → `peer-review` 的 `producer` 不再可派发 → 应被官方 pattern 回归抓住
- **把不动点退化成「环内有无 subagent」** → 应被 grill Q1 场景（环内有两个 subagent 但互等）抓住
- **删掉 `deadline_fired` 短路** → `best_effort` 环被误拒 → 应被 best_effort 用例抓住（首轮审阅 Issue 1）
- **删掉 `cases`/`default` 激活来源** → route 目标无声明边的图被误拒 → 应被 Issue 2 用例抓住
- **恢复控制边苛责**（waiting 段不排除 route 出边）→ 应被「不苛责控制边」的反向断言抓住（Issue 3）
- **去掉 `_bounded` 截断** → 大环报错超长 → 应被「报错有界」用例抓住（Issue 4）
- **去掉 how-to-fix 段落** → 应被报错三要素测试抓住

### 全量

- `uv run pytest tests/agent/subagent/ -q`
- `uv run pytest -q`

## Impact Analysis

（与 `proposal.md` 的同名章节同源；此处补充实现层落点）

| 落点 | 文件:符号 | 说明 |
|---|---|---|
| 新校验 | `workflow.py::_validate_cycle_can_start`，由 `workflow.py::parse_workflow_spec` 调用 | 复用 `_strongly_connected_components` |
| 不动点 | `workflow.py::_dispatchable_nodes` + `workflow.py::_route_activators` | 过近似真实派发规则（见 D1） |
| 新异常 | `workflow.py::WorkflowCycleError`（`WorkflowValidationError` 子类） | 让 `_invalid_spec` 能给指向性 hint |
| 复用 | `workflow.py::_strongly_connected_components` | 既有迭代式 Tarjan，**不改** |
| 提示面 | `agent/tools/builtin/subagents.py::_invalid_spec` + `DeclareWorkflowTool` 描述 | hint + 文案 |
| 测试改造 | `tests/agent/subagent/test_terminal_honesty.py` | 绕过声明期校验、直接构造 `WorkflowSpec`（grill Q5） |

> **落点与调用顺序**：新校验由 `parse_workflow_spec` 在校验段的**最后**调用——在全量既有校验
> 与 `entry`/`terminal` 解析**之后**，因为判据要用含隐式推导的最终 entry 集。既有报错优先级
> 未被改写：无 route 的环仍由 `_validate_cycles` 先报（实测确认）。

**受保护路径**：`openspec/specs/**`、`docs/openspec-change-backlog.md` 的改动需 `workflow-events.jsonl`
结构化解释事件。
