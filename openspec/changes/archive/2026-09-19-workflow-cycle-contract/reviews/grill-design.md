# Design Grilling: 循环图的契约对模型可见（workflow-cycle-contract）

我是**独立零记忆**的设计追问（grill）审阅员：本次会话未读取任何先前对话，工作目录
`/home/happy/.paseo/worktrees/0frj3kg8/workflow-cycle-contract-2026-09-19`（分支
`workflow-cycle-contract/2026-09-19`，基线 sha `b0a6604f858c5ea19f95f77618026c250749b2ad`）
的代码与文档是我唯一的事实来源。审阅对象是本 change 的 `proposal.md` / `design.md` /
`tasks.md` / `specs/multi-agent-collaboration/spec.md` delta 四份文档。审阅方法：**先读代码
建立调度器真实派发模型，再把 design 的 D1/D2 判据逐字实现成 `/tmp` 下的独立校验器，注入
真实 `WorkflowScheduler.run()` 实跑对照**——所有结论都来自实跑输出，不采信 design/proposal
的自我断言。全程未修改仓库任何文件（临时脚本全部在 `/tmp/grill_a/`，未落盘进仓库）。

## Reviewer

- run id: `grill-workflow-cycle-contract-20260919-001`
- 时间: 2026-09-19
- 审阅对象: `openspec/changes/workflow-cycle-contract/{proposal.md,design.md,tasks.md,specs/multi-agent-collaboration/spec.md}`
- 基线: `b0a6604f858c5ea19f95f77618026c250749b2ad`（分支 `workflow-cycle-contract/2026-09-19`）
- 审阅方法（实跑命令，均在 worktree 根目录、`export PATH=/home/happy/.local/bin:$PATH` 下执行）:
  - `PYTHONPATH=.:/tmp/grill_a uv run python /tmp/grill_a/run_a.py`
    —— 字面 D1/D2 对官方 4 pattern（`compile_pattern`）逐个判定 + SCC/数据入边全量 dump
  - `PYTHONPATH=.:/tmp/grill_a uv run python /tmp/grill_a/c2_final.py`
    —— 11 种环形 spec 的「字面 D1 / 字面 D2 / 候选判据 C2 / 候选判据 C3 / 真实 `run()` 实跑结果」五列对照
  - `PYTHONPATH=.:/tmp/grill_a uv run python /tmp/grill_a/verify_c.py`、`/tmp/grill_a/verify_de.py`、
    `/tmp/grill_a/verify_miss.py`、`/tmp/grill_a/spin_entry.py`、`/tmp/grill_a/spin_bound.py`、
    `/tmp/grill_a/diag_spec.py`、`/tmp/grill_a/route_slot.py`
    —— 逐条核验 design 关于调度器行为的断言（含 `_reset_subtree` 调用序列、`_route_verdict`、
    `_node_output`、`foreach`/`aggregate(llm)` 的实际 LLM 调用次数）
  - `PYTHONPATH=.:/tmp/grill_a uv run pytest tests/agent/subagent -q -p d12inject`
    —— 用 `/tmp` 下的 pytest 插件把**字面 D1/D2** 注入 `parse_workflow_spec`，跑既有回归套件，
    记录每条被拒测试（不修改仓库任何文件）
  - `PYTHONPATH=.:/tmp/grill_a uv run pytest tests/agent/subagent -q -p alt_inject`
    —— 同法注入候选判据 C2/C3 做对比
  - `PYTHONPATH=.:/tmp/grill_a uv run python /tmp/grill_a/repo_specs.py`
    —— AST 扫描仓库全部 `.py` 里的 spec 字面量（88 条可解析）逐个跑判据，查误伤面
  - `uv run pytest tests/agent/subagent/test_terminal_honesty.py -q`（基线：20 passed）

## Confirmed Decisions

