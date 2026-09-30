# Design: DryRunWorkflow — 零 token 模拟执行 workflow

## Context

`DeclareWorkflow` 是模型进入 workflow DSL 的唯一入口。它的 `spec` 参数在 #248 之后已是**从源码常量派生的嵌套 schema**（`agent/tools/builtin/subagents.py:517` 的 `_workflow_spec_schema()`），「域」（哪些合法值）可见了。但 #248 的验收实测暴露了一类 schema **结构性无法覆盖**的问题：

> **域可见了，运行期语义仍然不可见。**

改后残留的 17 条探针，逐条读下来全是「这张图的线怎么接、文本怎么流」——`foreach` 的 item 会不会注入、route 读的是谁的文本、回边带不带数据——**没有一条问「真实 LLM 会说什么」**。模型没有便宜的地方问这些，于是**手写一次性 workflow 去实测**（#248 基线自述：*"let me run a cheap probe to validate loop-dispatch semantics before committing to the full topology"*），代价 398,590 token / 498% 预算。

本 change 的核心命题：**把那件事内置化**——让模型能对着它**真正想用的那张图**，零 token 跑一遍，看数据往哪流。

### 已实测的机制事实（本设计的地基，不再重复验证）

以下全部由本 change 的 spike 实测得出（脚本与原始输出落 `research/`，下文逐一标注来源）：

| # | 事实 | 证据 |
|---|---|---|
| F1 | **`run()` 会落盘**。`_record_event`→`_workflow_store().append_event()`（`scheduler.py:714`）、`_write_root_result`→`save_result("root",text)`（`:3169`）、`_write_attribution`（`:1327`），落点是 `<workspace_root>/.asterwynd/workflows/<wf_id>/`（`workflow_store.py:56-60`） | `research/side_effects.py` 输出：一次普通 run 在真实 workspace 落 **11 个文件** |
| F2 | **默认 `graph_sink` 就是 `None`**（`manager.py:526`）。「去掉 sink」不是隔离手段——普通 run 本来就没 sink | `research/side_effects.py`：`graph_sink default = None` |
| F3 | **`run()` 会污染 manager 注册表**：`manager.register_workflow(self)`（`scheduler.py:829`）写 `_workflows`，`_workflow_store()` 写 `_workflow_stores` | `research/side_effects.py`：run 后 `_workflows = ['wf_836c837d']` |
| F4 | ⚠️ **`_launch_run` 不是 LLM 的唯一切入点**（**初稿写错，实测订正**）。它只是 `manager.run_subagent` 的唯一切入点；**第二条路径是 collect 聚合的压缩**：`_merge_contributions_bounded`（`:2399`）→ `_aggregator.merge()` → `LLMSummarizer(manager.llm)`（经 `_build_summarizer()` `:666-672`）。**该路径在 concat 超出聚合节点预算时触发，实测确实发生** | `research/summarizer_pollution.py`：leaf_chars=9000 时多出一次 `node_id=None` 的调用 |
| **F4a** | ⚠️ **该 summarizer 调用不可归因**：`current_node_id()` 在它执行时是 `None`（不在 `_launch_run` 的 contextvar 包裹内），且它**会覆盖聚合节点的产出**——实测 `root.summary` 从「两份 L 的拼接」变成假 LLM 的回复 `[SUMMARY-PLACEHOLDER]` | `research/summarizer_pollution.py` |
| F5 | **假 LLM 能通过 contextvar 知道自己是哪个节点**（`current_node_id()`，`agent/subagent/context.py`），**无需改调度器** | `research/nodeid.py`：每个节点看到自己的 id |
| F6 | **隔离可行**：一次性 manager + 假 LLM + 空 store ⇒ **真实 workspace 零落盘、真实 manager 注册表零污染** | `research/isolation.py` / `research/prototype.py`：`disk delta = (none)`、`_workflows = []` |
| F9 | **写入口有两个**（W1 = manager 的 `_write_result_artifacts` / W2 = scheduler 的 `_store`），但**都以 `workspace_root` 为路径根**——所以一次性 `workspace_root` 单独即可保证真实 workspace 零落盘；`_store` 替换只影响一次性目录里少写 2 个文件（8→6） | `research/sandbox_files.py` + `sandbox_noNull.py` 对照 |
| F7 | ⚠️ **调度器碰的 manager 属性是 14 个，不是 9 个**（**初稿漏了 `getattr` 形式**）。`self.manager.X` 形式 9 个：`config` / `find_run` / `workflow_store` / `register_workflow` / `register_workflow_bucket` / `release_workflow_bucket` / `max_active` / `max_queued_runs` / `cancel_subagent_run`；**`getattr(self.manager, ...)` 形式另 3 个**：`llm` / `graph_sink` / `cost_ledger`；**局部变量 `manager.X` 另 2 个**：`spawn_count_for` / `rejection_counts_for`。**漏掉 `llm` 是致命的**——它正是 F4 的第二条路径 | `rg 'self\.manager\.' + 'getattr\(self\.manager,' scheduler.py` |
| F8 | **成本极低**：小图 0.06–0.97s；chain-50 = 0.615s；foreach 受展开预算封顶（`foreach-50` 与 `foreach-20` 同为 22 次调用 = 20 项 + 2 个 auto 层，见 S5） | `research/perf.py` / `research/extra_calls.py` |

### 已实测的**语义**发现（本 change 要暴露给模型的东西本身）

这些是 spike 顺手测出来的真实语义，**它们正是探针想问的答案**：

| # | 发现 | 证据 |
|---|---|---|
| S1 | **route 读的是「直接上游节点自身的产出」**，不是更上游的文本 | `research/route_reads.py`：`a→mid→gate`，`gate.raw == mid.summary` |
| S2 | **但上游是 `aggregate` 时会回退到槽值**——`_node_output`（`scheduler.py:2478-2486`）先查 `state.slots`，`aggregate` 恰好填了槽，于是 route 读到的是**聚合结果**而非该节点 summary | `research/confirm_read.py`：三种形态对照，形态 2/3 的 `gate.raw` 都是 `FROM-LEAF`（聚合槽） |
| S3 | **route 回边会重跑循环体，但不投递文本**——`producer` 在 lap 1/2/3 收到的 prompt **逐字相同** | `research/rounds.py`：三次 lap 的 producer prompt 完全一致 |
| S4 | **盲回显（不传 script）时 route 必走 default**——因为占位输出永远不匹配任何 case | `research/prototype.py` CASE 1：`matched=null, used_default=true` |
| S5 | **执行计划里存在「自动插入层」，它们不在 `spec.nodes` 里，但会真的调 LLM**。实测：20 项 foreach 产生了 `__auto_agg__agg_0_0` / `__auto_agg__agg_0_1` 两个节点、各 1 次 LLM 调用（`research/extra_calls.py`：23 次调用 = 20 项 + 2 个 auto 层 + 1 个用户 agg） | `research/extra_calls.py` + `aggregation.py:40` `AUTO_NODE_PREFIX` / `:177` `inserted_nodes` |

