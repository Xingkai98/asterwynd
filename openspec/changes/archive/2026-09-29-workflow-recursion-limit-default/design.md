# Design: workflow 图级 recursion_limit 默认值调大（25 → 100）

## Context

C2 `workflow-dsl-scheduler`（#181）引入图级 `recursion_limit`，语义是**图级 superstep 数**（一次调度循环 = 就绪一批 → 派发 → 等一批完成 算 1 步），默认 **25**，超限抛 `GraphRecursionError` → envelope `status="graph_recursion_exceeded"` + `diagnostics`（C2 design D6 / grill Q5、Q8）。默认值写在 current spec `openspec/specs/multi-agent-collaboration/spec.md:124`。

实现落点（**四处默认值定义点**，加一处 docstring）：

- `agent/config.py:337` — `WorkflowLimitsConfig.recursion_limit: int = 25`（frozen dataclass 字段默认）。
- `agent/config.py:1659` — `_parse_workflow_limits` 的 `mapping.get("recursion_limit", 25)`（yaml 加载路径）。
- `agent/tools/builtin/subagents.py:469` — `_spec_bounds` 的 `getattr(limits, "recursion_limit", 25)`（`manager.config` 链路缺失时的兜底）。
- `agent/subagent/workflow.py:35` — `DEFAULT_RECURSION_LIMIT = 25`，被三处消费：`WorkflowSpec.recursion_limit` 字段默认（`:230`）、`parse_workflow_spec` 形参默认（`:316`）、`to_dict()` 的「等于默认值则省略」哨兵（`:288`）。
- `agent/subagent/workflow.py:13` — 模块 docstring「三闸默认值（Q5）：`recursion_limit=25` / `max_nodes=200` / `max_runs=300`」。

**#196 的教训（本 change 必须同样处理）**：`agent/config.py` 是逐字段 `mapping.get(...)` 构造（不是 `**mapping` 透传），只改 dataclass 默认值**不会**让 yaml 生效；只改 yaml 解析默认值则 `AsterwyndConfig()` 直构路径分叉。两处必须同时改，`_spec_bounds` 的 getattr 兜底同理。#196 的 grill 决策 1 已经把「默认值到底有几处」当作单独的确认项——本 change 沿用同一纪律，并额外核实了「无第五处」（见 Non-Goals）。

**#196 之后的新语境**：四维成本预算默认全 `0`（不限），`recursion_limit` 与 `max_runs` 成为默认配置下仅剩的结构后盾。实测（issue #262，peer-review 拓扑）默认 25 只够约 9 轮，而 `max_rounds` 因图级闸先触发而失效。

**换算比必须区分两个量纲（尺寸口径，易混，实现期取 N 时勿混用）**。同一组实测数据（peer-review 拓扑）可读出两个比值，二者**都**要记住：

| `recursion_limit` | run 总数 | producer 轮数 | superstep / 轮 | run / 轮 |
|---|---|---|---|---|
| 25（当前默认） | 17 | 9 | 2.78 | 1.89 |
| 50 | 34 | 17 | 2.94 | 1.97 |
| 100（目标） | 67 | 34 | 2.94 | 1.97 |
| 300 | 200 | 100 | **3.00** | **2.00** |

- **`recursion_limit ≈ 3 × 轮数`** 说的是 **superstep / 轮**，收敛到 **3.00**——这是图级闸的计量口径（一轮 = producer + reviewer + gate 各派发一次 = 3 superstep，见 Testing Strategy 的读码推演）。
- **`≈ 1.9 run / 轮`** 说的是 **run / 轮**，收敛到 **2.00**——这是成本/记账口径（一轮 = producer + reviewer 两个真实 run，route 是 `_run_cost=0` 的纯逻辑节点）。

取回归测试的 `N` 时**必须按 superstep/轮的比值（3）反推**：按 run/轮（≈2）反推会把 `N` 取小，导致对照组不触发旧默认、防恒真机制失效（见 Testing Strategy 与 `reviews/grill-design.md` 的 high 级 Design Correction）。

## Goals / Non-Goals

**Goals**

