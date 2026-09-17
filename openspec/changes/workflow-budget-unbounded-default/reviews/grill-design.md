# Grill: workflow-budget-unbounded-default 设计追问

## Reviewer

- run id: grill-workflow-budget-unbounded-default-20260917
- 时间: 2026-09-17
- 对象: `openspec/changes/workflow-budget-unbounded-default/design.md` D1–D6
- 基线: C4 `workflow-budget-attribution` 已合入

## Confirmed Decisions

- **决策**: 默认值确实只有 **3 处**，design D2 + D3 的落点清单是完整且必要的，不存在第四处独立默认值。理由: 逐字段核对：dataclass 字段默认在 `agent/config.py:292-295`；yaml 解析兜底在 `agent/config.py:1533/1538/1543/1548` 的四处 `mapping.get(key, <默认>)`；`getattr` 兜底在 `agent/subagent/workflow_budget.py:66-69`。另两处疑似候选经核实**不是**默认值：`agent/tools/builtin/subagents.py:409-411` 的 `default_recursion_limit/max_nodes/max_runs` 是 C2 三闸（与预算无关），`benchmarks/workflow_replay.py:74-87` 的 `_budget_config_dict` 用 `getattr(budget, ..., None)` 记录实际配置、缺配置返回 `{}`，是观测面不是默认值。只改前两处会让「直构 `AsterwyndConfig()`」与「yaml 加载」分叉（C4 决策 7 的教训），只改前两处而不改 `getattr` 兜底会让 `manager.config is None` 的路径退回 200k。来源: grill-workflow-budget-unbounded-default-20260917

- **决策**: 「`0 = 不限`」在四个维度上**全部**是真值判定，不存在 `is None` 或 `is not None` 之类的例外写法，因此把默认值改成 0 不需要任何新分支。理由: `agent/subagent/workflow_budget.py:112-118` 的 `exceeded_dimension` 四行依次是 `if self.max_tokens and ...` / `if self.max_cost_usd and ...` / `if self.max_runs and ...` / `if self.max_wall_time_s and ...`；`reserve_runs` 的判定在 `:128` 同款真值写法；`_remaining_expansion_capacity` 在 `agent/subagent/scheduler.py:2093` 也是 `if budget is not None and budget.max_runs:`。唯一可能读到 `None` 的是 config 链路缺失时 `getattr` 的兜底值，已由 D3 覆盖。设计文档里 `workflow_budget.py:110-120` / `:127-129` 的行号有轻微偏移（实际 112-118 / 128），机制结论正确。来源: grill-workflow-budget-unbounded-default-20260917

- **决策**: `_remaining_expansion_capacity`（`agent/subagent/scheduler.py:2082-2097`）在 `budget.max_runs` 默认变 0 后行为正确，`min(limits)` 不会取到意外值，也不会空列表。理由: `budget.max_runs=0` 为假值时 `limits` 只跳过 C4 那一项，仍会 append `spec.max_runs - self._runs` 与 `spec.max_nodes - self._expanded_nodes`；而 spec 侧这两个字段经 `agent/subagent/workflow.py:438-441` 的 `_positive_int`（`value < 1` 直接抛错）保证 ≥1，所以 `limits` 恒有 ≥2 项，`min(limits) if limits else 0` 的 `else 0` 分支今天是**不可达死代码**。默认配置下截断值与改动前逐值相同（旧默认 `max_total_runs=300` 与 spec 默认 `max_runs=300` 相等，min 本来也取到同一个值）；显式配置（如 `max_total_runs=5`）路径完全不受影响。来源: grill-workflow-budget-unbounded-default-20260917

- **决策**: 配置层对**字段级** `null` / 负值 / 非数值的拒绝路径与默认值无关，改默认值不会让任何既有校验失效。理由: `_parse_non_negative_int`（`agent/config.py:1663-1680`）与 `_parse_non_negative_float`（`agent/config.py:1682-1706`）只作用于「显式出现的键值」；用户写 null 时 `mapping.get(key, <默认>)` 返回的是 `None`（键存在、值为 None）而不是默认值，所以照旧抛 `ConfigError`。实测确认：`max_total_tokens: null` → `ConfigError: ...must be a non-negative integer`；四条参数化用例 `tests/agent/subagent/test_workflow_budget_config.py:136-151` 改默认值后仍绿。**但整段 null 是另一回事，见 Open Question Q2。** 来源: grill-workflow-budget-unbounded-default-20260917

