# Design: Workflow 流程图可视化体验增强

## Context

C7 `workflow-graph-visualization`（#190，已合入归档）交付了运行态流程图：`workflow_graph_snapshot()` 数据面、`workflow_started`/`workflow_snapshot` 事件通道、零依赖 SVG 自绘前端、桌面横向/手机纵向 DAG + pinch/pan。图**能画出来**了。

本 change 处理用户实测（手机端「代码体检」）暴露的 4 类**可读性缺口**：图例缺失（A）、异常态语义混淆（B）、节点详情缺失（C）、多图与 foreach 可读性差（D）。这是**展示层信息架构问题**，不是数据面缺失问题——大部分数据已在快照里（`status`/`reason`/`items`/`summary`），少数「图上看不到的语义」（图级时间、foreach 完成计数、节点 reason）需要**加法式**补字段。

现有实现的三层结构（本 change 沿用，不重排）：
- **纯函数层** `web/static/workflow_graph.js`：布局 / 状态映射 / 折叠 / 变换，与 DOM 解耦，node + vm 单测覆盖（`tests/web_tests/test_workflow_graph_js.py`）。
- **渲染层** `web/static/workflow.js`：SVG 自绘 + 手势 + tab 管理。
- **数据面** `agent/subagent/scheduler.py::workflow_graph_snapshot()`：显式挑字段的 bounded 快照。

**一个必须先说的事实（调研发现 + grill 决策 10 核实，非体验偏好）**：节点摘要今天**唯一**的出口是 `<svg:title>`（`workflow.js:418-421`，`id [kind] label` + `truncate(summary,200)`），而 **SVG `<title>` 在移动端触屏上不显示**——手机用户**根本看不到**任何节点摘要。更糟的是，**非折叠组长的节点点击是纯 no-op**（点击绑定在 `:423`，`toggleGroup` 对非 `groupLeader` 直接 return，`:435`）——这正是 proposal「非折叠组节点点击完全无效」的依据。这不是「体验欠佳」，是现有实现在主目标端（手机）上的**功能性缺失**，本 change 必须修掉（并入详情面板 + 自绘 tooltip + 让普通节点可点）。

## Goals / Non-Goals

**总目标（用户原话）**：「尽可能地对整个 workflow 的流程有更多的掌控感，能看到每个节点运行过程中的情况，如果报错了，为什么报错」。下面 A–F 是它的分解。

**Goals**

1. **A 图例**：用户不看文档就能读懂节点类型、8 档状态、5 档边状态与线型/箭头的含义。
2. **B 异常态语义**：一眼分清 `failed`（自身失败）/ `blocked`（被挡住没跑）/ `budget_exceeded`（预算停下）/ `skipped`（条件没走这条），并能看到「**为什么**是这个状态」的因果说明——**含失败位置与预算数字**。
3. **C 节点详情**：点任意节点 → 打开详情面板，看到该节点的 task / 状态与因由 / 起止耗时 / summary / **失败证据** / 完整 transcript（懒加载、运行中可刷新）。
4. **D 多图与 foreach 可读性**：多图 tab 能区分「第几次 run / 何时起 / 耗时 / 结果差异」；foreach 容器**运行中**就常显「完成 M/N」；统计行数字与图上可见线条数**一致且可解释**。
5. **E 运行过程可见性（本 change 补强）**：区分「等上游 / 排队等 slot / 真正在跑」；节点级 elapsed 跳动计时；图不"假活"（陈旧可见）；详情面板能看到**此刻**在干什么。
6. **F 掌控**：能**取消**一张正在跑的图（尤其预算超限 drain 期间）。
7. 桌面/手机两端都可用，复用既有 720/380 断点，不引入前端框架或新依赖。

**Non-Goals**

- **不做节点级重跑 / 重试**（需新调度器原语：用户触发复位 + 重派发 + 与 `_accepting`/预算/`activations` 的交互定义；且要回答「重跑已完成的节点？」「下游全级联？」「预算已耗尽还能重跑？」）。**另立 change**（见下 Issue）。
- **不做运行内事件流 / 状态迁移时间线**（数据齐备：`latest_events` 内存 5 条 + `events.jsonl` 落盘，但要先定暴露口径与容量）。注意：本 Non-Goal **不含**「不做时间轴回放（snapshot scrubber）」以外的含义——**节点级「变化高亮」不做为动画，但作为一次性标记做**（见 D8）。
- **不做节点搜索 / 筛选**（真过滤会破坏 DAG 布局：隐藏节点需重连边、重算层级）。本 change 只做**压暗（dim）**轻量版（G20 延后，见下）。
- **不做导出 / 分享（PNG / JSON）**（要定导出形态、是否含图例与时间戳）。另立 change。
- **不做长跑完成通知**（与图耦合度低）。另立 change。
- 不做时间轴 scrubber 式图历史回放（快照仍只表达当前态）。**措辞收窄**：原写「不做图历史回放（快照只表达当前态）」会连坐「同一次运行内的事件流」，那恰是「为什么报错」的最直接答案——已拆成上面两条。
- 不做动画/过渡效果（沿用「状态切换直接重绘」）；但**新快照到达时对变化节点给一次性高亮标记**（D8），这不是动画。
- 不做 Web 端编排画布（拖拽设计拓扑）；沿用 #190 的 Non-Goal。
- 不做力导向布局；**不做边捆绑（edge bundling）**——它是为几百条边的 hairball 设计的，我们同一对节点重叠的边只有 2–4 条，捆绑只会把信息藏得更深（见调研 D6）。
- **不改** `_envelope`/`parent_envelope` 的**结构**契约（唯一变化是节点 `status` 取值集合新增 `skipped`，消费方需容忍）；不改 `InspectSubagentTranscript` 工具（LLM 面）。
- 不做「跨 session 的 workflow 历史浏览」（详情面板只服务当前 session 的运行态图）。**注意**：这**不覆盖**「同 session 内被淘汰的图找不回来」（G22，前端策略问题），后者另记债务。

## 界面效果（预期的样子）

本节先固定「改完之后，用户看到什么、点什么、得到什么」，D1–D7 是实现它的一组手段。所有形态在桌面（>720px）与手机（≤720px）用**同一份 DOM**、按 720 断点切 class。

### 0. 节点 ↔ subagent 的真实对应（决定详情面板形状的**前置事实**，逐执行器核实）

| 节点 | kind | 有 subagent？ | 数量 | 依据 |
|---|---|---|---|---|
| 普通节点 | `subagent` | ✅ | **1:1** | `_execute_subagent` → `_launch_run(reuse_state=state)` 写 `state.subagent_id` |
| foreach 容器 | `foreach` | ✅（展开项） | **1:N** | 容器自身 `subagent_id=None`（`scheduler.py:1464`），每项独立 session |
| 聚合（LLM 策略） | `aggregate` `strategy="llm"` | ✅ | **1:1** | `_execute_aggregate` 走 `_launch_run` |
| 聚合（拼接策略） | `aggregate` `strategy="collect"` | ❌ | **0** | 纯逻辑合并，显式 `state.subagent_id = None; state.run_id = None` |
| 条件分支 | `route` | ❌ | **0** | `_execute_route` 只做标签匹配，全程不调 `_launch_run` |
| 自动插层聚合 | `__auto_agg__` | ✅ | **1:1** | kind 是 `aggregate`，默认 `strategy="llm"`（`aggregation.py:389`） |

