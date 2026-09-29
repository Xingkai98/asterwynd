# Grill Design: workflow 图级 recursion_limit 默认值调大（25 → 100）

关联 change：`workflow-recursion-limit-default`；执行方式：独立零记忆 subagent（`/grill` 等价流程，paseo 托管 agent `f273ea18-14d1-4ddf-af56-e279376130bc`，plan 模式只读）。

执行口径：追问者只读磁盘材料 + 逐条读代码核实 design 的事实性主张，**不写文件、不答 Open Questions**，产出的 `## Open Questions` 由主 session 停轮转达用户。

## Confirmed Decisions

- **决策**：默认值确为「四处定义点 + 一处 docstring」，无第五处；`agent/config.py` 不 import 任何 subagent 模块。**理由**：四处字面量为 `WorkflowLimitsConfig.recursion_limit`（`agent/config.py:337`）、`_parse_workflow_limits` 的 `mapping.get("recursion_limit", 25)`（`agent/config.py:1659`）、`_spec_bounds` 的 `getattr(limits, "recursion_limit", 25)`（`agent/tools/builtin/subagents.py:469`）、`DEFAULT_RECURSION_LIMIT = 25`（`agent/subagent/workflow.py:35`，含 `:230` 字段默认 / `:288` to_dict 哨兵 / `:316` parse 形参默认三个消费点）；docstring 在 `agent/subagent/workflow.py:13`。全仓（排除 tests/archive）grep `recursion_limit` 无第五处默认值字面量；工具 JSON schema 未给该字段设 `default`。**来源**：`agent/config.py:337,1659`、`agent/tools/builtin/subagents.py:469`、`agent/subagent/workflow.py:13,35,230,288,316`；`agent/config.py:12-28` 的顶层 import 仅 `code_intelligence.config` / `run_config` / `tool_permissions` / `tool_result_display` / `yaml`，**无 `agent.subagent.*`**。**影响**：design D2 清单可直接照改；D5 的「依赖方向」前提成立。

- **决策**：`scheduler.py:1974,2906` 的「默认 25」是并发容量，与 `recursion_limit` 同名不同义，不得改动。**理由**：两处注释指向 `_dispatch_capacity()`，其定义是 `manager.max_active + manager.max_queued_runs`，配置默认 `max_active=5` / `max_queued_runs=20`，顶 25。**来源**：`agent/subagent/scheduler.py:1593-1594`、`:1974`、`:2906`；`agent/config.py:364-365`。**影响**：design Non-Goals 处理正确，无需改。

- **决策**：`diagnostics.reason` 在现有实现里**确实可区分** `recursion_limit` 与 `max_routes`，Tasks 2.3 的判据可行。**理由**：两条触发路径各自硬编码 `reason`——图级步数超限写 `reason="recursion_limit"`，route 自身超 `max_routes` 写 `reason="max_routes"`；`GraphRecursionError.to_dict()` 把 `reason` 带进 `diagnostics`；既有测试已断言 `max_routes` 出口的 `reason`。**来源**：`agent/subagent/scheduler.py:959-970`（`:964`）、`:1640-1651`（`:1646`）、`:1860`（`_route_counts` 自增）、`:185-195`（`to_dict` 带 `reason`）；`tests/agent/subagent/test_scheduler.py:512`。**影响**：判据成立，无需改；但 N 标定必须修正（见 Design Corrections 第 1 条）。

- **决策**：`getattr(obj, name, <常量>)` 合法，故 D5 的「`_spec_bounds` 兜底必须留字面量」论证不成立。**理由**：`getattr` 第三参可以是模块常量；`agent/tools/builtin/subagents.py:20-25` **已经** import `agent.subagent.workflow`，该侧无新增依赖。技术上四处可收敛为**一**处。**来源**：`agent/tools/builtin/subagents.py:20-25,469`；`agent/subagent/workflow.py:18-23`（仅 stdlib import，无环）。**影响**：D5 理由 ② 必须改写（见 Design Corrections 第 2 条）；决策本身（本 change 不收敛）不变，成立的理由只有「避免 config→subagent 层间依赖」这一条。

- **决策**：spec delta 结构合法、未丢现行语义。**理由**：delta 的 Requirement 首行正文含 `SHALL`（strict validate 只读正文第一行）；三个 `#### Scenario:` 的 GIVEN/WHEN/THEN/AND 结构完整；现行 spec 的 reducer 声明句与递归上限句逐字保留。**来源**：现行 `openspec/specs/multi-agent-collaboration/spec.md:122-131`；delta `openspec/changes/workflow-recursion-limit-default/specs/multi-agent-collaboration/spec.md:7,9,16,24`。**影响**：结构无需改；delta 新增的「覆盖语义」句是否保留见 Open Question Q6。