- **决策**: D4 关于 CLI 现状的事实描述准确——`agent/main.py` 今天确实**没有**任何 `--workflow-budget-*` 入参，`ConfigOverrides` 也只有 3 个字段。理由: 全仓 `grep "workflow-budget" agent/` 零命中；`agent/config.py:429-433` 的 `ConfigOverrides` 仅含 `default_mode` / `benchmark_parallel` / `benchmark_timeout_seconds`；既有 `--budget-cap`（`agent/main.py:736-737`）是**单轮成本上限**（按 run 目录汇总 `_round_cost`，`agent/main.py:965-984`），与 workflow 四维预算是两个概念，design 说的「并存易混淆」属实。备选 A/B 的代价估计（新 `ConfigOverrides` 字段 + 4 个 Typer option + `_apply_cli_overrides` 分支 + 测试）与代码结构相符。是否纳入仍待用户拍板（Q1）。来源: grill-workflow-budget-unbounded-default-20260917

- **决策**: 「四维都越过旧默认」的回归测试**不成立**，tasks 2.3 的验收口径应收敛为「token 维度必须真越过 200k + 加对照组」。（1）runs 维度：旧默认 300 与 C2 `spec.max_runs` 默认 300 等值，预算关掉后 run 数上限仍是 300，越过即走 `graph_recursion_exceeded`（`scheduler.py:1232-1242`），永远到不了「预算不限所以跑完」；（2）wall_time 维度：1800 s 在单测里不可达，现有测试靠伪造 `started_at` 绕过（`tests/agent/subagent/test_workflow_budget.py:378`），不能当默认路径的回归；（3）cost 维度：可构造但要挑高价模型，价值低于 token。**推荐的具体构造**：`_chain_spec(8)`（`tests/agent/subagent/test_workflow_budget.py:173`）配 `StaticLLM(usage=Usage(50_000, 0))`——每 run 一次 LLM 调用、记 50k token，8 run 累计 400k，稳过旧的 200k。（4）**必须配对照组否则是假保护**：同一张图显式配 `max_total_tokens=200000` 时必须 `status == "budget_exceeded"` 且 `completed < 8`；只断言「默认配置下 completed」而不证明这张图真能触发旧上限，未来任何让 token 记账失效的重构都会让该测试静默变成恒真。来源: grill-workflow-budget-unbounded-default-20260917

- **决策**: 默认配置下 runs 维度的**失败出口会发生改变**（design 未提及），需在实现与文档中自觉，不必改设计。理由: C4 的 runs 检查刻意先于 C2（`scheduler.py:1227-1242` 派发点、`:1468-1475` foreach 展开点），默认 `max_total_runs=0` 后 C4 不再拦截，run 数触顶改由 C2 抛 `GraphRecursionError` → `_cancel_all_in_flight()` + `_mark_graph_recursion_exceeded`（`scheduler.py:669-673`），而不是 `budget_exceeded` + drain（`:676-679`）。两者都仍可恢复（普通 cancel 的 `CancelledError` handler 同样写 checkpoint，`agent/subagent/manager.py:1109-1110`），但节点终态、run 终态与 envelope `status` 都不同。C4 Q14 已定「C2 仍是结构闸、`max_total_runs=0` 不解除它」，spec delta 的 Scenario「预算不限不解除 C2 结构闸」（`specs/multi-agent-collaboration/spec.md:38-43`）已覆盖该语义，方向正确，只是要把「出口由 drain 变 cancel」记进影响面。来源: grill-workflow-budget-unbounded-default-20260917

- **决策**: 部分配置的语义（写一个维度 = 其余三维变 0/不限）是 #196 口径的直读结果，实现上不需要特判，但副作用要写进文档。理由: `_parse_workflow_budget` 逐字段 `mapping.get` + 默认 0 天然产生这个行为，与 spec delta「只有显式配置才设上限」一致；实现侧零成本。事实后果是：从旧的「默认是一组相互校准的安全值」变成「逐维 opt-in」——用户只写 `max_total_tokens: 200000` 就同时失去了 cost / runs / wall_time 三道闸。建议在 spec delta 或示例配置里明写一句，避免用户以为「我配了 token 上限就还有 cost 兜底」。来源: grill-workflow-budget-unbounded-default-20260917

- **决策**: 文档影响核对结论——`asterwynd.example.yaml` 确无改动，`README.md` / `README_EN.md` 也**不需要**同步；真正带旧默认值的是 spec 与 backlog。理由: `asterwynd.example.yaml`（100 行）里 `subagents` / `workflow` / `budget` 三个关键词零命中，design 的「预期无改动」属实；`README.md` / `README_EN.md` 搜 `max_total` / `workflow budget` 零命中，从不记载该默认值，因此不存在「必须同步 README」的义务。带旧默认值的是 `openspec/specs/multi-agent-collaboration/spec.md:190`（spec delta 已覆盖）与 `docs/openspec-change-backlog.md:99`、`:152`（按 backlog 规则在收尾更新）。`docs/interview-bullets/walkthrough.md:880` 的「预算默认关闭」说的是**单 run** 的 `subagents.budget.*`，不是 workflow 预算，不受影响。据此建议把 design 的 Risk 里「需要在 README / spec 明说『恢复默认上限』的写法」收敛为「写在 spec delta + 在 `asterwynd.example.yaml` 加一段注释示例（可选）」，因为 README 从未记载该能力，凭空加一段属于扩面。来源: grill-workflow-budget-unbounded-default-20260917

