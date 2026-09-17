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

### D4 — CLI 入参（`--workflow-budget-*`）：**本 change 不纳入**

- **状态**：**已由用户拍板确认（2026-09-17）：不改 CLI**（grill Q1）。
- **结论**：本 change 只通过配置文件 `subagents.workflow.budget.*` 设上限，不新增 `--workflow-budget-*` 系列入参。
- **理由**：默认改成不限后，#196 的原始痛点（体检被腰斩）已解决；恢复上限的通道是配置文件，已可用且可版本化。`--max-iterations` 先例的特殊性在于 AgentLoop 的 `max_iterations` **原本没有配置文件落点**，只能在 CLI 传；而 workflow 预算是配置驱动的，CLI 只是便利层。新增 4 个 flag × 多个命令会显著扩大公共 CLI 面、需新 `ConfigOverrides` 字段与 `_apply_cli_overrides` 分支、并与既有 `benchmark --budget-cap`（单轮成本上限，另一个概念）并存易混淆。
- **备选（未采纳）**：A = benchmark-only（新 `ConfigOverrides` 字段 + 4 个 Typer 选项 + 测试）；B = 全命令对齐 `--max-iterations`。若将来确有「一行命令临时设闸」需求可另立 change。

### D7 — 段落级显式 `null` 收紧为 `ConfigError`（grill Q2，已确认）

- **决策**：`subagents` / `subagents.workflow` / `subagents.workflow.budget` 三级，**键存在但值为 `null`** 时一律 `ConfigError`；键不存在则走默认（= 不限）。
- **理由**：今天段落级 `null` 被 `_expect_mapping` 静默当成 `{}`（`agent/config.py:1614-1619`），随即逐字段落回默认值。默认值改成 0 后，**同一份配置从「有闸」静默变成「四闸全无」**，而字段级 `null`（`max_total_tokens: null`）却是明确拒绝的——两者口径不一致，且这条缝恰好落在「安全闸被静默关闭」的方向上。用户拍板原则：**不写该字段 = 没有上限；写了且有值 = 设上限；写了但不给值（null）= 配置错误**。收紧正是本 change 的时机（它把「缺配置」的后果由有闸变成无闸）。
- **落点**：新增一个取子段的辅助函数（键缺失 → `{}`；键存在但为 `None` → `ConfigError`；非 mapping → `ConfigError`），在 `_parse_subagents_config`（取 `workflow`）、`_parse_workflow_limits`（取 `budget`）与顶层装配（取 `subagents`）三处替换现有 `mapping.get(key, {})`。
- **范围边界**：只收紧本预算链条上的三级。其它顶层段（`tools` / `mcp` / `agent` 等）的段落级 `null` 语义**不在本 change 范围**——那些段缺失只意味着「用功能默认值」，不存在「静默关掉安全闸」的后果。

### D5 — C2 结构闸不变，仍是兜底

- **决策**：`recursion_limit`（25）/ `max_nodes`（200）/ `max_runs`（300）默认值与语义**均不改**。
- **理由**：这是 C4 Q14 已确认的分工——C2 三闸是**声明期结构闸**（fail-fast，`parse_workflow_spec` 阶段就能拒绝超限 spec），C4 四维是**运行期资源预算**（drain 语义）。#196 的待定项之三（「预算无上限后结构闸是否仍兜底」）按既有分工回答：**仍兜底**。理由不止保守：C2 的数量闸是默认配置下**唯一**还在生效的兜底（见 Risks ①）。
- **副作用（需在文档明说）**：预算不限**不等于**无任何上限。run 总数仍受 C2 `max_runs`（300）与 `max_nodes`（200）约束，图级步数受 `recursion_limit`（25）约束。要真正放大这些上限，用户需显式调 `subagents.workflow.max_runs` / `max_nodes` / `recursion_limit`。这与 Q14 的既有结论一致。
- **grill 修正（20260917）**：原文「若无上限的预算同时解除结构闸，`max_items=0` 的 foreach 将失去一切 run 数上限」**与代码实际行为相反**。`_remaining_expansion_capacity`（`scheduler.py:2082-2097`）在三个候选上限全为 0/缺失时返回 0，调用方 `items[:0]` 是**空集**——失去上限的结果是**静默展开成 0 项**（图照常 `completed`、结果为空），而不是无限跑。本 change 不改变该不变式（spec 侧 `max_runs` / `max_nodes` 经 `_positive_int` 保证 ≥1，`limits` 恒有 ≥2 项，`else 0` 是当前不可达的死代码），但论证口径已按事实修正，避免误导后续读者。
- **失败出口变化（grill 补充，需写进影响面）**：默认配置下 runs 维度的触顶出口**会改变**。C4 的 runs 检查刻意先于 C2（`scheduler.py:1227-1242` 派发点、`:1468-1475` foreach 展开点）；默认 `max_total_runs=0` 后该检查不再拦截，run 数触顶改由 C2 抛 `GraphRecursionError` → `_cancel_all_in_flight()` + `_mark_graph_recursion_exceeded`（`scheduler.py:669-673`），而不是 `budget_exceeded` + drain（`:676-679`）。两者都仍可恢复（`CancelledError` handler 同样写 checkpoint，`manager.py:1109-1110`），但节点终态、run 终态与 envelope `status` 都不同。spec delta 的 Scenario「预算不限不解除 C2 结构闸」已覆盖该语义，方向正确。