> **S2 是一条尚未被任何测试钉住的语义**：`rg '_node_output' tests/` 只命中 `test_workflow_semantics_m1.py:305` 的注释（讲的是**另一个** bug：route 数据入边不做消费记账），没有任何断言覆盖「aggregate 上游 → route 读槽值」这条路径。四个内置模板无一命中该形态（`peer-review` 的 route 上游是 `reviewer` subagent，不是 aggregate）。**本 change 不修它**（不属本 change 范围，且改它 = 改调度语义），但 `DryRunWorkflow` 会把它**如实暴露**——这正是这个工具的价值：**让语义可见，而不是替模型决定语义对不对。**

---

## Goals / Non-Goals

### Goals

1. 新增只读工具 `DryRunWorkflow(spec, script?)`：零真实 LLM 调用、零持久副作用地模拟执行一张 workflow。
2. 返回**数据流报告**——`received` / `produced` / `route.input_seen|matched|walked_to|used_default` / `edges[].control` / 节点终态。字段名直接对应那 17 条探针在问的东西。
3. 允许 `script` 注入（what-if）：「假装 critic 输出 `GAPS`，图往哪走？」
4. 对报告的**有界性**与**可信边界**作显式声明。
5. **不修改 `scheduler.py` 的任何执行路径**——模拟复用既有 `run()`，隔离完全靠喂给它的依赖。

### Non-Goals

- 不改调度/门控/reducer/route 匹配/计数语义。
- 不产生可用的 workflow 结果（**不向真实 workspace 落盘**、不可被 `GetWorkflow` 查、不进注册表）。**注**：模拟**确实会**在一次性临时目录里写一些中间 artifact（W1/W2，见 D4）——那是隔离机制的实现细节，随 `TemporaryDirectory` 清理，**不构成「零写盘」**（措辞上须准确，别写成「不写任何文件」）。
- 不引入 `ValidateWorkflow`（#268 范畴）。
- 不做表达式求值（沿用 `matches_route` 的安全姿态）。
- 不修复 S2（那是调度语义，另议）。

---

## Decisions

### D1 — 工具形态：新工具，而非给既有工具加 `dry_run=true` 参数

**候选**：
- (a) **新增独立工具 `DryRunWorkflow`**；
- (b) 给 `DeclareWorkflow` 加 `dry_run: bool`；
- (c) 给 `RunWorkflow` 加 `dry_run: bool`。

**选 (a)**。理由：

1. **`DeclareWorkflow` 的描述已经很长**——实测 **3993 字符**（守卫上界 6000，`test_workflow_tool_discoverability.py:315`；**初稿误记为 5892，实测订正**）。往里塞**完整的** dry run 语义说明（schema + 用法 + 边界）会占掉相当一部分余量，而这个描述每轮都随工具面发给模型——**把 dry run 的说明放在 dry run 自己的工具上，比塞进声明入口更省、也更对位**。
2. **(b) 有语义陷阱**：`DeclareWorkflow` 是 `read_only` 注册动作，加 `dry_run` 会让一个本该幂等只读的调用产生两种形态。
3. **(c) 更糟**：`RunWorkflow` 在 `SPAWN_TOOL_NAMES`（`manager.py:437`）里，受 `max_depth` 撤工具管辖；dry run **不 spawn**，不该被深度限制牵连（同 `DeclareWorkflow` 的档位）。
4. **可发现性**：模型读工具列表就能看到 `DryRunWorkflow` 这个名字（带 `description`），比藏在 boolean 参数里更容易被想起来。

**形态**：`read_only = True`、`permission = SUBAGENT_CONTROL_PERMISSION`（与 `DeclareWorkflow` 同档，`subagents.py:799-800`）、**不进 `SPAWN_TOOL_NAMES`**。

**代价（如实记录）**：新增一个工具 = 每次 API 调用多一份 `description` + `schema` 的 input token。**缓解**：`spec` 的 schema 复用 `_workflow_spec_schema()` **同一份派生结果**（不新建第二份定义，也不新增派生成本），描述控制在 `DeclareWorkflow` 的 1/3 以内（见 D10）。

---

### D2 — 报告字段：以「探针在问什么」为设计输入，而非以「调度器有什么」为输出

**原则**：字段不是把 `NodeState` 直接 `to_dict()`，而是**逐条回答那 17 条探针**。

| 探针在问 | 报告里谁回答 | 取值来源 |
|---|---|---|
| foreach item 是否注入、占位符怎么写 | `nodes[].received`（foreach 的子节点 prompt） | 假 LLM 收到的 messages（F5） |
| route 读的是中间节点自身输出还是上游输入 | `nodes[route].input_seen` | `NodeState.raw`（`scheduler.py:1890`，route 判定文本） |
| route 重新求值时看 LATEST 还是累积 | `nodes[route].input_seen`（多次调用时的各轮值） | 同上，需按轮次记录 |
| 回边是否携带上游文本 | `nodes[].received`（被重派发节点的 prompt）+ `edges[].control` | 假 LLM messages + `spec.is_control_edge`（`workflow.py:261`） |
| bus channel 是否发布到总线 | `edges[].channel` | `WorkflowEdge.channel` |
| 某分支会不会跑到 | `nodes[].status`（`completed`/`skipped`/`blocked`） | `NodeState.status` |
| 回边能不能重跑 | `nodes[].runs`（>1 即重跑过） | `NodeState.runs` |

**`input_seen` 直接取 `NodeState.raw`**——它是 `_execute_route` 已经算好的**判定文本原文**（`scheduler.py:1890`：`state.raw = raw[:_SUMMARY_LIMIT]`）。这是「不新增第二份真相」的关键：报告**不重算** route 的判定输入，而是**读调度器自己用的那个值**。

