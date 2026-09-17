# Design: workflow 四维预算默认无上限

## Context

C4 `workflow-budget-attribution`（#185）落地了 workflow 级四维度总预算（tokens / cost_usd / runs / wall_time_s），默认 `200000 / 5.0 / 300 / 1800`。实现落在：

- `agent/config.py:280-295` `WorkflowBudgetConfig`（frozen dataclass，四字段默认值）。
- `agent/config.py:1481-1513` `_parse_workflow_budget`（逐字段 `mapping.get(key, <默认>)`）。
- `agent/subagent/workflow_budget.py:57-70` `WorkflowBudget.__init__`（`getattr(config, "<field>", <兜底>)`，配置链路缺失时用兜底）。
- `agent/subagent/scheduler.py:322-329` `_budget_config`（从 `manager.config` 取 `subagents.workflow.budget`，缺失返回 `None`）。

**关键既有事实**：四维预算的「不限」语义在 C4 已经存在并已文档化——grill Q11 确认「四字段均 `0 = 不限`」，实现用真值判定表达（`workflow_budget.py:110-120` 的 `if self.max_tokens and ...`、`:127-129` 的 `if self.max_runs and ...`、`scheduler.py:2093` 的 `if budget is not None and budget.max_runs`）。也就是说「关闭某一维」的机制**今天就已经跑通**，缺的只是把「未配置」这个最常见情形也映射到「不限」。

问题在于默认值：`openspec/specs/multi-agent-collaboration/spec.md:190` 把「默认 200k / 5.0 / 300 / 1800」写进了 current spec，于是**没配置 budget 的用户会得到一组从未显式要求的硬上限**。实测 12 文件 foreach 体检在约 18 万 token 处被 `budget_exceeded` 腰斩（#196）。

同层先例是 #192：AgentLoop 的 `max_iterations` 由「默认 20」改为「默认 `None`（无上限）」，只有显式 `--max-iterations` 才设上限。本 change 把同一口径搬到 workflow 预算。

## Goals / Non-Goals

**Goals**

- 未显式配置时，四维预算**不设上限**：长任务（token 消耗大、run 数多、挂钟长）不被默认值掐断。
- 显式配置（配置文件 `subagents.workflow.budget.*`，以及——若拍板——CLI 入参）**仍精确生效**，含显式 `0 = 不限`。
- 保持 C4 的全部既有机制：enforcement 判定、超限状态机（stop_new + 取消 queued + drain + 根节点 `budget_exceeded`）、envelope 的 `budget` 块 schema、C2 结构闸关系。

**Non-Goals**

- 不改 `WorkflowBudget` 的判定/记账逻辑，不改调度器接线，不改 envelope schema。
- 不改 C2 三闸（`recursion_limit` / `max_nodes` / `max_runs`）的默认值或语义。
- 不改单 run 预算（`agent/subagent/budget.py` 的 `subagents.budget.max_tokens` / `max_time_s`，这两个的默认值本来就是 `None` = 不限）。
- 不动 Web 页面展示口径（图例/异常态语义/节点详情/多图可读性属 #196 明确拆出的另一个 issue）。

## Decisions

### D1 — 默认值表示法：用 `0`（既有「不限」哨兵），不用 `None`，不加总开关

- **决策**：`WorkflowBudgetConfig` 四字段默认值改为 `0`（`max_total_tokens=0`、`max_total_cost_usd=0.0`、`max_total_runs=0`、`max_wall_time_s=0.0`）。
- **理由**：
  1. `0 = 不限` 是 C4 Q11 已确认并已文档化、已在实现里跑通的语义。默认值改成 0 = 「未配置即不限」，与显式写 0 走**同一条代码路径**，零新增分支。
  2. `None` 会引入**双哨兵**（`None` 与 `0` 都表示不限），且与 C4 Q11「显式 `null` 一律拒绝」的契约直接冲突——配置层已经用 `_parse_non_negative_int/float` 把 YAML 的 `null` 判为错误，dataclass 层再用 `None` 当默认值会让「null 被拒」这条规则难以自洽。此外 `WorkflowBudget.__init__` 的 `int(getattr(...))` / `float(getattr(...))` 需要额外的 `None` 分支。
  3. 「总开关 + 保留数值默认」是第三选项，但它引入**两种关闭方式**（开关 + 逐维 0），语义叠加后更难解释，且需要新字段与新的解析/校验路径——对「只改默认值」这个目标属于过度设计。