### D6 — envelope 表示与 spec 表述

- **决策**：envelope / `status()` 的 `budget.dimensions` 在「不限」时继续报 `limit: 0`，不新增 `unlimited` 布尔字段，不改 schema。
- **理由**：`0 = 不限` 已是该字段的既有口径（C4 Q11），增加并行字段会让消费方要同时处理两种表示。页面展示口径的改进属 #196 拆出的独立 issue。
- **spec**：MODIFIED 既有 Requirement「workflow 级四维度总预算」，把「默认 200k / 5.0 / 300 / 1800」改为「默认不限（0），显式配置才设上限」。

## Pre-Implementation Review

独立零记忆 subagent 已完成设计追问（run `grill-workflow-budget-unbounded-default-20260917`），完整记录见 `reviews/grill-design.md`。

**Confirmed Decisions（10 条，读代码可自行收敛，已整合进本 design）**：

1. 默认值确实只有 **3 处**（config dataclass / `mapping.get` / `getattr` 兜底），D2+D3 的落点清单完整；`subagents.py:409-411` 是 C2 三闸、`workflow_replay.py` 的 `_budget_config_dict` 是观测面，都不是第四处默认值。
2. 「`0 = 不限`」在四维**全部**是真值判定（`workflow_budget.py:112-118` / `:128` / `scheduler.py:2093`），改默认值**零新增分支**。
3. `_remaining_expansion_capacity` 在 `max_runs=0` 后行为正确，`min(limits)` 不会取到意外值，`else 0` 是当前不可达死代码。
4. 字段级 `null` / 负值 / 非数值的拒绝**与默认值无关**，改默认值不会让任何既有校验失效（已实测确认）。
5. D4 的 CLI 现状事实准确：`agent/main.py` 确无任何 `--workflow-budget-*` 入参，`ConfigOverrides` 仅 3 字段；既有 `--budget-cap` 是单轮成本上限，另一个概念。
6. 「四维都越过旧默认」的回归测试**不成立**，验收口径收敛为「token 维度必须真越过 200k + 配对照组」（见 Testing Strategy）。
7. 默认配置下 runs 维度**失败出口会改变**（drain → cancel），需记入影响面（已补进 D5）。
8. 部分配置（写一维 = 其余三维变不限）是 #196 口径的直读结果，实现零成本，副作用需写进文档（已补进 Risks）。
9. 文档影响收敛：`asterwynd.example.yaml` 无 budget 段属实；`README.md` / `README_EN.md` 从不记载该默认值，**不强制同步**；真正带旧默认值的是 spec 与 backlog。
10. 测试红名单（4 / 2 / 1）精确；另 `tests/benchmark/test_workflow_modes.py:181` 的合成字面量 `{"max_total_runs": 300}` 不参与断言、改后仍绿，但口径过期，建议顺手改成 0（非门禁要求）。

**必须修改（已落实）**：

- D5 的「解除结构闸会让 `max_items=0` 失去 run 数上限」推断与代码相反 → 已改为「会退化成静默空展开」。
- Risks 的缓解面②「单 run 预算仍在」是**空头承诺**（单 run 默认 `None`）→ 已改为条件句。
- 补充「默认下 runs 出口由 drain 变 cancel」与「部分配置 = 逐维 opt-in」两条副作用。

**Open Questions（2 条，已由用户停轮确认，答复记录在 `reviews/grill-design.md` 的 `## User Confirmation`）**：

- Q1（CLI 入参）→ **不改 CLI**，见 D4（已定结论）。
- Q2（段落级 `null`）→ **收紧为 `ConfigError`**，见 D7（新增 Decision）。