**不返回 `slots` 全文**（除 route 需要时）：`aggregate` 的槽是 N 份 concat 的巨型字符串，整段回给父上下文就是打爆上下文——与既有 `parent_envelope` 的 bounded 纪律冲突（见 D5）。

**S2 的机制订正（grill 复核，须如实写）**：初稿说「上游是 aggregate 时会回退到槽值」——**表述过窄**。真实机制是 `_node_output`（`scheduler.py:2478-2486`）的三段：

1. **`slot in state.slots and state.node.kind != "subagent"`** —— 注意这个 **`!= "subagent"` 守卫**：**subagent 自己的槽永远不被这条读**；
2. 否则**沿该节点自己的数据入边向上找**，返回**第一个**有该槽的上游的槽值（**可能跳到两跳以上**）；
3. 都不中才回退 `state.summary`。

所以准确表述是：**一个 subagent 节点在 route 眼里「自身产出」是会被它的聚合上游顶掉的**——因为守卫 (1) 不读它自己的槽，而 (2) 会向上走。**这解释了 S1 与 S2 为何同时成立**：`a→mid→gate` 里 `mid` 的上游 `a` 没有槽 → 走到 (3) 返回 `mid.summary`（S1）；`agg→critic→gate` 里 `critic` 的上游 `agg` 有槽 → 走 (2) 返回 `agg` 的槽（S2）。

**这个机制导致一个报告缺口（grill 发现）**：报告只给 `input_seen` 的**文本**，不给**它来自哪个节点**。模型要自己拿文本去比对 `produced` 才能推断——而文本被截断到 240 字符时**比对可能失败**。**修法**：报告 SHALL 为 route 额外给出**判定输入的来源节点 id**（`input_source`），它可由同一次 `_node_output` 调用顺带记录。→ 这是 **Q6** 的一部分。

**必须报告「自动插入层」（实测缺口 G3，research/extra_calls.py）**：

执行计划（`ExecutionPlan`）会**自动插入 aggregate 层**来降低扇入宽度（`aggregation.py:40` `AUTO_NODE_PREFIX = "__auto_agg__"`，`plan.inserted_nodes` 记录它们，`scheduler.py:3114` 已把它们暴露给快照）。实测：**20 项 foreach 插入了 2 个 auto 层节点，各真的调了 1 次 LLM**——即「模型声明 2 个节点」的图，实际跑了 4 个节点的活。

**若报告只遍历 `spec.nodes`，这些节点会被整个吞掉**——而它们恰好是「模型猜不到会发生什么」的典型：**模型写 20 项 foreach 时不会知道有个 auto 层会被插进来、更不知道它会改拓扑、还会产生额外 LLM 调用。**

修法：报告的节点列表 SHALL 基于**执行计划**（`plan.nodes`）而非 `spec.nodes`，并给每个节点标 `auto_inserted: true/false`（取自 `plan.inserted_nodes`）。这样：
- 拓扑是**真实的**（模型看到的就是会跑的图）；
- 同时能区分「这是你声明的」与「这是系统替你插的」——后者正是最需要被看见的信息。

**`received` 的寻址必须是 `(node_id, item_index)`，不是 `node_id`（实测缺口 G1，research/foreach_gap.py）**：

`current_node_id()` 对 foreach 的**每一个展开项返回同一个 id**（项间不区分）——实测 `fan` 展开 3 项，3 次 LLM 调用看到的 `node_id` 全是 `'fan'`，但 task 分别是 `propose alpha` / `propose beta` / `propose gamma`。若 `received` 直接按 node id 建 dict，**3 项会坍缩成 1 项**（实测：`fan.received` 只剩最后一项 `'propose gamma'`）。

这是本 design 初稿的一个真实缺口，修法：`received` SHALL 按 **`(node_id, item_index)`** 寻址（非 foreach 节点的 `item_index` 为 `null`）；报告里 foreach 节点的 `received` SHALL 是一个**按项排列的列表**，让模型能看到「N 项各自收到了什么」。**这同时回答了探针 #1（「foreach item 是否注入」）——坍缩掉就答不了。**

---

### D3 — 假 LLM：回显 + 可选 `script` 注入

**默认行为（不传 `script`）**：假 LLM 回显它收到的 prompt，并按节点 id 打标（`[{node_id} produced: auto]`）。

- 回显形态**有业界依据**：`deepseek-harness` 的 `MockDelegatingAdapter.stream()`（`packages/subagent/subagent-dsh-sdk/tests/fixtures/loader/mock-delegating-llm.ts`）就是「把上一轮 tool result 回显拼进回复、不发起真实调用」，与本设计同构（RIR RQ4 / finding 3）。
- **必须回显而非固定返回 `"ok"`**：固定值看不到「节点 X 收到的是 `[w1 的输出]` 还是 `[累积的所有轮次]`」——而后者正是 S3 要暴露的东西。
- **只返回文本、不发起 tool call**——否则就不叫 dry run（会真的执行工具）。

**`script` 参数（what-if 注入）**：`{"critic": "GAPS: missing tests"}`。

**为什么必须有（S4 逼出来的）**：**盲回显时 route 必走 default**（`research/prototype.py` CASE 1）——占位输出永远不匹配任何 case。于是「如果 critic 说 `GAPS`，图往哪走？」这个**最容易问出口的 what-if** 反而答不了。没有 `script`，工具只能画 happy path，价值折半。

**无先例，须自证（RIR RQ2 / finding 4）**：本地 6 个参考仓库**没有**「按节点 id 注入输出」的接口。最接近的是 `pi` 的 `setResponses`（`pi/packages/ai/src/providers/faux.ts:140`），但那是**按调用顺序排队**（`pi/packages/ai/README.md:1469`: `Responses are consumed from a queue in request start order`），不是按节点。**按节点 id 注入是本设计的自创**，其必要性来自 S4——顺序队列在循环图里会因重跑而错位，节点 id 是**唯一稳定的寻址方式**。

**`script` 的语义边界（必须写清，否则又是一个静默陷阱）**：
- 键是**节点 id**；值是**该节点的产出文本**。
- **只在「该节点的 LLM 调用」处生效**——对 `aggregate`（`collect` 策略）/`route` 这类**不产生 run 的节点**（`_execute_route` 不调 LLM、`collect` 聚合不产生 run），`script` **无效果**，报告 SHALL 说明。
- 未指定的节点走默认回显。
- **$\text{foreach}$ 节点：`script[node_id]` 会命中该节点的每一个展开项**（实测缺口 G1：项间不区分 node id）。**按项注入（项 A 输出 X、项 B 输出 Y）是一个未解决的设计点** → 见 Open Question Q1。
- **是否支持「按轮次的不同输出」**（如 lap 1 说 `GAPS`、lap 3 说 `APPROVED`）→ 见 Open Question Q1。

