# Grill: workflow-result-aggregation 设计追问

## Reviewer

- run id: grill-workflow-result-aggregation-2026-09-14
- 时间: 2026-09-14
- 对象: `openspec/changes/workflow-result-aggregation/design.md` D1–D6
- 基线: C2 `workflow-dsl-scheduler` 已合入（`agent/subagent/{workflow,scheduler,manager,snapshot,bus}.py`、`agent/config.py`、`agent/tools/builtin/subagents.py`）

## Confirmed Decisions

以下 8 条是本审阅员**读代码后可自行收敛**的结论（不需要用户拍板），实现时必须按此写，否则会与既有代码/测试事实冲突。

- **决策**: `result_ref` 落盘**不能复用 `SubagentSnapshotStore` 的目录命名空间**，必须新建独立 subtree（建议 `<workspace_root>/.asterwynd/workflows/<workflow_id>/`）。理由是 `SubagentSnapshotStore.remove()` 直接透传 `SessionStore.remove()`，而后者是 `shutil.rmtree(session_dir)`（`agent/session.py:184-191`），删的是**整个 run 目录**；同一个 `run_id` 既放 checkpoint 又放 result artifact 时，一次「清理 checkpoint」就会连结果一起删。同时 `SessionStore.save()` 带 dedup hash——内容不变时**直接返回 False 不落盘**（`agent/session.py:96-103`），「写完再读」在测试里会看到一个不存在的文件。而且 `SessionStore._write` 要求同时写 `snapshot.json` + `messages.json` 两个文件（`agent/session.py:205-220`），拿它存「一段 result 文本」是把 Session schema 当通用 KV 用，schema 一演进就炸。来源: grill-workflow-result-aggregation-2026-09-14

- **决策**: **正常完成的 run 今天根本不写 checkpoint**，因此 D1 若只复用「checkpoint 机制」则成功路径零落盘。`_write_checkpoint` 的调用点只有三处，全在异常/取消分支（`agent/subagent/manager.py:940` BudgetExceeded、`:945` Cancelled、`:955` 通用 Exception）；正常收尾走 `_complete_run`（`agent/subagent/manager.py:1031-1050`），它只把 `result.content` 写进 `run.summary`，不碰任何 store。所以「完整结果落盘」是**新增写点**，不是复用既有写点——落盘必须在 `_execute_run` 的成功分支或 `_complete_run` 里显式触发，否则 spec delta 的 Scenario「完整结果落盘、内存只持摘要」在正常路径下直接不成立。来源: grill-workflow-result-aggregation-2026-09-14

- **决策**: D1 的 `summary_ref` / `transcript_ref` / `artifact_refs` 三个字段里，`artifact_refs` **当前没有任何生产者**，本 change 必须显式表态。`SubagentRunRecord.artifacts`（`agent/subagent/manager.py:73`）在全仓只有一处读（`to_result_dict` 的 `agent/subagent/manager.py:107-110`），零处写——`grep -rn "SubagentArtifact(" agent/ tests/` 无命中。因此要么本 change 定义「什么时候往 `artifacts` 里记一条」，要么在 spec delta 里写明「`artifact_refs` 保留字段、本期恒为空数组、由后续 change 填充」，不能既保留字段又不说明它永远是 `[]`（否则模型会以为有东西可读）。`summary_ref`/`transcript_ref` 有明确区分：前者指 bounded summary 的落盘件（由本 change 的 token 预算裁剪产出），后者指完整 messages 序列的落盘件；两者**都必须按 run_id 独立成文件**（design.md:74 已定「每 run 独立文件 + 原子写」）。来源: grill-workflow-result-aggregation-2026-09-14

- **决策**: D3 的 bounded envelope **不能替换 `WorkflowScheduler.run()` 的返回值**，只能是新增的父 agent 面向投影（新方法/新字段）。`run()` 返回 `self.status()` → `_envelope()`（`agent/subagent/scheduler.py:330-351`、`:1092-1126`），其结构被 24 处既有断言依赖：`tests/agent/subagent/test_scheduler.py:214-219` 逐条断言 `result["nodes"]` 的 id 集合与状态、`:216` 断言 `result["completed"] == 3`、`:218` 断言 `result["current_nodes"] == []`；`test_workflow_tools.py` 与 `test_pattern_templates.py` 也经由 `_legacy_result` 消费 `envelope["nodes"]`（`agent/subagent/patterns.py:358-360`）。design.md:42-52 给的字段集（`workflow_id`/`status`/`completed`/`failed`/`pending`/`latest_events`/`root_result_ref`）里**没有 `nodes`**——按字面实现会让 C2 的整个测试面变红，且 `_legacy_result` 的 `by_id` 直接 KeyError。正确落法：`to_result_dict` 增 refs、`run()` 的 envelope 保留 `nodes`（节点摘要已由 `_SUMMARY_LIMIT=400` 裁剪，`agent/subagent/scheduler.py:64`、`:133`），bounded envelope 作为**父 agent 工具返回**（`StartWorkflow`/`GetWorkflow`）的独立投影。来源: grill-workflow-result-aggregation-2026-09-14

