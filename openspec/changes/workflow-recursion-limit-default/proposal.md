# Proposal: workflow 图级 recursion_limit 默认值调大（25 → 100）

关联跟踪 issue：[#262](https://github.com/Xingkai98/asterwynd/issues/262)。同类先例：`workflow-budget-unbounded-default`（issue #196，已合入归档 2026-09-17，同为「默认值调整」类 change）。

## Change Type

- primary: feature
- secondary:
  - agent-runtime
  - subagent

## Why

C2 `workflow-dsl-scheduler`（issue #181，已合入归档 2026-09-14）把图级 `recursion_limit` 默认值定为 **25**，并把它钉进 current spec（`openspec/specs/multi-agent-collaboration/spec.md:124`：「系统 SHALL 施加图级 recursion_limit（默认 25）」）与 `agent/config.py` 的 `WorkflowLimitsConfig`。

当时这组默认值的配套是 C4 的四维成本预算闸（200k token / 5.0 USD / 300 runs / 1800 s），即 `recursion_limit` 只是**多层防线中的一层**。但 `workflow-budget-unbounded-default`（#196，已合入 2026-09-17）把四维预算默认值**全部改为 0（不限）**——于是 `recursion_limit` 与 `max_runs` 成为默认配置下**仅剩的两个结构后盾**（#196 design.md D5 已明确这一点）。**25 这个值从未按「主要后盾」的新语境重新校准。**

实测（issue #262，peer-review 拓扑，权威记账 `_run_refs`）：

| `recursion_limit` | run 总数 | producer 实际轮数 |
|---|---|---|
| 25（当前默认） | 17 | ~9 |
| 50 | 34 | ~17 |
| 100 | 67 | ~34 |
| 300 | 200 | ~100 |

换算比**依赖模板拓扑**，且同一组数据有**两个量纲**须分清（详见 design Context 的比值表）：`recursion_limit ≈ 3 × 轮数` 说的是 **superstep/轮**（收敛 3.00，图级闸口径）；`≈ 1.9 run/轮` 说的是 **run/轮**（收敛 2.00，记账口径）。取回归测试的 `N` 必须按前者。两个后果：

1. **迭代式任务默认约 9 轮就撞顶**（例如「把方案改到批准」这类 `route` 回边循环），远低于用户直觉预期；用户看到 `graph_recursion_exceeded` 时容易误判成自己参数写错。
2. **调大 `max_rounds` 完全无效**：peer-review 的 `max_rounds` 只落到 route 节点的 `max_routes`（`agent/subagent/patterns.py:179,211`），而图级 `recursion_limit` 先于它触发（`agent/subagent/scheduler.py:959`）。实测 `max_rounds=9` 与 `max_rounds=100000` 输出逐字相同。

**本 change 只调默认值，不新增机制**：100 仍走既有 `_eff_limit` / `GraphRecursionError` / `graph_recursion_exceeded` 路径，零新增分支。可覆盖性与 #196 同形——用户仍可在 `subagents.workflow.recursion_limit` 显式覆盖（含调小）。

## What Changes

- `WorkflowLimitsConfig.recursion_limit` 默认值：`25` → `100`（`agent/config.py`）。
- `_parse_workflow_limits` 的 `mapping.get("recursion_limit", 25)` 默认值同步改为 `100`（`agent/config.py`）。
- `_spec_bounds` 的 `getattr(limits, "recursion_limit", 25)` 兜底同步改为 `100`（`agent/tools/builtin/subagents.py`）。
- `DEFAULT_RECURSION_LIMIT` 常量：`25` → `100`，同步模块 docstring 里的默认值表述（`agent/subagent/workflow.py`）。
- spec delta：MODIFIED 既有 Requirement「reducer 声明与图级递归上限」，把「（默认 25）」改为「（默认 100）」。

**不变**：`max_nodes=200` / `max_runs=300` 两个结构闸默认值与语义；`max_routes`（route 节点自身预算，先于图级闸触发）；`GraphRecursionError` 的构造、`graph_recursion_exceeded` 状态的终态语义、envelope schema；`_eff_limit` 的 min 钳制方向（声明值低于配置时不被抬高）；`to_dict()` 的「等于默认值则省略」序列化规则（其副作用见 Impact Analysis）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `multi-agent-collaboration`: 既有 Requirement「reducer 声明与图级递归上限」钉的**默认数值**由 25 改为 100。enforcement 机制（超限报 `GraphRecursionError` / `graph_recursion_exceeded`）、图级计数口径（superstep）、与 `max_nodes` / `max_runs` 的关系均不变。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 命中 `full` 判据「走 grill 的非平凡 change」——本 change 由仓库规则强制走 grill（触及 spec 契约钉死的全局默认值、影响**所有** workflow 而非单个模板），故按 `full` 完成完整 RIR。改动量虽小，但「调成多少、依据是什么」正是本 change 唯一的设计决策，必须由调研支撑而非拍脑袋。**不判 `light`/`exempt` 的理由**：调研结论会**反向挑战**候选值 100（见 findings 第 1 条：LangGraph 把同一语义的默认值一路提到 10007），因此这不是「成熟模式的局部应用」，而是需要写明依据与设计影响的取值决策。
- research questions:
  - **RQ1**：业界框架（LangGraph / CrewAI / AutoGen / 本地参考仓库）的**图级/工作流级**迭代上限默认值是多少？其调优依据是什么？
  - **RQ2**：这些框架是否经历过「默认值偏紧被迫调大」的同类事件？结论是否支持「有界但宽松」而非「默认不限」？
  - **RQ3**：当成本预算被设为不限、结构闸成为主要后盾时，业界怎么定结构闸的量级？
  - **RQ4**：候选值 100（≈33 轮）与业界取值相比处于什么位置？是否有更合理的依据支持其它取值？
- findings:
  1. **LangGraph（本仓 `recursion_limit` 语义的直接来源，C2 design D5 明写「抄 LangGraph」）已经把同一语义的默认值从 25 大幅上调，且**没有**停在 100**。`langchain-core` 仍保留 `DEFAULT_RECURSION_LIMIT = 25`（`libs/core/langchain_core/runnables/config.py:171`），但 LangGraph 自己覆写为 `langgraph/_internal/_config.py:32`：
     ```python
     DEFAULT_RECURSION_LIMIT = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007"))
     ```
     关键提交 `a5827c5c`「fix: change default recursion limit (#6676)」，commit message 逐字：*"25 is pretty unreasonable for most applications, bumping up to 1000 by default, burden really should be on the user to enforce this based on their application"*。随后 `2fb367e9`（#7355）因「默认值当哨兵会与用户显式值撞车」把 10000 调到 10007。**注意**：LangGraph 的 `recursion_limit` 也数 **superstep**（与本仓同口径），所以 10007 superstep 实际上接近「不限」，与本仓的 100 superstep 不在同一量级。
  2. **本地参考仓库中，与本 change 处境最像的是 `deepseek-harness` 的 Ralph workflow**：`packages/workflow/tool-ralph/src/index.ts:35` 的 `maxRounds` 默认 **256**，其 README 明写设计口径——*"Only round count bounds aggregate effort — token, price, and elapsed-time budgets are deferred."* 这与 #196 之后本仓「成本预算不限、只剩结构闸」的处境**逐字同构**，而它选的量级是 256 **轮**（若按本仓 peer-review 约 3 superstep/轮折算，相当于 768 量级的 superstep cap）。
  3. **另有两条业界路线选择「默认不限」**：`opencode` 的 `agent.steps` 默认 `Infinity`（`packages/opencode/src/session/prompt.ts:1178`，仅在末步注入 `MAX_STEPS_PROMPT` 促使模型收尾）；`kimi-code` 的 `loop_control.max_steps_per_turn` 默认 unset/`0`=不限，其 changelog 明写 *"Remove the default per-turn step limit of 1000. Users can still set `max_steps_per_turn` in config to enforce a custom limit."* 这两条与 #196 的「默认不限」口径同向。
  4. **反向样本：`zcode` 取更紧的值**。`finalCritic.maxIterations=3`、`clarify.maxRounds=3`、`reactLoop.maxRounds=30`（`apps/zcode-cli/packages/core/src/workflow/definition.ts:14,25,28`），subagent `maxTurns` 默认 **4**（`core/src/runtime/methods/subagent.ts:269`）。说明「按 loop 语义分层给不同上限」也是一种成熟做法，那些值计数的是**各自 loop 的轮数**而非图级 superstep，与本仓 `recursion_limit` 不同量纲。
  5. **CrewAI / AutoGen 的对应参数不可直接比价**：CrewAI `max_iter` 默认 25，但它是**单个 agent 对一个 task** 的迭代上限（per-agent-loop），不是图级；AutoGen `ConversableAgent.max_consecutive_auto_reply` 构造器默认 `None`，落到类属性 `MAX_CONSECUTIVE_AUTO_REPLY`（各版本文档口径不一致，有来源称 0.4.x 为 15）。两者量纲都与本仓图级 superstep 不同，仅作旁证。
  6. **本地参考仓库可用性**：`.dev/reference-repos.txt` 在本 worktree **不存在**（该文件不提交，属正常）。已改用 `/home/shared/agent-study/reference-repos/` 实测目录（`codex` / `deepseek-harness` / `kimi-code` / `opencode` / `pi` / `zcode`）作为参考仓库层；**其中不含 LangGraph / CrewAI / AutoGen 源码**，故这三者的结论来自其官方仓库源码与文档的在线核对（已记录 file:line / commit），不是本地推断。
- design impact: 见 design.md D1–D4。**调研对设计的主要影响**：RQ4 的结论是「100 是一个**有依据但偏保守**的取值，不是业界共识值」——它高于 zcode 的 loop 级上限、低于 LangGraph 的有效值，处在 deepseek-harness 256 轮与本仓现状 25 之间，主要正当性来自「与 `max_runs=300` 不打架」这条**本仓内部**约束（见 RQ3 / design D1）。该张力已转成 Open Question 交用户拍板，未在文档里单方面改写用户已定的 100。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（图级结构闸的默认数值）。
- **代码（四处默认值定义点，必须同步，否则直构 config 与 yaml 加载/兜底路径会分叉——#196 的既有教训）**:
  - `agent/config.py:337` — `WorkflowLimitsConfig.recursion_limit: int = 25`（dataclass 字段默认，`AsterwyndConfig()` 直构路径）。
  - `agent/config.py:1659` — `_parse_workflow_limits` 的 `mapping.get("recursion_limit", 25)`（yaml 加载路径）。
  - `agent/tools/builtin/subagents.py:469` — `_spec_bounds` 的 `getattr(limits, "recursion_limit", 25)`（`manager.config` 链路缺失时的兜底）。
  - `agent/subagent/workflow.py:35` — `DEFAULT_RECURSION_LIMIT = 25`；该常量另有三处消费者，改一处即自动跟随：`WorkflowSpec.recursion_limit` 字段默认（`:230`）、`parse_workflow_spec` 的 `default_recursion_limit` 形参默认（`:316`）、`to_dict()` 的「等于默认值则省略」哨兵（`:288`）。
  - **外加模块 docstring**：`agent/subagent/workflow.py:13` 的「三闸默认值（Q5）：`recursion_limit=25` / …」必须同步，否则文档说 25、代码行为 100。
  - **确认无第五处**：`subagents.py:471,473` 的 200/300 是另两个闸；`scheduler.py:1974,2906` 的「默认 25」是 `max_active + max_queued_runs = 5 + 20`（并发容量），与 `recursion_limit` 同名不同义，**不得**改动；`web/static/workflow_graph.js:1091` 只读 `diagnostics.recursion_limit`（运行时值），不含默认值。
- **`agent/config.py` 目前不 import `agent/subagent/workflow.py`**（已核实：config.py 无任何 subagent 模块导入）。因此本次是否顺手把四处字面量收敛为单一常量，取决于是否接受新增一条 config → subagent 的模块依赖（方向无环，`workflow.py` 只 import stdlib）。**该取舍列为 design D3 交 grill 审视**；若不收敛，四处字面量必须靠测试锁定一致性。
- **测试**:
  - **必须改**（现为红）：`tests/agent/subagent/test_workflow_tools.py:235` 的 `assert config.subagents.workflow.recursion_limit == 25`。
  - **需新增回归**：把既有「显式上限触发 `graph_recursion_exceeded`」语义测试**与默认值解耦**——现有触发类测试（`test_scheduler.py`、`test_terminal_honesty.py`、`test_dynamic_foreach.py`、`test_aggregation_runtime.py`、`test_workflow_graph_events.py`、`test_workflow_graph_snapshot.py`）均已**显式**声明 `recursion_limit` 或改用 `max_nodes` / `max_runs` 触顶，改默认值后应保持绿；新增一条「默认配置下 peer-review 形态的 `route` 回边循环能跑到 > 9 轮」的回归（构造口径见 design Testing Strategy），并配对照组证明旧默认 25 会撞顶，避免写成恒真断言。
  - `tests/agent/subagent/test_workflow_asset_limits.py:45,64,79`、`test_workflow_asset_tools.py:74`、`test_scheduler.py:479-480,507`、`test_terminal_honesty.py:166,186` 使用的是**显式** 25（构造参数或 spec 声明），不依赖默认值，预期保持绿。
- **文档**: `openspec/specs/multi-agent-collaboration/spec.md:124`（current spec 同步，受保护路径）；`docs/openspec-change-backlog.md`（本 change 入队/状态）。`README.md` / `README_EN.md` / `asterwynd.example.yaml` / `docs/` 经关键词扫描（`recursion_limit` / 默认 25）**无命中**，预期无改动；`docs/openspec-change-backlog.md` 中 `workflow-dsl-scheduler` 条目的「图级 recursion_limit=25」是**历史归档记录**（描述 C2 当时交付的内容），按「只更新当前变更造成的事实变化」原则**保留不改**，避免篡改历史。
- **副作用（资产指纹）**: `WorkflowSpec.to_dict()`（`workflow.py:288`）在字段等于 `DEFAULT_RECURSION_LIMIT` 时**省略**该键，而 `spec_hash` 由 `to_dict()` 计算。默认值 25→100 后（grill 已逐类实测）：
  - 未声明 `recursion_limit` 的 spec：`to_dict()` 照旧省略该键 → **`spec_hash` 不变**（绝大多数资产无感知）。
  - **显式**声明 `recursion_limit: 25` 的 spec：旧默认下它「等于默认」被省略；新默认下 25 ≠ 100 → 该键**开始被序列化** → `spec_hash` **变化**。后果是一次性的：同名资产再保存时 `save()` 的 `unchanged` 判据（`workflow_assets.py:381`）会首次判为 `updated`。这是语义上**正确**的收敛（25 从此是一个有意义的不同值），但需在文档写明，避免被误读成 bug。
  - **显式**声明 `recursion_limit: 100`（即**新**默认值）的 spec：改前 100 ≠ 25 被序列化，改后等于默认被省略 → `spec_hash` **同样变化**（方向相反、结论同）。
  - **资产加载/重跑路径不受破坏**：`WorkflowAsset.spec_hash` 保存时冻结、加载不重算（`workflow_assets.py:213`）；`RunWorkflowAsset` 重跑走 `parse_spec_for_manager` 重解析（`subagents.py:1209-1215`），故未声明键的存量资产**按新默认 100 生效**（本 change 的收益），显式 25 的资产仍按 25 生效、`limit_ceiling` 现为 100（钳制方向不变）。
- **代价权衡（issue #262 明确要求如实记录）**: `recursion_limit` 是默认配置下主要的结构后盾之一，调大 4 倍意味着**一次失控循环最坏烧掉的 run 数从约 17 涨到约 67**（peer-review 实测），而四维成本预算默认**不限**（#196），即最坏情况下没有成本闸兜底。这是**有意**的取舍：与 #196 同口径（不与「默认不限」精神冲突——`recursion_limit` 是结构闸，不是成本软闸），且 67 仍 **远低于** `max_runs=300`，两个结构闸不打架。缓解面：①`max_runs=300` 与 `max_nodes=200` 仍是硬上限；②用户可显式写回 `subagents.workflow.recursion_limit`（含调小）恢复旧行为；③route 节点自身的 `max_routes` 仍是环的第一道闸。
- **流程（process）**: 本 change 触及受保护路径 `openspec/specs/**`，需 `current_spec_synced` 结构化事件 + grill 证据 + building review；收尾按 OpenSpec archive 流程归档。实现须在独立 worktree、`workflow-recursion-limit-default/2026-09-29` 分支。
- **与 #246 的边界（避免重叠）**: 本 change **只调默认值**，不含任何诊断/反馈机制。`graph_recursion_exceeded` 诊断增补 `declared_max_rounds` / `rounds_actually_run` / `limit_source` 一类「让模型知道该调什么」的反馈，**不在本 change 范围**，由 change **`workflow-builtin-templates`**（issue #246）承担——该机制已定在该 change 的 `design.md` **D7**（增 `GraphRecursionError.to_dict()` 字段 + 用 `asset_source` 取 `declared_max_rounds`），并正在随其实现。**注意交叉引用方式**：机制写在 change 文档而非 issue #246 正文（正文无这三个字段名），故此处引 change-id 而非 issue 正文。两侧无顺序依赖（本 change 先合入或 `workflow-builtin-templates` 先合入均成立）。
- **已确认结论（2026-09-29，用户拍板）**: ①候选值 **100 维持**（正当性来自本仓 `max_runs=300` 约束而非业界先例，design D1 已如实写明）；②四处默认值字面量 **不收敛**（design D5）；③诊断反馈机制归属 **#246 / `workflow-builtin-templates`**（上一条）。详见 design 的 `## Open Questions`（Q1–Q6 全部 ✅ 已确认）与 `reviews/grill-design.md` 的 `## User Confirmation`。
