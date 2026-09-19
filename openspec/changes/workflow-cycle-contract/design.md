# Design: 循环图的契约对模型可见（workflow-cycle-contract）

## Context

issue #219 的实测（session `0a94250da7bf` 的 `wf_7bec352e`）证明：模型按现有提示写循环图会**大概率写错**。用户那张图同时踩了两个坑——回边是数据边（`required` 默认 true → 双向等待）+ 环内是纯聚合（无产出 → 空转）。而 `DeclareWorkflow` 的描述只有一句「Cycles are only allowed through a route node」。

关键判断（决定本 change 的形状）：**这两个坑都能在声明期静态判定**，不需要运行、不需要形式化证明——

| 坑 | 静态判据 | 为什么可判定 |
|---|---|---|
| 空转环 | 环（SCC）内无任何产出节点 | 状态空间不变化 ⇒ 退出条件永不成立 |
| 回边死锁 | route 有来自同环内的 `required` 数据入边 | `required` + 环内互等 ⇒ 定义上的死锁 |

一般性的「循环可终止性」不可判定，**但这两个特例可判定且无误报**，所以本 change 只做这两个特例。

## Goals / Non-Goals

**Goals**

- 模型能在 `DeclareWorkflow` 的描述里读到完整的循环契约（不再只有一句）
- 必然失败的环在**声明期**被拒，而不是运行期烧到 `max_routes`
- 拒绝时给出**可操作**的原因（说清是哪个环、缺什么）

**Non-Goals**

- 不改运行期行为（#217/#218/#220 已由 `workflow-terminal-honesty` 修复）
- 不改 `max_routes` 语义（只讲清楚）
- 不做自动修复（静默改图比报错危险）
- 不做一般性可终止性证明（不可判定）
- 不覆盖 `foreach` 的 `source` 环（既有 `_validate_foreach_source_cycles` 已处理）

## Decisions

### D1 — 空转环：环内必须有「会变」的节点，否则声明期拒绝

**判据**：对每个 SCC（复用既有 `_strongly_connected_components`，`workflow.py:690` 的迭代式 Tarjan），若分量大小 > 1（或自环），且**分量内没有任何产出节点** → 拒绝。

**「产出节点」的定义**：`kind == "subagent"` **或** `kind == "aggregate" and strategy == "llm"`。

- `subagent` 调 LLM，产出内容随每轮输入变化
- `aggregate(llm)` 同样调 LLM 做语义压缩（`scheduler.py` 的 `_execute_aggregate` 在 `strategy == "llm"` 时走 `_launch_run`）
- `aggregate(collect)` **不产出**（纯逻辑拼接，`scheduler.py:1579-1585` 显式 `state.subagent_id = None`）
- `route` **不产出** `result` 槽（`_node_output` 读不到）——这正是用户那张图 `raw` 永远为空串的原因
- `foreach` 是容器，展开项是 subagent，**计入产出节点**

**为什么这个判据无误报**：环内全是 `collect` 聚合 + `route` 时，每轮读到的输入完全相同（没有任何 rand/时间/外部状态），因此计算结果也完全相同、退出条件恒定——这个环**要么 0 轮要么烧到上限**，没有任何合法用途。

> **实现注意（避免过度拒绝）**：判据是「**整个 SCC 内**无产出节点」，不是「相邻两节点」。用户在环外放 subagent、只让一小段是纯逻辑环也应被拒（那一小段同样转不出去）。SCC 天然覆盖这个语义。

### D2 — 回边死锁：route 不得有来自同环内的 `required` 数据入边

**判据**：对每个 SCC，若其中存在 `route` 节点，且该 route 有**数据入边**（`data_incoming`，即源不是 route）的**源也在同一 SCC 内**，且该边 `required`（默认 true）→ 拒绝。

**为什么必然死锁**：`required` 数据入边的语义是「必须等上游到终态才允许派发」（`_data_deps_satisfied`，`scheduler.py:1221`）；而环内上游要启动，又必须等这个 route 的**控制激活**（`_ready_nodes`，`scheduler.py:1346`）。二者互等 ⇒ 图收敛时零节点跑起来。

**为什么官方 `peer-review` 不受影响**：它的回边是 `gate`(route) → `producer`，属**控制边**（route 的出边全是控制边，`workflow.py:243`），不在 `data_incoming` 里。所以判据对官方 pattern 天然免疫——**但必须有测试锁定**，这是最容易误伤的地方。

**修法提示（写进报错文案）**：把回边改成 `required: false`（声明「我不等它」），或把回边从 route 出发。

### D3 — 拒绝而非警告（**列为 grill Open Question**）

业界先例：Airflow / Argo 对拓扑错误都是**拒绝**（`AirflowDagCycleException` / Argo 声明期拒绝环），不是警告。

理由：本 change 的两条判据**无误报**——被拒的图**必然**失败，警告只会让模型带着一个必然失败的图往下走。

**但这是本 change 唯一的对外行为变更**（此前能声明的图会报错），故列为 grill 的 Open Question，由用户拍板。若用户选「警告」，实现改为「声明成功 + `warnings` 字段返回」，本 change 其余部分不变。

### D4 — 提示面：给「正确示例 + 反例」，不是罗列规则

调研结论（Temporal / LangGraph 的共同做法）：**契约靠示例传达**比列规则更易被遵守。故 `DeclareWorkflow` 描述补一个循环小节，结构为：

1. 一句核心规则：**环里必须有个「会变」的节点**（subagent 或 llm-aggregate），否则转不出去
2. 一句回边规则：**回边从 route 出发**（或显式 `required: false`），否则双向等待
3. 一句 `max_routes` 规则：默认 **1**、逐节点配、**跨轮累加不重置**
4. 最小正确示例（subagent 在环内）+ 最小反例（全是 collect 聚合）

**为什么不用「把校验错误喂回去」代替提示**：声明期拒绝**已经**会给模型可操作的原因（D5），但那是**纠错**；D4 是**预防**。两者互补，都要有。

### D5 — 报错文案必须可操作

拒绝时的错误信息要能让模型**直接改对**，至少含：环的成员节点 id、缺什么（无产出节点 / 回边是 required 数据边）、怎么改。

反面教材（必须避免）：`cycle without a route node is not allowed` 这类**只陈述规则、不给修法**的文案——模型看到也不知道下一步做什么。

## Pre-Implementation Review

> 本 change 含 `feature`（spec 可见：新增声明期拒绝路径 + 提示面契约），实现前须由**独立零记忆
> subagent** 审视本 design 的 D1–D5，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions +
> Open Questions 停轮确认）。实际 review 记录以该文件为准。
>
> **重点审视项**：D1/D2 的判据会不会**误伤合法图**（尤其官方 4 pattern 与既有测试里的环图）；
> D3 的「拒绝 vs 警告」需要用户拍板。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| **误伤合法图**（D1/D2 判据过严） | **高** | 官方 4 pattern 必须全部仍通过（测试锁定）；既有 `tests/agent/subagent/` 全量回归；grill 重点审视 |
| 拒绝路径破坏既有测试里的环图 | 中 | 逐个核对既有环测试，确认它们符合新契约（若有不符合的，那正是本 change 要拦的） |
| 提示面文案过长挤占工具描述预算 | 低 | 用最小示例 + 反例，不罗列全部字段 |
| 模型绕过校验（直接构造 spec） | 低 | 声明期校验在 `parse_workflow_spec` 内，所有入口共用；运行期诊断（C）兜底 |

**Trade-off（明确记录）**：新增拒绝路径的代价是「此前能声明的图现在会报错」；换来的是「模型不会再建出必然失败的图」。若选「警告」，代价变成「模型可能带着坏图继续走」——**这是 D3 要用户拍板的核心**。

## Testing Strategy

### 后端（`tests/agent/subagent/`）

**新增校验的判定**（每条都要有正向 + 反向）：

- 空转环（环内全 `collect` + `route`）→ **拒绝**，报错含环成员与修法
- 环内有 `subagent` → **通过**
- 环内有 `aggregate(strategy="llm")` → **通过**
- 环内有 `foreach`（展开项是 subagent）→ **通过**
- 回边死锁（route 有同环内 `required` 数据入边）→ **拒绝**
- 回边从 route 出发（控制边）→ **通过**
- 回边 `required: false` → **通过**

**回归红线**：

- 官方 4 个 pattern（`orchestrator-worker` / `peer-review` / `hierarchical` / `bidding`）**全部仍能声明通过**
- 既有 `tests/agent/subagent/` 全量绿（重点 `test_workflow_*.py`）

### 提示面（`tests/web_tests/` 或 `tests/agent/tools/`）

- `DeclareWorkflow` 的描述含循环小节的关键词（`max_routes` / 回边 / 产出节点）

### 变异验证（硬要求）

每条新校验都要能被「改坏实现」杀死，至少覆盖：D1 的产出节点定义（去掉 `llm` 分支 / 去掉 `foreach` 分支）、D2 的边类型判定（把 `data_incoming` 换成 `incoming` —— 应当**让 peer-review 误伤**从而被测试抓住）。

### 全量

- `uv run pytest tests/agent/subagent/ -q`
- `uv run pytest -q`

## Impact Analysis

（与 `proposal.md` 的同名章节同源；此处补充实现层落点）

| 落点 | 文件:符号 | 说明 |
|---|---|---|
| 新校验 | `workflow.py` 的 `parse_workflow_spec` 校验段（与 `_validate_cycles` / `_validate_foreach_source_cycles` 并列） | 复用 `_strongly_connected_components` |
| 复用 | `workflow.py:_strongly_connected_components`（`:690`） | 既有迭代式 Tarjan，不改 |
| 提示面 | `agent/tools/builtin/subagents.py:DeclareWorkflow` 描述 | 纯文案 |
| （可选 C）| `scheduler.py` 的 `_mark_graph_recursion_exceeded` | diagnostics 补因果 |

**受保护路径**：`openspec/specs/**`、`docs/openspec-change-backlog.md` 的改动需 `workflow-events.jsonl` 结构化解释事件。