- 图级 `recursion_limit` 默认值由 `25` 改为 `100`，四处定义点 + docstring 同步，直构 config / yaml 加载 / getattr 兜底三条路径不给出一致以外的结论。
- 让 `max_rounds`（落为 route 的 `max_routes`）在默认配置下**恢复有效**——这是本 change 对用户最直接的可观察收益，也是回归测试的判据（见 Testing Strategy）。
- 保留全部既有机制：superstep 计数口径、`GraphRecursionError` 构造与 `graph_recursion_exceeded` 终态、envelope schema、`_eff_limit` 的 min 钳制方向、`max_nodes` / `max_runs` 默认值与语义。

**Non-Goals**

- **不引入诊断/反馈机制**。`graph_recursion_exceeded` 诊断增补 `declared_max_rounds` / `rounds_actually_run` / `limit_source` 一类字段**不属本 change**（边界见 D4）。
- 不改 `max_nodes`（200）/ `max_runs`（300）默认值。
- 不改 `max_routes`（route 节点自身预算，`agent/subagent/patterns.py:211`）语义——它仍先于图级闸触发。
- 不改 `scheduler.py:1974,2906` 提到的「默认 25」——那是 `max_active + max_queued_runs = 5 + 20` 的**并发容量**，与 `recursion_limit` 同名不同义。
- 不改 CLI（无 `--workflow-recursion-limit` 入参；`ConfigOverrides` 仅 3 字段），与 #196 D4 同口径：默认值调整通过配置文件覆盖即可。
- 不改 spec 中 `web-ui` 侧把 `recursion_limit` 当**闸门名**列举的表述（`openspec/specs/web-ui/spec.md:813` 只提名字，不含默认值）。

## Decisions

### D1 — 取值 100（用户已拍板），但要如实记录「这是一个偏保守的有依据值，不是业界共识值」

- **决策**：默认值取 **100**（约 33 轮）。
- **理由**：覆盖绝大多数迭代式任务的合理轮数；run 总数 67 **远低于** `max_runs=300`，两个结构闸不打架；仍是**有界**的，符合「默认给合理边界」。
- **调研揭示的张力（必须如实记录，不得粉饰）**：RQ1–RQ4 的结论是 100 **不是**业界收敛值——
  - 本仓 `recursion_limit` 语义的直接来源 LangGraph，已把同口径默认值提到 **10007**（`_internal/_config.py:32`，commit `a5827c5c`：*"25 is pretty unreasonable for most applications"*）。LangGraph 那个值实际上接近「不限」。
  - 与「成本预算不限、只剩结构闸」处境**逐字同构**的 `deepseek-harness` Ralph workflow，默认 **256 轮**。
  - `opencode`（`steps=Infinity`）与 `kimi-code`（`max_steps_per_turn` 默认 unset=不限）选择**默认不限**。
  - 反向样本 `zcode` 取更紧的值，但其计数单位是各自 loop 的轮数（`reactLoop.maxRounds=30`、subagent `maxTurns=4`），与本仓图级 superstep 不同量纲。
- **100 的正当性来自本仓内部约束**：它是唯一同时满足「显著高于现状 25」「与 `max_runs=300` 不打架」的候选；取 LangGraph 式的 10007 会让 `recursion_limit` 事实上失去后盾意义，取 deepseek-harness 式的 256 轮折算约 768 superstep 后又会**先撞 `max_runs=300`**，两个结构闸语义打架（这正是 issue #262 要避免的）。因此 100 是在「本仓两个结构闸必须共存」这条硬约束下的合理选择。
- **该论证的适用范围（grill 收窄）**：「不打架」是 **peer-review 实测拓扑**（4 节点、无 foreach）的结论——该拓扑下 `recursion_limit=100` 对应约 67 run，距 `max_runs=300` 有余量。**对 foreach 重的拓扑不成立**：`max_items=20` 的 foreach 回边循环约 15 轮即把 300 run 烧穿，而 100 superstep 允许多得多，此时**首撞闸是 `max_runs` / `max_nodes`**（`scheduler.py:2133-2141` 抛 `reason="max_runs"`、`:2145-2150` 抛 `reason="max_nodes"`），`recursion_limit` 对该拓扑形同虚设。这不否定 100，但论证不能写成拓扑无关的一般陈述。
- **备选**：`50`（约 17 轮，仍偏紧，issue #262 已排除）；`256`/`300`（与 `max_runs` 打架）；`0 = 不限`（会与「结构闸是有界后盾」的定位冲突，且 C2 的 `_positive_int` 拒绝 0）。
- **✅ 已确认（2026-09-29，Q2）**：**维持 100**。用户答复实质：100 是「显著改善现状（9 → 33 轮）」与「远离 `max_runs=300` 冲突」的交点，且可被配置覆盖、日后偏紧再调成本低。**须如实写明（用户明确要求）**：调研**没有**支持 100 是业界共识值——LangGraph 取 10007（≈不限）、deepseek-harness 取 256 轮、opencode 与 kimi-code 默认不限；100 的正当性来自**本仓内部约束**（与 `max_runs=300` 共存），**非外部先例**。

