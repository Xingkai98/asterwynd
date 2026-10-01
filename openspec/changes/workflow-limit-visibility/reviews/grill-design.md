# Grill: workflow-limit-visibility 设计追问

## Reviewer

- run id: grill-workflow-limit-visibility/round-1（独立零记忆 subagent，非 `batch-grill-me` skill 环境下的同等标准追问）
- 时间: 2026-10-01
- 方法：逐条读 `proposal.md` / `design.md` / `tasks.md` / spec delta，跑通 `research/gap_probe.py`，并对 `subagents.py` / `scheduler.py` / `aggregation.py` / `workflow.py` 做 **实验性取证**（构造真实 scheduler + dry run，实测 `_expanded_nodes`、`_route_counts`、`state.runs`、`_diagnostics`、description 是否为静态属性），不依赖文档自述。

## Confirmed Decisions

- **决策**: D1 — 保留 `limits` 的三段式 `{declared, applied, clamped}` 形状，不复用扁平化 `{recursion_limit: 100}`，且保留 dry run 下 `clamped` 恒 `false` 的字段；理由：既有三出口（`status()` `scheduler.py:2866`、`_envelope()` `scheduler.py:3077`、资产加载 `subagents.py:2273`）全部三段式，dry run 是第四个出口，扁平化会引入第二形状，与「一处学会处处可用」相悖。`clamped` 恒 false 是**结构性事实**而非 bug：dry run 构造 `WorkflowScheduler(sim_manager)`（`subagents.py:1789`）**不传 `limit_ceiling`**，`limits_report(spec, {})` 下 `clamp_limit(declared, None) == declared`（实测 `CTRL_limits_report_available` 三闸 `clamped` 全 false），钳制只发生在资产加载路径（`subagents.py:2269`）。**条件**：必须在报告 `notes` 补一句口径说明（「这是当前会话直接运行会生效的值；存成资产在更小配置下加载时会被钳制，届时 `RunWorkflow` 的 `limits_clamped` 会报出」），否则 `clamped:false` 会被读成「永远不会被钳」。来源：本轮 grill D1 取证。
- **决策**: D2-a — `node_budget` 保持「只讲 `max_nodes` 一件事」的命名边界，不泛化成 `gates: {max_nodes:{...}, max_runs:{...}}` 映射；理由：`max_nodes` 是静态量（执行计划构建后确定），`max_runs` / `recursion_limit` 是动态量（取决于 route 实走轮数）。泛化结构会诱导实现方给动态闸也填「余量」字段，正是 spec delta 新增条款（`specs/.../spec.md:39`）与 #273 D6「不臆造」要防的假面。命名即边界，收紧字段面比事后加措辞更硬。来源：本轮 grill D2 取证。
- **决策**: D3-a — route 条目报出的闸门计数只能取自 `scheduler._route_counts`，读私有状态可接受；理由：`_route_counts[node.id]`（`scheduler.py:529` 定义、`:1891` 递增、`:1672` 判定）是 `max_routes` 超限判定唯一实际使用的计数；`_build_dry_run_report` 已在读 `scheduler._plan` / `scheduler._states`（`subagents.py:1496`、`:1503`、`:1542`），同包同私有类读取，不新增耦合面。实测 `gate` 被判定一次时 `_route_counts == {"gate": 1}`。**替代方案（在报告层重算 route 次数）会引入第二真相源，违反 D6**。来源：本轮 grill D3 取证。
- **决策**: D6-a — 明确要求实现必须复用 `limits_report()` / `_eff_limit()` / `ExecutionPlan` 字段 / `_route_counts` / `_diagnostics`，SHALL NOT 在报告层重算任何闸值；理由：spec 已有条款要求「所有对外报出限制值的出口都报实际生效值」；报告层重算会让钳制逻辑演进后 dry run 与其他三出口静默分叉。实测 `limits_report()` 与 `_eff_limit()` 共用 `clamp_limit()`（`scheduler.py:448`），「对内钳的值」与「对外报的值」在结构上不可分叉。方向确认。来源：本轮 grill D6 取证。
- **决策**: D5-a — 描述补三闸默认值句的长度预算成立（`4109 → ~4229 < 6000`，余量 1891）；理由：实测 `DeclareWorkflowTool.description` 长度 4109、`test_workflow_tool_discoverability.py:315` 的守卫上界 6000；`DryRunWorkflow` 描述 1581。补一句（~120 字符）无挤压风险。**仅确认长度，不确认「值=事实」这一更强断言**（见 Open Questions Q6 / Risks R4）。来源：本轮 grill D5 取证。