- **决策**：design D2 的字面判据（「`route` 节点有来自同一 SCC 内的 `required` 数据入边 → 拒绝」）
  **会拒绝官方 `peer-review` pattern**，design.md:56 的断言「判据对官方 pattern 天然免疫」与实测不符。
  实跑 `compile_pattern("peer-review", ...)` 得到 `D2_reject=True [('gate','reviewer','gate')]`：peer-review
  的 SCC 是 `{producer, reviewer, gate}`，其中 `reviewer → gate` 是**数据边**（`reviewer` 不是 route，
  故 `is_control_edge` 为假，`workflow.py:243-245`），`required` 默认 true 且 `reviewer` 与 `gate` 同 SCC。
  design.md:56 之所以断言免疫，是把「route 的**出**边是控制边」（正确）当成了「route 的入边不受影响」
  （错误）——判据看的是 `data_incoming(gate)`，与 route 出边无关。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：字面 D2 在既有测试上的误伤面**远大于** design 预期的「既有测试里的环图可能不符合契约」。
  实跑注入后 `tests/agent/subagent` 有 **32 条 FAILED**（基线全绿），其中 **23 条是纯 D2 命中**、6 条 D1+D2
  同时命中、仅 3 条是纯 D1。这 23 条横跨 **9 个不同测试文件**的正常循环测试——`test_patterns.py` 的
  peer-review 三连、`test_pattern_templates.py` 五连、`test_scheduler.py` 的
  `test_route_default_branch_loops_back` / `test_max_routes_caps_a_single_route_node` / `test_route_takes_matching_case`、
  `test_dynamic_route.py` 五连、`test_cost_attribution_runtime.py`、`test_workflow_graph_foreach_progress.py`、
  `test_workflow_semantics_m1.py`、甚至 `test_workflow_spec.py:146` 那条名为
  `test_accepts_cycle_through_route_node` 的**正向用例**。它们不是「不符合新契约的坏图」，而是
  **本 change 声称要保护的合法循环形态**。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：调度器的真实派发规则可以用一个**最小不动点**（下称 C3）精确刻画，且该模型能**逐条复现**所有
  实跑结果。另有一个更小的候选判据 **C2**（「`required` 数据边子图上有环」，即 `edge.required` 为真且源
  不是 route 的边构成的子图出现环 ⇒ 环上每个节点都在等对方终态）；C2 是 C3 的真子集，命中面更小但
  修法提示更具体。C3 的规则来自 `_ready_nodes`（`scheduler.py:1479`）+ `_data_deps_satisfied`（`scheduler.py:1236`）+
  `_is_entry`（`scheduler.py:1500`）+ `_node_output`（`scheduler.py:2324`）：
  节点可跑 ⟺ **全部 `required` 数据入边的源可跑**（AND，`_data_deps_satisfied` 对 `edge.required` 为假的边
  `continue`）**且**（该节点是 `plan.entry` 成员 **或** 它没有控制入边 **或** 存在一个可跑且选中它的控制源
  route）。实测校准（`/tmp/grill_a/c2_final.py` 五列对照）：C3 在 11 个形状上与真实 `run()` 的「最终有节点
  completed」逐格一致，包括 peer-review（真实循环到 `graph_recursion_exceeded`，producer 跑了 9 次）、
  无 route 的纯逻辑死锁（`stalled`）、不可达环岛（`blocked`）全部命中。C3 优于字面 D1/D2 之处在于它
  **不误报任何实跑能跑起来的图**。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：「环体是否是 `entry`」是环能否真的转起来的**必要条件**，design 的 D1 完全没有提到它。
  实测（`/tmp/grill_a/spin_entry.py`）显示同一张 `cycle_gate`(route) + `body`(collect) 环：
  `entry: ["g"]` 时 route 只派发 2 次、`body` 一次都没跑就 `blocked`（图报 `completed`，即用户原报告的
  「图和人都不知道发生了什么」）；把 `entry` 改成 `["g","body"]` 后 route 派发 6 次、`graph_recursion_exceeded`。
  原因在 `_ready_nodes`（`scheduler.py:1489-1496`）：**非 entry 且有控制入边的节点，`activations <= 0`
  时永不派发**；环体节点的 `activations` 只在 route 的 `_execute_route` 里 `+= 1`（`scheduler.py:1775`），
  而 route 又是环内唯一入口——于是「环体等 route 激活、route 想激活环体时发现它不在 ready 集」。
  这条机制**不是 D2 描述的那个机制**（D2 说的是 `required` 数据边互等），但它同样让环「一个节点都跑不起来」。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：design 声称「回边 `required: false` 可以救回 `required` 数据边死锁」——**实测只对「本就能跑起来
  的环」成立，对真正的结构性死锁无效**。`/tmp/grill_a/verify_miss.py` + `c2_final.py` 实跑：
  (a) 环内 `required` 互锁（`b`(collect) 等 `c`(subagent)、`c` 等 `b`，回边 `required:false`），把回边收紧放宽
  都改变不了 `b`/`c` 双双 `blocked` 的结局（C2 命中 `['b','c']`）；
  (b) 「环内 collect 从环外拿数据」的形状（`/tmp/grill_a/verify_c.py` 的 `collect_body_outside_data`）在环外
  `src` 跑完之后仍然 `gate`/`body` 互等、图报 `completed`，字面 D1 只看「环内有没有产出节点」会漏掉它
  （该例环内确实有 `src→body` 的外部产出输入，但没有任何东西会变）。
  即「怎么改」这句修法提示（design D2 末段 / D5）在若干死锁形态下**是无效建议**。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：design/proposal 引用的行号有 **5 处对不上**（其中 2 处指向的代码与所述机制完全无关），
  实现时按文档给的 `文件:行号` 直接定位会读错代码。逐条 Read 核验（`sed -n '<line>p'` 逐行比对）：
  - `workflow.py:145`（`max_routes` 默认值）✅ 正确，`:145` 就是 `max_routes: int = 1`；
  - `workflow.py:501`（`max_routes` 只能在 spec 里逐节点配）✅ 正确；
  - `workflow.py:243-245`（回边应从 route 出发）✅ 正确，`:243` 是 `def is_control_edge`、`:245` 是它的实现；
  - `workflow.py:690`（迭代式 Tarjan）❌ **错**：`design.md:36` 与 `design.md:144` 写 `:690`，实际
    `_strongly_connected_components` 的 `def` 在 `workflow.py:687`，`:690` 是函数 docstring；
  - `scheduler.py:1615`（`max_routes` 节点级/跨轮累加/不重置）❌ **错**：`proposal.md:24` 用它论证
    「`max_routes` 是节点级、跨轮累加、不重置」，但 `scheduler.py:1615` 是
    `state.reason = state.reason or state.error`（`_run_node` 的异常处理），真正的计数点与闸门在
    `scheduler.py:1552`（`_dispatch` 里的 `self._route_counts.get(...) >= max_routes`）与
    `scheduler.py:1766`（`_execute_route` 里的 `+= 1`），计数器本身在 `scheduler.py:462` 初始化；
  - `scheduler.py:1221`（design.md:54 引作 `_data_deps_satisfied`）❌ **偏移**：`:1221` 是 `_budget_summary`
    的 docstring 末行，`_data_deps_satisfied` 的 `def` 在 `scheduler.py:1236`；
  - `scheduler.py:1346`（design.md:54 引作 `_ready_nodes`）❌ **偏移**：`:1346` 是 `_blocked_reason` 文档里
    的 `` `max_runs`）：真因在... `` 文本，`_ready_nodes` 的 `def` 在 `scheduler.py:1479`；
  - `scheduler.py:1579-1585`（design.md:42 引作 collect 聚合不产出）❌ **偏移**：`:1579` 是
    `task = asyncio.create_task(self._run_node(state))`，collect 分支里 `state.subagent_id = None` 在
    `scheduler.py:1737`；`scheduler.py:1579-1585` 与「collect 不产出」无关。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：design D1 对「产出节点」的定义（`subagent` 或 `aggregate(strategy="llm")`，`foreach` 计入、
  `collect`/`route` 不计入）在**实现层是准确的**，但它作为「环是否会转不出去」的判据**不成立**。
  逐条实跑（`/tmp/grill_a/verify_de.py`，环体设为 entry 保证每轮真重跑）：
  `aggregate(strategy="llm")` 的 4 轮环调了 4 次 LLM（`llm_calls=4`）且 `state.slots` 每轮更新；
  `subagent` 同样 4 次；`foreach(items=[...])` 展开项确实调 LLM（4 次）——三者都算产出成立。
  `aggregate(strategy="collect")` 环确实 `llm_calls=0` 且 `state.slots` 保持 `''`——不产出成立。
  但 `route` 那一句**不成立**：design.md:43 说「`route` 不产出 `result` 槽（`_node_output` 读不到）」，
  实测 `_node_output(route_state, "result")` 在 route 只有控制出边时返回
  `state.summary or None`（`scheduler.py:2332`）即 `"default -> ['done']"`——**非空**，可被下游 reducer 读走。
  `route` 无数据入边时才返回 `''`；用户那张图 «raw 永远为空串» 的真实原因不是「route 不产出」，
  而是 `data_incoming(cycle_gate) = ['body->gate required=False']` 而 `body` 自己 `summary=''`
  （`/tmp/grill_a/route_slot.py`）。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：design Testing Strategy 规划的变异验证「把 `data_incoming` 换成 `incoming` 应当让 peer-review
  误伤从而被测试抓住」**无法区分**：实测两种写法对 peer-review 给出**完全相同**的拒绝结果
  `[('gate','reviewer','gate')]`。原因是 peer-review 里 `gate` 只有 `reviewer→gate` 一条**入**边
  （`gate→producer`、`gate→aggregate` 都是出边），该边既在 `data_incoming` 里也在 `incoming` 里，
  而它同时满足「同 SCC + required」——换用 `incoming` 不会新增任何命中。这条变异是**恒等变换**，
  起不到「改坏实现 → 测试变红」的作用。实测有区分度的替代变异是**删掉 `required` 判断**：
  在 `#220` 那张能跑的 spin 图上，正确实现给 `[]`、删掉判断给 `[('cycle_gate','body','cycle_gate')]`
  （把带 `required:false` 回边的合法图误拒）——这才是能被测试杀死的变异。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：design D4 关于提示面预算的判断「文案过长挤占工具描述预算」**风险低到可以不设防**，但
  `DeclareWorkflow` 的循环小节**没有任何工具描述长度上限可依据**。实测（AST 扫描
  `agent/tools/builtin/subagents.py:456-467` 的全部 8 个工具）当前 `DeclareWorkflow` 描述 **489 字符**，
  在 `subagents.py` 里仅次于 `GetWorkflow`(644) 排第二，其余工具在 182–429 字符之间；仓库里**不存在**
  工具描述截断/预算代码（对 `agent/` 全量 grep `description[:`、`max_tools`、`TRUNC` 均无命中）。
  所以 D4 的「不罗列规则、给最小示例」是**风格选择**
  而非预算约束——按此实现即可，无需为长度担心到牺牲信息量。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：用户原报告的那张图（`route` + `collect` 聚合 + 回边 `required:false`）实测是**空转环**，
  不是死锁——但**只有在环体不是 entry 时它才「空转」**，且它连一圈都没转完就收敛了。
  `/tmp/grill_a/diag_spec.py` 逐字复跑 archive 里 `workflow-terminal-honesty/diagnosis.md:29-38` 的 #220 spec：
  `route_counts={'cycle_gate': 2}`、`_reset_subtree` 调用 `['cycle_gate','body','cycle_gate']`、
  `body` 最终 `blocked`、图报 `completed`——即回边确实被走过一次、`body` 一次都没完成，
  与「环内无产出 → 每轮读同一份空串 → 烧到 max_routes」的描述**不符**（它没烧到 max_routes，它提前收敛了）。
  把 `entry` 加上 `body` 之后同一张图才真的烧到 `max_routes`（`route_counts={'cycle_gate': 3}`、
  `graph_recursion_exceeded`）。所以「空转到撞 max_routes」这一现象的前提（环体是 entry）在 design
  和 proposal 里都缺席，而它恰恰是复现 #219 的关键条件。
  来源: grill-workflow-cycle-contract-20260919-001