- **备选**：`None` 默认（更自描述，代价见上）；总开关（最重，语义最杂）。

### D2 — 配置层默认值落点：dataclass 字段 + 逐字段 `mapping.get` 同步改 0

- **决策**：`WorkflowBudgetConfig` 四字段默认值与 `_parse_workflow_budget` 里四处 `mapping.get(key, <默认>)` 的默认值**同时**改为 0。
- **理由**：C4 grill 决策 7 的教训是「只给 dataclass 默认值不会让 yaml 生效」——两处默认值必须一致，否则 `AsterwyndConfig()` 直构与 yaml 加载会走出不同结果。既有测试 `test_missing_budget_section_uses_defaults` 正是钉这条。
- **保留的校验不变**：显式 `null` 仍拒绝（`_expect_mapping` + 非负解析函数）；负值仍拒绝；非数值仍拒绝；显式数值（含显式 `0`）仍生效。

### D3 — `WorkflowBudget.__init__` 的 `getattr` 兜底同步改 0

- **决策**：`WorkflowBudget.__init__` 四处 `getattr(config, "<field>", <兜底>)` 的兜底值由 `200000/5.0/300/1800` 改为 `0`。
- **理由**：这条路径服务「`manager.config` 缺失或链路断」（`_budget_config` 返回 `None`）。默认语义统一为「不限」后，兜底也必须是「不限」，否则同一份「未配置」在两条路径上得到不同结论。`scheduler.py:322-329` 的防御式读取保持原样。

### D4 — CLI 入参（`--workflow-budget-*`）是否纳入本 change

- **状态**：**待 grill 停轮确认**（#196 的待定项之二）。倾向性推荐：**本 change 不改 CLI**，理由见下；若用户要求可扩为 benchmark-only 或全命令。
- **推荐（不改 CLI）**：默认改成不限后，#196 的原始痛点（体检被腰斩）已解决；恢复上限的通道是配置文件（`subagents.workflow.budget.*`），已可用且可版本化。`--max-iterations` 先例的特殊性在于 AgentLoop 的 `max_iterations` **原本没有配置文件落点**，只能在 CLI 传；而 workflow 预算是配置驱动的，CLI 只是便利层。新增 4 个 flag × 多个命令会显著扩大公共 CLI 面、需新 `ConfigOverrides` 字段与 `_apply_cli_overrides` 分支、并与既有 `benchmark --budget-cap`（单轮成本上限，另一个概念）并存易混淆。
- **备选 A（benchmark-only）**：只给 `benchmark` 加 `--workflow-budget-tokens/-cost-usd/-runs/-wall-time-s`，服务「批量重放时想临时设防烧钱闸」的运维场景。代价：新 `ConfigOverrides` 字段 + 4 个 Typer 选项 + 测试。
- **备选 B（全命令）**：`run` / `interactive` / `web` / `benchmark` 全加，最大化对齐 `--max-iterations` 先例。代价最大。

### D5 — C2 结构闸不变，仍是兜底

- **决策**：`recursion_limit`（25）/ `max_nodes`（200）/ `max_runs`（300）默认值与语义**均不改**。
- **理由**：这是 C4 Q14 已确认的分工——C2 三闸是**声明期结构闸**（fail-fast，`parse_workflow_spec` 阶段就能拒绝超限 spec），C4 四维是**运行期资源预算**（drain 语义）。#196 的待定项之三（「预算无上限后结构闸是否仍兜底」）按既有分工回答：**仍兜底**。这不只是保守——若无上限的预算同时解除结构闸，`max_items=0` 的 foreach 将失去一切 run 数上限，正是 C4 当初要防的烧钱面。
- **副作用（需在文档明说）**：预算不限**不等于**无任何上限。run 总数仍受 C2 `max_runs`（300）与 `max_nodes`（200）约束，图级步数受 `recursion_limit`（25）约束。要真正放大这些上限，用户需显式调 `subagents.workflow.max_runs` / `max_nodes` / `recursion_limit`。这与 Q14 的既有结论一致。