## Design Corrections（必须修改项）

追问者标注的必须修改项，**主 session 已逐条核实并落进 design.md**（下方括号内为处置结果）：

- **high: Tasks 2.3 的 N 标定估算自相矛盾** — design 原文写「约 1.9–3 superstep/轮，`N=12`（≈23–36 superstep）落在 25 与 100 之间」，但 `12 × 1.9 = 22.8 < 25`，低端并不落在 (25,100) 内；且若实现者误按低端比值构造，对照组会得到 `reason == "max_routes"` 而非 `"recursion_limit"`，防恒真机制失效。追问者读码推演出 peer-review **每轮恰好 3 个 superstep**（`producer→reviewer→gate→producer`，每批仅 1 个就绪节点），解析可行区间 `N ∈ [9, 32]`，`N=12` 合理。证据：`agent/subagent/scheduler.py:975`（每派发一批 `_steps += 1`）、`:1568-1587`（`_ready_nodes` 数据门控）。**（已处置：design Testing Strategy 在 grill 运行期间已由主 session 独立推演改正为「3 superstep/轮」，并注明「一轮约 1.9」实为 **1.9 run/轮** 的误记；本轮据追问者的区间推导补上上界 `N ≤ ~32`。）**

- **medium: D5 理由 ② 事实错误** — 「`getattr` 兜底必须留字面量」不成立，见 Confirmed Decisions 第 4 条。**（已处置：design D5 理由 ② 改写为「避免 config → subagent 的层间依赖」，不再作为独立论据。）**

- **medium: D3 漏「显式 100」的指纹变化支，且未覆盖资产加载/重跑路径** — design 只列了「显式声明 25」一支。追问者指出：显式声明**等于新默认值 100** 的 spec，改前被序列化、改后被省略，`spec_hash` **同样变化**（方向相反、结论同）。另核实资产加载**不重算** `spec_hash`（`workflow_assets.py:213` 直接读存值），故「未声明键的资产重存仍判 unchanged」成立。**（已处置：design D3 与 proposal Impact Analysis 补「显式 100」支 + 资产加载/重跑路径说明。）**

- **low: D1「不与 `max_runs=300` 打架」是 peer-review 专属，非拓扑普适** — 67 runs 只在 peer-review（4 节点、无 foreach）成立。对 **foreach 重拓扑**，`max_runs=300` / `max_nodes=200` 会**先于** `recursion_limit=100` 触发。**（已核实并处置：`agent/subagent/scheduler.py:2133-2141` 的 foreach 展开预检确实在 `self._runs + delta > max_runs` 时抛 `reason="max_runs"`，`:2145-2150` 同形抛 `reason="max_nodes"`；design D1 的论证已收窄为「peer-review 实测拓扑下」。）**

- **low: spec delta 混入范围外的新规范句** — delta 新增「该默认值 SHALL 可被配置项 `subagents.workflow.recursion_limit` 覆盖（显式值含小于默认值的值 SHALL 精确生效）」，现行 spec 无此句。**（未单方面处置：是否保留列入 Open Question Q6 交用户拍板，见下。）**

- **low: D4 把无法离线复核的断言写成了确定事实** — 追问者无法离线核实 issue #246 正文内容。**（已处置：主 session 本会话已用 `gh api repos/Xingkai98/asterwynd/issues/246` 实测核实标题与正文，design/proposal 保留该事实但补明确来源与核查日期。）**

**追加核实（追问者未提、主 session 自查发现）**：`agent/subagent/scheduler.py:974-975` 的 `_steps += 1` 只在「本轮确有派发」时触发，且 route 节点虽 `_run_cost=0` 但 `_dispatch` 仍返回 `True`（`:1650-1667`）——这正是「3 superstep/轮」的机制来源。用该模型回算 issue #262 的表（limit 25 → 8 整轮 24 superstep + 第 9 轮 producer 后 `_steps=25` 撞顶 → **9 轮 / 17 run**）与实测逐字吻合，交叉验证推演成立。

## Open Questions

> 本节点为**停轮确认清单**，每条配本 change 真实场景的例子。用户答复由主 session 回填进 `## User Confirmation`。