- **决策**：`aggregate(strategy="collect")` 的 Σ 聚合**可能调用 LLM**，因此「环内全是 collect 聚合 +
  route ⇒ 状态空间不变化 ⇒ 必然不可终止」这条 D1 的核心论证（design.md:11,46）在实现层**不是纯静态的**。
  `_execute_aggregate` 在 `strategy == "collect"` 分支里调用 `_merge_contributions_bounded`
  （`scheduler.py:1733`），后者在拼接结果超预算时走 `self._aggregator.merge(texts, budget)`（`scheduler.py:2281`），
  而 `_build_summarizer`（`scheduler.py:575-583`）在 manager 有 LLM 时构造的是 `LLMSummarizer`。
  实测正常路径下 collect 环 `llm_calls=0`（因为空输入不超预算），所以「无误报」的结论**在常见输入下成立**，
  但论据应从「没有任何 LLM 调用」收窄为「**环内没有任何会随轮次改变的状态**」——这恰好是候选判据 C2/C3
  的立场，也是本节其余决策的依据。
  来源: grill-workflow-cycle-contract-20260919-001

## Open Questions

- **Q1**: D1「空转环」的判据是否应改为「环内**没有任何节点能跑**」而非「环内没有产出节点」？
  产出节点（`subagent`/`llm-aggregate`/`foreach`）既不是空转的必要条件，也不是充分条件。
  **场景**：用户在 issue #219 里想要一张「审阅不过就重做」的循环图，他这样写（下面是**实跑过的原文**，
  来自 `/tmp/grill_a/verify_miss.py` 的 `inner_required_lock`）：

  ```json
  {"goal": "inner lock", "recursion_limit": 100,
   "nodes": [{"id":"g","kind":"route","max_routes":4,
              "cases":[{"when":"GO","to":"a"}],"default":"a"},
             {"id":"a","kind":"subagent","task":"a"},               ← 环内有产出节点
             {"id":"b","kind":"aggregate","strategy":"collect"},
             {"id":"c","kind":"subagent","task":"c"},
             {"id":"end","kind":"aggregate","strategy":"collect"}],
   "edges": [{"from":"g","to":"a"},{"from":"a","to":"b","reducer":"concat"},
             {"from":"b","to":"c"},{"from":"c","to":"b","reducer":"concat"},
             {"from":"c","to":"g","required":false},{"from":"g","to":"end"}],
   "entry":["g"],"terminal":["end"]}
  ```

  环 `{g,a,b,c}` 里有**两个** subagent（`a`、`c`），按 D1 **通过声明**（实测 `litD1=[]`）；但实跑
  `b`/`c` 互相 `required` 等待（`b` 等 `c`、`c` 等 `b`）：`a` 跑了 1 次后 `completed`，`b` 与 `c`
  **永久 `blocked`**（因由都是「入边互相等待」），图级 `status = completed`、`diagnostics` 为空——
  用户在返回体里看不到任何异常，只能逐个点开节点才读到 `c` 其实一次都没跑。这正是 #219 要消灭的
  「图和人都不知道发生了什么」。
  对比：若把判据改成「环内没有任何节点能跑」，这张图会在**声明期**被拒并指名 `{b,c}` 的互锁。
  请拍板：**D1 保持「环内无产出节点」，还是改成「环内无任何可跑节点」**（后者覆盖更广，但需要
  把 `_ready_nodes`/`_data_deps_satisfied` 的语义复制一份到声明期，落点从 `workflow.py` 单文件
  校验变成「声明期复刻运行期派发规则」）？