## Risks / Trade-offs

- **成本失控风险（最主要，grill 已修正缓解面口径）**：默认不限意味着一个失控的图可能烧掉任意 token / 金额。这是**有意为之**的取舍，与 #192 同口径（框架不替使用者决定花多少钱）。缓解面：①C2 结构闸仍限 run 总数（300）与节点数（200）；②单 run 预算 `subagents.budget.max_tokens` / `max_time_s` **仅在用户显式配置时**才生效（默认 `None` = 不限，`config.py:340-341`），**不是**默认兜底；③用户可随时在配置文件写回显式上限恢复旧行为。量级参考（grill 估算）：300 runs × 每 run 50 万 token ≈ 1.5 亿 token，按 opus 定价约 2000–3000 美元。「恢复/设置上限」的写法写入 spec delta，示例配置注释为可选。
- **既有测试断言默认值**：`test_workflow_budget_config.py`（4 处）、`test_workflow_budget.py`（2 处）、`test_workflow_replay.py`（1 处）都会红。风险不在改数字，而在**别把语义覆盖改丢**——尤其 `test_max_total_runs_default_matches_structural_max_runs` 的前提（D6/Q4「默认值与 C2 对齐」）在默认变 0 后不再成立，必须改写为「预算默认不限 + C2 max_runs 仍兜底」的新语义测试，而不是删掉了事。
- **回归测试的假保护风险（grill 重点标注）**：若按 tasks 2.3 字面写一条「小图在默认配置下 `completed`」，改动前后**都会通过**，等于没覆盖本 change 的核心行为。落地时必须用「真能越过旧默认」的构造 + 对照组（见 Testing Strategy）。
- **观测面信息量归零**：#196 拆出的 Web 展示 issue 应把「`limit: 0` 如何呈现」纳入，否则会出现「页面显示上限 0，用户以为没预算了」的误读。
- **文档漂移**：`asterwynd.example.yaml` 确无 budget 段（grill 核实），预期无改动；`README.md` / `README_EN.md` 不记载该默认值，无强制同步义务。

## Testing Strategy

- **单元（配置层）**：`AsterwyndConfig()` 四字段默认为 0；yaml 显式配置四字段生效；只配一个字段时其余保持 0；缺 budget 段时为 0；显式 `null` 仍 `ConfigError`；负值/非数值仍 `ConfigError`。
- **单元（账本层）**：默认构造的 `WorkflowBudget`（无 config）四维上限为 0 且 `exceeded_dimension` 恒 `None`；`dimensions()` 在默认下报 `limit: 0`。
- **调度器集成（回归，对 #196 场景）**：默认预算下，一条会累积超过旧默认 200k token 的链式图**跑完且 `status == "completed"`**、`budget.exceeded is False`。**构造口径（grill 确认，必须按此写否则是假保护）**：`_chain_spec(8)` 配 `StaticLLM(usage=Usage(50_000, 0))`——每 run 一次 LLM 调用记 50k token，8 run 累计 400k，稳过旧的 200k。**必须配对照组**：同一张图显式配 `max_total_tokens=200000` 时断言 `status == "budget_exceeded"` 且 `completed < 8`；只断言「默认配置下 completed」而不证明该图真能触发旧上限，则未来任何让 token 记账失效的重构都会让该测试静默恒真。
  - 注：runs 维度**不能**用作本回归（旧默认 300 与 C2 `spec.max_runs` 默认 300 等值，越过即走 C2 `graph_recursion_exceeded`）；wall_time 维度在单测不可达（需伪造 `started_at`），均不作为默认路径回归面。
- **调度器集成（显式上限仍生效）**：`max_total_tokens=100` 等显式配置仍触发 `budget_exceeded` + drain + 根节点终态（既有测试已覆盖，须保持绿）。
- **兼容**：C2 `max_runs` 在预算不限时仍兜底（既有 `test_workflow_budget.py` 的 Q14 用例保持绿）；`max_items=0` 的展开容量在预算不限时退化为 C2 两闸的最小值（`_remaining_expansion_capacity` 的 `budget.max_runs` 真值判定已天然处理）。
- **benchmark 记录面**：`workflow_record` 的 `budget_config` 反映新默认（0），replay 可比性断言同步。
- **全量**：`uv run pytest -q` 全绿；`npx openspec validate --all --strict` + `python3 scripts/check_openspec_artifacts.py` 通过。