## Open Questions

> 每条给出我的推荐答案。**主 session 停轮后逐条抛给用户，收到答复前不得写实现代码。**

- **Q1（D2 核心，阻塞级）：`node_budget.expanded` 应当报哪个数？** 实证：`max_nodes` 闸门的实际计数器是 `self._expanded_nodes`（`scheduler.py:2176` 的 `_check_foreach_budget` 与 `:2111` 的 `_expand_plan` 都用它），它 = 执行计划节点数 **+ 每个 foreach 展开项各计 1 个节点**（`workflow.py:331` 明写「`max_nodes` 数节点（含 foreach 展开）」）。
  - 实测（`max_nodes=200`，20 项 foreach）：`len(plan.nodes) == 4`，但 `_expanded_nodes == 24`。
  - 按 design D2 的定义（`expanded` 源 `ExecutionPlan.nodes`），`node_budget.expanded = 4`、`headroom = 200 - 4 = 196`；而闸门实际口径是 `200 - 24 = 176`。**两者差 20**，且 `196` 是**假余量**——这张图再放大 foreach 项数就能撞闸，报告却显示还有 196 的空位。
  - 更硬的对照（`max_nodes=5`，20 项 foreach）：闸门在 `_check_foreach_budget` 处 `4 + 20 > 5` 抛 `max_nodes`，但 `len(plan.nodes)` 始终是 `4`，`headroom` 报 **正数 1** —— **一张已经撞闸的图，`headroom` 却读出「还有余量」**。这与本 change 要消灭的「假面」同型。
  - 推荐答案：**`node_budget.expanded` 改为取自 `scheduler._expanded_nodes`（闸门同源计数），而非 `len(plan.nodes)`**；若仍想展示「图规模」，另加一个只读 `graph_nodes: len(plan.nodes)` 字段，两者口径在 `notes` 里点明。**必须同时重述字段身份**：改用 `_expanded_nodes` 后 `expanded - declared != auto_inserted` 不再成立（foreach 项既非 declared 也非 auto_inserted），design 测试里 `auto_inserted == expanded - declared` 的断言要删改。另需交代 `_expanded_nodes` 是**不退还的高水位**（`scheduler.py:2133`、`:2840`），收缩后不回退——dry run 单趟场景影响小，但措辞不能承诺「精确等于当前图节点数」。