**实现位置**：`script` 映射在假 LLM 内部按 `current_node_id()` 查表（F5），**不改调度器**。要支持按轮次/按项，需在假 LLM 内额外计数（项下标可从任务的 `{index}` 渲染或调用序推断）——**仍在假 LLM 内**，仍不改调度器。**这个「怎么在不改调度器的前提下拿到项下标」是 Q1 拍板后的实现细节，须在实现时验证。**

> **占位符语法（实测订正）**：foreach 的模板占位符是 `{item}` / `{index}`（`render_item_task`，`scheduler.py:369-380`），**不是 `$item`**。本 design 早期的探针脚本误用了 `$item`，导致替换不生效——实现与测试中一律用 `{item}`。

---

### D4 — 隔离：一次性 manager + 空 store，**不动 `scheduler.py`**

**这是本 change 最重要的设计承诺。**

**候选**：
- (a) 加 `scheduler.run(dry_run=True)` 分支，在 `run()` 内部短路所有落盘/注册；
- (b) **一次性 manager（独立 workspace root）+ 空 store + 假 LLM**，`run()` 原样调用；
- (c) 复制一份调度器逻辑做模拟。

**选 (b)**。理由：

1. **(a) 要改 `scheduler.py`**——在 `run()`/`_record_event`/`_write_*`/`_emit_*` 四处加条件分支。这是「可观测性通道反向影响执行」的温床（该文件自己的 docstring 就在警告这个，`scheduler.py:722`）。而且**每次改调度器都是一次语义回归风险**。
2. **(c) 必然与真调度器漂移**——模拟的意义是「跑的语义和真跑一样」，复制一份就失去了这个保证。
3. **(b) 的危险面已被实测封住（F1–F7）**：
   - **落盘**：写入口有**两个**（W1 manager / W2 scheduler，见下文订正），但**两者的路径根都是 `workspace_policy.workspace_root`**——所以**一次性 workspace_root 单独就能保证真实 workspace 零落盘**（实测确认）。`_store` 替换是额外的显式化手段（可选，见 Q2）。
   - **注册表污染**：`run()` 里会 `manager.register_workflow(self)`（`:829`）——但那是**一次性 manager 自己的注册表**，随局部变量一起丢弃，**真实 manager 不被触碰**（F6 实测：`real_mgr._workflows == []`）。
   - **事件 sink**：`_emit_graph_event` 读 `self.manager.graph_sink`（`:730`）——一次性 manager 的该属性**默认就是 `None`**（F2），天然静默。
   - **LLM**：`_launch_run` 是唯一切入点（F4），喂假 LLM 即可。
   - **真实 LLM 的调用数 = 0**：这必须是**测试断言**，不能是「应该不会」（见 tasks T-3 的变异验证）。

**⚠️ 实测订正（G2，`research/sandbox_files.py`）：写入口有**两个**，不是 design 初稿说的一个。**

design 初稿写「`_store` 是唯一的写入口」——**这是错的**。实测枚举发现第二条写路径：

| # | 写入口 | 覆盖它的是 | 落盘内容 |
|---|---|---|---|
| W1 | `manager._write_result_artifacts`（`manager.py:1353`，由 `_complete_run` `:1218` 调）→ `manager._workflow_store(workflow_id)`（`:1400`）→ `WorkflowStore.for_workspace(self.workspace_policy.workspace_root, ...)` | **一次性 manager 的 `workspace_root`** | 每个 run 的 `.txt`/`.summary.txt`/`.transcript.txt` |
| W2 | `scheduler._store`（经 `scheduler._workflow_store()`，`scheduler.py:681`） | **`_store` 替换** | `events.jsonl` / `root.txt` / `*.attribution` |

实测（`research/sandbox_files.py`）：只换 `scheduler._store` **不能**阻止 W1——一次性目录里仍有 **6 个文件**（全是 W1 写的）。不换 `_store` 时是 **8 个**（多出 W2 的 `events.jsonl` + `root.txt`）。

**关键结论（这反而让隔离更简单）**：

- **W1 与 W2 都锚定在 `self.workspace_policy.workspace_root`**——而模拟用的是**一次性 manager + 一次性 workspace_root**。所以**「真实 workspace 零落盘」由「一次性 workspace_root」单独保证**，根本不需要碰 `scheduler._store`。
- 实测确认：真实 workspace 的 `disk delta = (none)`、sentinel 完好（F6），且所有写都落在一次性目录里（随 `TemporaryDirectory` 清理）。

**因此 `_store` 替换是「锦上添花」而非必需**：

- **(i) 不换 `_store`**：一次性目录里有 8 个文件（含 `events.jsonl`），真实 workspace 照样零落盘。**零私有属性依赖、零生产代码改动。**
- **(ii) 换 `_store`（`scheduler._store = NullStore()`）**：一次性目录里只剩 6 个（W1 的），**且能显式断言「没有 workflow 事件/根结果被写出」**；代价是依赖一个私有属性名。

**倾向 (ii)**——虽然真实 workspace 两种都安全，但 (ii) 让「模拟不产生任何 workflow 级 artifact」成为**可断言的显式性质**（T-1/T-2 因此更强），而私有属性依赖有机械测试兜底（R2）。**因为这个取舍变了（不再是「安全 vs 不安全」而是「更强的断言 vs 零私有依赖」），重新列为 Open Question Q2。**

**隔离的完整性检查（实现时必做，见 tasks）**：模拟跑完后断言
1. 真实 `workspace_root` **零新增文件**（F1/F6）；
2. 真实 manager 的 `_workflows` / `_workflow_stores` **为空**（F3/F6）；
3. 真实 manager 的 `llm.chat` 调用数 **= 0**（F4）；
4. 真实 manager 的 `graph_sink` **未被调用**（F2）；
5. **（仅当 Q2 选 B）一次性临时目录里**的 workflow artifact 数 = 0，即 `events.jsonl`/`root.txt` 都不存在（G2）。
（1–4 已有 spike 支撑；5 由 G2 的对照实测给出预期值。）

---