- **决策**: 「100 个 leaf 不把 100 个完整结果注入父上下文」的**真正爆点不在父 agent 的返回值，而在节点间的任务文本拼接**；只改 envelope 修不好它。`_node_task_text` 把所有数据上游的 `_node_output(upstream, "result")` 原文拼进下游 task（`agent/subagent/scheduler.py:1026-1041`，`f"Input from {edge.source}:\n{text}"`），`_aggregate_task_text` 把 `state.slots` 的每个槽值原文拼进 aggregate 的 task（`agent/subagent/scheduler.py:1043-1049`）。100 个 leaf 经 `reducer=concat`（`agent/subagent/scheduler.py:154-179`）先把 100 份结果拼成**一个巨型字符串**存进 `state.slots`，再整段喂给 aggregate 节点——内存与 prompt 都在这一步炸，与父 agent 拿什么 envelope 无关。本 change 必须同时改这两个函数的取值路径（改取 bounded 引用或分层摘要），否则 spec delta 的 Scenario「上百个叶子不撑爆父上下文」在实现完成后仍然复现。来源: grill-workflow-result-aggregation-2026-09-14

- **决策**: 自动兜底插入的 aggregate **在 parse 之后插入，因此绕过 `max_nodes` 的既有校验**，必须补一道运行期记账。`parse_workflow_spec` 的 `max_nodes` 检查是**声明期**的——`if len(nodes) > limits["max_nodes"]` 在解析时一次算完（`agent/subagent/workflow.py:335`），此后调度器只看 `self._expanded_nodes`，而它只在 `spec` setter（`agent/subagent/scheduler.py:303-305`）与 `_check_foreach_budget`（`agent/subagent/scheduler.py:797-809`）里被加。自动插入的 shard/domain 节点若不加进 `_expanded_nodes` 并复检 `max_nodes`，则「100 个 leaf + 自动插入节点」的图可以超出用户配置的节点上限而无任何信号——这与 C2 grill Q5 定下的「max_nodes = 节点数（含 foreach 展开）」口径直接矛盾。另外 auto-aggregate 用 `strategy="llm"` 还是 `"collect"` 决定它是否消耗 `max_runs`：`_run_cost` 对 aggregate 返回 `1 if node.strategy == "llm" else 0`（`agent/subagent/scheduler.py:503-510`），`collect` 走 `state.status = "completed"` 且**不产生 run**（`agent/subagent/scheduler.py:676-680`）。这个选择必须显式定，因为它改变 100-leaf 图的 run 预算量级。来源: grill-workflow-result-aggregation-2026-09-14

- **决策**: D6 的配置项**不能只加 dataclass 默认值**，必须在 `WorkflowLimitsConfig` + `_parse_workflow_limits` 两处逐字段落地，且注意 `subagents.workflow.*` 已被 C2 占用。`WorkflowLimitsConfig` 是 `@dataclass(frozen=True)`，只有 `recursion_limit`/`max_nodes`/`max_runs` 三个字段（`agent/config.py:245-255`），挂在 `SubagentsConfig.workflow`（`agent/config.py:284`）；解析走独立的 `_parse_workflow_limits()`，每个字段 `mapping.get(...)` 显式取值（`agent/config.py:1402-1418`），函数 docstring 自己就写明了这条教训——「只给 dataclass 默认值不会让 yaml 生效（C1 grill 的教训）」（`agent/config.py:1403-1404`）。所以本 change 的自动兜底阈值 + 四档 token 预算若进 `subagents.workflow.*`，是**扩这个既有 dataclass**（第三种可能：另起 `AggregationConfig` 挂在 `WorkflowLimitsConfig` 下），不是新开一个 `subagents.aggregation.*`——因为 `_parse_subagents_config` 也是逐字段显式构造的（`agent/config.py:1365-1399`），新开 top-level key 同样要手工接线。两条路都可行，但**必须二选一并写进 design.md**，且新增字段与 `tests/agent/subagent/test_workflow_tools.py:233-237` 的默认值断言要保持同一口径。来源: grill-workflow-result-aggregation-2026-09-14