- **Q2（D1 边界，是否放开）：`clamped` 恒 false 之外，要不要让 dry run 也报「这张图存成资产后会被当前配置钳到多少」？** 推荐答案：**不做**（超出本 change 边界，属 #276/资产语义）。dry run 模拟的是「当前声明的 spec 直接运行」，钳制只在资产加载路径发生，报一个「假设它成为资产」的数值会是新的第二真相源。保持 D1 现口径 + `notes` 说明即可。
- **Q3（D3 命名与既有字段冲突）：route 条目已有的 `runs` 字段恒为 `0`，与新增 `used` 并存会不会自相矛盾？** 实证：`_execute_route` **从不**递增 `state.runs`（`_apply_run_status` 只在 `_execute_subagent` / `_execute_aggregate` 调用，`state.runs += 1` 见 `scheduler.py:2328`；foreach 走 `state.runs = len(items)`，`:1963`）。实测 gate 被判定一次时 `state.runs == 0`、`_route_counts == 1`。即 **design D3 的立论「`state.runs` 是 route 被求值的次数，与 `_route_counts` 未必相等」是错的——`runs` 对 route 结构性恒 0**。因此报告会同时出现 `runs: 0` 与 `used: 1`，模型读到的是矛盾而非「两个口径」。推荐答案：**新增字段命名为 `gate_count`（或 `max_routes_used`）而非 `used`，并在 `notes` 明确「route 节点 `runs` 恒为 0 是既有事实（route 不跑模型），`gate_count` 才是 `max_routes` 判定的计数」**；`runs` 字段本身不在本 change 改（属既有字段语义）。请在选项中确认字段名。
- **Q4（D4 挂载条件，与 spec delta 冲突，阻塞级）：`diagnostics` 在 dry run 报告里的挂载条件取哪种口径？** 实证推翻 design 的自述：design Context #4 / D4 称「真实运行的 `_envelope()`**有条件**携带 diagnostics（`scheduler.py:3107`，`if self._diagnostics`）」——**这是一处事实错误**。`_envelope()` 的 `scheduler.py:3107` 是 `"diagnostics": dict(self._diagnostics),`，**无条件**写在 payload 字面量里；`if self._diagnostics` 出现在 `status()` 的 `scheduler.py:2886`（另一条出口）。实测：一张干净跑完的图，模型可见的 `parent_envelope()`（= RunWorkflow 的返回体）**始终带 `diagnostics` 键**，值为 `{}`。
  - 后果：spec delta 的 Scenario「未撞闸时不产出现实不存在的诊断」要求 dry run **不挂空诊断**，这与「SHALL 与真实运行的同一诊断出口一致」**在 `_envelope` 口径下不可兼得**（`_envelope` 恰恰会在未撞闸时挂 `{}`）。
  - 另：`_diagnostics` 会被**非闸门**诊断填充。实测一张**未撞任何闸**的图（`$ref` 槽为空）得到 `{"route_ref_misses": [...]}`——用 `if self._diagnostics` 判定会把这份非闸门诊断也挂上，而 D4 的标题「撞闸时报告带 diagnostics」并未覆盖这种情况。
  - 推荐答案：**取 `parent_envelope`（模型可见出口）的真实形状——始终挂载，未撞闸时为 `{}`（甚至可只挂闸门相关的子集）**，并**同步修改 spec delta**：删掉「SHALL NOT 因此挂一个空诊断」的措辞，改为「诊断字段与真实运行同一出口形状一致（未撞闸时为空对象）」。理由：模型在 `RunWorkflow` 学到「diagnostics 恒在」，dry run 保持同形才符合「一处学会处处可用」；用 `status()` 的条件口径会与模型最常打交道的 `RunWorkflow` 分叉。若用户坚持「不挂空诊断」，则必须把 delta 的「与真实运行的同一诊断出口一致」改成明确点名 `status()`，且要接受与 `RunWorkflow` 形状不一致。
- **Q5（验收 L0 可判定性）：L0「模型能否报出生效值 100/200/300」会不会被描述本身污染、变成测「照抄描述」而非测「读到报告」？** 实证：D5 会在 `DeclareWorkflow` 描述里写入 `recursion_limit=100 / max_nodes=200 / max_runs=300`。那么模型只要复述它刚读过的描述，就能「通过」L0，**无需读 dry run 报告**——L0 因此测不出本 change 的核心价值。推荐答案：**L0 改问一个只在报告里存在、描述里没有的量**，例如「这张图展开后离 `max_nodes` 上限还有多少」（即 `node_budget.headroom`）或「报告里 `limits.max_nodes.applied` 是多少」；这样答对即证明模型确实读了报告。请在改验收口径时一并修订 `proposal.md` 的 L0 定义。
- **Q6（D5 措辞）：描述里的三闸默认值该表述为「模块默认值」还是「你当前会话的默认值」？** 实证：`DeclareWorkflowTool.description` 是**静态类属性**（实测任意实例返回同一字符串），而运行期默认来自配置——`_spec_bounds()`（`subagents.py:442`）随 config 变化，实测配置 `max_nodes=777` 时 `bounds={"max_nodes":777, ...}`，但静态描述里**没有**任何三闸值（当前），补进去后就会成为 `200` 的硬编码。即：**一个把 `subagents.workflow.max_nodes` 覆盖成 777 的部署，描述会说「默认 200」，而 dry run 报告会说生效值 777**——两处对同一事实表述不同，恰是 D6 精神（唯一数据源）要防的分叉。推荐答案：**措辞写成「模块默认值 `recursion_limit=100 / max_nodes=200 / max_runs=300`（部署可用配置覆盖；以 dry run 报告里的生效值为准）」**，明确「以报告为准」，并把「部署可覆盖」写进 delta 的披露条款；同时 `test_workflow_tool_discoverability.py` 的断言应宽松到「描述含三闸名 + 三个数值」而非绑定「运行时等于描述」。请在 grill 后确认此措辞。