### D4b — **必须切断 collect 聚合的 summarizer 路径**（F4/F4a 逼出来的硬要求）

**问题**：`_merge_contributions_bounded`（`scheduler.py:2399`）在 concat 超出聚合节点预算时，会调 `_aggregator.merge()` → `LLMSummarizer(manager.llm)`。在 dry run 里那是**假 LLM**，后果有两个（均已实测，`research/summarizer_pollution.py`）：

1. **报告会说谎**：聚合节点的 `summary`/`slots` 变成假 LLM 的占位回复，**而不是上游文本的拼接**。而 `summary`/`slots` 正是「回边带不带数据」「route 读到什么」的答案来源——**报告的核心价值被这条路径污染**。
2. **调用不可归因**：该调用发生时 `current_node_id()` 是 `None`（不在 `_launch_run` 的包裹内），会在 `received` 里多出一个 `None`/`?` 键。

**为什么不能靠「假 LLM 好好回答」绕过**：假 LLM 无法在**不知道自己在做压缩**的情况下给出「拼接」这个正确的语义——它看到的是「多份文本」，而正确产出是「把它们拼起来」。**让假 LLM 猜这个语义就是模拟与真实漂移。**

**三个候选**：
- **(a) 让假 LLM 对该调用返回「上游文本的拼接」**——需要假 LLM 能识别「这是压缩调用」，脆弱且它并不总能正确重建拼接语义（reducer 可能是 `merge_dict`/`last`）。
- **(b) 在 dry run 里把聚合节点的预算调到极大**（如 `budget = +inf`），使 `len(merged) <= budget * CHARS_PER_TOKEN` 恒真、**永不进 summarizer**——单点、不碰生产代码，但改变了「预算」这一模拟条件（报告里的截断行为会与真实运行不同）。
- **(c) 用一个「结构感知的假 summarizer」替换 aggregator 的 summarizer**（如 `TruncationSummarizer`，它**就是**无 LLM 时的既有兜底，`aggregation.py:88`）——`WorkflowAggregator(summarizer=TruncationSummarizer())`。**这是既有代码里现成的降级路径**，语义上正好是「没有 LLM 时怎么办」。

**倾向 (c)**。理由：`TruncationSummarizer` 是**既有生产路径**（无 LLM 时的兜底），不是为模拟造的新东西；它产出的是**有界的拼接/截断**——正是 dry run 想展示的「文本怎么流」。而且 (c) 只需在构造 scheduler 后改一个属性（或 Q2 若选构造参数则一并注入），**不碰 `scheduler.py` 的执行逻辑**。**(b) 的问题**是它让报告对「预算截断」撒谎——而预算是模型需要看到的真实约束。**(a) 最差**，它让假 LLM 承担它无法可靠承担的语义。

> **注意**：**(c) 使「collect 聚合的产出」在 dry run 里是截断拼接而非语义压缩**——这是**正确的模拟**（真实无 LLM 时就长这样），但报告 SHALL 说明「聚合节点的产出在此为截断投影」。**这是 Q6**（新增，见 Open Questions）。

### D5 — 有界性：所有文本截断，复用既有 bounded 纪律

- 报告里每个文本字段按 `max_report_chars`（默认值见 Open Question Q3）截断，附 `…[+N chars]` 标记（与 `WorkflowAggregator.bounded` 的标记风格一致，`scheduler.py:2570`）。
- **`slots` 不在默认报告里**（D2）；若 Open Question Q4 决定暴露，须**单独截断**且不与 `received` 混在一层。
- 理由：与既有 `parent_envelope` 的 bounded 投影纪律同源（`scheduler.py:3119`）——父 agent 永远只拿 bounded 面。

---

### D6 — 边界声明：**断言式**措辞，不是散文式提醒

**依据**：RIR RQ3 / finding 5——`codex` 的 `Dry-run (no API call; no network required; ...)` 用的是**可机械判定的断言**，不是「请注意这只是模拟」。本 change 采用同样的风格：

- 工具 `description` SHALL 含一句**断言式**声明（形如「This makes **no model calls** and writes **nothing**; it shows topology and data flow, not what a model would say.」）。
- 返回体 SHALL 含一个**固定字段**（如 `simulated: true`）与一条 `notes` 文案，让模型在任何一次调用后都能看到边界——**不能只在描述里说一次**（模型可能读了描述但报告里看到像模像样的 `produced` 就忘了）。
- **必须显式写出的不可答项**：「真实 LLM 会不会真的输出 `APPROVED`」——dry run **答不了**。不写清会变成新的假安全感（#248 的教训是「模型会把示例学错」，不只是「示例不够」）。

**为什么这条是硬性的**：RIR finding 7 指出，**业界所有假 LLM 都在测试基建层，没有一个包成模型可调用的工具**。本 change 是把测试基建产品化——**没有现成模板可抄**，所以「如何防止模型把它当真实执行」必须由本设计自己承担（见 D8）。

---

### D7 — 防滥用：调用上限，仿 deepseek 的 runaway-loop backstop

**依据**：RIR RQ5 / finding 6——`deepseek-harness` 的做法是 `maxTotalAgents`（默认 1000）+ 越界文案 `this run reached its total agent cap (...) — a runaway-loop backstop; raise the applicable maxTotalAgents limit if the scale is intentional`。

**本 change 做同构迁移**，但**要解决的滥用形态不同**：
- deepseek 防的是「一张图内部 spawn 失控」；
- 本 change 要防的是「**模型反复 dry run 同一张图**」——#273 issue 的「成本与滥用」节明确要求验收看这个。

**方案候选**：
- (a) **per-session 调用上限**（如 20 次），越界给可读原因 + 提高路径；
- (b) 不设界，只在验收里观察是否形成循环；
- (c) 设界但只在报告里提示「你已经 dry run 了 N 次」。

**倾向 (a)**，理由：dry run 虽然零 token，但**每次仍是一次工具调用往返**（消耗父 agent 的迭代与上下文）——#248 的教训就是「模型迷路」会被放大成巨额代价。设界是廉价的保险。

**但「界设在哪一层」是一个真实的设计问题** → 见 Open Question Q5。

---

### D8 — 无先例风险：**「模型把模拟当真实执行」单独处理**

RIR findings 1 / 4 / 7 共同指出：**本地 6 个参考仓库没有一个「面向模型的零成本模拟工具」**。这带来两类本 change 独有的风险，**必须在 design 里单列**（因为无模板可抄）：