- **决策**: D5「复用 MemoryManager 的 L1/L2 分层摘要能力」在代码层面**没有可直接复用的入口函数**，必须重新定义复用点。`MemoryManager` 的 L1/L2 状态是**实例私有的、绑定单个 AgentLoop 的 messages 流**：`_l1_chunks`/`_l2_summary`/`_tiers` 三个私有字段（`agent/memory/manager.py:97-101`），推进逻辑写在 `compact()` 内部（`agent/memory/manager.py:274-294`），输入类型是 `list[Message]`。workflow 级汇聚的输入是「多个节点的 result_ref / summary 字符串」，与 `Message` 不同型。真正可复用的是 summarizer 抽象：`Summarizer` Protocol 的 `summarize(messages, budget)`（`agent/context/summarizer.py:34`）和 `compress(tier_summaries: list[str], budget)`（`agent/context/summarizer.py:215`），后者签名最贴近（吃 `list[str]`、带 budget），但 `TruncationSummarizer.compress` 只是 `"\n\n---\n\n".join(...)`（`agent/context/summarizer.py:308-312`），无 LLM 时不会真的压缩。结论：复用点是 `agent/context/summarizer.py`，**不是** `agent/memory/manager.py`；design.md:62 与 tasks.md:16 的表述要改，(D5 后半句「不能替代 workflow 级分层汇聚」是对的，前半句的「复用 L1/L2」指的其实是 summarizer)。来源: grill-workflow-result-aggregation-2026-09-14

## Open Questions

- **Q1**: `result_ref` 落地后，**模型用什么工具把它换成内容**？design.md 只定义了「父 agent 不默认展开」（design.md:54）与「要看再显式 inspect（GetWorkflow 带 detail 参数 / InspectSubagentTranscript）」（design.md:54），但没有定义「拿一个 `artifact://workflow/wf_x/root` 去读」的通道。
  **场景**: 一个 100-leaf 的调研 workflow 跑完，父 agent 收到 `{"root_result_ref": "artifact://workflow/wf_3f9a/root", "completed": 100, ...}`。它想回答用户「A 和 B 两个方向的结论冲突在哪」：
  - 若走 **GetWorkflow(detail)**：detail 的取值枚举是什么？返回的是「按节点的 summary 列表」还是「root artifact 的正文」？100 个节点的 summary 全返回，等于 bounded envelope 白做。
  - 若走 **InspectSubagentTranscript**：它今天只接受 `subagent_id`（`agent/tools/builtin/subagents.py:185-197`，scope 二选一 `summary`/`recent_messages`，`agent/subagent/manager.py:850-890`），不接受路径或 result_ref；父 agent 手上没有 subagent_id（envelope 里被拿掉了）。
  - 若新增**独立读取工具**（如 `ReadWorkflowResult(ref, offset, limit)`）：需要定分页/timeout/大小上限，并加进 `agent/loop.py` 的注册表（`agent/loop.py:386-395`）与 `SPAWN_TOOL_NAMES` 的评估（`agent/subagent/manager.py:284-291`）——只读工具通常不入 spawn 名单，但要显式确认。
  请拍板读取通道、工具名与 `detail` 的取值枚举。

- **Q2**: bounded envelope 里的 `completed`/`failed`/`pending` **分母是什么**？design.md:45-50 给的例子 `completed: 73, failed: 4, pending: 23` 隐含 `73+4+23=100` 一个整数总数，但代码里今天没有这个总数。
  **场景 A（foreach 未展开）**: 一个 `foreach(items=[…40 项…])` 节点的图。`_envelope` 的 `completed`/`failed` 是对 `self._run_refs` 按 status 计数（`agent/subagent/scheduler.py:1094-1103`），而 `_run_refs` 只在 `_launch_run` 成功派发后 append（`agent/subagent/scheduler.py:875`）。展开前 pending 该算 1（节点）还是 40（未来 run）？
  **场景 B（collect aggregate）**: `strategy="collect"` 的 aggregate 不产生 run（`agent/subagent/scheduler.py:676-680`），它是「completed」还是根本不进分母？C2 既有断言明确按「collect aggregate 不产生 run」计数（`tests/agent/subagent/test_scheduler.py:216` 的 `completed == 3` 对应 3 个 subagent + 1 个 collect aggregate）。
  **场景 C（被取消/阻塞的节点）**: `cancel()` 把未派发节点标 `blocked`（`agent/subagent/scheduler.py:361-363`），`_teardown` 同理。`failed` 今天把 `failed`/`cancelled`/`budget_exceeded` 混算（`agent/subagent/scheduler.py:1099-1103`）——`blocked` 归哪一桶？
  请拍板分母（节点数 vs run 数）与 `pending` 的定义。