### D2 — 四处定义点同步改 100 + docstring 同步

- **决策**：D 节 Context 列出的四处字面量与一处 docstring 一并改为 100。
- **理由**：#196 的既有教训（「只给 dataclass 默认值不会让 yaml 生效」，两处默认值必须一致否则直构与 yaml 加载分叉）在本 change 同样成立；`_spec_bounds` 的 getattr 兜底服务「`manager.config` 缺失」路径，兜底值不一致会让同一份「未配置」在两条路径上给出不同结论。
- **`to_dict()` 哨兵自动跟随**：`DEFAULT_RECURSION_LIMIT` 同时是 `to_dict()` 的省略哨兵，改常量即自动跟随，无需单独改；其副作用见 D3。

### D3 — 序列化哨兵副作用：接受「显式 25 的资产 spec_hash 一次性变化」

- **事实**：`WorkflowSpec.to_dict()`（`workflow.py:288`）在字段值**等于** `DEFAULT_RECURSION_LIMIT` 时省略 `recursion_limit` 键；`spec_hash` 由 `to_dict()` 的 canonical JSON 计算（`workflow.py:300`）。三类 spec 的影响面（grill 已逐类实测）：
  - 未声明 `recursion_limit` 的 spec：键在改前改后**都**被省略 → `spec_hash` 不变。
  - **显式**声明 `recursion_limit: 25` 的 spec：改前等于默认被省略，改后 25 ≠ 100 被序列化 → `spec_hash` **变化**。
  - **显式**声明 `recursion_limit: 100`（即**新**默认值）的 spec：改前 100 ≠ 25 被序列化，改后等于默认被省略 → `spec_hash` **同样变化**（方向相反、结论同）。初稿只列了「显式 25」一支，grill 补上此支。
  - **资产加载路径不受影响**：`WorkflowAsset.spec_hash` 是**保存时刻冻结**的字段，加载时 `asset_from_dict` 直接读 `payload["spec_hash"]`、**不重算**（`workflow_assets.py:213`）；`RunWorkflowAsset` 重跑走 `_apply_asset_overrides` → `parse_spec_for_manager` 重解析（`subagents.py:1209-1215`），故未声明键的存量资产**按新默认 100 生效**（正是本 change 的收益），显式 25 的资产仍按 25 生效、且 `limit_ceiling` 现为 100（钳制方向不变）。
- **决策**：**接受**该一次性变化，不改哨兵设计（不加版本前缀、不改哈希口径）。
- **理由**：①变化方向是**正确**的——25 从此是一个有别于默认值的有意义取值，把它序列化进指纹是对的；②爆炸半径小——绝大多数 spec 不写该字段（模型生成的 spec 通常省略、模板编译产出的 spec 也不写）；③改哨兵（例如引入 `schema_version` 参与哈希或统一「总是序列化」）会**放大**爆炸半径到**所有**资产，与本 change「只调默认值」的最小化目标相悖。唯一后果是：显式写过 25 的同名资产再保存时，`save()` 的 `unchanged` 判据（`workflow_assets.py:381`）首次判为 `updated`。
- **备选（未采纳）**：把 `to_dict()` 改为「总是序列化三闸」——更可预测，但会让**每个**存量资产指纹变化，代价远大于收益；改为「省略哨兵改用 `None` 表示未声明」——需要 `WorkflowSpec` 增加三态语义，超出本 change 范围。
- **✅ 已确认（2026-09-29，Q3）**：**接受**该一次性指纹变化，不改哨兵设计。用户答复实质：接受「显式 25/100 的资产 `spec_hash` 一次性变化」；不做「总是序列化三闸」的替代（否则每个存量资产指纹都会变）。