- **Q1**: 四处默认值字面量是否在本 change 内收敛为单一常量？
  - **场景/例子**: 现状改一个默认值要同步改 4 处 + 1 docstring。漏改任一处，就会出现三路径分叉：`AsterwyndConfig()` 直构得 100、yaml 未写键也得 100、但 `manager.config` 链路断时 `_spec_bounds` 兜底仍是 25——**同一份「未配置」在两条路径上给出不同结论**（#196 踩过此坑）。收敛后只改 `DEFAULT_RECURSION_LIMIT = 100` 一处，其余 3 处引用它。
  - **候选答案**: **A（推荐）** 不收敛，本 change 只改数值 + 用测试锁三路径一致性（最小改动，代价是保留 4 处重复）；**B** 收敛到 1 处（消除重复，代价是新增 `agent/config.py` → `agent/subagent/workflow.py` 层间依赖，超出「只调默认值」范围）。

- **Q2**: 调研显示业界取值跨越 30–10007、处境同构的 deepseek-harness 取 256 轮，是否维持 100？
  - **场景/例子**: 同一张 peer-review 图，`max_rounds=40`。取 100：跑到约 33 轮撞 `recursion_limit`（**仍达不到 40**）；取 256 轮（≈768 superstep）：约 150 轮前先撞 `max_runs=300`（图级闸形同虚设）。现状 100 是「本仓两结构闸共存」约束下的折中。
  - **候选答案**: **A（推荐）** 维持 100；**B** 改取其它值（如 150/256），接受与 `max_runs=300` 的张力。

- **Q3**: 接受「显式写 `recursion_limit: 25`（**以及显式写 100**）的资产 `spec_hash` 一次性变化」吗？
  - **场景/例子**: 用户存过一个显式 `recursion_limit: 25` 的 peer-review 资产。改前该值=默认被省略进指纹；改后 25≠100 被序列化进指纹 → 同名资产再 `SaveWorkflowAsset` **首次判 `updated`** 并写事件日志（内容其实没变）。显式写 100 者反向变化。两者都只发生一次、方向正确，且 `RunWorkflowAsset` 重跑时显式 25 的资产仍按 25 生效（不被抬到 100）。
  - **候选答案**: **A（推荐）** 接受（最小改动、爆炸半径小）；**B** 不接受，改为「总是序列化三闸」——但会让**每个**存量资产指纹变化，代价更大。

- **Q4**: `graph_recursion_exceeded` 诊断反馈机制（`declared_max_rounds` / `rounds_actually_run` / `limit_source`）归属哪个 issue？
  - **场景/例子**: 模型在默认配置下撞了 `recursion_limit=100`，只拿到 `reason/steps/limit/current_nodes`，**看不到**「你声明的 `max_rounds` 是多少、实际跑到几轮、这个 100 是默认还是你配的」，于是无法判断该调 `max_rounds` 还是 `recursion_limit`。issue #262 正文写「归 #246」，但主 session 用 `gh api repos/Xingkai98/asterwynd/issues/246` 实测（2026-09-29）发现 **#246 标题与正文是「内置模板归一：RunPattern 融合进 Workflow DSL 入口」、0 条评论、全文无这三个标识符**；全仓 grep 亦零命中。
  - **候选答案**: **A（推荐）** 只声明「诊断反馈不属本 change」、不代 #246 认领（当前 design 写法）；**B** 由用户指定真正归属的 issue 并回填。

- **Q5**: 默认调大后是否需要**跨拓扑**回归，防止 foreach 重拓扑里 `max_runs`/`max_nodes` 先撞、`recursion_limit` 形同虚设？
  - **场景/例子**: peer-review 回归证明「100 > 25 有效」，但一张含 `max_items=20` 的 foreach 回边循环图，在 100 superstep 内会先撞 `max_runs=300`（约 15 轮），用户看到的仍是 `reason=="max_runs"` 的 `graph_recursion_exceeded`——**默认调大对该拓扑没有可观察收益**。
  - **候选答案**: **A（推荐）** 只在 peer-review 拓扑做回归，其它拓扑由既有 `max_runs`/`max_nodes` 测试覆盖（与 design Testing Strategy 一致）；**B** 补一条 foreach 拓扑断言，锁住「不同拓扑下首撞闸不同」这一已被文档承认的差异。

- **Q6**: spec delta 是否保留新增的「配置项覆盖语义」规范句？
  - **场景/例子**: delta 新增「该默认值 SHALL 可被 `subagents.workflow.recursion_limit` 覆盖（显式值含小于默认值者 SHALL 精确生效）」。该句固化的是既有行为（`_eff_limit` 的 min 钳制方向），但不属于「默认值 25→100」这一动机。保留 = 契约更完整但混入范围外内容；删除 = 严格最小变更但少一条正式保证。
  - **候选答案**: **A（推荐）** 保留（固化既有行为，便于后续 `RunWorkflowAsset` 钳制相关 change 引用）；**B** 删除，本 change 只改数值，覆盖语义留待单独 change 契约化。

## User Confirmation

待主 session 回填