## User Confirmation

- **Q1**: 用户答复：采用「闸门投影值 + 单列 graph_nodes」——`node_budget.expanded_nodes` 取闸门等价投影（`len(plan.nodes) + Σ foreach items`，即 `max_nodes` 闸门真正会数到的数），撞闸图上该值超过上限、`headroom` 为负（如实报「超了」）；另单列 `graph_nodes = len(plan.nodes)` 表示图本身多大。接受为此在 scheduler 的 `_check_foreach_budget` 内**只增一个只读字段**（记投影值于超限判定前，不改判定逻辑/异常路径）；`auto_inserted` 改直接取 `len(plan.inserted_nodes)`，原稿 `auto_inserted == expanded - declared` 断言作废。；确认时间: 2026-10-01
- **Q2**: 用户答复：不做——dry run 只报「当前 spec 直接运行会生效的值」，**不**额外报「这张图若存成资产后会被当前配置钳到多少」（那属资产语义、会造第二真相源）。保持 D1 现口径 + notes 说明；确认时间: 2026-10-01
- **Q3**: 用户答复：字段名用 `gate_count`（不用 `used`）——因 route 条目既有 `runs` 字段结构性恒 0，`used` 会与之并列成表观矛盾；`gate_count` 取 `scheduler._route_counts`，并在 notes 写明「route 的 `runs` 恒 0 是既有事实（它不跑模型），`gate_count` 才是 `max_routes` 判定的计数」；`runs` 字段本身不改；确认时间: 2026-10-01
- **Q4**: 用户答复：无条件挂载 `diagnostics`，未撞闸时为空对象 `{}`——与模型最常打交道的 `parent_envelope`（RunWorkflow 返回体）同形，`notes` 说明「诊断非空 ≠ 一定撞闸，看 `reason` 键」；同步改 spec delta，删「未撞闸时 SHALL NOT 挂空诊断」的措辞，改为「与真实运行模型可见出口同形（未撞闸时为空对象）」；确认时间: 2026-10-01
- **Q5**: 用户答复：L0 验收改问**只在 dry run 报告里存在**的量（如 `node_budget.headroom` 或 `limits.max_nodes.applied`），**不**问「三闸默认值是多少」（描述里就有，照抄即通过、测不出本 change 价值）；确认时间: 2026-10-01
- **Q6**: 用户答复：描述措辞写成「**图级**（graph-level）**模块默认值** `recursion_limit=100 / max_nodes=200 / max_runs=300`——部署可用配置覆盖，资产在更小配置下会被钳制，**以工具报告出的生效值为准**」；明确限定「图级」以区别于路由级 `max_routes` 默认 1；描述长度守卫（< 6000）不变；确认时间: 2026-10-01

## 风险