- **Q2**: D2 的字面判据会拒绝官方 `peer-review`（实测），必须收窄。请拍板收窄到哪一档：

  **场景**：同一张 `peer-review`（`producer → reviewer → gate(route) → producer`，外加
  `producer/reviewer → aggregate`）。它在 master 上**声明成功且真能循环**（实跑 `max_rounds=8` 时
  `producer` 跑了 9 次、`gate` 派发 8 次、最终 `graph_recursion_exceeded`），是本项目**唯一能工作的多轮审阅循环**。
  三个候选：
  - **(a) 保持字面 D2**：peer-review 从此**声明失败**，`test_patterns.py`/`test_pattern_templates.py`/
    `test_workflow_spec.py` 等 23 条既有测试要一起改（含改掉 `test_accepts_cycle_through_route_node`
    这条正向用例）——等于本 change 顺手废掉官方 pattern 库的一半能力。
  - **(b) 收窄为「环内唯一的 route 有同环内 `required` 数据入边，且该数据源自身也依赖该 route」**
    （即判据 C3 的一个特例）：peer-review **通过**（`reviewer→gate` 虽是 `required` 数据边，但
    `reviewer` 由 entry `producer` 启动、不依赖 `gate`，实跑证明能跑）；`#217` 那张死锁图仍被拒。
  - **(c) 完全不做 D2，只做「环内无任何可跑节点」（C3）**：把 D2 并入 Q1 的判据，实现更少但报错
    粒度更粗（只报「这个环跑不起来」，不报「你这条回边是 required 数据边」）。
  推荐 (b)+(c) 同时要（(b) 给出可操作的修法提示，(c) 兜住 (b) 漏掉的互锁形态），但这意味着
  D2 的判据要从「route 的入边类型」改写成「环内 route 的数据源是否自环依赖」——
  **请确认是否接受这一改写**。