### D4 — 与诊断/反馈机制的边界：本 change 不含，且不代 #246 认领

- **决策**：本 change 的范围**严格限定为默认数值调整**。`graph_recursion_exceeded` 诊断增补 `declared_max_rounds` / `rounds_actually_run` / `limit_source` 一类「让模型知道该调什么」的反馈**不在本 change 范围**。
- **理由**：两者是互补的两件事——本 change 让闸更宽，反馈机制让模型能据此调整；issue #262 正文也确认过顺序上无依赖（本 change 先合入或后合入，反馈机制都成立）。
- **诊断反馈的归属（已澄清，2026-09-29）**：issue #262 正文写「#246 提供反馈机制」，本 change 初查发现 **issue #246 正文**（`gh api repos/Xingkai98/asterwynd/issues/246`）标题为「内置模板归一：RunPattern 融合进 Workflow DSL 入口」、0 条评论、正文无 `declared_max_rounds` / `rounds_actually_run` / `limit_source` 字样。**用户主 session 核验后澄清：归属确实是 #246，但机制写在 #246 的 change 文档而非 issue 正文**——`declared_max_rounds` / `rounds_actually_run` / `limit_source` 出现在 change **`workflow-builtin-templates`** 的 `design.md` **D7**（5 处，含 `GraphRecursionError.to_dict()` 增字段的 Requirement 与 `asset_source` 取值通道），并正在随该 change 实现。**本 change 的处理**：只声明「诊断反馈不属本 change」，**交叉引用 change-id `workflow-builtin-templates`**（不引 issue #246 正文，避免读者按正文找不到该机制）。两侧无顺序依赖：本 change 先合入或 `workflow-builtin-templates` 先合入，反馈机制与默认值调整都各自成立。
- **备选**：在本 change 里顺手加诊断字段——违反「默认值调整单独立 change」的用户决策（issue #262「与其他 change 的关系」节），且会让本 change 从「改四个字面量」膨胀成行为变更，收益与风险都不划算。

### D5 — 不把四处字面量收敛为单一常量（本 change 内），但用测试锁一致性

- **决策**：本 change **只改数值**，不重构默认值的来源结构（即不让 `agent/config.py` import `agent/subagent/workflow.py` 的 `DEFAULT_RECURSION_LIMIT`）。
- **理由**：①**依赖方向**：`agent/config.py` 目前不 import 任何 subagent 模块（已核实：`agent/config.py:12-28` 的顶层 import 无 `agent.subagent.*`），新增 config → subagent 的依赖虽无环（`workflow.py:18-23` 只 import stdlib），但会让配置层依赖运行时层，属于架构方向变更，与本 change 的最小化目标不符；②**真正防腐的是测试**：`test_workflow_tools.py` 断言 `AsterwyndConfig()` 的默认值、yaml 加载路径与 `_spec_bounds` 兜底的一致性，比模块间 import 更能锁住「三路径同结论」这条不变式。
- **grill 更正（须记录，避免后续读者被误导）**：本节初稿曾写「收敛只能把 3 处变 2 处，因为 `_spec_bounds` 的 `getattr` 兜底必须留字面量」——**该论据错误**。`getattr(obj, name, <常量>)` 的第三参可以是模块常量，且 `agent/tools/builtin/subagents.py:20-25` **已经** import `agent.subagent.workflow`，该侧无新增依赖；技术上四处可收敛为**一**处。因此 D5 的决策只由理由 ① 支撑，不再以「不能消灭重复」为据。收敛仍属有价值的 refactor 债务，应单独立项。
- **备选（未来可另立 change）**：模块级单一常量（如把三闸默认值提升到独立的、无依赖的常量模块，config 与 subagent 双向可引）。这是有价值的技术债，但属于 refactor 范畴，应单独立项，不混进默认值调整。
- **✅ 已确认（2026-09-29，Q1）**：**方案 A——不收敛**。用户答复实质：接受保留 4 处重复，不为「只调默认值」这一个目标引入 `agent/config.py` → `agent/subagent/workflow.py` 层间依赖；一致性由测试保证（Tasks 2.2）。

