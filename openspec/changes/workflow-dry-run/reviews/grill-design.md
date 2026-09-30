# Grill 设计追问记录：workflow-dry-run

- **执行方式**：独立零记忆 subagent（paseo 托管 agent `202346af-e8f6-43e4-9a3a-8879e59aad44`，provider `claude/claude-fable-5[1m]`，`bypassPermissions`）
- **执行时间**：2026-09-30
- **任务**：逐条验证 design 的「已实测机制事实」表（F1–F9）与「语义发现」表（S1–S5）是否属实；独立验证 D4 的隔离承诺；评估 `script`/foreach 缺口；逐条评估 Q1–Q5
- **最终 verdict**：**CHANGES_REQUESTED**（4 条 high：I1–I4；均已在本 change 回写 design/spec/tasks 后关闭，见下）

## Confirmed Decisions

- **决策**: 用 `DryRunWorkflow` 独立工具（而非给既有工具加 `dry_run` 参数）是对的。；理由: `RunWorkflow` 在 `SPAWN_TOOL_NAMES` 里受 `max_depth` 撤工具管辖（design D1 第 3 点），而 dry run 不 spawn；实测 dry run 全程不产生 `run_subagent` 之外的新 spawn，归在 `read_only` 档站得住。；来源: 202346af-e8f6-43e4-9a3a-8879e59aad44
- **决策**: 隔离靠「一次性 manager + 假 LLM」这条路线本身成立，真实 workspace 零污染。；理由: 跑 `research/isolation.py` 得真实 workspace `disk delta = (none)`；跑 `research/prototype.py` 得 `real manager registry = []`。；来源: 202346af-e8f6-43e4-9a3a-8879e59aad44
- **决策**: 假 LLM 能通过 contextvar 拿到节点身份、无需改调度器，属实。；理由: `agent/subagent/context.py:104-105`（`current_node_id`）；`research/nodeid.py` 输出每个节点看到自己的 id。；来源: 202346af-e8f6-43e4-9a3a-8879e59aad44
- **决策**: `input_seen` 直接取 `NodeState.raw`（不重算第二份真相）是对的。；理由: `scheduler.py:1890` `state.raw = raw[:_SUMMARY_LIMIT]`；`_route_verdict`（`scheduler.py:2605-2624`）确实把判定文本算好放在这里。；来源: 202346af-e8f6-43e4-9a3a-8879e59aad44
- **决策**: 「复用 `run()` 而非复制一份模拟器」的取舍成立（R8 的消除）。；理由: `run()`（`scheduler.py:791`）的语义（门控/reducer/route 匹配/foreach 展开）全部经由 `_execute_*` 四个函数走到，模拟天然同源。；来源: 202346af-e8f6-43e4-9a3a-8879e59aad44
- **决策**: `run()` 会污染 manager 注册表（F3）属实，且隔离方式是 fresh manager 而非「去 sink」。；理由: `scheduler.py:829` `self.manager.register_workflow(self)`；`manager.py:526` 证实默认 `graph_sink = None`。；来源: 202346af-e8f6-43e4-9a3a-8879e59aad44
- **决策**: 不给既有工具加 `dry_run` 参数、「主引导放 `DryRunWorkflow` 自身描述」的分工方向正确。；理由: 实测 `DeclareWorkflow` 描述只有 **3993** 字符（不是 design 说的 5892），守卫上界 6000，指针成本远低于 design 估计。；来源: 202346af-e8f6-43e4-9a3a-8879e59aad44

## 验证结果：已实测事实表