- **Q3**: 自动兜底的第二个阈值「**总叶子数 >10**」在 **foreach 场景下何时求值**？「单 aggregate 直接上游 >10」可以用 `spec.data_incoming(agg_id)` 数出来（`agent/subagent/workflow.py:213-219`），但「总叶子数」对含 foreach 的图**声明期不可知**——展开项数来自上游产出，只能在 `_resolve_items` 时确定（`agent/subagent/scheduler.py:1065-1073`）。
  **场景**: `declared leaves` 只有 2 个节点：一个 `foreach(items=[...])` + 一个 aggregate。运行时 foreach 展开 100 项，全部汇入同一个 aggregate。
  - 若只在**声明期**算叶子数：2 ≤ 10，自动兜底不触发；运行时 100 份结果经 `concat` 拼成巨型字符串喂给单个 aggregate（`agent/subagent/scheduler.py:1043-1049`）——正是 spec delta Scenario 要防的场景，却没被防住。
  - 若在**展开期**算：兜底节点必须在 `_check_foreach_budget`（`agent/subagent/scheduler.py:776-810`）附近动态改图，而此时 `self._states` 已由 spec 构建（`agent/subagent/scheduler.py:336-337`），动态加节点要处理「新节点无 `WorkflowNode` 声明的 outputs/reducer」等 schema 缺口。
  - 若**两处都算**（声明期 + 展开期各一次）：要定「展开期触发时是否回溯重排已有边」。
  请拍板阈值求值时机，以及动态插入节点是否需要重建 `WorkflowSpec`（注意 `spec_hash` 会随之变化，`agent/subagent/workflow.py:253-257`，而 C5 要用它做 replay 锚点）。

- **Q4**: 自动插入的分层 aggregate，**层级归属与 token 预算档位**怎么定？四档预算是 leaf 300 / shard 800 / domain 1500 / root 3000（design.md:36），但自动兜底插进来的节点不是模型按层声明的。
  **场景**: 100 个 leaf 直接汇入根 aggregate。调度器检测到「单 aggregate 直接上游 100 > 10」，自动插入中间层。此时：
  - 插 1 层（10 个 shard，各吃 10 个 leaf）还是插 2 层（10 个 shard + 3 个近似 domain）？插入层数由什么公式决定（`ceil(n/10)`？固定 2 层？）。
  - 自动插的这层算 **shard（800）还是 domain（1500）**？判据是「距 leaf 的层数」（1 层 = shard）还是「距 root 的层数」（1 层 = domain）？同一张图里两者会给出相反答案。
  - 若模型**部分显式**：已声明了 shard 层但漏了 domain 层（10 个 shard 直连 root）。D2 说「兜底只在模型没建树且超阈值时触发」（design.md:75）——「部分建树」算不算「没建树」？若不触发，root 仍有 10 个直接上游（恰好等于阈值 10，边界是 `>10` 还是 `>=10`？）；若触发，插入的 domain 层与模型声明的 shard 层如何区分预算档。
  请拍板层级判定规则、层数公式、阈值边界（`>` vs `>=`）与「部分显式」的处置。

- **Q5**: `latest_events: 5` 的**数据源是什么**？design.md:50 把它放进 bounded envelope，但今天没有任何「workflow 事件」的载体。
  **场景**: 父 agent 轮询 `GetWorkflow` 看进度。可选数据源：
  - **节点状态迁移**（最近 5 个进入终态的节点）——数据在 `NodeState` 上（`agent/subagent/scheduler.py:98-148`），但没有迁移时间序列，要新增 ring buffer。
  - **最近 5 个 run**（`self._run_refs` 尾部）——`_run_refs` 只含已派发 run（`agent/subagent/scheduler.py:875`），且是 list 无时间序保证。
  - **bus 消息**（`bus.snapshot_payload()`，`agent/subagent/bus.py:135-139`）——但 D4 正要把 bus 降级为非权威，用它填权威 envelope 是自相矛盾。
  另外「5」这个数字是条目数还是 token 数？若一条事件文本 300 token，5 条就是 1500 token，bounded envelope 的「bounded」要靠什么保证？
  请拍板数据源、条目语义（节点/run/事件）与字符或 token 上限。