## Pre-Implementation Review

**状态**：设计追问（独立零记忆 subagent，`/grill` 等价流程）在本节记录；产物为 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条 + `## Open Questions` + `## User Confirmation`）。

**审阅对象**：本 design 的 D1–D5 与 `## Open Questions` Q1–Q4。重点复核项：

1. **四处定义点是否真的是四处、且无第五处**——尤其 `scheduler.py:1974,2906` 的「默认 25」是否确为并发容量 `max_active + max_queued_runs`（非 `recursion_limit`），以及 `agent/config.py` 是否真的不 import subagent 模块（这决定 D5 的「不收敛」取舍是否成立）。
2. **回归测试的构造是否非恒真**——Tasks 2.3 的 `N` 标定与对照组是否真能把「旧默认撞顶 / 新默认不撞顶」区分开；`diagnostics.reason` 判据（`recursion_limit` vs `max_routes`）是否在现有实现里确实可区分。
3. **D1 的取值张力**——调研显示业界取值跨越 30–10007，100 的正当性来自「不与 `max_runs=300` 打架」这条本仓内部约束；该论证是否成立、是否应改取其它值。
4. **D3 的 `spec_hash` 副作用**——`to_dict()` 哨兵导致的「显式 25 资产指纹一次性变化」是否被完整识别，接受该代价是否合理。
5. **D4 的边界与事实核实**——「诊断反馈不属本 change、且不代 #246 认领」的论证是否成立；#246 实际内容与 issue #262 正文不符这一发现是否属实。

**Grill 已完成**（独立零记忆 subagent `f273ea18-14d1-4ddf-af56-e279376130bc`，plan 模式只读；完整记录见 `reviews/grill-design.md`）。产出 **5 条 Confirmed Decisions + 6 条 Design Corrections + 6 条 Open Questions**。读代码可自行收敛的结论（已整合进本 design）：

1. 默认值确为**四处定义点 + 一处 docstring，无第五处**；`agent/config.py:12-28` 确实不 import 任何 subagent 模块（D2/D5 前提成立）。
2. `scheduler.py:1974,2906` 的「默认 25」确为并发容量 `max_active + max_queued_runs`（`scheduler.py:1593-1594`），不得改动。
3. `diagnostics.reason` 在现有实现里确实可区分 `recursion_limit`（`scheduler.py:964`）与 `max_routes`（`:1646`），Tasks 2.3 的判据可行。
4. `WorkflowAsset.spec_hash` 保存时冻结、加载不重算（`workflow_assets.py:213`），故「未声明键的资产指纹不变」成立。
5. spec delta 结构合法、未丢现行语义（首行含 `SHALL`、三个 Scenario 完整、reducer 句逐字保留）。

**已落实的必须修改项（Design Corrections）**：

- **high** — Tasks 2.3 的 N 标定估算「1.9–3 superstep/轮」自相矛盾（`12×1.9 < 25`，按低端取 N 会让对照组失效）。已改正为解析推导「**3 superstep/轮**，`N ∈ [9, 32]`，取 `N=12`」，并注明「1.9」实为 run/轮。同结论已由主 session 用「回算 issue #262 表格得 9 轮/17 run 逐字吻合」交叉验证。
- **medium** — D5 理由 ② 事实错误（`getattr` 兜底可用常量，技术上可收敛为 1 处）。已改写（见 D5 的 grill 更正段）。
- **medium** — D3 漏「显式等于**新**默认值 100」的指纹变化支，且未覆盖资产加载/重跑路径。已补（见 D3）。
- **low** — D1「不与 `max_runs=300` 打架」是 peer-review 专属、非拓扑普适。已收窄（见 D1 适用范围段，并核实 `scheduler.py:2133-2150` 的 foreach 预检确实先抛 `max_runs`/`max_nodes`）。
- **low** — D4 把「#246 内容不符」写成无来源硬事实。已补来源（`gh api .../issues/246`）与核查日期（2026-09-29）。
- **low** — spec delta 混入范围外的新规范句（「配置项覆盖语义」）是否保留。**（已处置：Q6 ✅ **保留**（2026-09-29）——该句固化既有 `_eff_limit` min 钳制方向，便于后续 `RunWorkflowAsset` 钳制相关 change 引用。）**