| 风险 | 后果 | 缓解 |
|---|---|---|
| 模型把 `produced` 的占位文本当成真实产出 | 以为「图已经跑过了」，不去 `StartWorkflow` | D6 的断言式边界 + 报告里 `produced` 值带 `auto` 标记（D3） |
| 模型用 dry run **替代**真实运行 | 任务没完成却以为完成了 | `DryRunWorkflow` 的 `description` **SHALL NOT** 出现「run」「execute」的完成时态承诺；工具**不返回** `workflow_id`（无 id = 无法被 `StartWorkflow` 误用） |
| 模型对同一张图反复 dry run | 迭代浪费 | D7 |

**关键设计约束（由本风险推出）**：`DryRunWorkflow` **不返回 `workflow_id`**。理由：一旦返回 id，模型可能把它拿去 `StartWorkflow` / `GetWorkflow`——把一个「不存在的运行」当存在。报告里用 `simulated: true` 明确状态，**没有任何可被后续工具消费的标识符**。

---

### D9 — 测试策略

见下节 `## Testing Strategy`。

---

## Risks / Trade-offs

| # | 风险 / 取舍 | 严重度 | 缓解 |
|---|---|---|---|
| R1 | **模型把模拟当真实执行**（`produced` 占位被当成真产出、或用 dry run 替代真实运行） | **高** | D6 断言式边界 + D8「不返回 `workflow_id`」+ 报告 `simulated: true`；RIR finding 7 证明**业界无先例可抄**，故必须自证 |
| R2 | **隔离静默失效**（G2 实测后**降级**）：真实 workspace 的安全性由「一次性 `workspace_root`」保证，**不依赖 `_store` 替换**；`_store` 只影响一次性目录里少写不写 W2 的 2 个文件 | **低** | T-1/T-2 断言真实 workspace 零落盘；T-3 做变异验证（把假 LLM 换回真 LLM 必须变红） |
| R3 | **报告本身打爆父上下文**：大图的 `received` 全量拼接会很大 | 中 | D5 有界 + 全部字段截断；F8 实测大图 `received` 受 bounded 投影约束 |
| R4 | **新增工具的常驻 token 成本**（描述 + schema 每轮都发） | 中 | 描述 ≤2000 字符（D10）；schema 复用同一份 `_workflow_spec_schema()`，不新增派生成本 |
| R5 | **`script` 是无先例设计**，可能被误用（对不产生 run 的节点注入却以为生效） | 中 | D3 明确「只对会调 LLM 的节点生效」并写进描述与报告；T-8 覆盖 |
| R6 | **模型反复 dry run** 形成新的试探循环 | 中 | D7（Q5 待拍板）；验收 S7 负面检查 |
| R7 | **`DeclareWorkflow` 描述压不进 6000 守卫**（若 Q4 选「加指针」） | 低 | 指针极短；压不下就放弃引导（主引导在 `DryRunWorkflow` 自己描述里） |
| R8 | **模拟与真实执行的语义漂移**（未来 `scheduler.run()` 变了而模拟没跟） | 低 | D4 选「复用 `run()`」从机制上消除——**这正是 (b) 优于 (c) 的核心理由** |
| R9 | **T-7 断言 S2 现状被误读为「批准了 S2 的语义」** | 低 | tasks 2.7 显式写明「断言的是报告如实反映现状，不是现状是对的」 |

**最大的取舍（必须让用户知道）**：本 change 交付的是一个**模型可能不会用**的工具——D10 的可发现性引导是**尽力而为**，不是保证。#248 的实测已经证明「模型会跳过工具描述直接用」。**若改后 S0 仍不为 0，归因必须落到「模型没想起来用它」还是「用错了」，而不是默认工具没用**（见验收 4.5 的软判断）。

## Testing Strategy

**必须新增** `tests/agent/subagent/test_workflow_dry_run.py`：

| # | 测什么 | 断言要点 |
|---|---|---|
| T-1 | **隔离·落盘** | 模拟后真实 `workspace_root` 零新增文件（F1/F6） |
| T-2 | **隔离·注册表** | 真实 manager 的 `_workflows`/`_workflow_stores` 为空（F3/F6） |
| T-3 | **隔离·零 token** | 真实 `manager.llm.chat` 调用数 = 0。**变异验证**：把假 LLM 换回真 LLM，测试必须变红 |
| T-4 | **隔离·sink** | 真实 manager 的 `graph_sink` 未被调用（F2） |
| T-5 | **数据流·received** | `foreach` 展开项的 prompt 含 item；下游节点 prompt 含上游 bounded 产出 |
| T-6 | **数据流·input_seen（S1）** | `a→mid→gate` 时 `gate.input_seen == mid` 的产出 |
| T-7 | **数据流·input_seen（S2）** | `aggregate→critic→gate` 时 `gate.input_seen` 是**聚合槽值**——把这条未钉住的语义**固化为断言** |
| T-8 | **`script` 注入（S4）** | 不传 script → route 走 default；传 `{"critic": "GAPS"}` → route 走回边 |
| T-9 | **回边不带文本（S3）** | 回边重跑时被重派发节点的 `received` 与首轮**相同** |
| T-10 | **有界性（D5）** | 超长产出被截断到 `max_report_chars` |
| T-11 | **边界声明（D6）** | 返回体含 `simulated: true` 与边界文案；**不含 `workflow_id`**（D8） |
| T-12 | **schema parity** | `DryRunWorkflow.spec` 的 schema 与 `DeclareWorkflow.spec` **逐字相等**（同一份 `_workflow_spec_schema()`） |
| T-13 | **工具面** | `DryRunWorkflow` **不在** `SPAWN_TOOL_NAMES`；depth 撤工具时不撤它 |

**T-7 的意义**：S2 是一条**没有测试保护的现存语义**。把它写成断言有两个作用——(1) 锁住 dry run 的**报告正确性**（报告必须如实反映 S2）；(2) 让 S2 的语义**显式化**（未来若有人改 `_node_output`，会立刻看到「这会影响 dry run 报告」）。**注意 T-7 断言的是「报告如实反映现状」，不是「现状是对的」**——判据要写清，避免被误读为「批准了 S2 的语义」。

### D10 — 描述预算与可发现性引导