- **F1**: ✅ —— 跑 `research/side_effects.py`，真实 workspace 新增 **11 个文件**（`events.jsonl` + `results/` 下 3 run × 3 文件 + `root.txt`）。落点、行号（`:714`/`:3169`/`:1327`）都对。
- **F2**: ✅ —— `manager.py:526` `self.graph_sink = None`。
- **F3**: ✅ —— `scheduler.py:829`；输出 `_workflows = ['wf_6df27711']`、`_workflow_stores = ['wf_6df27711']`。
- **F4**: ❌ —— **表述过强，且是本设计最关键的一处事实错误。** `_launch_run` 确实是唯一调用 `manager.run_subagent` 的地方（全文件 grep 只有 `scheduler.py:2240` 一处），**但它不是「真实 LLM 的唯一切入点」**。第二条通道是 `WorkflowAggregator`：`WorkflowScheduler.__init__`（`:515`）→ `_build_summarizer()`（`:666-673`）在 `manager.llm` 非空时构造 `LLMSummarizer(llm)`；`collect` 聚合的 `_merge_contributions_bounded`（`:2435`）在拼接超预算时调 `_aggregator.merge` → `LLMSummarizer.compress` → **真实 `llm.chat()`**。**已回写 design F4/F4a/F7 + 新增 D4b。**
- **F5**: ✅ —— `context.py:104-109`；`research/nodeid.py`。
- **F6**: ✅（对真实 workspace）—— `isolation.py`：`new files: (none)`、`sentinel intact`；`prototype.py`：`real manager registry: []`。**但对「零落盘」的广义表述存疑 → I1，已订正措辞。**
- **F7**: ⚠️ —— 清单**不完整但无害**。真实访问面还有 `self.manager.llm`（`:671`）、`cost_ledger`（`:1252`/`:2714`）、别名形式的 `spawn_count_for` / `rejection_counts_for`（`:867-869`）、`max_active` / `max_queued_runs`（`:1625`）。**已订正为 14 个并注明「漏 `llm` 是致命的」。**
- **F8**: ✅ —— `research/perf.py`：`foreach-5 = 0.304s`、`foreach-20 = 0.099s`、`foreach-50 = 0.097s`（20/50 都是 22 次调用）、`chain-50 = 0.696s`。
- **F9（grill 新增的 I1 副产品）**: ✅ 已纳入 —— 写入口两个（manager 级 `_write_result_artifacts` / scheduler 级 `_store`），但都以 `workspace_root` 为路径根。
- **S1**: ✅ —— `research/route_reads.py`：`gate.raw == 'MID-SAYS-A' == mid.summary`。
- **S2**: ⚠️ —— **方向对，机制说错了。** 真实规则（`scheduler.py:2478-2486` `_node_output`）是「**先查自身槽（仅非 subagent），否则一跳回退到任一直接父节点已物化的同名槽，最后才回退 `state.summary`**」。aggregate 之所以触发，是因为它**总会物化一个 `result` 槽**，而 **subagent 从不写自己的槽**。**已按此订正 design D2 的机制段。**
- **S3**: ✅ —— `research/rounds.py`：producer 在 lap 1/2/3 收到的 prompt **逐字相同**。
- **S4**: ✅ —— `prototype.py` CASE 1 `matched=null, used_default=true`。

## Issues Found（全部已在 design/spec/tasks 回写）