**停轮确认结果：Q1–Q6 全部 ✅ 已确认（2026-09-29）**，答复实质见下节与 `reviews/grill-design.md` 的 `## User Confirmation`。D1/D3/D5 的「备选（未采纳）」已按答复改为明确结论（各处标 ✅）。Q5 的答复（只做 peer-review 拓扑回归）已落进 Testing Strategy。

## Risks / Trade-offs

- **成本失控面扩大（最主要，issue #262 明确要求如实记录）**：`recursion_limit` 是默认配置下主要结构后盾，调大 4 倍意味着一次失控循环最坏烧掉的 run 数由约 17 涨到约 67（peer-review 实测），而四维成本预算默认**不限**。缓解面：①`max_runs=300` / `max_nodes=200` 仍是硬上限，67 距 300 有充分余量；②route 的 `max_routes` 仍是环的第一道闸（本 change 不削弱它）；③用户可显式写回 `subagents.workflow.recursion_limit`（含调小）恢复旧行为，通道已存在。**这是有意取舍**，与 #196「框架不替使用者决定花多少钱」同口径，但本 change 的对象是**结构闸**而非成本软闸，故不能照抄 #196 的「默认不限」结论。
- **回归测试写成恒真（grill 须重点审）**：若只断言「默认配置下某个循环图能跑完」，改前改后**都可能通过**（取决于构造），等于没覆盖本 change 的核心行为。必须用「同一张图、同一个显式 `max_rounds`、改前后 `diagnostics.reason` 不同」的构造 + 对照组（见 Testing Strategy）。
- **默认值改动的跨拓扑不确定性**：`recursion_limit ≈ 3 × 轮数`（superstep/轮，见 Context 比值表）是 **peer-review 拓扑**的实测值，依赖模板形状（orchestrator-worker 是无环 foreach+aggregate，superstep/轮 ≈ 1；嵌套 hierarchical 又不同）。**100 不保证在所有拓扑下都等于约 33 轮**——这是 superstep 计量口径的固有性质，C2 D6 已确定图级而非节点级。文档须写明「按 peer-review 折算约 33 轮」，避免读者把它当成跨拓扑的轮数保证。
- **`to_dict()` 哨兵的一次性指纹变化**：见 D3，已被接受并记录；实现时须在 change 文档与（如需）发布说明里写明，避免被误报为 bug。
- **docstring 漂移**：`workflow.py:13` 的 docstring 若不同步，会出现「文档说 25、代码行为 100」的自相矛盾——C2/C4 都有过同类教训，实现须把 docstring 列入必改项。

## Testing Strategy

- **配置层（三路径一致性，锁 D2）**：
  - `AsterwyndConfig().subagents.workflow.recursion_limit == 100`（dataclass 直构路径）。
  - yaml 未写该键时 `load_config(...)` 得到 100（解析路径）。
  - `_spec_bounds(manager)` 在 `manager.config` 缺失/链路断时兜底为 100（getattr 路径）。
  - yaml 显式写 `recursion_limit: 7` 仍生效（既有测试 `test_workflow_limits_are_configurable` 保持绿）。