- `DryRunWorkflow` 的 `description` SHALL ≤ **2000 字符**（`DeclareWorkflow` 实测 3993；本工具是辅助工具，应更短）。新增守卫测试。
- **主引导放在 `DryRunWorkflow` 自己的描述里**，`DeclareWorkflow` 描述只加**一句**指针。
- 理由：`DeclareWorkflow` 描述已 3993/6000（**有余量但不多**，且每轮都发），把 dry run 的**完整**说明放过去不划算；且「不确定语义时先 dry run」这句话放在**被调用方**（`DryRunWorkflow`）比放在**声明入口**更合适——模型决定「我要不要 dry run」时，看的就是这个工具。**但既然有余量，加一句极短指针是低风险的**（见 Q4）。
- **但「模型会不会想起来有这个工具」是不可保证的** → 见 Open Question Q4。

---

## Open Questions（**停轮交用户确认，每条配具体例子**）

> 以下 **6 条**（Q1–Q6）**刻意未拍板**。grill-confirmation-gate 未通过前，实现不得开工。

### Q1 — `script` 怎么表达「随轮次 / 随项变化」？

**背景**：同一个节点会被调用多次——循环图里按**轮次**重复，foreach 里按**项**重复。这是两个不同维度，但同一个机制要解决它们。实测缺口 G1（`research/foreach_gap.py`）证明：**按 node id 建表会让 N 个展开项坍缩成 1 个**，所以这不是"锦上添花"，是**必须解决**。

**具体例子（维度一·轮次）**：图是 `producer → reviewer → gate(route) → 回边到 producer`，你想知道「这个环转几圈才收敛」。
- **方案 A（单值）**：`script: {"reviewer": "APPROVED"}` → 环**一圈都不转**，你看不到第二、三轮的 `received`。
- **方案 B（有序列表）**：`script: {"reviewer": ["GAPS: tests", "GAPS: docs", "APPROVED"]}` → 环转 3 圈后收敛，报告里第 2、3 圈的 `received`/`input_seen` 都可见。

**具体例子（维度二·项）**：`fan(foreach, items=["alpha","beta","gamma"])` 展开 3 项，你想验「不同项拿到不同 task」。
- **方案 A（单值）**：`script: {"fan": "done"}` → 3 项产出**完全相同**；但 `received` 里仍能看到 3 项各自的 task 是 `propose alpha`/`beta`/`gamma`（这部分不需要 script 就能看到）。
- **方案 B（按项列表/字典）**：`script: {"fan": ["a-out","b-out","c-out"]}` 或 `{"fan": {"alpha": "a-out"}}` → 能验「项 A 产出 X 时下游聚合出什么」。

**三个候选方案**：
- **(a) 不支持序列，单值 + 按项展开仍可见**：最简单。循环收敛与按项注入**都答不了**，但 `received` 仍能显示每项收到的 task（G1 的坍缩问题用列表寻址解决，与 script 无关）。
- **(b) 支持「字符串或字符串数组」**：数组在循环里**按轮次**消费、在 foreach 里**按项**消费（同一语法，两种语义——**有歧义风险**：一个节点既在循环里又被展开时怎么算？）。
- **(c) 显式两种形式**：`script: {"reviewer": {"laps": [...]}, "fan": {"items": [...]}}`——**无歧义，但 schema 更重**。

**代价对比**：#248 RIR 已实测**顶层 `oneOf` 在部分 provider 上受限**，所以 (b)/(c) 都要用「两种类型并列 + 运行期判别」的写法（参考 `pi` 的 `modeCount` 判别，RIR RQ3）。**(a) 零 schema 复杂度**，但对「循环收敛」这个**最容易问出口的 what-if** 失明。

**我的倾向**：**(b)**，并在描述里写明「数组按『该节点被调用的次序』消费」——**轮次与项的统一口径就是「调用次序」**，这样歧义消解（同一次调用不可能既是第 2 轮又是第 3 项）。理由是 S3（回边不带文本）这类**最反直觉的语义只有在第二轮才能观察到**，(a) 会让工具对循环失明（而循环是这个 DSL 最复杂的部分）。**但这确实引入 schema 复杂度，请你拍板。**

> **不论选哪个，G1 的修法（`received` 按 `(node_id, item_index)` 寻址、foreach 的 received 是列表）都要做**——它与 script 无关，是 D2 的正确性要求。

### Q2 — 要不要额外替换 `scheduler._store`？（G2 实测后**问题变了**）

**背景**：D4 发现写入口有两个（W1 manager / W2 scheduler），真实 workspace 的安全性**由一次性 workspace_root 单独保证**。所以这条**不再是「安全 vs 不安全」**，而是「要不要多写一点代码换更强的断言」。

**具体例子**（都在一次性临时目录里，真实 workspace 两种都零落盘）：
- **方案 A（不换 `_store`）**：临时目录里有 **8** 个文件（含 `events.jsonl` 与 `root.txt`）。
  - 好处：**零私有属性依赖、零生产代码改动**——隔离完全靠「给了一次性 workspace_root」这个不涉及任何私有名的机制。
  - 代价：无法断言「没有 workflow 事件被写出」（因为确实写了，只是在一次性目录里）。
- **方案 B（构造后 `scheduler._store = NullStore()`）**：临时目录里 **6** 个文件（W1 的）。
  - 好处：能**显式断言**「模拟不产生任何 workflow 级 artifact（事件/根结果/归因）」——断言更强，语义更清楚。
  - 代价：依赖 `_store` 私有属性名；若被重构掉会**静默降级**成 8 个文件（不影响安全，只影响断言的强度）。
- **方案 C（给 `WorkflowScheduler.__init__` 加 `store=` 参数）**：显式、不依赖私有名，但**改生产代码**。

**我的倾向**：**B**。理由是它让 T-1/T-2 的断言从「真实 workspace 零落盘」（A 也能过）升级到「**模拟不产生任何 workflow artifact**」——后者才是 `DryRunWorkflow` 想承诺的语义。且它的降级模式是**安全**的（私有名没了 → 变回 A 的行为，真实 workspace 照样安全）。**请你拍板。**

### Q3 — `max_report_chars` 的默认值取多少？

**背景**：D5 的截断上界。

**具体例子**：假设 `received` 字段里，`critic` 节点收到了 `merge` 投递过来的一段长文本。
- 取 **240 字符**：够看到「文本的开头长什么样、是不是我预期的那个上游」（判断数据流对错通常只需要开头），但长文本的**尾部信息丢失**。
- 取 **800 字符**：看到更多，但一张 10 节点图的报告可能到 8KB——**父上下文成本上升**。