**八档状态（本 change 从七档扩为八档，新增 `skipped`）**：`pending` / `started` / `completed` / `failed` / `cancelled` / `blocked` / `budget_exceeded` / **`skipped`（未选中，见 D2b）**。`skipped` 专给「route 条件判断没走这条 → 该分支本来就不该跑」——它与 `blocked`（被上游连累）的区别正是 issue 里用户混淆的那一档。八档在图上以**颜色 + 角标 + 边框形状 + 状态词**四重编码区分。

**结论**：详情面板的「对话」tab 天然有 **3 种形态**（`single` / `candidates` / `none`），它对应**节点类型**而非某个特例：

- **`single`** — subagent / aggregate(llm) / auto-agg → 单条 transcript。
- **`candidates`** — foreach 容器 → N 个并行项清单，点某项看该项 transcript。
- **`none`** — route / aggregate(collect) → 「该节点不产生对话」，改显示该类型的**自有信息**（route：命中标签 + 选中出口；collect：合并后的产出）。

这条事实要求 Q1 的接口必须按**三态 union** 设计（`none`/`single`/`candidates`），不能写成「foreach 特例 + 其余走单条」——否则 route / collect 会被塞进错误的兜底分支。

### 1. 图例条（D1）

```
桌面（默认展开）:
┌──────────────────────────────────────────────────────────────────────┐
│ 节点  S 子代理   F 并行展开   R 条件分支   A 聚合                       │
│ 状态  ■pending ■running ■completed ■failed ■blocked ■budget ■cancelled│
│       □□给每个状态配一句人话，如 blocked=被上游或预算挡住，未执行        │
│ 边    ─inactive ─ready ━active ━passed ┄blocked     线型=channel       │
└──────────────────────────────────────────────────────────────────────┘

手机（默认折叠，点开）:
  图例 ▾
  ← 点开后纵向列出上面三段
```

### 2. 图上的节点（D2 + D5）

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│▌S scan       │   │▌F fan    ▸  │   │▌R gate       │   │▌S archive —  │
│  completed   │   │ ⊘ blocked    │   │  completed   │   │ //skipped//  │
└──────────────┘   │  完成 3/12    │   └──────────────┘   └──────────────┘
   ↳ 点击开详情     │  被上游 scan  │    ↳ 点击开详情       冷灰蓝 + 虚框 +
                   │  失败挡住     │    ↳ ▸ 是独立的       「条件没走这条 =  —
                   └──────────────┘      展开控件         未选中」，不是失败
                     ↑ 计数常显（D5）
                     ↑ why 小字只在异常态出现
```

- **四重编码**：状态色（色带 + 描边）+ 角标（`✕`/`⊘`/`‖`/`⊝`/`—`）+ 边框形状（实线/虚线/双线）+ 状态词（异常态加粗）——不靠颜色单独承载语义（D2）。
- **`skipped` 与 `blocked` 必须一眼可分**：一个是「被上游连累没跑成」（黄 + ⊘），一个是「条件没选它，本来就不该跑」（冷灰蓝 + 虚框 + —）。这是本 change 的立项命题之一（D2b）。
- **`▸` 只对折叠组出现**（`groupLeader`），点它展开/收起，点节点其余区域开详情（D4）。

### 3. 详情面板（D4，按断点切位置）

```
桌面：右侧抽屉（覆盖画布右侧，不挤压）    手机：底部抽屉（可上拖）
┌────────────────────────────┐        ┌────────────────────────────┐
│ fan  [foreach]  ⊘ blocked ✕│        │         ────                │
│ ──────────────────────────│        │ fan [foreach]   ⊘ blocked   │
│ [任务] [产出] [对话]        │        │ ──────────────────────────│
│ ──────────────────────────│        │ [任务] [产出] [对话]        │
│ 状态   blocked              │        │ ──────────────────────────│
│ 因由   被上游 scan 失败挡住  │        │ 状态   blocked              │
│ 耗时   —                    │        │ 因由   被上游 scan 失败挡住  │
│ runs   0                    │        └────────────────────────────┘
│ 任务   "对每个文件做体检…"   │
└────────────────────────────┘
```

**「对话」tab 的三种形态**（对应上表）：

```
single（subagent / aggregate-llm）     candidates（foreach 容器）        none（route / collect）
┌──────────────────────────┐      ┌──────────────────────────┐    ┌──────────────────────────┐
│ user                     │      │ 该节点为 12 个并行项的容器 │    │ 该节点是条件判断，          │
│   扫描仓库结构…            │      │ ┌──────────────────────┐ │    │ 不产生对话                  │
│ assistant                │      │ │#0 a.js   ● completed │ │    │                            │
│   发现 3 处问题…           │      │ │#1 b.js   ✕ failed    │ │    │ 判定结果：APPROVED          │
│ …（按 50 行聚簇虚拟化）     │      │ │#2 c.js   ● completed │ │    │ 命中出口：→ gate            │
└──────────────────────────┘      │ └──────────────────────┘ │    └──────────────────────────┘
                                   │  点某行 → 取该项 transcript│
                                   └──────────────────────────┘