- **默认值语义回归（本 change 的核心，**必须非恒真**）**：
  - **判据选 `diagnostics.reason`，而非「跑完/没跑完」**。构造：`run_pattern("peer-review", max_rounds=N)` 配一个**始终回 `CRITIQUE`、永不 `APPROVED`** 的 `StaticLLM`，使 route 的 `max_routes=N` 成为唯一自然终点。则
    - 旧默认 25 下：图级 `recursion_limit` 先触发 → `status == "graph_recursion_exceeded"` 且 `diagnostics.reason == "recursion_limit"`；
    - 新默认 100 下：能跑满 N 轮 → 终点由 `max_routes` 决定 → `diagnostics.reason == "max_routes"`（既有 `test_max_routes_caps_a_single_route_node` 已确认该出口的 `status` 同为 `graph_recursion_exceeded`，但 `reason` 不同）。
  - **N 的标定**：取使「旧默认必然撞顶、新默认必然不撞顶」的值。**读码推演（本 design 已独立核对，非照抄 issue 估算）**：peer-review 一轮 = producer + reviewer + gate(route) 三个节点各派发一次，而 `_steps += 1` 只在「本轮确有派发」时触发一次（`scheduler.py:974-975`），route 虽 `_run_cost=0` 但 `_dispatch` 仍返回 `True`（`:1650-1667`），故 **3 superstep/轮**；每轮 2 个真实 run（producer/reviewer）。用该模型回算 issue #262 的表：limit 25 → 第 9 轮 producer 后 `_steps=25`，下一个就绪节点（reviewer）在 `:959` 的 `_steps >= limit` 前置检查处撞顶 → **9 轮 / 17 run**，与实测逐字吻合（issue 正文写的「一轮约 1.9 superstep」实为 **1.9 run/轮** 的误记，superstep/轮 是 3）。据此解析可行区间为 **`N ∈ [9, 32]`**——对照组触发需 `3N > 25 ⇒ N ≥ 9`，主组不触需 `3N < 100 ⇒ N ≤ ~32`。取 **`N=12`**（≈36 ≤ 100）留两侧余量；实现时仍须**实测标定**（先跑探针确认 `N` 轮所需 superstep 严格落在 (25, 100)），不得照抄本推演——这是防恒真的关键一步。**注意**：初稿引用的「约 1.9 superstep/轮」是错的（`12 × 1.9 = 22.8 < 25`，按它取 N 会让对照组得到 `max_routes` 而非 `recursion_limit`，防恒真机制失效）；「1.9」实为 **run/轮**（17 run ÷ 9 轮），与 superstep/轮（3）是不同量。
  - **必须配对照组**：同图同 N，显式 `recursion_limit=25` → 断言 `reason == "recursion_limit"`。对照组证明「该图确实能触发旧默认」，否则未来任何让 superstep 记账失效的重构都会让主断言静默恒真。
- **跨拓扑覆盖边界（✅ 已确认 2026-09-29，Q5）**：**只在 peer-review 拓扑做本 change 的核心回归**；foreach 重拓扑不额外补断言——「默认调大对 foreach 重拓扑无可观察收益（首撞闸仍是 `max_runs`/`max_nodes`）」是已知且可接受的性质，由既有 `max_runs`/`max_nodes` 测试覆盖。用户答复实质：方案 A。
- **既有触发类测试保持绿（锁「只改默认值、不改机制」）**：`tests/agent/subagent/test_scheduler.py`（`recursion_limit: 2` 触发 + `recursion_limit: 25` 下 `max_routes=1` 触发）、`test_terminal_honesty.py`、`test_dynamic_foreach.py`、`test_aggregation_runtime.py`、`test_workflow_graph_events.py`、`test_workflow_graph_snapshot.py` 均已用**显式**上限或 `max_nodes`/`max_runs` 触顶，不受默认值影响，须全部保持绿。
- **钳制与报告面不变**：`test_workflow_asset_limits.py` 的 `_eff_limit` min 方向、`limits_report` 的 declared/applied/clamped 三值语义保持绿（资产声明 5000、配置 300 的既有 Scenario 不受本 change 影响）。
- **序列化面（锁 D3）**：新增/保留一条断言——未声明 `recursion_limit` 的 spec 的 `to_dict()` **不含**该键且 `spec_hash` 与改前逐字相同（防止有人顺手改成「总是序列化」）；显式 `recursion_limit=25` 的 spec 在新默认下**含**该键。
- **全量**：`uv run pytest -q` 全绿；`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py` 通过。
- **benchmark smoke**：本 change 触及 agent-runtime / subagent 面，按门禁跑 `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`。