**我的倾向**：**默认 240，并在报告里带「被截断了，完整值可用 `script` 复现或直接 RunWorkflow 看」的提示**。理由是 dry run 的目的是**看数据往哪流**（拓扑判断），不是**读内容**（那是真实运行的事）。但这个数字应该由**模型实际怎么用**来决定，所以交你拍板（也可选「让调用方传参、默认 240」）。

### Q4 — `slots` 要不要进报告？可发现性引导放哪？

**这是两个相关的小决策，合并成一条问。**

**具体例子（slots）**：`aggregate` 节点的 `slots` 是它把 N 个上游 concat 后的**巨型字符串**。`S2` 告诉我们 route 读的正是这个槽值——所以「route 为什么读到 `FROM-LEAF`」的完整答案**在槽里**。
- **不返回 slots**：报告干净、有界；但模型看到 `input_seen` 是聚合结果时会疑惑「它从哪来的」，得**再 dry run 一次**或去读描述。
- **返回 slots（截断后）**：能直接看到「槽里是什么」；但每个 aggregate 节点都带一个字段，**报告体积上升**。

**具体例子（引导位置）**：
- **只放 `DryRunWorkflow` 自己的描述**：模型**读到了**这个工具的描述才会想起来用。若它压根没读（#248 实测模型会跳过工具描述直接用），就白搭。
- **在 `DeclareWorkflow` 描述里也加一句**（如「Unsure how the graph will route? Dry-run it first.」）：更可能被看到；`DeclareWorkflow` 实测 3993/6000 **有余量**，加一句（~60 字符）**不需要压缩既有分节**（初稿以为要塞不下，实测订正）。

**我的倾向**：**slots 返回（截断，单独字段）；引导放 `DryRunWorkflow` 描述为主，`DeclareWorkflow` 加一句极短指针（若压不下 6000 就放弃）**。交你拍板。

### Q5 — 防滥用上限设在哪一层？

**背景**：D7。

**具体例子**：模型在写图时反复 dry run（每次微调一下 spec 再 dry run），一轮任务里调了 30 次。
- **方案 A（per-session 上限，如 20 次）**：第 21 次返回 `{"status": "dry_run_limit_reached", "reason": "...", "hint": "..."}`。**可能误伤**合法的「反复调试图」场景（这恰恰是我们要鼓励的行为！）。
- **方案 B（不设界）**：不限制，靠验收观察。**可能失控**（但 dry run 零 token，失控的代价只是迭代次数）。
- **方案 C（软提醒）**：到 N 次后在报告里加一句「你已经 dry run 了 N 次，考虑直接 RunWorkflow？」。**不阻断**，只提示。

**我的倾向**：**C**。理由：dry run 是**我们主动引导的行为**（D10 就是让模型多用它），设硬界等于**惩罚正确的行为**；而它零 token、亚秒级（F8），滥用代价远低于 #248 的探针循环。软提醒能覆盖「模型陷入死循环」的极端情况，又不误伤调试图。**但 A 的理由也成立**（防止「用 dry run 代替思考」），所以交你拍板。

---

### Q6 — 聚合产出在 dry run 里是「截断拼接」而非「语义压缩」，且 route 判定输入需要来源（D4b + S2 订正逼出来）

**这是两个相关的报告正确性问题，合并一条。**

**具体例子（聚合产出的语义）**：一张 `a → root(aggregate, collect)` 图，两份上游产出各 9000 字符。
- **真实运行**（有 LLM）：`root.summary` 是 LLM **语义压缩**后的摘要（~3000 token）。
- **dry run（选 (c) 后）**：`root.summary` 是**截断拼接**（`TruncationSummarizer`）——**内容形状不同**。
- 问题：这**是不是**会误导？一方面它如实反映「无 LLM 时的行为」，另一方面模型可能以为「真实跑出来也是这个」。
- **方案 A**：报告里明说「聚合节点产出为截断投影（无 LLM 语义压缩）」。
- **方案 B**：干脆不报 `produced` 的聚合内容，只报「它收到了什么」。**但那样模型就看不到「聚合后文本长什么样」，而这正是 S2（route 读到聚合槽值）的关键。**

**具体例子（`input_source`）**：`agg → critic → gate`，`gate.input_seen = "FROM-LEAF"`（S2）。模型看到这串文本会问「这是 critic 说的还是 agg 说的？」
- **不加 `input_source`**：模型得把文本和 `produced` 逐一比对；截断到 240 字符后可能比对不出。
- **加 `input_source: "agg"`**：一眼看到「route 读的是 agg 的槽」。

**我的倾向**：**A（明说）+ 加 `input_source`**。两者都是「把真相说清楚」而非「改变行为」，与本 change 的宗旨一致。**请你拍板。**

## Pre-Implementation Review

- **本 change 是 `feature` 类型**（新增工具 = 新增能力面）→ **实现前必须走 `batch-grill-me` + 停轮确认 Q1–Q6**。
- **机械门禁**：
  - 触及受保护路径 → 需 `current_spec_synced` / `backlog_updated` 结构化事件；
  - 需 grill 证据（`reviews/grill-design.md`，≥3 条 Confirmed Decisions + Open Questions 全部有 User Confirmation）；
  - 实现完成后需 `/review-loop` + `reviews/building-review.md`（PASS + manifest）。
- **实现工作区**：独立 worktree，分支 `workflow-dry-run/2026-09-30`。
- **要回写的事实**（实现若发现与本 design 不符，先停轮回写）：D4 的「不改 `scheduler.py`」、D2 的 `input_seen ← NodeState.raw`、D8 的「不返回 `workflow_id`」。

---

## Impact Analysis（design 视角的补充）

见 proposal 的同名节。design 补充两条：

1. **`scheduler.py` 不改**是本 change 的核心承诺（D4）。若实现中发现必须改，SHALL 先停轮回写 proposal 的 Impact Analysis 与本 design 的 D4——**不得直接改**。
2. **`NodeState.to_dict()` 不改**：报告是**新建**的投影函数，不复用也不修改 `NodeState.to_dict()`（`scheduler.py:265`）——后者是既有的图快照契约（`workflow-graph-visualization` 的 `SNAPSHOT_NODE_KEYS` 白名单断言钉着它）。

## Reference Implementation Research

完整 findings 见 proposal 的同名节（`research_tier: full`）。design 侧的关键影响已在 D3 / D6 / D7 / D8 逐条落地，此处不重复。