```

### 4. 多图 tab（D6）

```
[● #1 体检                ] [● #2 修复方案            ] [✕]
    ├ 副行: completed · 2 分钟前 · 2m18s · 5/5
    └ title: 完整 goal + workflow_id + 绝对起止时间

运行中的图排最前，其余按开始时间倒序；# 为会话内展示序（Q3）。
```

### 5. 边统计（D7）

```
改前: 11 nodes · 11 edges · …            ← 报原始边数，图上只有 6 条线
改后: 11 nodes · 6 paths · …             ← 一致，不解释（小图未折叠，去重不发生）
      11 nodes · 6 paths (原始 11 edges) · …   ← 不一致时才解释
```

## Decisions

### D1 — 图例：常驻可折叠图例条，每条目配「人话解释」

**选型**：图上方（`#workflow-summary` 与 `#workflow-canvas` 之间）加一个**常驻可折叠图例条**（`#workflow-legend`）。

- **桌面（>720px）**：默认展开，横向排布三段——**节点类型**（`S subagent` / `F foreach` / `R route` / `A aggregate`）、**节点状态**（7 档色块 + 状态词 + **人话解释**）、**边状态**（5 档线型 + 箭头图例 + channel 线型说明）。
- **手机（≤720px）**：默认折叠为一行 `图例 ▾`，点开显示纵向列表（复用同一 DOM，由 720 断点切 class）。
- **每条目是人话，不是裸术语**：`blocked — 被上游或预算挡住，未执行`、`budget_exceeded — 预算耗尽主动停止`、`passed — 数据已被下游读取`。这套文案与 D2 的因果文案**同源**（同一张表）。

**为什么不用 hover-only 或首次引导**：hover 在手机上不存在（且现有 `<svg:title>` 已证明在移动端失效）；强制首次引导 tour 看完就消失、复现靠记忆；「用户看不懂」是**持续**问题，图例必须常驻可得。折叠解决手机空间。

**放在纯函数层**：图例的**内容模型** `legendModel()` 放 `workflow_graph.js`，由 node+vm 单测锁定（文案表与 `NODE_COLORS`/`EDGE_STYLES`/`KIND_GLYPHS`/`NODE_LABELS` **同源**，改词表时图例自动跟随、不漂移）。

### D2 — 异常态：三重编码（色 + 形状/角标 + 状态词）+ 因果推导

现状：三种非成功态**只有色块**区分（红/黄/橙）。调研核实这是业界公认的反面教材——Airflow 的 `failed`/`upstream_failed` 两色在绿色盲下 ΔE≈0.4（近乎同色），其 AIP-38 因此立规「**不得仅靠颜色表达状态**」。我们**不能**继承这个坑。

**方案**：异常节点升为**三重编码**：

1. **色**（既有）：红 / 黄 / 橙。
2. **形状 + 角标**（新增）：
   - `failed` → 实线边框 + `✕` 角标；
   - `blocked` → **虚线边框** + `⊘` 角标（虚线读作「未发生/非终局」，Temporal 的重试态语义）；
   - `budget_exceeded` → **双线边框** + `‖` 角标；
   - `cancelled` → 深灰 + `⊝` 角标；
   - `skipped`（新增第 8 档，见 D2b）→ **冷灰蓝** + 虚边框 + `—` 角标。
   - **字形约束（实现时踩到过）**：角标只用**默认字体普遍覆盖**的字符。实测 `⏸`（U+23F8）在多数系统字体缺失，会渲染成豆腐块（□）——已改 `‖`。落地时逐个在目标字体下目视确认。
3. **状态词**（既有 `label`，强化）：异常态**加粗**显示。

**因果说明（「为什么是这个状态」）**——纯函数层新增 `explainNode(node, edges, nodesById)`，返回一句人话因由；这是调研里**投入产出比最高**的一项（先例：Airflow 在日志里已生成这类因果串却没搬上 UI，用户反复困惑；Tekton 明确改用 status **reason** 而非 message 来区分失败类别）：

- `failed` → 自身 `reason`（`RuntimeError: ...`）→ 「节点自身执行失败：`<reason>`」。
- `blocked` → **沿入边向上找第一个 `failed`/`cancelled` 的上游** → 「被上游 `<id>` 失败挡住，未执行」；找不到失败上游（预算路径）→ 用自身 `reason` → 「流程结束前该节点一直未就绪」。
- `budget_exceeded` → 自身 `reason`（`budget exceeded (tokens)`）→ 「预算超限（`tokens` 维度）后停止」。
- `cancelled` → 「流程被取消，未执行完」。

因果句用于三处：**节点 `why` 小字**（仅异常态显示，正常态不占位）、节点 `<title>`、详情面板的「状态」区。**因果推导是纯函数**（拿 nodes + edges 即可算），可在 node+vm 里直接测「12 文件 foreach 超预算」这个真实场景的因果链。

**配色校验**：`blocked=#facc15`/`budget_exceeded=#fb923c`/`pending=#94a3b8` 转灰度后区分度不足——落地时按「拉开**明度**差而非只拉色相」调一轮，用 Chrome DevTools 的 deuteranopia 模拟目视验证（无自动化门禁，记录到 building review）。

### D2b — **后端语义适配**：新增 `skipped` 档 + 补 route 数据入边的 `passed` 记账

> **来源**：用户实测示例图时问「archive 分支没走，应该是灰色吧，为什么是（黄/橙）？」——实跑代码后确认这不是显示问题，是**上游 change 留下的两个真实语义缺口**，且正好落在本 change 的核心命题（异常态语义）上。用户裁决：**「一块搞，这个 change 的目标就是前端易用性，后端有需要适配的都适配」**（方案 A）。

**缺口 1：未选中的分支被标成 `blocked`，但系统里没有「未选中」这一档。**

实跑 `_route_spec()`（正常完成，gate 走 `APPROVED`）得到的真实快照：

```
node a      completed
node gate   completed
node yes    completed     ← 被选中的分支
node no     blocked       ← 未被选中的分支：错标成 blocked
edges: a→gate=inactive, gate→yes=passed, gate→no=inactive
```

`no` 四类都不是：不是自身失败（`failed`）、不是被上游连累（`blocked` 的本义）、不是预算停下（`budget_exceeded`）、也不是被取消（`cancelled`）。它是**「route 判定不走这条，本来就不该跑」**。根因：`_teardown` 的 `pending` 分支只有两个出口——`_budget_stop` 时走 `_apply_budget_exhausted_status`（根→`budget_exceeded` / 其余→`blocked`），否则一律 `blocked`（`scheduler.py:762-772`）。**没有第三种落点**。业界先例：Airflow 专门有 `skipped` 档区分「条件不需要跑」与 `upstream_failed`「被上游连累」；Argo 叫 `Omitted`（`depends` 不满足）vs `Skipped`（`when` 为 false）。

**方案：新增第 8 档节点状态 `skipped`（未选中）。**

- **判据（有权威信号，不需要新记账）**：节点在 `_teardown` 时仍是 `pending`，且 `_has_control_incoming(node) and state.activations <= 0` —— 即「只被 route 控制边门控、且没有任何 route 选中它」。`activations` 是既有计数器（`_execute_route` 命中时 `successor.activations += 1`，`:1450`；派发时清零 `:1261`），`_ready_nodes` 已用它做「回边目标等激活」的门控（`:1184-1189`），**复用它不引入新机制**。
- **优先级（必须先判 blocked 再判 skipped）**：若节点有数据入边且上游 `failed`/`cancelled`/`blocked` → 记 `blocked`（**被连累优先于未选中**，否则会把「上游挂了」误报成「条件没选它」）。数据依赖本身没问题（或本就没有数据入边）、纯粹因为 route 没选中 → `skipped`。
- **预算路径同样适用**：预算停下时，未选中节点仍是 `skipped`（**route 没选它跟预算无关**），不参与 `budget_exceeded`/`blocked` 的二分。
- **状态语义**：`skipped` 是**终态**（要进 `TERMINAL_NODE_STATUSES`，否则 `_teardown`/收敛逻辑会把它当未完成），但是**良性终态**——不使整图 `failed`，要进 `_unit_counts` 的独立计数桶（**不能落进 `pending_units`**，否则「图跑完了还有 pending」自相矛盾）。
- **前端**：第 8 档配色（**冷灰蓝**，与 `blocked` 的黄明显区隔）、角标 `—`、**虚边框**（沿用 Temporal 的「虚线 = 非终局/未发生」语汇）；图例加一行人话「未选中：条件判断没走这条分支」；`groupStatus` 聚合时 `skipped` **不参与**「最差状态」竞争（它既不是失败也不是受阻）。
- **下游传播**：`skipped` 节点无产出，其数据出边按既有规则落到 `inactive`（不新增 `_EDGE_BLOCKED_SOURCE_STATUSES` 成员——`skipped` 不是「源挂了」，不该把下游标成 `blocked`；下游若因此永不就绪，会在 `_teardown` 时按缺口 1 的同一条规则各自归位）。

**缺口 2：route 的数据入边永远等不到 `passed`，掉进 `inactive` 兜底。**

同一张实跑快照里 `a→gate` 是 **`inactive`**，但 `a` 明明 `completed`、gate 也确实读到了 `a` 的产出（才判出 APPROVED）。根因：`gate` 是 route，它读上游走 `_route_verdict()` → `_node_output(upstream, "result")`（`scheduler.py:2019-2029`），**这条路径不经过任何 `_mark_consumed` 调用点**（四个调用点分别在 `_collect_slots` / `_node_task_text` / `_aggregate_task_text` / `_write_root_result`，route 一个都不走）。于是 `_consumed_edges` 里没有 `(a, gate)`，`_edge_status` 的 `passed` 档命中不了，掉到 `inactive` 兜底。

**方案**：在 `_route_verdict` 读上游产出处**旁加** per-edge 记账（`_consumed_edges.add((edge.source, edge.target))`），与 #190 决策 7/2026-09-15 的做法**完全同构**——`_mark_consumed` 本体一行不改（grill 决策 12 的红线），C5 的 `_consumed_run_ids`/`useful_runs`/`redundancy` **逐位不变**。

**影响面（比前端项大，必须写清）**：
- `agent/subagent/scheduler.py`：`TERMINAL_NODE_STATUSES` 加 `skipped`；`_teardown` 的 `pending` 分支加判据；`_unit_counts` 加 `skipped_units` 桶；`_route_verdict` 旁加 per-edge 记账。
- `agent/subagent/aggregation.py` 或相关：确认自动插层/聚合对 `skipped` 的处理（若无引用则不改）。
- 契约面：`_envelope` 的节点 `status` 取值集合**新增一个值**（`NodeState.to_dict` 直出 status，不需要改代码，但**消费方**——benchmark 报告、`GetWorkflow`——要容忍新值）。**这是本 change 唯一动到父 Agent 可见契约的地方**，`_envelope` 的**结构**不变、只是 status 多一个可能值。
- spec：`openspec/specs/multi-agent-collaboration/spec.md` 或 `subagents` 需要一条 MODIFIED 说明「未选中分支记 `skipped` 而非 `blocked`」；本 change 的 delta 里加对应 Requirement。

### D3 — 数据面：三处**加法**字段，bounded，不动父契约

`workflow_graph_snapshot()` 补三个**加法**字段（既有字段语义/顺序/键名一字不改）：

| 字段 | 位置 | 来源 | 为什么需要 |
|---|---|---|---|
| `reason` | node | `NodeState.reason`（既有字段，**今天没进快照**，grill 决策 1 已核实） | B 的因果权威文本 |
| `started_at` / `finished_at` | 图级 payload | scheduler 已有 `self._started_at`/`self._finished_at` | D 的多图 tab「何时起 / 耗时」 |
| `items_completed` / `items_failed` | node（仅 foreach / `__auto_agg__`） | 新增 `NodeState` 计数（见下） | D 的「完成 M/N」 |

**bounded 是硬要求（grill 决策 1）**：`state.reason` 可能取到完整异常文本——`_run_node` 的 `except` 分支写 `state.error = f"{type(exc).__name__}: {exc}"` 后 `state.reason = state.reason or state.error`（`scheduler.py:1294-1310`），另一条来自 `envelope["reason"]`（即 `run.reason = result.error`，`manager.py:1215`）。截断必须在**投影里**做（`reason[: _SUMMARY_LIMIT]`，=400）——`state.reason` 本体**不能改**（它是 `_envelope` 的字段）。**这条不写清，快照 bounded 就是空话**（#190 决策 4 的同类坑）。

**图级时间的哨兵语义（grill 决策 2）**：`self._started_at = 0.0` 是构造期哨兵（`scheduler.py:419`，`declared` 态可取快照，测试 `test_workflow_graph_snapshot.py:341-351` 就断言 `declared`），`self._finished_at: float | None = None`（`:687` 的 finally 才赋值，运行中为 `None`）。快照**必须把「没有值」统一成 `null`**：`started_at: (self._started_at or None)`、`finished_at: self._finished_at`——绝不能让前端把 `0.0` 当 epoch 0 渲染成「56 年前」或算出天文耗时。**不要复用** `_envelope` 的 `self._finished_at or time.time()` 口径（`:2336`）。

**`items_completed`/`items_failed` 的记账（grill 决策 3；⚠ **记账点已按 G1 修正**）**：

> **G1 修正说明（本 change 的完备性审查发现的设计错误）**：原写「在 `gather` 结果循环里旁加自增」——但那个循环在 `await asyncio.gather(...)`（`scheduler.py:1482`）**之后**才执行（`:1485-1497`）。所以计数只有两种取值：**0 和 N**，整个运行期显示「完成 0/12」，全部跑完才跳到 12。**D5 的立项动机（「看到并行」）在时间维度上完全落空**——这是「按 design 实现完仍然看不到」的缺陷，必须改设计。
>
> **正确记账点：每项完成即 +1——在 `_run_foreach_item` 的返回处（`:1517-1525` 的 `try` 返回前 / `finally` 旁），而不是 `_execute_foreach` 的 gather 之后。** 每项的 `_launch_run` 返回时该项已终态，此刻自增；`asyncio.gather` 只是汇总，不承担记账。

- **失败口径必须与既有 `failures` 对齐**：`_launch_run` 返回的 envelope `status != "completed"` 即算失败（与 gather 循环的判据一致）；`_run_foreach_item` 抛异常/`CancelledError` 的路径也要落到计数（异常不吞、继续抛，但计数在抛前更新）。
- **必须在 `_execute_foreach` 开头（`:1462-1466`，与 `state.items`/`state.subagent_ids`/`state.run_ids` 重置同一处）把两个计数清零**——route 回边激活同一个 foreach 容器重跑会累加出 `M > N`。
- **项级状态（G7）**：同时维护 `items_running`（已派发未终态）与 per-item 状态数组（`state.item_states: list[str]`，长度 N）。这是 D5.2 迷你堆叠条的数据源，也是「N 项里有几个在跑/几个在排队」的答案。bounded：N 有 `max_items` 上限（200），状态是短字符串。
- **每次项级迁移都要推帧（G2）**：否则即使计数对了，前端在 A→B 迁移点之间仍收不到（见 D2c）。用既有 `GraphEventForwarder` 的 0.1s 合并窗削峰，不放大流量。
- `asyncio.CancelledError` 分支提前 return 时，计数停在部分值——与既有 `state.status = "cancelled"` 一致，前端要容忍 `M < N`。

**白名单同步（grill 决策 4）**：只影响 `tests/agent/subagent/test_workflow_graph_snapshot.py` 一个文件——节点白名单 `SNAPSHOT_NODE_KEYS` 是模块级 `frozenset`（`:34-36`），用 `<=` 断言（`:150`）；**图级白名单是内联 set 字面量**（`:173-176`），加两个时间戳要改那里（没有常量可改）。全仓 grep 确认没有第二个测试断言快照键集（`test_workflow_graph_events.py` 只看 `node["status"]`/`diagnostics`），`test_snapshot_does_not_drift_envelope_contract`（`:358-368`）断言 `_envelope`/`parent_envelope` 键、本 change 不动这两者会继续绿。白名单是「多一个键都是没挑字段」的守卫，改它必须是**有意识**的，且**保留**排除断言（`subagent_ids`/`slots`/`raw`/`error`/`bus`/`attribution`）。

### D4 — 节点详情：分 Tab 的抽屉面板 + 新增只读 transcript 路由（复用 `inspect_transcript`）

**交互（调研对标 AWS Step Functions 的 Step details，最贴近本场景的形态）**：点节点 → 打开**详情抽屉**。桌面（>720px）从**右侧**滑入（宽 360–420px，`position:absolute` 覆盖画布右侧，**不挤压画布宽度**，否则 SVG 要重排）；手机（≤720px）从**底部**滑入（高 ~70vh，带拖拽把手）。**同一份 DOM**，720 断点切 class（与既有跨端手法一致，不加新断点）。**移动端不用居中模态**（拇指够不到、丢失「我在看哪个节点」的上下文）。关闭：`×` / 点遮罩 / Esc；`role="dialog"` + `aria-modal` + focus trap + 关闭后焦点回到节点。

**面板内容分 Tab**（默认 `任务`）：
1. **任务**：node id（完整）+ kind 徽标 + 状态色点/角标 + 状态词 + **因果句（D2）** + runs 次数 + 起止与耗时 + 节点 task 模板。
2. **产出**：快照里的 bounded summary（截断标注）+ `result_ref`（有则显示）。
3. **对话**：**完整 transcript，懒加载**——切到该 tab 才发请求、才建 DOM。

**点击语义拆分（重要行为变更；grill 决策 5 修正了要改的测试文件）**：今天点节点 = 展开/收起折叠组（`workflow.js:423` 绑定 → `:434-443` 的 `toggleGroup`，非 `groupLeader` 直接 return）。改为——**点节点 = 打开详情面板；折叠组的展开/收起挪到节点上的一个独立小控件**（形态见 Q2）。否则 foreach 容器的「看详情」与「展开项」两个意图在同一个点击上打架。**真正会红的不是 `test_workflow_graph_js.py`**（那是纯函数单测，无 click 用例），而是浏览器 smoke `tests/web_tests/test_workflow_graph_browser.py:343-369` 的 `test_collapsed_group_click_expands_members`（两次点 `.workflow-node[data-node-id='fan']`）；配套 CSS 是 `web/static/style.css:1482` 的 `.workflow-node.group-leader { cursor: pointer }`——拆分后普通节点也要可点，cursor 口径要一起改。（`test_workflow_graph_js.py:322-354` 的折叠相关断言是 `collapseGraph`/`groupLeader` **数据**断言，与点击无关，本 change 不动。）

**transcript 的渲染（对标 GitHub Actions 大日志工程的结论）**：**只做 UI 虚拟化，不做数据虚拟化**（数据是快照/接口一次取回的，本来就在内存）——按 **50 行一组聚簇**、按簇增删 DOM 而非按行；超长单行截断；不引入可视化库（GitHub 试遍现成库后自研，理由：换行可变行高、文本选择失效、多滚动条——我们零依赖自绘，更不该引库）。

**数据来源（关键决策）**：**新增只读路由**，而非复用 `InspectSubagentTranscript` 工具：

```
GET /api/sessions/{session_id}/workflows/{workflow_id}/nodes/{node_id}/transcript
  → 三态 union（对应「界面效果 §0」的节点↔subagent 三类）：
    {kind: "single",     node_id, subagent_id, status, messages: [...], truncated, included_tool_results}   # subagent / aggregate(llm) / auto-agg
    {kind: "candidates", node_id, node_kind, total, offset, limit, has_more, candidates: [{index, subagent_id, run_id, status, label, summary, started_at, finished_at}]}  # foreach 容器
    {kind: "none",       node_id, node_kind, reason}   # route / aggregate(collect) / 未派发节点
```

- **为什么新路由**：`InspectSubagentTranscript` 是 **LLM 面工具**（`Tool` 子类、要 permission、走 AgentLoop 工具注册与协议）。Web 层要用它得绕过工具协议直接调 manager——不如直接暴露一个 HTTP 只读接口。两者底层**复用同一个 `SubAgentManager.inspect_transcript()`**，不复制逻辑。
- **`inspect_transcript` 的真实口径（grill 决策 7，防实现踩坑）**：它**不按 `run_id` 过滤**——messages 分支取的是 `session.messages[-limit:]`（`manager.py:1035-1038`，即整段 session 消息尾部，跨多次 run 累积），`run_id` 只是**回显**；默认 `limit=5`；**没有单条内容截断**；`scope="summary"` 的返回体**根本没有 `messages` 键**（只有 `summary`）。所以路由必须：显式传 `scope="recent_messages"` + `limit`（上限 200）、**自己在路由层加单条内容截断**、并在 `_require_session` 抛 `KeyError`（`manager.py:1433-1437`）时转结构化响应。`truncated` 的语义是 `len(messages) > limit`（已剔除 tool 角色后）——前端文案别写成「内容被截断」。
- **node_id → subagent 解析（grill 决策 8 + 「界面效果 §0」，按候选集而非首条）**：`SubagentSessionRecord` 已有 `workflow_id` + `node_id`（`manager.py:168-169`）。解析规则按候选**收集**：**0 条** → `kind:"none"`（未派发，或 route / aggregate(collect) 这类**本就不产生 run** 的节点）；**1 条** → `kind:"single"`；**N>1 条** → `kind:"candidates"`。**foreach 容器**因容器清空 `subagent_id`（`scheduler.py:1464`）后每项独立建 session、而 `_launch_run` 的 `set_node_id(node.id)`（`:1669`）写的是**容器 id**，故 `_sessions`（`manager.py:360`）里有 N 条同键记录 → 走 `candidates`（**含 N=1 的 foreach 也归 `single`**，不设特例分支）。普通节点重跑**不会**产生第二条候选（`_launch_run` 复用 `reuse_state.subagent_id`，`:1673-1682`）。
- **`candidates` 必须 bounded**：默认 `limit=50`、硬上限 200，带 `total`/`has_more`/`offset`；候选只带短摘要（`summary` 再截断），真正 messages 等点某项时按 `subagent_id`（+`run_id`）再取一次。
- **`run_id` 过滤（grill 决策 7 的连带约束）**：`inspect_transcript` 当前**不按 `run_id` 过滤**（取 `session.messages[-limit:]`）——候选列表若要精确到某项的 run，必须**先修候选定位与 run 级取数**，否则只是把「展示错 run」换个入口（codex 复核指出的坑）。
- **边界（不猜、优雅降级）**：未派发节点（`pending`/`blocked`）→ `kind:"none"` + 说明，前端显示「该节点未执行，无对话」（配合 D2 因果句，这本身就是有用信息）；route 节点改为展示**命中标签 + 选中出口**，collect 节点改为展示**合并产出**（`kind:"none"` 时的类型化信息，不是一句「无对话」了事）。
- **信任级与 session 口径（grill 决策 9）**：「需真实存在的 `session_id`」在本仓库 = **在内存里存在**——既有路由用 `session_manager.get_session()`（`web/server.py:160-175`），只查内存字典（`web/session.py:1013-1014`），冷会话/进程重启后一律 404（与 `/api/sessions/{id}/timeline` 同口径）。**这不是缺陷但要写进 spec/测试**（tasks 2.4 的「未知 session 404」要覆盖「进程重启后同名 session」这个最易误判为 bug 的场景），前端「对话」tab 对 404 降级为「该会话未在本进程加载」。只读、**不调 LLM、不写盘、不改执行状态**、`include_tool_results` 默认 false。

**实时更新**：面板开着时，节点状态/产出随快照**就地刷新**；但**`对话` tab 的 transcript 不跟着重排**（会打断阅读）——沿用 Temporal 的「暂停实时更新以便调查」思路，给一个暂停按钮。

### D5 — foreach 并行可见性：容器常显 `完成 M/N` + 项列表进抽屉

**先明确 foreach 的语义（「每个项到底是什么」）**：一个字面**任务是模板、每个 item 展开成一个独立 subagent**：

- 声明层只有**一个** `fan` 节点和它的 `task` 模板（如 `"对 {item} 执行代码体检"`）。
- 运行时 `_resolve_items` 解析出 N 个 item（静态 `items` 列表，或由上游产出经 `source`/`source_field` 抽取）；`render_item_task(template, item, index)` 把 `{item}`/`{index}`/字典字段替换成具体值 → 得到 N 个**具体任务**（`"对 a.js 执行代码体检"`…）。
- 每个 item 经 `_run_foreach_item` → `_launch_run` → `create_subagent` 建**一个独立 subagent**（自己的 `SubagentSessionRecord` + `messages` + 完整 `AgentLoop` + 自己的 `subagent_id`/`run_id`/预算/状态/transcript）。**不是「跑一段代码」**——它是一个被派了具体任务的 AI agent，这正是「点进去看它聊了什么」有意义的原因。
- 并发不是无界：N 个 `asyncio.gather` 提交后各自 `await _acquire_slot()` 排队，**实际并行度受 `max_active` 约束**（12 项可能只同时跑 3–4 个，其余排队）。所以候选列表里会看到部分项仍是排队/未派发态。

**同时必须区分三种「展开」**（本文档后续凡说「展开」都要指明是哪一种，避免歧义）：

| # | 名称 | 触发 | 揭示什么 | 现状 |
|---|---|---|---|---|
| ① | **图级折叠展开** | 节点数 ≥50 时点节点上的 `▸`（`collapseGraph` 的 `expandedGroups`） | 被折叠隐藏的**真节点**——即 `__auto_agg__` 自动插层节点（`isAutoNode` 判据），**不是** foreach 的 N 个 item | #190 已有 |
| ② | **项列表展开**（本 change 的 D5） | 点 foreach 容器节点 → 详情抽屉「对话」tab | 该容器的 N 个**候选项**（`kind:"candidates"`），点某一项再取那一项的 transcript | 本 change 新增 |
| ③ | **项级画布展开**（**明确不做**） | —— | 把 `fan` 在画布上炸成 N 个节点 | Non-Goal，理由见下 |

**为什么不做 ③（项级画布展开）**：
- **项不是 `NodeState`，不在 `ExecutionPlan` 里**——`_expand_plan`/`with_expansion` 只把**自动插层的 aggregate 节点**塞进 plan（`aggregation.py:242` 的 `with_expansion` + `inserted_nodes`），展开项本身只体现在容器的 `state.items`（计数）/`subagent_ids`/`run_ids` 上。所以画布上不存在「项节点」这种实体，要做只能**前端凭空合成**：合成的节点没有真实入/出边（N 个项语义上同源同汇）、没有 scheduler 推的状态、布局层与边推导全部要特判——**等于在图里维护第二套假节点**。
- **规模会爆炸**：`max_items` 上限允许 N 到 200，画布上 = 200 个无边的孤立节点。
- **业界一致选择「计数 + 列表」而非「铺节点」**（调研结论）：Airflow Graph view 把映射实例叠成一个节点（issue #54229 正在抱怨），Grid view 走 `Mapped Instances` 列表；Step Functions 的 Map 用 **iteration viewer** + 计数；Argo 的 Graph view 在 N 大时会爆炸。**三家都没把 fan-out 铺成 N 个图节点。**
- 「看到并行」这个诉求由 ② 满足：抽屉里的候选列表本身就是「N 个并行项」的呈现，且能逐项下钻。

**现状**：`N items` 只在 ≥50 节点折叠时才显示，<50 全展开时容器**完全不提并行项数**——「并行」隐形。

**方案**：
1. 容器节点**常显**计数行：`M/N 完成`（M = `items_completed`，N = 既有 `items`），有失败时追加 `· 失败 K`。计数行是**容器状态的补充**，不改变状态语义。
2. 计数行旁加**迷你堆叠条**（N 小则 N 个 2px 小格各按自身状态着色，N>20 退化为按比例着色的宽条）——对标 Dagster 的分区健康条（「传范围不传 N 个状态」）。
3. **点容器节点 → 详情面板的「任务」tab 展示项列表**（`#0..#N-1` + 每项状态/摘要，可点进单项；数据源就是 D4 路由返回的**候选集**，见 Q1）。**不把项铺成 N 个 DAG 节点**：项不是 `NodeState`（#190 决策 8），铺节点要新增布局/边/交互一整套，且 Argo 的 Graph view 在 N 大时会爆炸、Airflow 干脆不在 Graph view 展开——两者都选了「列表 + 计数」（Airflow Grid 的 Mapped Instances、Step Functions 的 iteration viewer）。
4. **上界**：N 超过 50 时项列表只渲染「失败项 + 前若干项 + 聚合统计」，且列表本身做 UI 虚拟化（D4）。

### D6 — 多图 tab 元信息：序号 + 起止 + 耗时 + 完成计数

**现状**：tab 只有 `truncate(goal, 24)` + 状态词，三张图分不清。

**方案**：tab 升级为紧凑多段标签（对标 GitHub Actions run 列表 + Temporal 的 relative time）：

```
[●] #3 · 2 分钟前 · 2m18s · 3/5
```

- `#3` = **该 session 内 workflow 出现顺序**（口径见 Q3）。**实现注意（grill 决策）**：**不能拿 `Map` 的插入下标当序号**——`pruneGraphs` 会 `state.graphs.delete(evicted.id)`（`workflow.js:124-135`），删掉 `#1` 后原 `#2` 下标变 0、编号整体前移；必须在 `graphState` 上存一个**显式计数器/显式字段**。另外 tab 可能**无快照存在**（`workflow_started` 一到就 `ensureGraph`，`entry.snapshot === null`，`renderGraphTabs` 已用 `entry.snapshot && …` 兜底，`:180-189`）——本 change 新增的耗时/`M/N` 格式化函数**必须能吃 `null` 快照**并退化为只显示 `#序号 · goal`。
- 相对时间（`2 分钟前`），运行中显示 `已跑 42s` 并**实时跳秒**；`title` 给绝对时间（Temporal 的 UTC/Local/Relative 三格式思路）。
- 耗时用图级 `started_at`/`finished_at`（D3 补齐）。
- `3/5` = 完成节点数/总数（「结果差异」最直接的摘要）。
- 状态圆点用**最差状态色**（复用既有 `groupStatus()` 逻辑）。
- **排序**：运行中的排最前，其余按开始时间倒序（Temporal 的 `NULLS FIRST` 思路）；淘汰策略（最近 5 张终态 + 全部 running）沿用 #190 Q9 **不变**。
- 完整 goal 进 `title`（避免截断信息丢失）。

### D7 — 边统计口径如实 + 并行边垂直偏移

**现状根因（grill 决策 11 修正为两条并存的根因）**：
1. **口径不一致**：`renderSummary()` 报 `snapshot.edges.length`（原始快照边数，`workflow.js:262-265`），而实际画的是 `collapsed.edges`。
2. **几何重合**：`edgePath()` **没有任何垂直偏移**（`workflow_graph.js:285-300`），同一对节点多条边完全重叠。

**关键修正**：`collapseGraph` 的去重**只在折叠态发生**（节点数 ≥ threshold，`workflow_graph.js:507-516` 的 `seenPairs` 按 `from->to:kind`）；**未折叠时边原样透传**（`:404-406`）——所以 <50 节点的小图上「11 edges 只画 6 条线」**只能由几何重合解释**。实现**不能假设「去重一定发生」**，文案也不能写死「含并行边/折叠合并」。

**方案**：
1. **统计如实（必做）**：summary 报**实际绘制路径数 + 原始边数**，两个数字相等时不加解释后缀（小图场景 `collapsed.edges.length === snapshot.edges.length`），不等时才给可解释口径（如 `6 paths (原始 11 edges)`）。
2. **并行边垂直偏移（推荐；grill 决策 6 修正了改动面）**：同一对 `(from,to)` 的第 k 条（共 n 条）可见边在法向等距铺开 `offset = (k - (n-1)/2) * DELTA`（`DELTA` 8–10px，横向偏移 y、纵向偏移 x），抄 igraph `curve_multiple()`。**改动面不止 `edgePath()`**——它的签名 `edgePath(from,to,orientation)` 拿不到 multiplicity，必须在 `layoutGraph` 的 `layoutEdges`（`:248-266`，唯一能同时看到同一对 `(from,to)` 全部边的地方）**先按 `(from,to)` 分组**统计 `n`/`k`，再把 `{index,total}`（或算好的 `offset`）作为**可选参数**传进 `edgePath`（保持对外导出 API `:563` 向后兼容）。分组键用 **`(from,to)` 而不是 `(from,to,kind)`**：同一对端点上控制边与数据边不会共存（route 出边全被 `is_control_edge` 判为控制边，`workflow.py:243-245`），用 `(from,to)` 更简单且不会因未来新增 kind 而漏铺。
3. **边 `channel` 不要指望线型**：小屏 + 缩放后实/虚/点线基本不可见——边 `title` 明确写 `channel: artifact · status: active · from: X · to: Y`，且 hover 高亮整条链路。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 本 change 走 grill 的非平凡 change——DAG 观测 UI 的信息架构有多条互斥可选路径（图例形态、详情面板形态、foreach 展示、点击语义），且需决策「前端增强 vs 后端补字段」的边界，命中 `full` 判据。
- research questions:
  1. 工作流/DAG UI 的图例怎么做（固定图例条 / hover / 首次引导），状态如何多重编码（色 + 图标 + 形状）以兼顾色盲无障碍？
  2. 业界如何让用户分清「自身失败 vs 被上游挡住没跑 vs 被资源/预算闸门停掉」，有没有「为什么是这个状态」的因果提示？
  3. 节点级 drill-down（任务/产出/对话日志）在业界主流是侧边栏/弹窗/底部抽屉/展开行，移动端怎么处理，大文本怎么做截断与懒加载？
  4. foreach / map-reduce 这类 fan-out「一个容器 N 个并行项」在流程图里怎么表达最直观？
  5. 同一会话多次运行的列表展示哪些元信息、怎么排序命名？
  6. 同一对节点多条边几何重合导致「统计数 ≠ 可见线数」，业界怎么做？
- findings: 本轮由**独立零记忆调研 subagent**（paseo 托管，`claude-fable-5[1m]`，2026-09-17）完成，覆盖 Airflow / Argo Workflows / Temporal / Prefect / Dagster / n8n / Tekton / AWS Step Functions / GitHub Actions 九个产品的源码 issue、官方文档与工程博客。**本地参考仓库不可用**（`.dev/reference-repos.txt` 在本工作区不存在），故本轮依据为公开业界来源；codegraph 在本仓库未索引。关键结论：
  1. **图例**：Airflow 长期只有色块、直到 issue #28737 才加**常驻可见**图例条（有人主张塞进 InfoTooltip 被否，理由是图例应「easily visible」）。更关键的反面教材是 issue #66323：Airflow `failed`/`upstream_failed` 两色在绿绿色盲下 ΔE≈0.4（近乎同色），AIP-38（#43054）因此立规「**should always try to depict state through other means than simply color**」；Tekton Dashboard #832 改用 status **reason** 而非 message；n8n 用**角标图标**（黄色三角=数据过期）+ 悬停 tooltip；Dagster 每个状态枚举带 color **和 label 文本**、混合状态用**斜条纹**。色盲规范（WCAG 1.4.1 不得仅用颜色）建议**拉开明度差而非只拉色相**，用 deuteranopia 模拟验证。
  2. **非成功态语义**：Airflow 的 `failed`（自己挂）/`upstream_failed`（被上游挡住）/`skipped`（trigger rule 判定不用跑）语义分开，且日志里**已有机器生成的因果串**（issue #33446：「Task's trigger rule 'all_success' requires all upstream tasks to have succeeded…」）——**但这段因果没进 UI**，正是用户反复困惑的根因。Argo 把「被挡住」命名得更精确：`Skipped`（自己的 when 为 false）vs `Omitted`（depends 不满足）。Prefect/Temporal 用状态名与**线型**承载「还会不会继续」（红线=失败、红虚线=重试中）。
  3. **节点 drill-down**：**AWS Step Functions 与本场景最贴近**——Graph view 点节点 → 右侧滑出 Step details，面板内**分 Tab**（Input/Output/Details/Definition/Events），出错时 tab 头带错误图标并**同步高亮图中出错节点**；Map 状态在 Details 里给迭代计数 + **iteration viewer 下拉**。Temporal 的 History 面板有四种视图 + 手风琴展开态按设备持久化。**GitHub Actions 大日志工程**是最权威的性能参考：99.51% 的 job 日志 <5 万行、浏览器 2 万行以上吃力，最终**自研**渲染（现成库在前端要么不支持可变行高、要么虚拟化破坏文本选择），采「**只做 UI 虚拟化、不做数据虚拟化**」+ **50 行一组聚簇、按簇增删 DOM**。移动端通行结论：桌面右侧抽屉 / **移动底部抽屉（带拖拽把手）**，**不用居中模态**（拇指够不到、丢上下文），触控目标 ≥44px。
  4. **fan-out 可视化**：Airflow 的 Graph view 把映射实例叠成一个节点（issue #54229 正在抱怨「看不出映射几个、各自成败」），**Grid view 走另一条路**——`3 Tasks Mapped` 计数 + Mapped Instances 列表（分页 `1-3 of 3`）；Step Functions 的 Map 直接给 **Failed/Aborted/Succeeded/InProgress 四计数 + iteration viewer**；Dagster 用**状态点 + 健康条 + 斜条纹**（按 range 下发，不是传 N 个状态）。**结论：计数 + 可展开列表是主流，铺成 N 个图节点会被拒**。
  5. **multi-run 列表**：GitHub Actions 给 状态徽标 + **耗时** + **run number** + 触发事件/人（且刻意把 status/conclusion **拍平成一个字段**）；Airflow Runs tab 给 `run_type`（manual/scheduled/backfill，即「触发原因」枚举化）+ duration + 可排序；Temporal **默认 `ClosedTime DESC NULLS FIRST`**（未结束排最前）+ **可切相对时间**（「3 分钟前」，移动端更好读）。
  6. **重叠边**：igraph 文档直陈「多条边画成直线时**会重叠不可见**」，其 `curve_multiple()` 为多重边在 `-start..+start` 等距铺开曲率——**最小改动、信息量最大**；Graphviz 在 `splines=true` 时把平行边**合并成一条**（正是我们现在的问题）。边捆绑（Holten 2006 / `ggraph::geom_conn_bundle`）是为几百条边的 hairball 设计，**本场景用不上也不该用**。
- design impact: 直接改写了本 change 的多项选型——**D1** 定「常驻可折叠图例条 + 人话解释」（否掉 hover-only 与首次引导 tour）；**D2** 增「形状/角标/虚边框」第二编码（否掉「只调色」）并把「因果句」提为最高 ROI 项，同时暴露「`<svg:title>` 在移动端不显示」这一**功能性缺失**；**D3** 的 `reason` 字段被证实是业界共识缺口（Airflow 有因果串但没搬上 UI）；**D4** 定「分 Tab 抽屉 + 只做 UI 虚拟化 + 50 行聚簇 + 移动端底部抽屉/不用模态」并新增「点击语义拆分」；**D5** 定「常显计数 + 堆叠条 + 项列表进抽屉、**不铺 N 个节点**」；**D6** 定 tab 的 `#序号 · 相对时间 · 耗时 · M/N` 与「运行中排最前」；**D7** 定「统计如实 + `edgePath()` 内平行边等距偏移」。明确**不采纳**：边捆绑、可视化库（vis-timeline 等）、数据虚拟化、强制引导 tour、移动端居中模态、照搬 Airflow 配色。

## Pre-Implementation Review

> **已执行（2026-09-17）**：独立零记忆 grill subagent（paseo 托管，`claude-fable-5[1m]`）审视 D1–D7，产出 `reviews/grill-design.md`（**12 条 Confirmed Decisions + 4 条 Open Questions**），逐条 Read 代码复核并纠正了本 design 的 8 处 file:line/行为断言。本设计已按 12 条 Confirmed Decisions 回写（`reason` 截断在投影层、图级时间哨兵统一 `null`、foreach 计数清零与失败口径、白名单内联字面量、点击语义的**真实**受影响测试是浏览器 smoke、并行边偏移的改动面不止 `edgePath`、`inspect_transcript` 不按 run_id 过滤、`(workflow_id,node_id)` 候选集语义、session 为内存口径）。
> **停轮中**：4 条 Open Questions（Q1 foreach 容器 transcript 语义 / Q2 展开控件形态 / Q3 tab 序号口径 / Q4 `reason` 截断额度）须逐条抛给用户、收到答复后回填 `reviews/grill-design.md` 的 `## User Confirmation`；**全部确认前不得写实现代码**。

## Risks / Trade-offs

- **风险**：快照加字段会碰既有白名单契约测试（`SNAPSHOT_NODE_KEYS`/图级断言）→ **对策**：同步更新白名单，并保留「`_envelope`/`parent_envelope` 逐字节不变」的回归断言（#190 已有此测试，本 change 必须让它继续绿）。
- **风险**：`reason` 忘记截断会让快照失去 bounded 保证 → **对策**：与 `summary` 同用 `_SUMMARY_LIMIT`，加一条「超长 error 被截断」单测。
- **风险**：**点击语义变更**（点节点从「展开组」改为「开详情」）会破坏既有交互与测试 → **对策**：为折叠组提供独立展开控件，同步更新 `test_workflow_graph_js.py`/浏览器 smoke 的点击用例；这是**行为变更**，须写进 spec delta 与 proposal。
- **风险**：transcript 接口把子 agent 运行内容经 HTTP 暴露 → **对策**：只读、需真实 session、bounded（条数 + 单条长度上限）、默认排除工具结果；与 Chat 视图同信任级（Chat 本已展示这些对话）。**不新增写路径、不调 LLM**。
- **风险**：`(workflow_id, node_id)` 解析不到唯一 subagent（foreach 容器、route 未派发、node 重跑）→ **对策**：返回结构化「无单一 transcript」+ 说明，前端优雅降级；**不猜**。
- **风险**：图例/因果文案与 `NODE_COLORS` 等词表漂移 → **对策**：图例内容模型从词表**同源生成**，单测断言「7 档状态都在图例里」。
- **风险**：详情抽屉在手机端遮挡图 → **对策**：底部抽屉可拖拽/点遮罩关闭；抽屉开合**不改变图的 viewBox**（不重排）。
- **风险**：并行边偏移算法在极端情况（同对 10+ 条边）产生视觉重叠或越界 → **对策**：偏移量设上限，n 很大时退化为「聚合标注」（一条边 + `×N` 徽标，点开列 channel/status）。
- **Trade-off**：新增 HTTP 路由增加一个后端面 → 换「点节点看完整产出」这一最大痛点被解决。
- **Trade-off**：`items_completed`/`items_failed` 要动 `NodeState` + foreach 结果循环 → 换「并行可见」；改动局限在既有 `gather` 结果循环内，旁加计数、不改既有 status/reason 语义。
- **Trade-off**：图例条 + 抽屉占屏幕空间（手机尤甚）→ 用「默认折叠 + 同一 DOM 切 class」把增量压到最小。

## Testing Strategy

- **前端纯函数（node + vm）**：
  - 图例：`legendModel()` 覆盖 4 类节点 + 7 档状态 + 5 档边状态 + channel 线型，且与 `NODE_COLORS`/`EDGE_STYLES`/`KIND_GLYPHS`/`NODE_LABELS` **同源**（改词表则图例跟随）。
  - 因果：`explainNode()` 对 failed / blocked（有失败上游 / 无失败上游）/ budget_exceeded / cancelled 各返回正确人话；**回归「12 文件 foreach 预算超限」场景**（3 failed + 2 blocked + 1 budget_exceeded）断言每类因由正确。
  - 并行边偏移：同一对节点 3 条可见边 → 3 条路径**互不相同**且都有限；n 超上限时退化聚合。
  - 边统计：`11 edges` 去重成 6 条路径 → summary 报 `6 paths (原始 11 edges)`。
  - tab 元信息：`#序号 · 相对时间 · 耗时 · M/N` 格式化，运行中/终态两分支，运行中排最前。
  - foreach 计数与堆叠条：`M/N 完成`（进行中）/ `· 失败 K`（有失败）/ 堆叠条退化阈值。
- **后端**：
  - 快照新增字段（`reason` bounded 截断、图级 `started_at`/`finished_at`、foreach `items_completed`/`items_failed`）；白名单更新；**`_envelope`/`parent_envelope` 不漂移**回归。
  - transcript 路由：正常（有 subagent）/ foreach 容器（无单一 transcript，附项数）/ 未派发节点（`subagent_id: null`）/ 未知 node 404 / 未知 session 404 / bounded（条数 + 单条长度 + 默认排除 tool 结果）。
- **浏览器（Playwright smoke）**：图例条可见且可折叠；点节点打开详情抽屉（桌面右侧 / 手机底部）；切「对话」tab 触发 transcript 请求并渲染；折叠组用独立控件展开（点击语义拆分后仍可展开）。
- **benchmark smoke**：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`（本 change 触及 observability/快照链，按 artifact checker 门禁执行）。
- **兼容回归**：既有无 workflow 会话前端不崩；`test_workflow_graph_js.py` 既有用例（含点击语义相关）继续绿。