- **Q6**: `to_result_dict` 的 **bounded summary 预算与既有断言的兼容边界**在哪？design.md:30 说它「默认返回 bounded summary + refs」，但 `to_result_dict` 是所有 run envelope 的唯一出口——`_format_run_envelope`（`agent/subagent/manager.py:1173-1180`）、调度器的 `_await_run`（`agent/subagent/scheduler.py:899`）、`GetSubagentRun` 工具都走它。
  **场景**: 一个 worker 的 `run.summary` 是 12k 字的调研笔记。
  - 截断到多少？四档预算是**聚合节点**的输出预算（leaf 300 等），但 `to_result_dict` 是**任意 run** 的出口——leaf 的 summary 截到 300 token 后，调度器拿它去喂 `_node_task_text`（`agent/subagent/scheduler.py:1026-1041`）和 aggregate，下游看到的是残缺输入；可若不截，100 leaf 场景下 `state.slots` 直接爆。
  - 既有断言依赖**精确相等**：`tests/agent/subagent/test_subagent_manager.py:111`、`:135` 断言 `result["summary"] == "subagent done"`，`:219` 断言 `inspected["summary"] == "latest summary"`，`tests/agent/subagent/test_concurrency_queue.py:327` 断言 `== "done"`——所以截断必须对短文本是 no-op，且默认预算远大于这些测试字符串。
  - 关键区分：bounded summary 是「**写进内存/信封的裁剪版**」，还是「**落盘后再读回的摘要版**」？前者让 `run.summary` 本身变短（信息真丢，checkpoint 里也是短的），后者只在 `to_result_dict` 出口裁剪、`run.summary` 保留全文。这对 `inspect_transcript` 的 `scope="summary"` 返回（`agent/subagent/manager.py:866-874`）行为不同。
  请拍板截断点（写时 vs 出口）、预算数值与 `run.summary` 是否仍保留全文。

- **Q7**: D5 的「workflow 级汇聚器」**是否还是一个真实 subagent run**？今天 `strategy="llm"` 的 aggregate 是一次真实 `run_subagent`（`agent/subagent/scheduler.py:660-674` 调 `_launch_run`），它计入 `max_runs`（`_run_cost` 见 `agent/subagent/scheduler.py:503-510`）、有 `subagent_id`/`run_id`、会出现在 `manager._sessions` 里——`test_pattern_templates.py` 的 `workers[]` 断言依赖节点的 `subagent_id` 能查到 session（`agent/subagent/patterns.py:314-330`）。
  **场景**: 改写 aggregate 为「直接调 summarizer 压缩，不 spawn run」——
  - 好处：省一个 run 预算、省一次子 agent 冷启动、归位「聚合是纯逻辑」。
  - 代价：aggregate 的 `state.subagent_id` 变 `None`。`tests/agent/subagent/test_pattern_templates.py:184-185`、`:284` 断言 `len(result["workers"]) == 3` / `== 2`，`_workers_from_node` 靠 `node["subagent_id"]` 取 session（`agent/subagent/patterns.py:320-325`）；而 peer-review/bidding 模板的 aggregate 正是 `strategy="collect"`（`agent/subagent/patterns.py:214-229`），暂不受影响——但如果本 change 顺带把 aggregate 全改成非 run 形态，`tests/agent/subagent/test_scheduler.py:216` 的 `completed == 3` 口径也要重新核对。
  - 若**保持真实 run**：复用点就只是「给 aggregate 节点的 task 文本做预算裁剪」，summarizer 由子 agent 自己的 AgentLoop 调用，本 change 只需把四档预算翻译成节点级 `max_tokens`（`WorkflowNode.max_tokens` 已存在并在 `_launch_run` 透传，`agent/subagent/scheduler.py:852-858`）。
  请拍板：aggregate 保持「真实 run + 预算透传」还是改「进程内直调 summarizer」。这条直接决定 tasks 2.3 的工作量。