## Open Questions

> 本节由 grill 产出并停轮确认；每条配本 change 真实场景的具体例子。**Q1–Q6 已全部由用户拍板（2026-09-29）**，答复实质见下，完整记录在 `reviews/grill-design.md` 的 `## User Confirmation`。

- **Q1** ✅ 已确认（2026-09-29）：**方案 A——不收敛**。四处默认值字面量保持现状，本 change 只改数值 + 用测试锁「三路径一致」。**用户答复实质**：接受保留 4 处重复，不为「只调默认值」这一个目标引入 `agent/config.py` → `agent/subagent/workflow.py` 的层间依赖；一致性由测试保证（见 Tasks 2.2）。**例**：漏改任一处会出现三路径分叉——`AsterwyndConfig()` 直构得 100、yaml 未写键也得 100、但 `manager.config` 链路断时 `_spec_bounds` 兜底仍是 25。
- **Q2** ✅ 已确认（2026-09-29）：**维持 100**。**用户答复实质**：100（≈33 轮、67 run）是「显著改善现状（9 → 33 轮）」与「远离 `max_runs=300` 冲突」的交点；且该值可被配置覆盖，日后偏紧再调成本低。**如实写明（用户明确要求）**：调研**没有**支持 100 是业界共识值——LangGraph 取 10007（≈不限）、deepseek-harness 取 256 轮、opencode 与 kimi-code 默认不限；**100 的正当性来自本仓内部约束**（与 `max_runs=300` 共存、两个结构闸不打架），而非外部先例。**例**：`max_rounds=40` 的 peer-review 图，取 100 时约 33 轮撞 `recursion_limit`（达不到 40）；取 256 轮则约 150 轮前先撞 `max_runs=300`。
- **Q3** ✅ 已确认（2026-09-29）：**方案 A——接受**「显式写 25/100 的资产 `spec_hash` 一次性变化」。**用户答复实质**：接受该一次性、方向正确的指纹变化；不改哨兵设计（不做「总是序列化三闸」，否则**每个**存量资产指纹都会变）。见 D3。**例**：显式 25 的存量资产再 `SaveWorkflowAsset` 时首次判 `updated`（内容其实没变）；显式 100 者反向变化；未声明键者不受影响。
- **Q4** ✅ 已确认（2026-09-29）：**方案 A——本 change 只声明「诊断反馈不属本 change」，归属确认为 #246**。**用户答复实质 + 事实订正**：主 session 核验 —— 本 change 查证「issue #246 **正文** 0 处含那三个字段」是**对的**，但**归属确实是 #246**：`declared_max_rounds` / `rounds_actually_run` / `limit_source` 已在 #246 的 change 文档（change-id **`workflow-builtin-templates`**）`design.md` **D7** 里定下并正在实现，只是**没回填到 issue #246 正文**。故无需用户另行指定归属。完整记录在 `reviews/grill-design.md` 的 Cross-Reference（`docs/openspec-change-backlog.md` 的说明）。
- **Q5** ✅ 已确认（2026-09-29）：**方案 A——只做 peer-review 拓扑回归**，其它拓扑由既有 `max_runs`/`max_nodes` 测试覆盖。**用户答复实质**：接受「默认调大对 foreach 重拓扑无可观察收益」是已知且可接受的性质；不额外补 foreach 断言。**例**：`max_items=20` 的 foreach 回边循环约 15 轮即烧穿 300 run，用户看到的仍是 `reason=="max_runs"`。
- **Q6** ✅ 已确认（2026-09-29）：**方案 A——保留** spec delta 新增的「配置项覆盖语义」规范句。**用户答复实质**：该句固化既有 `_eff_limit` min 钳制方向，保留便于后续 `RunWorkflowAsset` 钳制相关 change 引用，值得纳入本 change 契约。**例**：保留 = 固化既有行为；删除 = 本 change 只改数值（用户选保留）。