- **Q3**: **（D3，必须由用户拍板）** 「空转环 / 死锁环」在声明期**拒绝**还是**警告**？
  **场景**：模型在 session 里想试一张「先看看效果」的图——`g`(route) + `body`(collect) 的小环，
  它打算先跑一遍看输出再决定要不要加 subagent。当前（master）`DeclareWorkflow` 返回
  `{"status":"declared","workflow_id":"wf_xxx","nodes":["g","body","end"],...}`，图能跑、只是 `body`
  一次都没 `completed`（实跑：`route_counts={'cycle_gate': 2}`、`body` 终态 `blocked`、图级
  `status = completed`、`diagnostics` 为空——用户实际抱怨的是**这个**：没有任何地方告诉他环没转起来）。
  改成「拒绝」后同一句调用会落到 `_invalid_spec`（`agent/tools/builtin/subagents.py:433-439`）的
  返回形状 `{"status":"invalid_spec","reason":"<校验异常文本>","hint":"fix the workflow spec..."}`，
  其中 `reason` 就是本 change D5 要写好的那句话（如「cycle {g,body} has no producing node;
  add a subagent or aggregate(strategy=\"llm\") inside the cycle」）——**注意这个返回体里没有
  `workflow_id`**，模型拿不到可运行的图，只能改 spec 重声明。
  「警告」方案则是声明成功 + 返回体多一个 `"warnings": [...]`，模型仍能跑那张图。
  实测的数据点：本 change 声称的两条判据若按字面实现，会拒掉 **32 条既有测试**（横跨 9 个测试文件的
  正常循环）——这个数量本身就是「拒绝」路径的对外影响面证据。业界 Airflow/Argo 选拒绝、
  Temporal/LangGraph 不做声明期检查，两边都有先例，故**必须**由用户拍板。
  若选「警告」，请一并确认 **D1 的判据是否也要跟着收窄到 C3**（警告一个「其实能跑」的图等于噪音）。

- **Q4**: 「环内必须有产出节点」这条提示契约（D4 第 1 句）要不要改成「环内必须有**能跑起来**的节点」？
  **场景**：模型照着新描述里给的「最小正确示例」（route + 一个 `collect` 聚合 + **环内一个 subagent**）
  仿写一张两阶段审阅图，把 subagent 放在环外、只让 `collect` 在环内（这正是本 change design.md:48
  明确说要拒的形态，也是**结构上最自然的写法**——「先聚合意见、再决定要不要再来一轮」）。
  我实测过这个形态（`/tmp/grill_a/verify_c.py` 的 `collect_body_outside_data`，环外 `src` 只被 `body`
  以 `required` 数据边引用）：`src` 跑完 `completed`，`gate`/`body` 双双 `blocked`，图级
  `status = completed`、`diagnostics` 为空。
  若提示面写「环里必须有个会变的节点」，模型会把 subagent 塞进环里敷衍过关，但**塞进去也不一定
  让环转起来**（Q1 的场景）；若提示面改成「环里必须有个节点**先跑起来**，且它不能反过来等环里的
  东西」，模型需要理解 entry 语义——这对 LLM 是不是过高的要求？
  请拍板提示面的**一句话核心规则**该写哪句（这直接决定 D4 示例的形状，也决定实现时测试断言什么关键词）。

- **Q5**（**由主 session 追加，非 grill 审阅员提出**）: 新建的声明期拒绝路径会让上个 change 刚合入的运行期
  回归测试 `tests/agent/subagent/test_terminal_honesty.py` 的 `_deadlock_spec()` **在声明期就被拒**——
  而那套测试正是用来锁住运行期「入边互等」诊断的。它还能不能继续测它原本要测的东西？
  **场景**：`_deadlock_spec()`（`cycle_gate`(route) + `body`(collect) + 回边 `required` 默认 true）今天能声明成功、
  跑到 `body`/`cycle_gate` 双双 `blocked`、节点因由「入边互相等待」，测试断言的就是这句因由；改动后
  `parse_workflow_spec` 会在**声明期**抛错，`_run(manager, _deadlock_spec())` 直接挂掉。
  三个选项：**(甲)** 该套件改为**绕过声明期校验、直接构造 `WorkflowSpec` 对象**（保住运行期诊断覆盖）；
  **(乙)** 删掉这些用例；(**丙**) 放弃本 change 的声明期拒绝。
  **推荐 (甲)**——运行期诊断本身没错，它描述的是真实发生的状态，只是触发路径变窄了
  （从「模型声明出坏图」变成「图在运行期因其它原因陷入互等」），应继续锁住。

## User Confirmation

- **Q1**: 用户答复：**改成不动点判据**——「环内无任何可跑节点」替换原 D1 的「环内无产出节点」。理由：产出节点既非空转的必要条件也非充分条件（grill 实测：环里有两个 subagent 的图仍会 `b`/`c` 永久 `blocked` 而图报 `completed`），而不动点判据在实测中零误报（拒掉两张真死锁图、通过全部 4 个官方 pattern 与能正常工作的 collector 环）。；确认时间: 2026-09-19
- **Q2**: 用户答复：**选 (c)**——不做独立 D2，并入 Q1 的不动点判据。但要把 (b) 的诊断价值并进来：**若被拒的环里存在「同环内 required 数据入边」，必须在 `reason` 里点出这些边并给出「改成 `required: false`（或把回边改从 route 出发）」的建议**，保留 D2 原本的报错粒度。；确认时间: 2026-09-19
- **Q3**: 用户答复：**选「拒绝」**（原话：「直接拒绝吧，这种图没意义，但是要确保给到 llm 足够的信息引导他改正」）。**核心附加要求：报错信息必须足以让模型自己改对**——`_invalid_spec` 的返回体里没有 `workflow_id`，`reason` + `hint` 是模型唯一的信息来源，必须自足。错误信息必须含三要素：**哪个环**（成员节点 id）、**缺什么**（为什么跑不起来）、**怎么改**（可照做的具体动作）；D5 因此提级为本 change 的关键路径。；确认时间: 2026-09-19
- **Q4**: 用户答复：提示面核心规则用**「环里必须有个节点先跑起来，且它不能反过来等环里的东西」**，并配一个反例。不采用「环里必须有个会变的节点」——实测表明把 subagent 塞进环里敷衍过关也未必能让环转起来（Q1 场景）。；确认时间: 2026-09-19
- **Q5**（连带影响，grill 报告外由主 session 提出）: 用户答复：**采用 (甲)**——`tests/agent/subagent/test_terminal_honesty.py` 改为**绕过声明期校验、直接构造 `WorkflowSpec` 对象**，保住运行期「入边互等」诊断的覆盖。理由（用户已认可）：运行期诊断本身没错，它描述的是真实发生的状态，只是触发路径变窄（从「模型声明出坏图」变成「图在运行期因其它原因陷入互等」），测试应继续锁住它。；确认时间: 2026-09-19