### D6 — envelope 表示与 spec 表述

- **决策**：envelope / `status()` 的 `budget.dimensions` 在「不限」时继续报 `limit: 0`，不新增 `unlimited` 布尔字段，不改 schema。
- **理由**：`0 = 不限` 已是该字段的既有口径（C4 Q11），增加并行字段会让消费方要同时处理两种表示。页面展示口径的改进属 #196 拆出的独立 issue。
- **spec**：MODIFIED 既有 Requirement「workflow 级四维度总预算」，把「默认 200k / 5.0 / 300 / 1800」改为「默认不限（0），显式配置才设上限」。

## Pre-Implementation Review

（本节在实现前的独立 grill 完成后回填：Confirmed Decisions、必须修改项、Open Questions 处理结论，见 `reviews/grill-design.md`。）

## Risks / Trade-offs

- **成本失控风险（最主要）**：默认不限意味着一个失控的图可能烧掉任意 token / 金额。这是**有意为之**的取舍，与 #192 同口径（框架不替使用者决定花多少钱）。缓解面：①C2 结构闸仍限 run 总数与节点数；②单 run 预算 `subagents.budget.max_tokens` / `max_time_s` 仍在（超限杀 run）；③用户可随时在配置文件写回 200k/5.0 恢复旧行为。需要在 README / spec 明说「恢复默认上限」的写法。
- **既有测试断言默认值**：`test_workflow_budget_config.py`（4 处）、`test_workflow_budget.py`（2 处）、`test_workflow_replay.py`（1 处）都会红。风险不在改数字，而在**别把语义覆盖改丢**——尤其 `test_max_total_runs_default_matches_structural_max_runs` 的前提（D6/Q4「默认值与 C2 对齐」）在默认变 0 后不再成立，必须改写为「预算默认不限 + C2 max_runs 仍兜底」的新语义测试，而不是删掉了事。
- **`test_budget_not_configured_is_noop_for_existing_behavior`** 的断言面要扩：不能只断言 `exceeded is False`，还应断言一个**明确会越过旧默认**（如 20 万 token）的图在默认配置下跑完不触发 budget_exceeded——否则这条测试在新默认下仍会通过，但完全没有覆盖本 change 的核心行为。
- **文档漂移**：`asterwynd.example.yaml` 若含 budget 示例需同步；当前该文件未含 budget 段，预期无改动，收尾时须复核。

## Testing Strategy

- **单元（配置层）**：`AsterwyndConfig()` 四字段默认为 0；yaml 显式配置四字段生效；只配一个字段时其余保持 0；缺 budget 段时为 0；显式 `null` 仍 `ConfigError`；负值/非数值仍 `ConfigError`。
- **单元（账本层）**：默认构造的 `WorkflowBudget`（无 config）四维上限为 0 且 `exceeded_dimension` 恒 `None`；`dimensions()` 在默认下报 `limit: 0`。
- **调度器集成（回归，对 #196 场景）**：默认预算下，一条会累积超过旧默认 200k token 的链式/foreach 图**跑完且 `status == "completed"`**、`budget.exceeded is False`。这是本 change 的核心回归。
- **调度器集成（显式上限仍生效）**：`max_total_tokens=100` 等显式配置仍触发 `budget_exceeded` + drain + 根节点终态（既有测试已覆盖，须保持绿）。
- **兼容**：C2 `max_runs` 在预算不限时仍兜底（既有 `test_workflow_budget.py` 的 Q14 用例保持绿）；`max_items=0` 的展开容量在预算不限时退化为 C2 两闸的最小值（`_remaining_expansion_capacity` 的 `budget.max_runs` 真值判定已天然处理）。
- **benchmark 记录面**：`workflow_record` 的 `budget_config` 反映新默认（0），replay 可比性断言同步。
- **全量**：`uv run pytest -q` 全绿；`npx openspec validate --all --strict` + `python3 scripts/check_openspec_artifacts.py` 通过。