- **Q8**: D6 的新配置项**放哪一层、叫什么名字**？`subagents.workflow.*` 已被 C2 的三个闸占用（`agent/config.py:246-255`、`:1402-1418`）。
  **场景**: 用户要在 yaml 里把「单 aggregate 直接上游阈值」从 10 改成 4、把 leaf 预算从 300 改成 500：
  ```yaml
  subagents:
    workflow:
      recursion_limit: 25
      max_nodes: 200
      max_runs: 300
      # 新增的写在这里 —— 键名待定
  ```
  - **方案 A（扁平）**: `subagents.workflow.autosplit_max_upstreams`、`subagents.workflow.budget_leaf` —— 与三闸同级，`WorkflowLimitsConfig` 从 3 字段涨到 3+2+4=9 字段，`_parse_workflow_limits` 加 6 个 `mapping.get`。好处：单一 flat 面；坏处：语义混杂（闸门 vs 聚合策略）。
  - **方案 B（嵌套 dataclass）**: 新增 `AggregationConfig`（含 `thresholds` + `token_budgets` 两个子 dataclass），挂成 `WorkflowLimitsConfig.aggregation`；`_parse_workflow_limits` 里多调一个 `_parse_aggregation(...)`。好处：职责清晰、四档预算可以做成可比对的结构（校验 `leaf <= shard <= domain <= root` 单调性）；坏处：多一层 yaml 缩进。
  - **方案 C（新 top-level key）**: `subagents.aggregation.*` —— 要在 `_parse_subagents_config` 里手工加一行（`agent/config.py:1377-1398` 是逐字段构造，不会自动透传）。
  另外要定：四档预算**是否允许不单调**（leaf 500 > shard 300 是否报 ConfigError）？阈值与预算都是 `_validate_positive_int` 的口径吗？请拍板层级、键名与校验规则。

- **Q9**: tasks 5.2 的「**checkpoint/resume 后能恢复 workflow 状态 + 结果 ref**」具体指什么？今天调度器**没有 resume 能力**：`run()` 每次重建 `self._states`（`agent/subagent/scheduler.py:336-337`），workflow 注册表是 manager 作用域内存（`agent/subagent/manager.py:358`、`:444-451`），且 C2 grill 的 Q1 已拍板「落盘留给 C5」（见 `openspec/changes/archive/2026-09-14-workflow-dsl-scheduler/reviews/grill-design.md:80`）。
  **场景 A（子 run 级 resume）**: workflow 中途被 `CancelWorkflow`，某个节点 run 写了 checkpoint（`agent/subagent/manager.py:944-952`）。父 agent 调 `ResumeSubagent(run_id)` 恢复那个**子 run**——这条链路今天通（`agent/subagent/manager.py:532` 用 `_snapshot_store().load(run_id)`），但恢复后**谁来把它的结果接回 workflow**？调度器已经 `_teardown` 完、`_status = "cancelled"`（`agent/subagent/scheduler.py:380-382`），没有任何入口重新挂上。
  **场景 B（workflow 级 resume）**: 进程重启后，用 workflow_id 恢复整张图的 `_states` 与各节点 `result_ref`。这要求 spec + 节点状态 + ref 全部落盘——但 spec 落盘被 C2 grill 明确推给了 C5。
  **场景 C（只测 ref 可解析性）**: 5.2 实际只测「跑完后按 result_ref 能从盘上读回完整结果」（不涉及进程重启），那「恢复 workflow 状态」这半句应从 tasks 里删掉或降级。
  请拍板 5.2 的验收边界，以及 `ResumeSubagent` 与 workflow 的关系（是否需要在 `WorkflowScheduler` 上加「resume from refs」入口）。

## User Confirmation

