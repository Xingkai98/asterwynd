# Proposal: foreach 截断可见性 — 声明/展开/省略数不静默

关联跟踪 issue：[#279](https://github.com/Xingkai98/asterwynd/issues/279)。诊断来源：[#248](https://github.com/Xingkai98/asterwynd/issues/248)/[#273](https://github.com/Xingkai98/asterwynd/issues/273)/[#275](https://github.com/Xingkai98/asterwynd/issues/275) 的「不静默截断」纪律线。

## Change Type

- primary: feature
- secondary:
  - workflow
  - observability

## Why

### 问题：foreach 的 `max_items` 截断是**唯一**不报告的截断

`foreach` 节点的 `max_items` 默认 **20**（`agent/subagent/workflow.py:168`）。当模型声明的 `items` 超过 20 且**未显式声明 `max_items`** 时，`_resolve_items` 执行 `items[:max_items]`（`agent/subagent/scheduler.py:2669`）——**超出的项被丢弃，且运行时没有任何地方报告**。

**实测（2026-10-01）**：模型声明含 **60 项** 的 foreach、不写 `max_items` ⇒ `DeclareWorkflow` 返回 `warnings: []`、dry run 只报 `items_expanded: 20`、**无任何 `items_omitted`/截断提示**。即：**模型以为「对 60 个东西各做一次」，实际只做了 20 个，aggregate 拿到残缺输入，全程无人告知。**

### 为什么算 defect（按项目自己的标准）

项目在**别处**严格执行「不静默截断、显式报告省略数」：

| 截断点 | 报告字段 | 位置 |
|---|---|---|
| 节点数超 `max_nodes` | `nodes_omitted` | `scheduler.py:118` / `:3163` |
| 报告的 warnings 超限 | `warnings_omitted` | `subagents.py:1661` |
| foreach 展开项的 result_ref 超限 | `item_refs_omitted` | `subagents.py:1132` |
| **`max_items` 截断 `items`** | **（无）** | **本 issue** |

**唯独这一处不报**——与 #248/#273/#275 一直在消除的「静默行为模型看不见」同型。

### 边界（如实）

- **不是 spec 违规**：spec 只规定 `max_items=0` = 不静态截断（`multi-agent-collaboration` spec:315），**未规定静态截断须报告**。本 change 是**透明性缺陷**的修复 + 新增报告面。
- **与 #278（OOM）无关**：那次真实运行模型用了 `max_items: 0`，反而没撞这个。
- **`max_items` 默认值 20 本身**是否该改，属另一个问题（#276 或单议）；本 change **只修「截断不报告」**，不动默认值。

## What Changes

1. **声明期报告**：`DeclareWorkflow` / `RunWorkflow(spec=...)` 的 `warnings` 增一条**可行动**警告——当 foreach 节点的 `items` 是**字面列表**且长度 > `max_items`（>0）时，报「声明 N 项、仅前 M 项会运行」并给行动指引（减小 items / 声明 `max_items: 0` / 调大 `max_items`）。**声明期无法知的（`source` 驱动）不在此面报告**（见 D3）。
2. **dry run 报告**：`DryRunWorkflow` 的 foreach 条目在既有 `items_expanded` 旁补 `items_declared`（声明集合大小）与 `items_omitted`（被 `max_items` 丢弃的项数）——使 dry run 能显示「展开 20 / 共 60 / 省略 40」。
3. **运行期报告**：运行期 `GetWorkflow`（或其 diagnostics）暴露 foreach 节点的**静态截断**信号（`max_items` 丢弃的项数），使运行后的读回也可见（dry run 是**预计**，运行期是**实际**）。

**不变**：`max_items` 的默认值（20）与 `max_items=0` 语义（不静态截断）；`item_refs_omitted`（那是 **ref 列表**的界，与本 change 的 **items 截断**是两件事，SHALL NOT 混用同一字段）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `multi-agent-collaboration`：
  - **ADDED** 新 Requirement「foreach 静态截断可见」——`max_items > 0` 且 `items` 被截断时，系统 SHALL 在模型可见出口（声明期 warnings / dry run / 运行期投影）如实报告「声明 N / 展开 M / 省略 K」，SHALL NOT 静默丢弃。措辞 SHALL 可行动。

## 验收（本 change 的验收口径，**只进 proposal、不进 spec**）

| # | 指标 | 主/辅 |
|---|---|---|
| **T1** | 声明含 60 项、`max_items` 默认（20）的 foreach ⇒ `DeclareWorkflow` warnings 报「60 声明 / 20 运行」+ 行动指引 | **主指标** |
| **T2** | 同上图 `RunWorkflow(spec=...)` 的 warnings 同样报（两条声明入口一致） | **主指标** |
| **T3** | dry run 的 foreach 条目含 `items_declared`=60 / `items_expanded`=20 / `items_omitted`=40 | **主指标** |
| T4 | 运行期 `GetWorkflow` 暴露静态截断信号（实际丢弃数） | 辅 |
| T5 | `items` ≤ `max_items`（不截断）时**不产生**截断警告/字段（零噪声） | 辅 |
| T6 | `max_items: 0`（不静态截断）时不报静态截断（预算截断是另一层，不误报） | 辅 |
| T7 | 既有 `item_refs_omitted`（ref 列表界）语义不变、与新字段不混 | 辅 |
| T8 | 不退化：既有 workflow 测试全绿 | 辅 |

**通过门槛**：T1 + T2 + T3 成立（三条出口一致可见），T5/T6 无假报，T7/T8 不退化。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 命中 `light` 判据「常规功能增强；**成熟模式的局部应用**」。本 change 是项目内**已有**的「不静默截断」范式（`nodes_omitted`/`warnings_omitted`/`item_refs_omitted`）在**第 4 个截断点**上的局部应用，不引入新框架/新协议/新依赖。不判 `full`：非架构级改造，形态已被同仓三处先例钉死。不判 `exempt`：虽形似 bugfix，但**新增了报告字段（能力面）**，非「无新增能力面」。
- research questions:
  - **RQ1**：截断报告的**字段命名与出口形态**，项目内既有先例怎么做的？（对齐即可，不必新造。）
- findings:
  1. **项目内三处同型先例已钉死形态**：`nodes_omitted`（`scheduler.py:3163`，`max(total - limit, 0)`）、`warnings_omitted`（`subagents.py:1661`）、`item_refs_omitted`（`subagents.py:1132`）——**统一是「`X_omitted = max(total - shown, 0)`」+ 一个 `X_total`**。本 change 的 `items_declared` / `items_omitted` 直接沿用该形态（**不用 `items_total`**——该名已被既有 `item_refs_omitted` 语境占用，见 design D2），**不新造词表**。
  2. **声明期 warnings 的既有投递面**：`_route_task_warnings(spec)`（`subagents.py:710`）是「声明期、声明期可知」警告的现成 helper，由 `DeclareWorkflow`（`:841`）与 `RunWorkflow(spec=)`（`:1284`）**共用**——本 change 的新 warnhelper 与它并列调用，天然覆盖两条入口。
  3. **无本地参考仓库同款**（`/home/shared/agent-study/reference-repos/`）：这是本项目自有的 workflow DSL 概念（foreach/`max_items`），业界框架无直接对应；形态依据来自**项目内先例**（finding 1）而非外部。本地仓库可用性：`.dev/reference-repos.txt` 在本 worktree 不存在（不提交，属正常）；不构成 exempt 理由，此处如实记录。
- design impact: 见 design D1（三出口一致）、D2（字段名沿用先例）、D3（声明期 vs 运行期可知性边界）、D4（与 `item_refs_omitted` 不混）。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（workflow DSL 的 foreach 行为 + 报告面）。
- **代码**:
  - `agent/tools/builtin/subagents.py` — 新增 `_foreach_truncation_warnings(spec)` helper（与 `_route_task_warnings` 并列），在 `DeclareWorkflow`（`:841`）与 `RunWorkflow(spec=)`（`:1284`）的 warnings 处调用；dry-run 的 foreach 条目（`:1584`）补 `items_declared`/`items_omitted`。
  - `agent/subagent/scheduler.py` — `_resolve_items`（`:2669`）记录「声明总数 / 实际展开数」，供运行期投影读取；运行期 `GetWorkflow` 出口暴露静态截断信号。
  - `agent/subagent/workflow.py` — 若需在 `WorkflowNode` 上暴露「声明 items 数」（字面列表长度），在此取（`items` 字段既有）。
- **测试**:
  - **必须新增**：T1/T2（两条声明入口 warnings）、T3（dry-run 三字段）、T5（不截断不报）、T6（`max_items=0` 不误报）、T7（`item_refs_omitted` 不受影响）。
  - **必须回归**：workflow dry-run / declare / run 既有测试；`multi-agent-collaboration` 相关；全量 `uv run pytest -q`。
- **文档**:
  - `openspec/specs/multi-agent-collaboration/spec.md`（ADDED 1 Requirement；受保护路径）。
  - `docs/openspec-change-backlog.md`（受保护路径）。
  - `README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描（预计无需改——内部 DSL 报告面）。
- **流程（process）**: 触及受保护路径，需结构化事件 + grill + building review；实现须独立 worktree、`foreach-truncation-visibility/2026-10-03` 分支。**change type = feature → 实现前必须走 `batch-grill-me` + 停轮确认 Open Questions**；**grill 结论须先走独立对抗验证**（`reviews/grill-adversarial.md`）。
- **与既有 change / issue 的边界**:
  - **#276**（上限数值重估）：参数 vs 报告，独立。本 change **不动** `max_items` 默认值。
  - **#248/#273/#275**（不静默截断线）：同纪律，本 change 补齐第 4 个截断点。
  - **#283/#285**（内存）：无关。
- **代价权衡**: 声明期多算一次 `len(items)` 与 `len(items) > max_items`（字面列表，O(1) 级）；dry-run/运行期多点计数。零运行时热路径开销。
- **可回滚性**: 改动集中在新 warnhelper + 两个字段；回滚 = revert，无数据迁移。

## Non-Goals（摘要）

- **不改** `max_items` 默认值（20）——参数另议（#276）。
- **不改** `max_items=0` 语义（不静态截断）。
- **不报告 `max_items=0` 路径下的预算截断静默**（`_resolve_items` 切到 `_remaining_expansion_capacity()` 刚好合身 → `_check_foreach_budget` 不触发，超预算项静默丢弃）——**与本 change 同缺陷类但范围外**（#279 原文只点 `max_items` 静态截断），**显式 Non-Goal + 开 follow-up issue**（见 design 边界节）。
- **不合并** `item_refs_omitted`（ref 列表界）与本 change 的 items 截断（两件事）。
- **不做**「声明期预测/提示 `source` 驱动 foreach 的展开或截断」——声明期本就不知，且会给**最常见**配置加噪声、行动性弱（对抗否决了 grill 的弱提示，见 D3）。
- **字段名** SHALL NOT 复用既有 `items_total`（同 dict 同键会覆盖，见 D2）。