- **I1（高）**：D4 漏了 manager 级写入口，`scheduler._store` 不是唯一写口，「零落盘」只在**调用方 workspace** 口径成立。→ 已订正 F9 / D4 / Non-Goals / R2，并在 tasks 2.1 加「变异验证：换成真实 manager 必须变红」。
- **I2（高）**：LLM 通道不止一条，aggregator→summarizer 会污染报告（多出不可归因调用 + 改写聚合槽 → 翻转 route）。→ 已订正 F4/F4a/F7，新增 **D4b**（切断 summarizer 路径，倾向 `TruncationSummarizer`）与 **Q6**，spec delta 加「聚合产出不被替身污染」「无不可归因调用」两条。
- **I3（高）**：T-8 按 design 自己的原型图（`agg→critic→gate`）**跑不通**——`script:{"critic":...}` 不生效，因为 route 读的是聚合槽（S2）。→ 已在 tasks 2.8 标注图形态必须是 `a→mid→gate`，并说明原因。
- **I4（中）**：`script` 与 `received` 都无法区分 foreach 展开项；实测 `received` 只剩第一项。→ 已订正 D2（`received` 按 `(node_id, item_index)` 寻址）、新增 **G1** 与 tasks 2.5a（变异验证）。
- **I5（中）**：节点 `failed` 与 `reason` 不在报告契约里，「模拟失败」会被读成「拓扑答案」。→ spec delta 加「非正常结束节点 SHALL 给原因」，tasks 加 T-8a。
- **I6（中）**：spec delta 缺 proposal 承诺的 MODIFIED requirement。→ proposal 已改为**条件性**（仅当 Q4 选「加指针」），并说明当前 delta 无 MODIFIED 节的理由。
- **I7（低）**：描述长度事实错误（5892 → 实测 3993）。→ 已订正 D1/D10/R7/Q4/proposal 全部 5 处。
- **I8（低）**：两处引用错位（截断标记在 `aggregation.py:67` 而非 `scheduler.py:2570`；且标记须与既有 `_BOUNDED_MARKER` 可区分）。→ 已订正 D5。
- **I9（低）**：T-3 的变异验证比看上去弱（真实 manager 从不交给 scheduler，`real.llm.chat == 0` 结构性恒真）。→ 已订正 tasks 2.3 的变异形态。

## Design-Level Open Questions（已并入 design 的 Q1–Q6）

- **OQ-A（口径）**：「零落盘」是「调用方 workspace 零落盘」还是「字面零写盘」？→ 并入 **Q2**（一次性 workspace_root 单独是否足够，以及要不要额外换 `_store`）。
- **OQ-B（summarizer 通道）**：`collect` 聚合触发的内部 summarizer 调用怎么处理？→ **Q6**。
- **OQ-C（foreach 项级寻址）**：`script`/`received` 要不要项级寻址？→ **Q1**。
- **OQ-D（模拟中途失败）**：报告怎么表达「模拟没跑完」？→ 已按 I5 落为 spec 要求；其**文案形态**并入 **Q6**。

## 对 Q1–Q5 的独立意见（grill 原文摘要）

- **Q1（script 按轮次）**：同意 **B（有序列表）**。补：不能用 `oneOf`（本仓 `parameters` 逐字透传，`#246` RIR 已实测 Anthropic 拒绝顶层 `oneOf`/`anyOf`）；建议两个并列可选字段（`script` 收标量、`script_sequence` 收列表）+ 运行期判别。
- **Q2（私有属性 vs 构造参数）**：倾向 **A（替换私有属性）+ 断言兜底**，但兜底面要按 I1 扩大（断言「真实 workspace 零新增」，而非「所有写口被 NullStore 覆盖」），并加 `assert hasattr(scheduler, "_store")` 让重构在构造点就红。
- **Q3（max_report_chars）**：同意 **默认 240 + 允许覆盖**。补：截断标记必须与 `_BOUNDED_MARKER` 视觉可区分。
- **Q4（slots + 引导位置）**：**slots 要返回**（独立顶层字段、单独截断、只在被 route 读到时展开）；引导**两边都放**（描述实测 3993/6000，加指针成本极低）。
- **Q5（防滥用设界）**：**不认可 design 的 C（软提醒）**——issue #273 原文明确要求「调用次数**上界**」，软提醒是无界的。推荐 **A+C 混合**：软提醒在 ~10 次，硬上限在 ~40 次并返回 `{"status":"dry_run_limit_reached", ...}`（照抄 deepseek 的 runaway-loop backstop 形态）。

## User Confirmation

**（待用户逐条答复 Q1–Q6；每条 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`）**

- **Q1**:
- **Q2**:
- **Q3**:
- **Q4**:
- **Q5**:
- **Q6**:
