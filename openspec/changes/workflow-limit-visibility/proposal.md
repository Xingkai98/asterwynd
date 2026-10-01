# Proposal: 工作流闸门可见性 — 让模型在撞闸前看见生效上限与余量

关联跟踪 issue：[#275](https://github.com/Xingkai98/asterwynd/issues/275)。同族先例（同一个工具面）：`workflow-dry-run`（issue #273，已归档 2026-09-30）、`workflow-tool-discoverability`（issue #248，已归档 2026-09-29）、`workflow-recursion-limit-default`（issue #262，已归档 2026-09-29）。

后续依赖：本 change 完成后解锁 issue #276（「工作流上限按新能力重估」）——#276 的定值必须以本 change 带来的可见性为实测前提，不得凭感觉调。

## Change Type

- primary: feature
- secondary:
  - subagent
  - tool-surface

## Why

### 问题：模型看不见闸门在哪，也看不见离闸多远

#273 落地 `DryRunWorkflow` 后，N=3 真实验收（证据归档于 `openspec/changes/archive/2026-09-30-workflow-dry-run/reviews/`）暴露同一类现象：

- run 3 **自己声明 `recursion_limit: 80`**（低于默认 100）并撞限（`graph_recursion_exceeded` ×2）；模型靠自身推理才得出「循环没收敛（这本身是很有价值的发现）」。**它不知道默认是 100，也不知道自己离闸多远。**
- run 2 撞了一次节点级 `budget exceeded (token)`——该节点的 `max_tokens: 300` 也是**模型自己设低的**，它不知道自己设的界会掐死节点。

把「模型能从哪里知道闸门值」逐条查一遍（本 change 的侦察脚本 `research/gap_probe.py` / `research/gate_trip_probe.py`，实测输出见 `research/`），缺口是**精确且可复现**的：

| 观察 | 实测结论 |
|---|---|
| **G1 无生效值** | `DryRunWorkflow` 报告顶层**没有任何** `limits` 字段（键集实测：`status/simulated/run_status/spec_hash/goal/nodes/edges/slots/warnings/notes/...`，无限制值）。 |
| **G2 无「声明 vs 展开」** | 一张声明 3 节点、运行期展开成 5 节点（2 个 `__auto_agg__` 自动插层）的图，报告只有逐节点 `auto_inserted` 布尔，**没有顶层汇总**。模型要自己数。 |
| **G3 route 无 `max_routes`** | dry run 报告里 route 节点的条目键集**不含** `max_routes`（实测键：`id/kind/status/runs/produced/received/input_seen/matched/walked_to/used_default/input_sources`）。 |
| **G4 描述不披露图级三闸** | `DeclareWorkflow` 描述（4109 字符）**不提** `max_nodes`/`recursion_limit`，也不提默认值 `200`；只披露了路由的 `max_routes` 默认 1。`DryRunWorkflow` 描述提到闸门**名字**（`max_nodes / max_runs / recursion_limit / max_routes`）却**不提数值**。 |
| **G5 撞闸时非结构化** | dry run 撞 `max_nodes` 时，报告**没有** `limits`、**没有** `diagnostics` 字段（键集实测）。原因只藏在 `warnings[]` 的一句散文里（`...exceeding max_nodes 3 (2 already declared)`）——而**真实运行的** `status()` / `_envelope()` **两者都有**（`limits` + `diagnostics`）。**dry run 是唯一漏掉这两个字段的出口。** |

**关键对照：机制早已存在，只是 dry run 没接上。** `scheduler.py:456` 的 `limits_report(spec, ceiling)` 已经产出 `{declared, applied, clamped}` 三段式，且已接进**三个**出口——`status()`（`scheduler.py:2866`）、`_envelope()`（`scheduler.py:3077`）、资产加载（`subagents.py:2275`）。spec 也早有条款要求「所有对外报出限制值的出口都报实际生效值」。**`DryRunWorkflow` 是第四个出口，但它没接。** 本 change 在很大程度上是**把一个既有机制接到一个漏掉的出口**，而非新建机制。

### 命题

> #273 证明了「模型愿意用 dry run 预演拓扑」。但它预演的是**数据流**，不是**闸门**。
> 模型画完一张 17 节点的大图，dry run 会告诉它「线怎么接」，**不会告诉它「离 200 节点的上限还有多远」**。

本 change 让 dry run（以及相关的模型可见出口）**如实报出闸门**：生效值是多少、声明图展开后多大、离闸多远、撞闸了是哪个闸。

### 为什么这件事现在做

用户判断：「有了 dry run 之后能力大大提升，可以画更复杂的图了，上限值应该再提升一些。」**但「该提升多少」不该凭感觉定**——#196 的先例正是凭感觉调上限、把 12 文件任务腰斩、只好改回来。正确的顺序是：**先让闸门可见（本 change）→ 跑一轮真实验收看模型实际撞什么、余量多少 → 据实定新值（#276）。** 本 change 是 #276 的前置。

## What Changes

1. **`DryRunWorkflow` 报告新增 `limits` 字段**：复用 `limits_report()` 的 `{declared, applied, clamped}`，覆盖 `recursion_limit` / `max_nodes` / `max_runs`。与另外三个出口同源同形，消除「dry run 是唯一不报生效值的出口」这个不一致。
2. **`DryRunWorkflow` 报告新增「声明 vs 展开」节点预算汇总**：例如 `node_budget: {declared: N, expanded: M, auto_inserted: K, limit: L, headroom: L-M}`。数据源是 `ExecutionPlan.declared_nodes` / `.inserted_nodes` / `.nodes` 与 `_eff_limit("max_nodes")`，**零新增计算通道**。
3. **`DryRunWorkflow` 报告的 route 条目新增 `max_routes`（生效值）与已用闸门计数**：让模型看见「这个 route 允许转几次 / 已经转了几次」。
4. **`DryRunWorkflow` 撞闸时报告带 `diagnostics`**：复用 `GraphRecursionError.to_dict()`（或 scheduler 已有的同一结构），让撞闸原因**结构化可见**，而非只在 `warnings[]` 散文里。
5. **工具描述披露图级三闸的默认值**：`DeclareWorkflow` 描述补一句「图级三闸默认 `recursion_limit=100 / max_nodes=200 / max_runs=300`，可在 spec 里声明、可被配置钳制」——**只补事实（值），不补示例**（#248 教训：示例是模型学错的地方；值是事实，不会误导）。

**不变**：闸门的**判定逻辑**（`scheduler.py` 的 `_check_declared_limits` / `_drive` / `_route_verdict` 等）；闸门的**默认值**（本 change 只报值、不改值——改值属 #276）；`WorkflowSpec` 数据结构；既有三个出口的返回体；资产 schema 与 `spec_hash`。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `multi-agent-collaboration`：
  - **MODIFIED** 既有 Requirement「工作流可零成本模拟执行以暴露数据投递语义」——报告的必含字段 SHALL 增加：结构闸的**生效值**（`declared`/`applied`/`clamped` 三段式，与既有出口同源）、「声明 vs 展开」的节点预算汇总、route 节点的生效 `max_routes` 与已用闸门计数；撞闸时 SHALL 附结构化诊断，SHALL NOT 只把原因留在散文 warning 里。
  - **MODIFIED** 既有 Requirement「DeclareWorkflow 描述暴露循环契约」——描述 SHALL 披露图级三闸的默认值（值，SHALL NOT 是示例）。

## 验收（本 change 的验收口径，**只进 proposal、不进 spec**）

沿用 #248/#273 的验收 harness——**同一提示词、同一模型（`deepseek-v4-flash`）、同 `--mode bypass`，N=3**。

| # | 指标 | 主/辅 |
|---|---|---|
| **L0** | 模型能否在**声明大图之前**报出当前生效的图级三闸值（读 transcript：它是否在描述/报告中读到了 100/200/300） | **主指标** |
| **L1** | 模型能否报出「某张图声明 N 节点、展开后 M 节点、离上限还有多少」 | **主指标** |
| L2 | 模型撞闸后，能否从诊断**直接读出**是哪个闸、上限多少、超了多少 | 辅 |
| L3 | 是否因新增字段而**引入新的误读**（如把 `declared` 当 `applied`） | 负面检查 |

**通过门槛**：L0 与 L1 成立（模型能报出生效值与余量），且 L3 无新误读。

**跑之前必须清空全局资产库，且每次 rollout 之间 quarantine 记忆**（`MemoryIndexSource` always-loaded，#248/#273 实测踩过）。

**证据归属**：rollout 证据由实现方产出并落盘（`reviews/acceptance-evidence.md` + 原始 transcript），`/review-loop` 的独立 reviewer 核验可信度。**reviewer 不自己跑 rollout**。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 命中 `full` 判据「走 grill 的非平凡 change」与「对标业界产品」。本 change 触碰**模型可见的工具契约**（报告字段 + 工具描述），其形态（**事前披露限值 vs 事后错误**、**生效值 vs 声明值**）需要业界依据，不是成熟模式的局部照搬。**不判 `light`/`exempt` 的理由**：`exempt` 仅适用 docs-only / 无新增能力面的 bugfix / 上游决策锁定，本 change 三者皆不满足；本 change 有新增模型可见字段与描述条款，是新增能力面。
- research questions:
  - **RQ1**：业界 agent 框架把资源限值（步数 / 节点数 / token 预算 / 重试次数）**在模型动手前**就披露给模型吗？还是只在越界错误里报？形态是什么？
  - **RQ2**：有没有框架把「生效值（钳制后）vs 声明值」分别报给模型？钳制点的报告纪律是什么？
  - **RQ3**：编排/工作流引擎的**干跑 / 预演**输出里，会不会包含「资源预算 / 余量」？还是只报控制流拓扑？
  - **RQ4**：工具体系里，「把既有内部量接到一个漏掉的出口」这类改动，业界有没有「唯一数据源」的纪律（避免两条真相分叉）？
- findings:
  - 待填（侦察阶段产出，见下「研究状态」）。
- design impact:
  - 待填。

**研究状态**：本 change 的 RIR 调研与 `research/` 脚本实证同步进行——先落 `proposal`/`design` 骨架与实测缺口证据（已完成，见 `research/gap_probe.py` / `research/gate_trip_probe.py` 输出），findings 与 design impact 在 grill 前补齐（对齐 #273 的节奏：立项期完成调研并回写 design）。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（Workflow DSL 的工具面与可观测性）。
- **代码**:
  - `agent/tools/builtin/subagents.py` — `_build_dry_run_report` 增 `limits` / `node_budget` / route 的 `max_routes`+计数 / 撞闸时的 `diagnostics`；`DeclareWorkflow` 描述补三闸默认值句。**不改任何既有字段的语义**，只增字段。
  - `agent/subagent/scheduler.py` — **预期不改**。`limits_report()` / `_eff_limit()` / `ExecutionPlan` 字段 / `GraphRecursionError.to_dict()` 都已存在且可复用。**若实现中发现必须改 scheduler，SHALL 先停轮回写本 Impact Analysis**（与 #273 的「不改调度器」不变量同精神：本 change 是「接出口」，不是「改闸门」）。
  - `agent/loop.py` — **预期不改**（不新增工具、不改注册）。
- **测试**:
  - **必须新增**：`tests/agent/subagent/test_workflow_limit_visibility.py`（dry run）
    - `limits` 三段式存在且与 `limits_report()` 逐字段相等（用**钳制**场景断言 `applied != declared` 且 `clamped=True`）；
    - `node_budget` 在**宽扇入**图（`items > MAX_FAN_IN=10`，触发自动插层）上给出 `expanded > declared` 且 `auto_inserted == expanded - declared`；在**窄扇入**图上 `expanded == declared`；
    - route 条目含生效 `max_routes` 与已用计数；
    - 撞闸图（把 `max_nodes` 配小）报告含结构化 `diagnostics`，且 `diagnostics.reason` 为闸名；
    - **不变式回归**：`limits.applied` 与 `_eff_limit` 同源（同一 spec + ceiling 下逐字段相等）——防止「对内钳、对外报声明值」的假面。
  - **必须新增/扩展**：工具描述断言（沿用 `test_workflow_tool_discoverability.py` 范式）——`DeclareWorkflow` 描述含三闸默认值，且**描述长度仍在守卫上界（6000）内**。
  - **必须回归**：既有 dry run 测试（`tests/agent/subagent/test_workflow_dry_run.py`）不因新增字段而失效（新字段是**增**，不是改）。
- **文档**:
  - `openspec/specs/multi-agent-collaboration/spec.md`（current spec 同步，受保护路径）——MODIFIED 2 条。
  - `docs/openspec-change-backlog.md`（本 change 入队；受保护路径）。
  - `README.md` / `README_EN.md` / `docs/architecture.md`：关键词扫描确认工具/报告字段段落是否有事实变化。
- **流程（process）**: 触及受保护路径，需 `current_spec_synced` / `backlog_updated` 结构化事件 + grill 证据 + building review；实现须在独立 worktree、`workflow-limit-visibility/2026-10-01` 分支。**change type = feature → 实现前必须走 `batch-grill-me` + 停轮确认 Open Questions**。
- **与既有 change / issue 的边界（避免重叠）**：
  - **与 #273（`DryRunWorkflow`）**：本 change **扩展**它的报告，**不改**它的模拟语义与隔离机制。是「同一工具的下一个能力层」，非重做。
  - **与 #276（上限重估）**：本 change **只报值、不改值**；#276 才改值，且 #276 blocked-by 本 change（必须先有可见性才能据实测定值）。
  - **与 #262（`recursion_limit` 25→100）**：那次改的是**默认值**；本 change 改的是**可见性**。互补。
  - **与 #248（声明期 schema 可发现性）**：那次解决「域」（合法值集合）可见；本 change 解决「闸门」（资源上限）可见。两类问题。
  - **与 #268（`ValidateWorkflow`）/ #269（运行期语义）**：本 change 不触碰它们的范畴（静态校验 / 数据流语义）。
- **代价权衡（如实记录）**: 新增字段会**增大 dry run 报告的体积**（`limits` 三段式 + `node_budget` ≈ 数百字符）。但报告本就有 `max_report_chars` 有界纪律，且这些字段是**定长小对象**（不随图规模增长），对父上下文的边际成本可忽略。收益是「让模型不必靠撞闸才知道闸门在哪」。
- **可回滚性**: 全部改动集中在 dry run 报告字段 + 一句描述；回滚 = revert 该 commit，无数据迁移、无资产指纹变化（`spec_hash` 由 `WorkflowSpec.to_dict()` 计算，与报告字段无关）。

## Non-Goals（摘要）

- **不改任何上限的默认值**（属 #276）。本 change 只让值可见。
- **不改闸门判定逻辑**。若需改 `scheduler.py` 才能接上出口，先回写 Impact Analysis。
- **不引入第二个真相源**。所有报出的生效值 SHALL 走既有 `limits_report()` / `_eff_limit()`，SHALL NOT 在报告层另算一遍。
- **不做「预测是否撞闸」的推演**。dry run 已能报「当前图展开后是否撞闸」（它真跑了调度器）；本 change 只把结果结构化，不新增静态预测。