- **决策**: 既有测试红名单核对属实，另有一处「不会红但口径已过期」的测试字面量建议顺手对齐。理由: config 侧确为 4 个测试（`test_budget_defaults_match_documented_values`、`test_max_total_runs_default_matches_structural_max_runs`、`test_partial_budget_keeps_other_defaults`、`test_missing_budget_section_uses_defaults`），budget 侧确为 2 个（`test_defaults_come_from_config`、`test_dimensions_snapshot_shape`），replay 侧 1 个（`tests/benchmark/test_workflow_replay.py:170` 的 `max_total_cost_usd == 5.0`）——design 的「4 / 2 / 1」精确。额外发现：`tests/benchmark/test_workflow_modes.py:181` 的合成 record 字面量 `"budget_config": {"max_total_runs": 300}` 不参与任何断言（`compare_record_and_replay` 只硬断言 `spec_hash` 与 `OBSERVED_FIELDS = node_count/run_count/status`，见 `benchmarks/workflow_e2e.py:46-92`），改默认值后仍绿，但它写进记录的口径会与新实现不一致，建议同 PR 内顺手改成 0（非门禁要求）。来源: grill-workflow-budget-unbounded-default-20260917

## Open Questions

- **Q1**: 本 change 是否纳入 CLI 入参 `--workflow-budget-tokens / -cost-usd / -runs / -wall-time-s`？（design D4 明标「待 grill 停轮确认」，是 #196 的待定项之二）
  **场景**: 用户想「默认不限，但批量重放时临时上一道防烧钱闸」。**不改 CLI（推荐）**：他在 `asterwynd.yaml` 里写 `subagents.workflow.budget.max_total_cost_usd: 20` 再跑 `uv run asterwynd benchmark benchmarks/tasks --agent asterwynd --source-repo .`——配置文件可版本化、可随任务分支走，代价是要改文件或临时建一份配置。**备选 A（benchmark-only）**：同一条命令直接加 `--workflow-budget-cost-usd 20`，不动仓库文件，代价是新增 4 个 Typer option + `ConfigOverrides` 字段 + `_apply_cli_overrides` 分支 + 测试，且与既有 `--budget-cap 20`（单轮成本上限，另一个概念）并存时用户很难分辨「这两个 20 有什么区别」。**备选 B（全命令）**：`run` / `interactive` / `web` / `benchmark` 全加，公共 CLI 面最大。**我的推荐：不改 CLI**——design 的理由成立：`--max-iterations` 先例的特殊性在于 AgentLoop 迭代数**当时没有配置文件落点**，而 workflow 预算本来就是配置驱动的，CLI 只是便利层；默认改不限后 #196 的原始痛点（体检被腰斩）已消除，恢复上限的通道已可用。若你希望 benchmark 场景能一行命令设闸，选备选 A；若希望与 `--max-iterations` 完全对齐，选备选 B。

- **Q2**: 整段 `budget: null`（以及 `subagents.workflow: null`、`subagents: null`）要不要判为配置错误？今天它是**静默等同于「用默认值」**，默认值改成 0 之后这个写法就静默变成「四维全部不限」。
  **场景**: 用户在 `asterwynd.yaml` 里先写了个空段准备稍后填：
  ```yaml
  subagents:
    workflow:
      budget:          # 值为 null
  ```
  实测今天：`load_config` 成功，`budget` 取到 `200000 / 5.0 / 300 / 1800`（`_expect_mapping` 对 `None` 返回 `{}`，`agent/config.py:1614-1619`，随即逐字段落回默认值）。本 change 合入后同一份配置仍然 `load_config` 成功，但四维上限全部变成 0 —— 用户以为「我没配 = 用默认」，实际拿到的是「完全不设闸」，且没有任何报错或警告。字段级 null 是明确拒绝的（`max_total_tokens: null` → `ConfigError`），段落级却是静默放行，两者口径不一致。**选项 A（推荐，收紧）**：把 `budget`/`workflow`/`subagents` 三处的段落级 `null` 也判为 `ConfigError`，与字段级口径统一——代价约 3 行改动 + 3 个参数化测试，会让「今天能加载、明天报错」的极端写法变成硬错误。**选项 B（保持现状）**：只在 spec/文档写明「整段 null 视为未配置 = 不限」，零改动，但保留了这条静默关闸的缝。**我的推荐：选 A**——本 change 把「缺配置」的后果从「有闸」变成「无闸」，正是收紧这条缝的时机；若你更看重与 C4 既有行为的兼容性，选 B。

## User Confirmation