- **Q1**: 用户答复：新增只读工具 `ReadWorkflowResult(ref, offset, limit)` 分页读回 artifact 正文；`GetWorkflow(detail)` 只返回节点级摘要列表（不展开正文）；确认时间: 2026-09-14
- **Q2**: 用户答复（codex 独立确认修正）：分母改「逻辑执行单元」——普通节点=1、foreach=展开项数（含容器节点计入）；`blocked` 是终态、单独计数不计入 pending；`cancelled`/`budget_exceeded` 单独计数不混入 `failed`；保留旧 run 计数字段兼容（`completed`/`failed` 既有语义不动，新增 `total`/`cancelled`/`budget_exceeded`/`blocked`/`pending` 字段）；确认时间: 2026-09-14
- **Q3**: 用户答复（codex 独立确认修正）：声明期 + 展开期都算；**三 hash**——`declared_spec_hash`（原始 spec 不可变）/ `expansion_plan_hash`（foreach 展开计划）/ `runtime_graph_hash`（含自动插节点的执行图）；**不原地改 `WorkflowSpec`**，用独立 execution plan（否则状态表/入边/reducer 全乱）；确认时间: 2026-09-14
- **Q4**: 用户答复（codex 独立确认修正）：阈值 `>10`（max fan-in=10，n=10 不触发拆分）；层数按 fan-in 分组（`shard_count=ceil(leaf/10)`，逐层向上直到 root 输入 ≤10）；预算按「距 leaf 层数」（第 1 层 shard 800，再上 domain 1500，根 root 3000）；**auto aggregate 默认 `strategy="llm"`**（collect 只是拼接不解决 prompt 膨胀），auto 节点预算计入 `max_nodes` + `max_runs`；部分显式树补缺（只补缺失层，已声明层保留）；确认时间: 2026-09-14
- **Q5**: 用户答复（codex 独立确认修正）：ring buffer 放 **scheduler 内部**（非 manager），记「最近 5 次**终态迁移事件**」（同节点重跑可再次出现）；事件字段 = `node_id + status + summary_preview(首个非空行)`，不承诺「一句话」；每条事件分配字符上限（5×80 或整体裁剪）；不用 bus 填；确认时间: 2026-09-14
- **Q6**: 用户答复（codex 独立确认修正）：**拆三种表示**——①artifact 完整落盘 ②scheduler 内部 full formatter（下游用）③父 agent/普通工具 bounded formatter。**不能只做 `to_result_dict` 出口裁剪**（否则裁剪经 `_format_run_envelope`→`_execute_subagent`→`state.summary`→`_node_task_text` 一路传导，下游也拿到裁剪版）；`run.summary` 保留全文；确认时间: 2026-09-14
- **Q7**: 用户答复（codex 独立确认修正）：aggregate 保持**真实 run** 对，但 `max_tokens` 透传**不够**——它只限 token 消耗、不限 task 输入文本长度。必须**同时改 `_aggregate_task_text` 输入构造**（层级中间节点消费 bounded summary/ref，不是 concat 后的全文）；auto aggregate 默认 `strategy="llm"`；四档预算当前是「per-run total token budget」而非「输出预算」，需明确语义；确认时间: 2026-09-14
- **Q8**: 用户答复（codex 独立确认修正）：嵌套 `AggregationConfig`（`thresholds` + `token_budgets` 两个子 dataclass，均 frozen + `field(default_factory)`）挂 `WorkflowLimitsConfig.aggregation`；四档预算校验**非递减（允许相等）**，拒绝严格递减；`_parse_aggregation` 显式逐字段解析；确认时间: 2026-09-14
- **Q9**: 用户答复（codex 独立确认修正）：tasks 5.2 删「恢复 workflow 状态」；验收不能只做同进程读回——补**最小跨进程 result artifact 读取测试**（新 store 实例/subprocess，验证跨进程可解析 + 非 dedup 假象）；确认时间: 2026-09-14

## 风险

- **严重: `SubagentSnapshotStore.remove()` 会连结果一起删（带 file:line）**: `remove()` 透传 `SessionStore.remove()`，后者 `shutil.rmtree(session_dir)` 删整个目录（`agent/session.py:184-191`）；`snapshot.py:43-44` 无任何保护。若 result artifact 与 checkpoint 共用 `run_id` 命名空间，任何一次 checkpoint 清理都会静默销毁 result_ref 指向的文件——而 result_ref 是**跨进程可解析**的承诺（design.md:76）。必须独立 subtree，且 result 落盘不做 dedup skip（`agent/session.py:96-103` 的 dedup 会让「同样内容第二次写」变成 no-op，测试里表现为文件不存在）。

- **严重: bounded envelope 只改返回值，100-leaf 场景仍然撑爆（带 file:line）**: 爆点在 `_node_task_text`（`agent/subagent/scheduler.py:1026-1041`）与 `_aggregate_task_text`（`:1043-1049`）把上游产出**原文**拼进 task，以及 `aggregate_slots(..., "concat")` 先把 N 份结果拼成一个大字符串（`:154-179`）。spec delta 的 Scenario「上百个叶子不撑爆父上下文」若只验收父 agent 侧，会在实现完成后依然复现——验收测试必须覆盖 `_aggregate_task_text` 产出的字符串长度上界。

