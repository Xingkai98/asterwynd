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

- **不做节点级重跑 / 重试**（需新调度器原语：用户触发复位 + 重派发 + 与 `_accepting`/预算/`activations` 的交互定义；且要回答「重跑已完成的节点？」「下游全级联？」「预算已耗尽还能重跑？」）。**另立 change：[#201](https://github.com/Xingkai98/asterwynd/issues/201)**。
- **不做运行内事件流 / 状态迁移时间线**（数据齐备：`latest_events` 内存 5 条 + `events.jsonl` 落盘，但要先定暴露口径与容量）。**另立 change：[#202](https://github.com/Xingkai98/asterwynd/issues/202)**。注意：本 Non-Goal **不含**「不做时间轴回放（snapshot scrubber）」以外的含义——**节点级「变化高亮」不做为动画，但作为一次性标记做**（见 D8）。
- **不做节点搜索 / 筛选**（真过滤会破坏 DAG 布局：隐藏节点需重连边、重算层级）。本 change 只做**压暗（dim）**轻量版（G20 延后）。**另立 change：[#203](https://github.com/Xingkai98/asterwynd/issues/203)**。
- **不做异常节点定位/聚焦**（G19：统计行异常计数可点 → viewBox 聚焦；零后端成本，但用户裁决不进本 change）——**显式记录为延后：[#203](https://github.com/Xingkai98/asterwynd/issues/203)**。
- **不做内容复制**（G21：节点 id / `reason` / transcript 的 copy affordance；成本极低但用户裁决不进）——**另立 change：[#204](https://github.com/Xingkai98/asterwynd/issues/204)**。
- **不做导出 / 分享（PNG / JSON）**（要定导出形态、是否含图例与时间戳）。**另立 change：[#204](https://github.com/Xingkai98/asterwynd/issues/204)**。
- **不做长跑完成通知**（与图耦合度低）。**另立 change：[#205](https://github.com/Xingkai98/asterwynd/issues/205)**。
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
- `blocked` → **图级停止原因优先**（若快照 `status` ∈ {`budget_exceeded`/`cancelled`/`graph_recursion_exceeded`}，直接引用它）→ 否则**沿数据入边向上穿透**，收集**全部**未完成/失败的上游（含本身 `blocked` 的）→ 「被上游 `<ids>` 挡住，未执行」；一条都找不到 → 用自身 `reason` → 「流程结束前该节点一直未就绪」。
- `budget_exceeded` → 自身 `reason`（`budget exceeded (tokens)`）+ **图级 `budget` 数字**（见 D3/G13）→ 「预算超限（`tokens`：用掉 152.3k / 上限 100k）后停止」。
- `cancelled` → 「流程被取消，未执行完」。

> **审阅员 B 的两处修正（防 G1 类）**：
> 1. **`explainNode` 必须扩签名**。原写 `explainNode(node, edges, nodesById)`——它**看不到图级 `status`/`diagnostics`**，而「图级停止原因优先」这条修法在现签名下**无法实现**。签名改为 `explainNode(node, edges, nodesById, graphStatus, diagnostics)`（或直接收整个 snapshot）。
> 2. **扫描必须穿过 `blocked` 上游**。因为**本调度器里上游 `failed` 时下游会被派发、不会 `blocked`**（实跑证实：`_data_deps_satisfied` 只要求上游 ∈ `TERMINAL_NODE_STATUSES`，而 `failed` 在其中，`:79-81`/`:1161-1168`）。`blocked` 的真正来源是 `_teardown` 的 pending 分支——而那时整条链上的节点常常**一起**是 `blocked`（S 被门控 → R 未就绪 → T 未就绪）。只扫 `failed`/`cancelled` 在整条链上一无所获，会落到兜底句。**同时去掉「取 `finished_at` 最早」**——最早只说明它先失败、不代表它是原因，且 `finished_at` 在 G11 修好前对它自己也不可信。

因果句用于三处：**节点 `why` 小字**（仅异常态显示，正常态不占位）、节点 `<title>`、详情面板的「状态」区。**因果推导是纯函数**（拿 snapshot 即可算），可在 node+vm 里直接测「12 文件 foreach 超预算」这个真实场景的因果链。

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

- **判据（三个条件同时成立；有权威信号，不需要新记账）**：节点在 `_teardown` 时仍是 `pending`，且
  1. `_has_control_incoming(node)` —— 存在以 route 为源的入边；
  2. `state.activations <= 0` —— 没有任何 route 选中它；
  3. **（审阅员 B 补强，防「报假话」）每一条控制入边的源头 route 都已 `completed`** —— 即「确实做过判定，且没选它」。
  `activations` 是既有计数器（`_execute_route` 命中时 `successor.activations += 1`，`:1450`；派发时清零 `:1261`），`_ready_nodes` 已用它做「回边目标等激活」的门控（`:1184-1189`），**复用它不引入新机制**。
- **为什么必须有条件 3**：只满足 1+2 时，构造 `S`（被门控、从未激活）→ `R`（route，数据依赖 S）→ `T`（R 的控制出边）就能证伪——图收敛时 S/R/T 全 pending，R 因无控制入边落普通 `blocked`，而 **T 会被标成 `skipped`**。但 T 的真因是「R 根本没跑」，不是「条件没走这条」——**用户读到的是假话**，正是本 change 要消灭的那类错误。加上条件 3（R 未 `completed` → T 不满足 skipped）即落到 `blocked`，语义正确。
- **优先级（顺序在实现上必须写死）**：`_teardown` 的 pending 分支里，**先判 `skipped`（含条件 3），再判 `_budget_stop`**。否则 `_apply_budget_exhausted_status`（`:961-984`）会抢走判据，把被 route 门控的**根节点**写成 `budget_exceeded` 而非 `skipped`。
- **优先级（语义上）**：若节点有数据入边且上游 `failed`/`cancelled`/`blocked` → 记 `blocked`（**被连累优先于未选中**，否则会把「上游挂了」误报成「条件没选它」）。数据依赖本身没问题（或本就没有数据入边）、纯粹因为 route 没选中 → `skipped`。
- **预算路径**：预算停下时，**已确认未选中**的节点仍是 `skipped`（route 没选它跟预算无关），不参与 `budget_exceeded`/`blocked` 的二分；未确认（条件 2/3 不满足）的仍走既有二分。
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
> **正确记账点（审阅员 B 修正了落点）：在 `tasks` 创建处（`:1476-1479`）给每个 task `add_done_callback`，而不是「在 `_run_foreach_item` 的返回处」。** 后者**落不了地**——`_run_foreach_item` 的签名是 `(node, index, item)`（`:1509-1511`），**没有 `state` 形参**，文档指的「返回处 +1」实现者够不到容器 state（除非改签名，那是更大的改动）。`add_done_callback` 一处改动、天然覆盖正常返回与异常路径、不动 gather 循环。

- **回调必须区分「完成」与「非失败的中断」**：`_run_foreach_item` 在 `_acquire_slot()` 返回 False 时 `raise asyncio.CancelledError`（`:1513-1515`），`GraphRecursionError`/`WorkflowBudgetExceeded` 也会从该项抛出。**这三类一律不得计入 `items_failed`**（否则前端把「被取消」「图超限」「预算停」谎报成「失败 K」）。判据：`task.cancelled()` 或异常类型属于上述三类 → 只从 `items_running` 减；`task.exception()` 是普通异常、或返回的 envelope `status != "completed"` → `items_failed += 1`；否则 `items_completed += 1`。
- **必须在 `_execute_foreach` 开头（`:1462-1466`，与 `state.items`/`state.subagent_ids`/`state.run_ids` 重置同一处）把两个计数与 `item_states` 清零**——route 回边激活同一个 foreach 容器重跑会累加出 `M > N`。
- **项级状态（G7）**：维护 `state.item_states: list[str]`（长度 N）作为**权威 per-item 状态**（`pending`/`queued`/`started`/终态），以及派生计数 `items_running`/`items_completed`/`items_failed`。这是 D5.2 迷你堆叠条的数据源，也是「N 项里有几个在跑/几个在排队」的答案。bounded：N 有 `max_items` 上限（200），状态是短字符串。
- **`items_running` 的口径（审阅员 B 修正）**：**不能用「已派发未终态」**——那含排队项（`_acquire_slot` 的闸是 `_dispatch_capacity`=25，真跑只有 5），12 项会全画成「在跑」。**从 run record 取**：`manager.find_run(subagent_id, run_id).status == "running"` 才算在跑（`manager.py:1439-1442` 才置 running），其余已派发项算 `queued`。
- **计数只对 `kind == "foreach"` 输出**：`_graph_node_projection` 现在对 `kind == "foreach"` **或** `id.startswith(AUTO_NODE_PREFIX)` 输出 `items`（`:2276-2278`），但 auto 聚合节点**永不经过 `_execute_foreach`**——给它输出 `items_completed` 会恒定显示「0/3 完成」。计数与 `item_states` 的投影门槛**只认 `kind == "foreach"`**。
- **`state.subagent_ids` 的下标 ≠ item 下标**：它是 gather 结束后才 append（`:1493-1494`）且异常项走 `continue` 不 append → **不能**用它做 index→session 映射。per-item 身份用 `item_states`（按 index 维护）+ run record（`run.task` 含渲染后的具体任务）。
- **每次项级迁移都要推帧（G2）**，否则计数对了前端仍收不到（见 D2c）。**但要注意构造成本**：`_emit_graph_snapshot` 先全量重建快照（`:2226-2242`）再交 sink，**scheduler 侧无节流**，0.1s 窗只合并发送、不合并构建。200 项 × O(nodes+edges) 构造全在事件循环上——**项级帧必须在调度器侧就限频**（同一容器最多 N Hz），或用轻量 `workflow_items_progress` 事件而非全量快照。
- `asyncio.CancelledError` 提前 return 时计数停在部分值——与既有 `state.status = "cancelled"` 一致，前端要容忍 `M < N`。

**白名单同步（grill 决策 4）**：只影响 `tests/agent/subagent/test_workflow_graph_snapshot.py` 一个文件——节点白名单 `SNAPSHOT_NODE_KEYS` 是模块级 `frozenset`（`:34-36`），用 `<=` 断言（`:150`）；**图级白名单是内联 set 字面量**（`:173-176`），加两个时间戳要改那里（没有常量可改）。全仓 grep 确认没有第二个测试断言快照键集（`test_workflow_graph_events.py` 只看 `node["status"]`/`diagnostics`），`test_snapshot_does_not_drift_envelope_contract`（`:358-368`）断言 `_envelope`/`parent_envelope` 键、本 change 不动这两者会继续绿。白名单是「多一个键都是没挑字段」的守卫，改它必须是**有意识**的，且**保留**排除断言（`subagent_ids`/`slots`/`raw`/`error`/`bus`/`attribution`）。

> **注意**：`test_workflow_graph_snapshot.py:173-176` 的禁项列表里**没有** `budget`，图级新增 `budget` 只受 `<=` 白名单约束。

### D3b — 陈旧因由与负耗时（G11，审阅员 B 复核成立）

**问题**：`_reset_subtree`（`:1349-1361`）只重置 `status`/`activations`/`deadline_fired`/`verdict`/`targets`，**不清 `reason`/`error`/`finished_at`/`summary`**。叠加 `state.reason = state.reason or state.error`（`:1310`）的 `or` 语义与 `finished_at` 只在为 `None` 时写（`:1312-1313`）→ route 回边重跑（review 循环，本项目常见形态）后：节点显示**上一轮的失败因由**，且 `finished_at < started_at`（**负耗时**）。**答错比答不出更糟**，而 D4 面板要显示起止耗时、D6 要显示耗时，全踩这个坑。

**方案**：`_reset_subtree` 一并清 `reason`/`error`/`finished_at`/`summary`，以及 foreach 容器的 `items_completed`/`items_failed`/`item_states`（否则从复位到被重新派发之间，前端会显示上一轮的「3/12 完成」配 `pending` 状态）。

**回归**：既有测试**无依赖**（`finished_at` 只在 `test_workflow_graph_snapshot.py:225` 手工设值与 `test_scheduler.py:998` 首次 run 出现；重跑用例 `test_route_default_branch_loops_back` 只断言 `runs == 2`）。新增「route 回边重跑后 `finished_at >= started_at`」回归。

### D4 — 节点详情：分 Tab 的抽屉面板 + 新增只读 transcript 路由（复用 `inspect_transcript`）

**交互（调研对标 AWS Step Functions 的 Step details，最贴近本场景的形态）**：点节点 → 打开**详情抽屉**。桌面（>720px）从**右侧**滑入（宽 360–420px，`position:absolute` 覆盖画布右侧，**不挤压画布宽度**，否则 SVG 要重排）；手机（≤720px）从**底部**滑入（高 ~70vh，带拖拽把手）。**同一份 DOM**，720 断点切 class（与既有跨端手法一致，不加新断点）。**移动端不用居中模态**（拇指够不到、丢失「我在看哪个节点」的上下文）。关闭：`×` / 点遮罩 / Esc；`role="dialog"` + `aria-modal` + focus trap + 关闭后焦点回到节点。

**面板内容分 Tab**（默认 `任务`）：
1. **任务**：node id（完整）+ kind 徽标 + 状态色点/角标 + 状态词 + **因果句（D2）** + runs 次数 + 起止与耗时 + 节点 task 模板。
2. **产出**：快照里的 bounded summary（截断标注）+ `result_ref`（有则显示）。
3. **对话**：**完整 transcript，懒加载**——切到该 tab 才发请求、才建 DOM。

**点击语义拆分（重要行为变更；grill 决策 5 修正了要改的测试文件）**：今天点节点 = 展开/收起折叠组（`workflow.js:423` 绑定 → `:434-443` 的 `toggleGroup`，非 `groupLeader` 直接 return）。改为——**点节点 = 打开详情面板；折叠组的展开/收起收进详情抽屉**（**Q2 用户裁决定案：选 B**）。抽屉里给 `groupLeader` 节点一个「展开成员 / 收起成员」动作，点它切换 `expandedGroups` 并重绘。
**为什么选 B 而不是「节点上的独立小控件」**：该控件**只服务 ≥50 节点的大图**（`collapseGraph` 的 `COLLAPSE_THRESHOLD`，小图如 12 文件体检 6–7 节点根本够不到，永远看不到它）。而手机纵向 DAG 上图会缩到约 0.5 倍，节点实显仅 27–36px——要在节点上做出真 44px 的触控目标，必须用**脱离 SVG 缩放的 HTML 覆盖层**（按节点屏幕坐标定位、随 pinch/pan 重算），实现复杂；且 `TAP_SLOP=4` 的点击/拖动判定会让手指漂移超过 4px 后 `setPointerCapture`（`workflow.js:490-497`）吃掉 click。**为一个只服务大图的控件付这个代价不划算**；收进抽屉零触控目标问题、零手势冲突。代价（手机抽屉占 70vh、展开后需先关抽屉才能看到结果）用户接受。否则 foreach 容器的「看详情」与「展开项」两个意图在同一个点击上打架。**真正会红的不是 `test_workflow_graph_js.py`**（那是纯函数单测，无 click 用例），而是浏览器 smoke `tests/web_tests/test_workflow_graph_browser.py:343-369` 的 `test_collapsed_group_click_expands_members`（两次点 `.workflow-node[data-node-id='fan']`）；配套 CSS 是 `web/static/style.css:1482` 的 `.workflow-node.group-leader { cursor: pointer }`——拆分后普通节点也要可点，cursor 口径要一起改。（`test_workflow_graph_js.py:322-354` 的折叠相关断言是 `collapseGraph`/`groupLeader` **数据**断言，与点击无关，本 change 不动。）

**transcript 的渲染（对标 GitHub Actions 大日志工程的结论）**：**只做 UI 虚拟化，不做数据虚拟化**（数据是快照/接口一次取回的，本来就在内存）——按 **50 行一组聚簇**、按簇增删 DOM 而非按行；超长单行截断；不引入可视化库（GitHub 试遍现成库后自研，理由：换行可变行高、文本选择失效、多滚动条——我们零依赖自绘，更不该引库）。

**数据来源（关键决策）**：**新增只读路由**，而非复用 `InspectSubagentTranscript` 工具：

```
GET /api/sessions/{session_id}/workflows/{workflow_id}/nodes/{node_id}/transcript
  → 三态 union（对应「界面效果 §0」的节点↔subagent 三类）：
    {kind: "single",     node_id, subagent_id, status, messages: [...], truncated, included_tool_results}   # subagent / aggregate(llm) / auto-agg
    {kind: "candidates", node_id, node_kind, total, offset, limit, has_more, candidates: [{index, subagent_id, run_id, status, label, summary, started_at, finished_at}]}  # foreach 容器
    {kind: "none",       node_id, node_kind, reason_full, reason_truncated, reason_length}   # route / aggregate(collect) / 未派发节点
```

- **为什么新路由**：`InspectSubagentTranscript` 是 **LLM 面工具**（`Tool` 子类、要 permission、走 AgentLoop 工具注册与协议）。Web 层要用它得绕过工具协议直接调 manager——不如直接暴露一个 HTTP 只读接口。两者底层**复用同一个 `SubAgentManager.inspect_transcript()`**，不复制逻辑。
- **`inspect_transcript` 的真实口径（grill 决策 7，防实现踩坑）**：它**不按 `run_id` 过滤**——messages 分支取的是 `session.messages[-limit:]`（`manager.py:1035-1038`，即整段 session 消息尾部，跨多次 run 累积），`run_id` 只是**回显**；默认 `limit=5`；**没有单条内容截断**；`scope="summary"` 的返回体**根本没有 `messages` 键**（只有 `summary`）。所以路由必须：显式传 `scope="recent_messages"` + `limit`（上限 200）、**自己在路由层加单条内容截断**、并在 `_require_session` 抛 `KeyError`（`manager.py:1433-1437`）时转结构化响应。`truncated` 的语义是 `len(messages) > limit`（已剔除 tool 角色后）——前端文案别写成「内容被截断」。
- **node_id → subagent 解析（grill 决策 8 + 「界面效果 §0」+ **审阅员 B 的重大修正**）**：
  - **索引源是 `item_states`（index 空间 0..N-1），不是 `subagent_ids`；`subagent_ids` 只做真实性校验**（grill B 反例修正）。`state.subagent_ids` 是**稀疏数组**——append 在 `_execute_foreach` 的 gather 结果循环里，而**异常 envelope 走 `continue` 跳过 append**（`scheduler.py:1487-1492`），`_run_foreach_item` 拿不到 slot 时抛 `CancelledError`（`:1513-1515`）、`_launch_run` 的超限/`queue_full` 路径也返回非 completed。**若拿它当索引源，12 项里被取消/异常的那几项会从候选列表里消失**——而「还有哪几个没跑」正是用户最想知道的。候选必须按 index 空间生成：`item_states[i]` 给状态、`i` 对应的 run record 给 `task`/`reason`。
  - **不反查 `manager._sessions`**（孙代 session 会污染）。：`create_subagent`（`manager.py:450-479`）从**当前 contextvar** 取 `workflow_id`/`node_id`，而节点的 AgentLoop 跑在入队时 `copy_context()` 捕获的上下文里（`manager.py:780-786` 捕获、`:1439-1442` 用 `item.context` 启动），且**工具层从不 reset `node_id`/`workflow_id`**（`set_node_id`/`reset_node_id` 在 `agent/tools/`、`agent/loop.py`、`manager.py` 全无命中）。所以**一个普通 subagent 节点只要自己 spawn 过子 agent，就满足「N>1」，会被误判成 `candidates`**，0/1/N 规则随之失准。
  - 解析规则（在 `subagent_ids` 上）：**0 条** → `kind:"none"`（未派发，或 route / aggregate(collect) 这类本就不产生 run 的节点）；**1 条** → `kind:"single"`；**N>1 条** → `kind:"candidates"`（**含 N=1 的 foreach 也归 `single`**，不设特例分支）。普通节点重跑复用 `reuse_state.subagent_id`（`:1673-1682`），不会产生第二条。
  - **`index`/`task` 的来源**：候选顺序 ≠ item 序号（`create_subagent` 发生在 `_acquire_slot()` **之后**，并发下 item#5 可能先建 session；`_sessions` 是插入序 dict）。**不要靠 `session.name = f"{node.id}-{index}"` 反解**——用 **`SubagentRunRecord.task`**（= `render_item_task` 的产物，`scheduler.py:1519`）+ **显式落一个 `index` 字段**（来自 `item_states` 的维护序）。
- **`candidates` 每条必须带 `reason` 与 `task`（G10，issue 原始场景的唯一排查入口）**：失败项 `summary` 通常是空的（异常 envelope 分支 `append("")`，`scheduler.py:1490`），没有 `reason` 就是「3 个红点、点开每行空白」。`reason` 取 **`run.reason`**（`manager._mark_failed` `:1293` 写；`_complete_run` `:1215` 写 `result.error`），**bounded 截断**；`task` 即渲染后的具体任务（「哪个文件」的答案）。`single` union **同样补 `reason`**（失败原因从不追加进 `session.messages`，`_mark_failed` 只写 checkpoint + `run.reason`）。
- **`candidates` 必须 bounded**：默认 `limit=50`、硬上限 200，带 `total`/`has_more`/`offset`；候选只带短摘要（`summary` 再截断），真正 messages 等点某项时按 `subagent_id`（+`run_id`）再取一次。
- **`run_id` 过滤（grill 决策 7 的连带约束）**：`inspect_transcript` 当前**不按 `run_id` 过滤**（取 `session.messages[-limit:]`）——候选列表若要精确到某项的 run，必须**先修候选定位与 run 级取数**，否则只是把「展示错 run」换个入口（codex 复核指出的坑）。
- **`reason` 全文出口（G17）**：快照里截断到 400，但**没有任何接口返回全文**（transcript 只是 `session.messages` 尾部，失败时不会追加错误消息）。D4 路由的 `single`/`candidates` **必须返回 `reason` 全文**（或 `reason_full` + `reason_truncated` + `reason_length`），scheduler 侧 reason 才能被用户读到——这类 reason（`budget exceeded (tokens)`、`workflow ended before the node became ready`、`3/12 foreach items did not complete`）**从不出现在任何 subagent transcript 里**。
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
3. **点容器节点 → 详情面板的「对话」tab 展示项列表**（`#0..#N-1` + 每项状态/摘要，可点进单项；数据源就是 D4 路由返回的**候选集**，见 Q1）。**放在「对话」tab 而非「任务」tab**（grill A 指出原措辞与此矛盾）：放「任务」tab 意味着**一打开面板就得发 transcript 请求**，破掉 D4 的「切到该 tab 才发请求」懒加载契约。**不把项铺成 N 个 DAG 节点**：项不是 `NodeState`（#190 决策 8），铺节点要新增布局/边/交互一整套，且 Argo 的 Graph view 在 N 大时会爆炸、Airflow 干脆不在 Graph view 展开——两者都选了「列表 + 计数」（Airflow Grid 的 Mapped Instances、Step Functions 的 iteration viewer）。
4. **上界**：N 超过 50 时项列表只渲染「失败项 + 前若干项 + 聚合统计」，且列表本身做 UI 虚拟化（D4）。

### D6 — 多图 tab 元信息：序号 + 起止 + 耗时 + 完成计数

**现状**：tab 只有 `truncate(goal, 24)` + 状态词，三张图分不清。

**方案**：tab 升级为紧凑多段标签（对标 GitHub Actions run 列表 + Temporal 的 relative time）：

```
[●] #3 · 2 分钟前 · 2m18s · 3/5
```

- **`#3` = 按图级 `started_at` 排序的秩**（**Q3 用户裁决定案：选 A**）。**排序也按编号**（即 tab 序列 = `started_at` 升序），**运行中不用位置表达，改用徽标**（如 `●`）区分。
  **为什么选 A 而不是「到达序计数器 + 运行中排最前」**：(a) 「按出现序编号 + 运行中排最前」**必然产生非单调序列**——长跑 wf1 + 快结 wf2/wf3 → tab 读作 `#1 #3 #2`，(原始 Q3 的三个选项里没有「排序」这一维，这是审阅员补的)；(b) `_workflows` **永不注销**（`manager.py:408/567`），WS 重连补发（`web/session.py:695-723`）会把前端**早已淘汰**的图塞回来并分配新 `nextSeq` → 同一张图重连前 `#2`、重连后 `#9`，「第几次 run」**答错**。按 `started_at` 排序的秩则跨整页刷新稳定、与用户嘴里的「第几次 run」同义。
  **接受的代价**：淘汰后编号前移（原 `#2` 变 `#1`）。**实现注意**：**不能拿 `Map` 的插入下标当序号**——`pruneGraphs` 会 `state.graphs.delete(evicted.id)`（`workflow.js:124-135`）；秩要**在渲染时按当前可见图的 `started_at` 现算**（`started_at` 已由 D3 进快照）。**排序必须把 `started_at == null`（D3 的哨兵统一）当 unknown**——排到最后，绝不按 epoch 0 排到最前。
- 相对时间（`2 分钟前`），运行中显示 `已跑 42s` 并**实时跳秒**；`title` 给绝对时间（Temporal 的 UTC/Local/Relative 三格式思路）。
- 耗时用图级 `started_at`/`finished_at`（D3 补齐）。
- `3/5` = 完成**节点**数/总数（「结果差异」最直接的摘要）。**口径注意**：这**不用**快照的 `total/completed/failed`（那是 `_unit_counts()` 的**逻辑单元**口径，foreach 容器按 N+1 计，且 running 帧根本不带——`_SNAPSHOT_TERMINAL_STATUSES` 门控）。**由前端从 `snapshot.nodes` 自行统计**（`renderSummary` 已经就是这么算 per-status 计数的），零后端改动、running 帧天然可用，也顺带解掉 gap-analysis G6 指出的「D6 要 running 计数 vs #190 决策不给」冲突。
- 状态圆点用**最差状态色**（复用既有 `groupStatus()` 逻辑）。
- 淘汰策略（最近 5 张终态 + 全部 running）沿用 #190 Q9 **不变**。**但新增的图级终态 `completed_with_failures`（G26）必须加进 `TERMINAL_STATUSES`（`workflow.js:16`）**，否则那张图被当成 running → 永不淘汰、永久排最前（见 D9/G26 影响面 (d)）。
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

### D8 — 运行过程可见性（G2/G3/G4/G8，对应 Goal E）

> 来源：`gap-analysis.md` 的运行可见性 7 条（用户裁决全进）。核心事实：**design 在「把已发生的事画好看」上很完整，在「正在发生的事」上基本空白**——八档状态里没有一档表达「在跑 vs 排队」，快照只在迁移点推送，节点没有计时。

- **G2 推送时机**：`_emit_graph_snapshot` 只在 7 个**迁移点**调用（cancel/run 起/run 止/图超限/预算停/dispatch/节点终态），迁移点之间的内部变化**永不外发** → 交互是**跳变**不是渐进。补：项级迁移（见 D5）与节点级进度都要推帧。**但必须先在调度器侧限频**——`_emit_graph_snapshot` 是无条件全量重建（`:2226-2242` 遍历全部 nodes+edges）再交 sink，0.1s 窗只合并发送、不合并构建。
- **G3 「排队 vs 在跑」——采纳审阅员 B 的投影层省法**：
  - **不改状态机**。原因：`NodeState.status` **从不写 `queued`**（全仓 `"queued"` 只在读取侧判据 `:600/758/760/866/1772/2385`，是死代码、判据恒为假）；给它加赋值点会让这 6 处判据**同时激活**，其中 `:758` 参与 `_in_flight_nodes` 类收敛判断，而预算 drain 正靠「在跑的 run 归零」落终态——**爆炸半径比 G1 大**。且 `_dispatch` 在 `:1278` 就置 `started`，真正的 `_acquire_slot()` 在 `_launch_run` 内部（`:1644-1723`），中间隔异步边界。
  - **在 `_graph_node_projection` 里投影**：若 `state.status == "started"` 且 `manager.find_run(state.subagent_id, state.run_id)` 的 `status == "queued"` → 投影成 `"queued"`。**一处函数、不动状态机、不多推一帧**；`_edge_status` 读的是 state 而非投影，边配色不受影响（语义也对：边确实 active）。
  - **绝不要动 `_dispatch_capacity` 的取值**（= `max_active + max_queued_runs` = 25）：它是「workflow 永不撞 queue_full」不变量的一半（`manager.py:925`）。
- **G4 节点 elapsed**：`started_at` 早在快照里，但前端从不读、无计时器。补：节点状态词旁常显 elapsed，`started`/`queued` 态按秒 tick。**注意**：快照不到达时没有重绘事件，**必须有一个独立于快照的本地计时器**（否则 A→B 迁移之间计时也是死的）；终态时冻结为 `finished_at - started_at`。
- **G8 陈旧可见**：payload 里已有 `timestamp`（`:2250`），前端从不读。补「最后更新于 N 秒前」——用户据此区分「慢」与「死」。

### D9 — 诊断数据面（G9/G13/G15/G26，对应 Goal B/C）

- **G13 预算数字**：图级 payload 加 `budget`（复用 `_budget_summary()`，`:1138-1157`）。**运行中取值正确**（`wall_time_s` 自取 `now`、tokens/cost 逐次累加）。**两个边界**：(a) `declared` 态 `self._budget is None` → 返回 `{}`，前端须容忍空 dict；(b) 图级 `budget` 与节点级 `budget_exceeded` 是两回事，别混。用户看到「预算超限（tokens）」的下一个动作必然是「花了多少」——本 change 花整节解释「为什么停」却不给数字，是明显缺口。
- **G15 route 判定诊断**：`route_ref_misses` 进了快照，但前端唯一读 `diagnostics` 的地方 gate 在 `graph_recursion_exceeded`（`workflow_graph.js:528-534`）→ 图正常完成时一个字都不显示。补：route 节点详情 + 图级告警都能显示；`none` union 补 `verdict`/`targets`/`raw`（截断后的上游原文 excerpt，从调度器按 node_id 取，**不进快照**）；对**字面标签不匹配**也记一条 miss（现在只有 `$ref` 未命中记，诊断只覆盖半张网）。
- **G26 图级 status 修正（P0，主 session 实跑新发现）**：`_drive` 的收敛出口（`:824`）是 `self._status = "budget_exceeded" if self._budget_stop else "completed"`——**只看预算，完全不检查有没有节点失败**。实跑证实：有节点 `failed` 的图，图级 status 仍报 `completed`（而 envelope 里 `failed=1` 数据是对的）。**用户根本不会被告知去看失败**——直接击穿用户原话。
  **决策（用户 2026-09-17 拍板）**：**新增独立的图级终态 `completed_with_failures`，不与 `completed` 混用**。判据：图收敛（`_drive` 收敛出口）时，若存在任何节点 `status == "failed"` → `completed_with_failures`；无节点失败才 `completed`。**优先级**：`budget_exceeded` / `cancelled` / `graph_recursion_exceeded` 仍优先于它（预算停与取消是更强的停止原因）。**影响面**：(a) 图级 status 是 `_envelope` 的字段，消费方（benchmark 报告 / `GetWorkflow` / `_first_started_scheduler`）需容忍新值；(b) 前端 tab 徽标与视图头走**独立 `GRAPH_STATUS_*` 表**（见 D10），不碰 `NODE_COLORS`；(c) 该档的语义是「正常跑完但有节点失败」——**不使整图算失败**，但必须让用户一眼看到「有东西没成功」，这正是 G26 的立项理由。
  **(d) ⚠ 必须同步两处终态列表（grill B 反例，此前 design/tasks 未点名）**：终态集合有**两个独立副本**——`scheduler.py:104-109` 的 `_SNAPSHOT_TERMINAL_STATUSES` 与 `web/static/workflow.js:16` 的 `TERMINAL_STATUSES`。前者被三处消费（快照计数门控 `:2252`、终态帧绕开 0.1s 合并窗 `web/session.py:535-537`、重连补发分类 `:719`），后者被 `pruneGraphs`（`:124-135`）消费。**任一处漏加 `completed_with_failures`**，一张「跑完了但有节点失败」的图会被当成 **running**：永远排 tab 最前、计时器一直跳、每次重连都补发、**永不进淘汰池**（tab 无限增长）——而这恰是最需要用户看到的图。
  **(e) 三处 reason 上限口径**（grill B 补充）：父 Agent 面 `_PARENT_FIELD_LIMIT`=200（`scheduler.py:105`）、Web 快照 400（`_SUMMARY_LIMIT`）、D4 路由给全文。三个消费者用途不同、不算错误，但 spec 与文档要写清，否则「为什么父 agent 报告里的 reason 更短」会成为下一个困惑源。
- **G9 trace 摘要**：`run.trace` 在四个终态落点写入（`manager.py:1223/1295/1310/1329`），session 挂 `manager._sessions`、manager 经 `session.agent.subagent_manager` 可达（`loop.py:152`）。补 bounded `trace_digest`（最近 N 条 `status != ok` 的 `tool_result` + `llm_error`）。**两个坑**：(a) `run.trace` **只在终态写入**，运行中是 `None` → **Goal 5「详情面板能看到此刻在干什么」做不到**，G9 只对**已失败节点**有效，这条必须写进 spec（否则 spec 无法验收）；(b) `trace is None` 有三种成因（queue_full 根本没有 / 排队取消是空 steps 不是 None / `_mark_budget_exceeded` 在 trace is None 时写 None），前端不能把 None 与 `steps==[]` 都显示成「无失败证据」。

### D10 — 图级超限仍画图（G14）

`workflow.js:225-231` 命中 notice 就 `renderMessage + return` → **用户失去整幅画面**，看不到哪些节点已完成、卡在哪个环。而 `nodes`/`edges` 无条件存在（`:2243-2251`），`total`/`completed`/`failed` 也发（`_SNAPSHOT_TERMINAL_STATUSES` 含 `graph_recursion_exceeded`），`diagnostics` 带 `reason`/`message`/`steps`/`limit`/`current_nodes`。补：**超限时仍然画图**，图上叠告警条；告警条补 `current_nodes`（超限那刻的 ready 节点 = 回边死循环的直接答案）与 `steps`。
**做法修正（审阅员 B）**：图级 status 的配色走**独立的 `GRAPH_STATUS_COLORS`/`GRAPH_STATUS_LABELS`**，**不塞进 `NODE_COLORS`**——后者是**节点**状态词表，有精确相等契约测试（`test_workflow_graph_js.py:73-80`）与 `groupStatus` 落表断言（`:273-276`），塞图级状态会污染它。（tab 圆点现在走 `G.nodeColor(status)` 兜底成灰，正是「圆点退化」的成因。）

### D11 — 取消运行中的图（G18，对应 Goal F）

**现状**：后端 `scheduler.cancel()` 就绪且立即返回（`:594-620`），但 `web/server.py` 12 条路由**零 workflow**、WS `msg_type` 分支**零 workflow**、前端面板**一个按钮都没有**。命中 issue 主线场景：预算超限是**粘性 stop_new + drain**（只停派发、**不取消在跑的 run**，要等 `_in_flight_nodes==0` 落终态）→ 用户看着橙图继续烧 token 只能干等。**更糟**：`reset` 只 `fail_pending` + `remove_session` + 重建，**从不调 `cancel()`**；而图是 `ensure_future(scheduler.run(spec))` 起的后台任务、`manager._workflows` **永不注销** → **图继续跑、继续烧预算，而 forwarder 已被 detach，用户彻底看不到**。手机端无法 kill。

**方案（采纳审阅员 B：走 WS 而非新 HTTP 路由）**：新增 WS 消息 `cancel_workflow`。WS handler 手里有 `session`，`session.agent.subagent_manager.get_workflow(wf_id)` 就能拿 scheduler；`cancel()` 内部 `ensure_future` 需要 running loop，WS 天然满足；HTTP 还要重做内存口径 session 校验。前端在面板加 toolbar + 运行中显示「停止」+ 二次确认（**不可逆**，`_cancelled`/`_accepting` 全仓无复位点，文案要说清「已跑的 run 会写 checkpoint，但工作流本身不能续」）。**并修 `reset`**：`remove_session` 之前遍历 `list_workflows()` → 逐个 `cancel()`（`cancel()` 对 `declared` 态不改状态，符合预期）。

**必须划清的边界**：`web/session.py:1142-1143` 已有 `if msg_type in {"reset","cancel"}: fail_pending_interactions(...)` —— **前端今天发 `{"type":"cancel"}` 只会让待审批失败，run 照跑**。新增的 `cancel_workflow` 必须与这个既有语义区分开。
**副作用**：`cancel()` 返回 `{"status":"cancelling"}` **不是终态**（终态要等 `_teardown` 后的快照）；取消是「立即标终态 + 异步 cancel 底层 run」，若 run 恰在取消前完成，`_apply_run_status` 可能把节点从 cancelled 改回 completed（既有行为，按钮要容忍状态闪动）。

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
> **停轮已解除（2026-09-18）**：Q1–Q4 全部收敛并回填 `reviews/grill-design.md` 的 `## User Confirmation`——**Q1/Q4 被后续设计唯一确定**（Q1 由三态 union、Q4 由 G17 的全文出口取代其前提，见 `reviews/grill-design.md` 的「重评估」节）；**Q2/Q3 经改写后由用户拍板**（Q2 选 B：展开收进详情抽屉；Q3 选 A：按 `started_at` 编号且排序按编号）。**grill 门禁已满足，可进入实现。**

> **范围审阅（2026-09-17）**：本 change 范围从「纯前端展示」扩到「前端 + scheduler 语义 + 运行期推送 + 诊断数据面 + 控制面」后，派两名独立只读审阅员做范围切分与技术正确性审阅，产出 `reviews/scope-audit.md`。
> **裁决：不切分**，保持「观测面」定位，但采纳两条降风险省法——**G3 走投影层**（不动状态机，避开「加 `queued` 赋值会同时激活 6 处死代码判据、其中一处参与收敛判断」的爆炸半径）、**G18 走 WS 而非新 HTTP 路由**（handler 手里有 session，`cancel()` 需要的 running loop 天然满足）。tasks 分 M1 语义层 / M2 展示层 / M3 下钻层三个里程碑，**每个以实跑收口**（这正是发现 G1 的方式）。
> 审阅员另核实出 **9 条必须改**（含 4 条新的 G1 类：`_run_foreach_item` 无 `state` 形参致记账落点写错、G10 候选集反查 `_sessions` 会被孙代 session 污染、`explainNode` 签名看不到图级 status、D2b 判据不查「控制源 route 是否跑过」会报假话），已全部回写本 design 与 tasks。

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