- **Q1**（CLI 入参是否纳入本 change）: 用户答复：不改 CLI——只通过配置文件的 `subagents.workflow.budget.*` 设上限，本 change 不加 `--workflow-budget-*` 系列入参；默认改不限后原始痛点（体检被腰斩）已消除，恢复上限的通道已由配置提供。；确认时间: 2026-09-17
- **Q2**（整段 `budget: null` 是否收紧为配置错误）: 用户答复：收紧为 ConfigError。用户原则：不写这个字段就是没有上限，写了字段且有值就算设了上限，写了字段又不给值（null）不合理，应该报错。落实范围：`subagents` → `subagents.workflow` → `subagents.workflow.budget` 三级段落级显式 null 一律 ConfigError，与既有字段级 null 拒绝口径统一。；确认时间: 2026-09-17

## 风险

- **默认配置下 workflow 层不再有任何 token 上限，design 的缓解面②是空头承诺。** `agent/subagent/budget.py` 的单 run `max_tokens` 默认是 `None`（`agent/config.py:340-341` 的 `default_max_tokens: int | None = None`，未配置则不注入 BudgetHook），所以 design Risks 里写的「单 run 预算 `subagents.budget.max_tokens` / `max_time_s` 仍在（超限杀 run）」只在用户**显式配过**时成立；默认状态下真正的兜底只剩 C2 的 `max_runs=300` / `max_nodes=200`，而这两者只管数量、不管每个 run 烧多少 token——单个 run 的迭代数也默认无上限（`agent/loop.py:131` `max_iterations: int | None = None`）。量级估算：300 runs × 每 run 50 万 token ≈ 1.5 亿 token，按 `claude-opus-4`（`agent/cost_tracker.py:17`，15 / 75 USD per 1M）约 2000–3000 美元，按 `claude-fable-5` 也有同量级。这是 #196 明确要的取舍（框架不替用户决定花多少钱），不建议改方向，但 design 的 Risks 段必须把②改成条件句（「仅在用户显式配置了单 run 预算时生效」），否则读者会误以为默认仍有 per-run 兜底。

- **「默认不限」在 run 数维度上是名义上的**：真正的天花板仍是 C2 的 `max_runs=300` / `max_nodes=200`，而触顶后的出口从「drain + `budget_exceeded`」变成「立即取消在跑 run + `graph_recursion_exceeded`」。对 #196 的动机场景（12 文件 foreach ≈ 12 runs）无影响，但对「真想要无限跑」的用户，体验可能比改动前更差（不是优雅收敛而是硬取消）。建议在 spec delta 或文档里显式写「要突破 300 runs / 200 nodes 必须显式调大 `subagents.workflow.max_runs` / `max_nodes`（或 spec 内的同名字段）」，把 escalation 路径讲清楚。

- **`_remaining_expansion_capacity` 的 `else 0` 分支是一条埋着的雷，本 change 不触发但值得记一笔。** 该函数（`scheduler.py:2082-2097`）在三个候选上限**全部**为 0/缺失时返回 0，调用方是 `return items[: self._remaining_expansion_capacity()]`（`:2050`），`items[:0]` 是**空集**而不是「不限」——若将来有人把「0 = 不限」推广到 C2 三闸，`max_items=0` 的 foreach 会静默展开成 0 项（图照常 `completed`、结果为空），是个很难查的静默错误。今天不可达（`_positive_int` 保证 spec 侧 ≥1，见 `workflow.py:438-441`），本 change 也不改变该不变式，但 D5 里「若无上限的预算同时解除结构闸，`max_items=0` 的 foreach 将失去一切 run 数上限」这句推断与代码实际行为相反（失去上限的结果是展开成 0 项而非无限跑），建议顺手把 D5 的这句论证改成「会退化成静默空展开」。

- **观测面信息量归零**：D6 决定 envelope 继续用 `limit: 0` 表达不限、不加 `unlimited` 字段。默认配置下这意味着每个图的 `budget.dimensions[*].limit` 恒为 0、`exceeded` 恒为 false，父 agent 与 Web 页面看到的是一排恒定的 0，且**无法区分「未配置」与「显式设 0」**。对一个默认行为就是「不限」的系统，这个字段基本退化为常量。这不影响功能，但 #196 拆出去的「Web 展示口径」那个 issue 应把「limit=0 如何呈现」一并纳入，否则会出现「页面显示上限 0，用户以为是没预算了」的误读。

- **回归测试的假保护风险**（已在 Confirmed Decisions 第 6 条给出构造与对照组要求，此处只标注为风险项）：如果实现者按 tasks 2.3 的字面写一条「小图在默认配置下 `completed`」的测试，它在改动前后**都会通过**，等于没有覆盖本 change 的核心行为。落地时必须同时断言「同一张图 + 显式 200k 上限 → `budget_exceeded`」作为对照。