- **严重: 自动插入的 aggregate 绕过 `max_nodes` 与 `_expanded_nodes` 记账（带 file:line）**: `max_nodes` 只在 `parse_workflow_spec` 的声明期检查一次（`agent/subagent/workflow.py:335`），运行期记账靠 `_expanded_nodes`（`agent/subagent/scheduler.py:303-305`、`:797-809`）。自动插入发生在 parse 之后，若不显式 `self._expanded_nodes += k` 并复检，用户配置的 200 节点上限对自动插入节点完全失效；同时若 auto-aggregate 用 `strategy="llm"`，还会额外吃 `max_runs`（`:503-510`），让「100 leaf」图的 run 预算从 100 涨到 100+shards+1——C2 grill 已记录过「图级步数与 spawn 预算互相误伤」的同类风险（archive grill-design.md:94）。

- **中: `summary` 字段语义变更会红既有断言（带 file:line）**: `to_result_dict` 的 `summary` 是精确相等断言的对象（`tests/agent/subagent/test_subagent_manager.py:111`、`:135`、`:219`，`tests/agent/subagent/test_concurrency_queue.py:327`），`_legacy_result` 也用 `worker.get("summary")` 拼结果文本（`agent/subagent/patterns.py:368-372`）。截断必须对短文本 no-op、且不能把 `summary` 换成 ref 字符串（会同时破坏 `tests/agent/subagent/test_pattern_templates.py:185` 的 `assert result["summary"]`）。加字段是安全的，改字段语义不是。

- **中: envelope 的 `completed`/`failed`/`pending` 口径不闭合（带 file:line）**: `completed`/`failed` 只数 `self._run_refs`（已派发 run，`agent/subagent/scheduler.py:875`、`:1094-1103`），不含未展开的 foreach 项、被 `blocked` 的节点、`collect` aggregate（不产生 run，`:676-680`）；`failed` 还把 `cancelled`/`budget_exceeded` 混算。D3 直接给出 `completed: 73, failed: 4, pending: 23` 的三元组而不定义分母，实现时几乎必然与 `_envelope` 现有口径打架，且父 agent 无法据此判断「还差多少」。

- **中: bus 的 checkpoint 持久化路径与「降级为非权威」冲突（带 file:line）**: `_write_checkpoint` 主动把 `bus.compact_summary()` 折进快照的 `bus_summary` 字段（`agent/subagent/manager.py:1123-1127`），bus 自身文档却写「not persisted across runs」（`agent/subagent/bus.py:17-18`）。D4 若只改文档不改这条写路径，checkpoint 里会留一条**非权威但被持久化**的消息摘要——恢复的 run 会看到它，与「bus 丢消息不影响结果正确性」的 spec Scenario 语义不一致。同时要确认 `PublishBusMessage`/`ReadBus` 是否继续暴露给模型（今天无条件注册，`agent/loop.py:386-387`）。

- **低: `artifact_refs` 无生产者、`latest_events` 无数据源（带 file:line）**: `SubagentRunRecord.artifacts` 全仓零写点（`agent/subagent/manager.py:73`，仅 `:107-110` 读）；`latest_events` 在 `_envelope` 里没有任何对应结构（`agent/subagent/scheduler.py:1092-1126`）。两个字段若直接进 spec delta 而不定义生产者/数据源，实现者只能填 `[]`/`0`，违反 requirement 的 SHALL 措辞（`openspec/changes/workflow-result-aggregation/specs/multi-agent-collaboration/spec.md:7`）。

- **低: `WorkflowSpec.spec_hash` 与动态插节点互斥（带 file:line）**: `spec_hash` 由 `to_dict()` 的规范化 JSON 算出（`agent/subagent/workflow.py:253-257`），是 C5 replay 的锚点（`docs/openspec-change-backlog.md:100` 记录 C5 `benchmark-workflow-replay` 依赖「C2 的 spec 可哈希」）。若自动兜底在运行期重建 spec（Q3 的展开期方案），哈希会变，「同一份声明式 spec 产生同一哈希」的 replay 前提被打破。若必须动态改图，应把「原始 spec」与「运行期展开图」的哈希分开记录。