- **R1（阻塞，必须改）：D2 的 `headroom` 口径用错计数器，会制造**新的**「假余量」。** 见 Q1 实证：`len(plan.nodes)` 对 foreach 展开项**完全不计**，而 `max_nodes` 闸门把每个 foreach 项各计一个节点。极端例子：`max_nodes=5` + 20 项 foreach 的图**已经撞闸**，但按 D2 的定义 `headroom = 5 - 4 = 1`（正数）。本 change 的整个命题是「让模型在撞闸前看见余量」，若余量数字本身会把撞闸图报成有余量，则**方向性反噬**。必须改为闸门同源计数（`_expanded_nodes`），并按 Q1 重述字段身份与测试断言。
- **R2（阻塞，必须改）：D6 的「同源锁」测试是假保护，且会锁死 R1 的 bug。** design 写的 `report["limits"] == limits_report(spec, {})` 是**输出值相等**——报告层若自行重算、数值恰好相同（无 ceiling 时 `min(declared, None) == declared`，重算极易得到同样结果），测试**照样绿**，「改成重算测试须变红」不会发生。真正的同源锁需要**调用证据**：monkeypatch `limits_report` / `_eff_limit` 返回哨兵值，断言报告字段反映哨兵（证明它确实**调用了**该函数），或对 `node_budget` 断言其等于 `scheduler._expanded_nodes` 的**同一对象读取**。此外 design 的 `node_budget` 测试断言 `auto_inserted == expanded - declared`，恰好把 R1 的错误口径**固化为期望值**——必须与 Q1 一并改。
- **R3（必须改）：D3 的立论事实错误（route `runs` 恒 0）。** design D3 说「`state.runs` 对 route 是『route 被求值的次数』，与 `_route_counts` 未必相等」——实测 route 的 `state.runs` **结构性恒为 0**（`_execute_route` 不递增）。这不是「未必相等」，而是「恒不相等且左侧恒 0」。设计的理由与「测试里锁 `route.used == _route_counts` 同源」的论证都要按 Q3 重写；报告若原样加 `used` 会与既有 `runs:0` 形成表观矛盾。
- **R4（必须处置）：D5 的默认值硬编码会与运行期配置分叉。** 见 Q6 实证。若按 Q6 措辞（「模块默认值，以报告为准」）可降为**低风险**；若坚持让描述充当「当前生效默认值」的事实来源则**与 D6 冲突**，必须改。
- **R5（低）：spec delta 的 `node_budget` 字段清单未含 `headroom`（`specs/.../spec.md:35` 只列 `declared/expanded/auto_inserted/limit` 四项），而 proposal/design 把 `headroom` 当作卖点。** 这本身不算冲突（spec 更松），但要注意：**当前 spec 条款对 `expanded` 未定义口径**，实现按 R1 修正（改取 `_expanded_nodes`）后，delta 的「`expanded` 严格大于 `declared`」在**窄图（无 foreach、无自动插层）**上会变成 `expanded == declared`——这与 Scenario「报告暴露自动插层造成的节点放大」（`specs/.../spec.md:114-120` 的 GIVEN 是「扇入宽度会触发自动插入」）一致，但 delta 正文没有像「节点预算」那样给出窄图对照。建议 delta 补一句「无展开/无插层时三项相等」，避免模型在大图上学会后就假设差值恒存在。
- **R6（低）：`route_ref_misses` 随 `diagnostics` 上车会带来一处新的**误读面**。** 见 Q4：一张**没撞闸**但有一次 `$ref` 未命中的图，报告将带 `diagnostics.route_ref_misses`。若 delta 的措辞停留在「因结构闸中止时 SHALL 附结构化诊断」，模型可能把这份非闸门诊断误当作「撞闸了」。Q4 定的口径必须同时覆盖此情形（推荐：保留 `_diagnostics` 全量、但在 `notes` 说明「`diagnostics` 非空 ≠ 一定撞了闸，看 `reason` 键」——与 `scheduler.py:1476` 既有纪律一致）。
- **R7（低，门禁/流程）：受保护路径与分支纪律已正确铺设，但 worktree 内 `.claude/` 被 gitignore、guard hook 不生效，受保护路径只能靠 CI 的 artifact checker 兜底。** 本 change 触及 `openspec/specs/**`、`docs/openspec-change-backlog.md`、归档目录，必须在 `workflow-events.jsonl` 落结构化解释事件；manifest 必须在 `tasks.md` 最终化（含归档 move）**之后**生成。此点 tasks.md 已按流程列明，无冲突，仅提示实现方不要依赖本地 guard。
- **R8（低）：连续两个「默认值」句可能让描述读起来重复。** 既有描述已有一句「max_routes defaults to 1」（`subagents.py:782`，路由级，且明说「no config-level default」），D5 新增句是「图级三闸默认值」。两者量纲不同（route 级 vs 图级）、不冲突，但新增句应显式区分「图级（graph-level）」，避免模型把 `max_routes` 默认 1 与三闸默认值混为一谈。design D5 的备选句已含 `Graph-level gates`，保持即可。

## 结论

- **必须改（阻塞实现）**：R1（D2 计数器口径）、R2（D6 测试须为调用级同源锁，且去除固化的错误断言）、R3（D3 立论事实错误 + 字段名）、R4/Q6（D5 措辞，避免与配置分叉）、Q4（D4 挂载条件与 spec delta 冲突）。
- **已确认可保留**：D1 三段式 + `clamped` 恒 false（+ notes 说明）、D2-a 命名边界、D3-a 读 `_route_counts`、D6-a 复用既有函数方向、D5-a 长度预算。
- **Open Questions（停轮待用户答复）**：Q1、Q2、Q3、Q4、Q5、Q6（每条附推荐答案与实证例子）。
