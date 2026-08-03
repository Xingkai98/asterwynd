# Grill: multi-agent-collaboration 设计追问

## Reviewer
- run id: grill-subagent-independent-design-review
- 时间: 2026-08-03

## Confirmed Decisions

- **决策**: Decision 1 复用 `agent/workflow/` 持久化纪律而非阶段机器；理由: `state_machine.py` 的 PHASES/PHASE_TO_ROLE/WITHIN_PHASE_ADJACENT 全部硬编码 dev-workflow 四阶段词汇（wayfinding/planning/building/closing），与四编排模式语义不匹配，泛化会改动已硬化模块（#63 教训）；来源: 代码事实核对（`agent/workflow/state_machine.py` + `models.py`）+ design.md Decision 1 + spec delta 已修正措辞为 "persistence discipline"。
- **决策**: Decision 3 per-run token/time 双预算 + 硬 kill；理由: `agent/loop.py:601-613` 已有 `after_llm_call` hook（line 601）且 token_counters 就地累计 `response.usage.input/output_tokens`，`TraceRecorder.record_iteration` 已带 input/output_tokens 字段（#78 已合入），`CostLedger.record(model, input, output, session_id, phase, tool_name)` 真实可用且 `SubAgentManager._build_subagent_loop` 已传 `cost_ledger + ledger_tool_name="subagent"`；来源: 代码事实核对（`agent/loop.py`/`agent/trace_recorder.py`/`agent/cost_tracker.py`）+ design.md Decision 3。
- **决策**: Decision 5 消息总线三层预算（bounded + 发布方摘要化 + 消费端 token 窗口）；理由: `LLMSummarizer` 的 `summarize/merge/compress` 已存在且 `MemoryManager._get_summarizer` 延迟注入，发布方摘要化可复用；NATS DiscardOld / LangGraph trim_messages 是业界参照；来源: 代码事实核对（`agent/context/summarizer.py`/`agent/memory/manager.py`）+ design.md Decision 5。
- **决策**: Decision 7 budget 状态并入 `GetSubagentRun` 返回字段（不单独建 QueryBudget 工具）；理由: `SubagentRunRecord.to_result_dict()` 是加性返回 dict，新增 status 值/usage 字段向后兼容；来源: 代码事实核对（`agent/subagent/manager.py:55-71`）+ design.md Decision 7。
- **决策**: Decision 4 并发/深度护栏进第一版；理由: `_active_tasks` dict 可直接统计全局活跃 run 数，`active_run_id` 已保证同 session 串行；max_concurrent_runs 是增量计数器；来源: 代码事实核对（`agent/subagent/manager.py:117-119,181-182`）+ design.md Decision 4。

## Open Questions

- **子代理快照格式与 AgentLoop resume 路径不匹配**：design 提议 `~/.asterwynd/subagents/<id>/snapshot.json` 用社区最小快照 `{objective, completed, blockers, next_steps, messages骨架, run_meta}`，但 `AgentLoop.run()` 的 resume 路径（`agent/loop.py:527-554`）消费的是 `SessionSnapshot`（含 mode/todos/active_skills/user_system_prompt）。"复用 SessionStore 的 schema_version/fingerprint/dedup 模式"只复用类/方法模式，不是快照形状。推荐答案：扩展现有 `SessionSnapshot` 加可选 `objective/blockers/next_steps` 字段，子代理恢复直接走 `loop.run(resume_snapshot=...)` 已存在路径，避免建平行恢复机制；社区最小快照作为可选精简导出，不作为恢复主格式。
- **token 预算与时间预算的 kill 机制必须区分**：token 预算在 loop 内 `after_llm_call` 检测，天然是"迭代边界自终止"；时间预算若子代理卡在长工具调用（如挂起的 Bash），`after_llm_call` 检测不到，必须由 manager 起并发 monitor task 到点 `task.cancel()`。design 未区分两条路径，只写"超限 → 先落快照 → task.cancel()"。推荐答案：token 超限 = loop 内抛 `BudgetExceededError`（`_execute_run` 的 `except Exception` 分支捕获并写快照+标状态，不需要 task.cancel，task 自终止）；时间超限 = manager monitor 外部 cancel。二者都要在 kill 前写快照。
- **`budget_exceeded` 状态与 `_mark_cancelled` 的竞态**：`cancel_subagent_run` 里 `if run.status == "running": self._mark_cancelled(...)`（`manager.py:237`）。若预算 kill 先标 `budget_exceeded`，后续外部 cancel 会因 status != "running" 跳过覆盖——这是好消息但要显式设计：新增 `_mark_budget_exceeded`，且 status 判定顺序要保证 budget_exceeded 优先于 cancelled。推荐答案：状态机加 `budget_exceeded` 终态，cancel 路径对非 running 终态直接 no-op。
- **快照落盘目录基准与 SessionStore.sessions_root 不一致**：`SessionStore.sessions_root` 是 workspace 基准 `workspace_root/.asterwynd/sessions`（`agent/main.py:_sessions_root`），design 却写 HOME 基准 `~/.asterwynd/subagents/<id>/`。多 workspace 会混。推荐答案：改为 `<workspace_root>/.asterwynd/subagents/<id>/`，与 sessions 同基座；若坚持 HOME，需说明多 workspace 隔离策略。
- **子代理 loop 未注入消息总线，总线工具接不进去**：`_build_subagent_loop`（`manager.py:331-360`）为每个 run 新建 registry 和 `AgentLoop`，且**未设 `expose_subagent_tools=True`**——子代理 loop 没有 subagent 工具，也没有任何总线引用。design 说"父代理与参与子代理都可通过工具读写"但没给出接线机制。推荐答案：仿照 `current_sandbox_sink`（`agent/sandbox_events.py`）/`current_tool_call_id`（`agent/background.py`）用 contextvar 存当前 orchestration bus，`_build_subagent_loop` 注册 `PublishBusMessage/ReadBus` 工具时从 contextvar 取 bus；per-orchestration-run 的 bus 由 `RunPattern` 创建并通过 contextvar 传播到 worker 子代理。
- **RunPattern 是否阻塞父代理 loop 未明确**：`OrcPattern` "spawn N → wait → collect" 若作为父代理工具调用，`execute()` 里 `await` worker 结果即阻塞父 loop 当前迭代（等价 wait=True 的 RunSubagent）。推荐答案：第一版 RunPattern 默认阻塞并返回聚合 envelope；不提供 wait=False 半程返回，避免父代理在编排中途无法获知进度（GetSubagentRun 已能查单 worker）。
- **worker 失败聚合策略未定**：orchestrator-worker/竞标中单个 worker failed/budget_exceeded/cancelled 时，聚合是 fail-fast 还是收集部分结果？推荐答案：不 fail-fast，聚合返回每 worker `{status, summary/result_ref, usage}` + 模式级汇总（完成 worker 数/失败原因分布），使 benchmark 的"完成率/成本"可比；预算超限 worker 的结果也保留部分产物（快照已落盘）。
- **竞标模式 selector 的输入来源未定**：N 个 proposer 的方案如何喂给 selector 子代理？走总线、走 artifact、还是拼进 task 字符串？推荐答案：selector 的 task = 各 proposal 的紧凑摘要拼接（受消费端 token 窗口约束，~≤N tokens），不用总线（总线有 drop-oldest，可能丢关键 proposal）；proposal 全文落 artifact 供 selector 用 Read 读。
- **max_depth 依赖嵌套 spawn，而子代理当前不能 spawn**：`_build_subagent_loop` 未设 `expose_subagent_tools=True`，子代理无 CreateSubagent/RunSubagent 工具——Decision 6 hierarchical "天然支持子代理再 spawn" 与现状矛盾。推荐答案：`_build_subagent_loop` 增加 `expose_subagent_tools=True` + depth contextvar（`spawn_depth`），manager 每次 `run_subagent` 时 depth+1 校验 `max_depth`；同时把并发计数从"活跃任务数"（`_active_tasks`）计为全局护栏，Depth 超限与 Concurrent 超限都返回明确错误。
- **"从断点继续"语义需在 spec 中软化**：proposal/spec scenario 写 "execution continues from the interruption point"，但恢复 = 重建 transcript + 追加续接消息 + 重试 pending tool_call_id（LLMSummarizer prompt 已保留 `[call#<i>: <tool_call_id> pending]` 标记），模型是否原样重发同一 tool call 非确定性。推荐答案：spec 措辞改为 "resumes from the checkpoint and continues toward the objective；进行中工具调用由模型重试"，避免 benchmark 验收误读为位级续跑。
- **护栏拒绝与预算 kill 的优先级**：二者时域不重叠（护栏在 spawn 时拒，预算在 run 中 kill），但同一子代理若先被护栏拒、又被预算超限，状态机应保证 spawn 拒绝不产生 run 记录。推荐答案：spawn 拒绝在 `run_subagent` 创建 `SubagentRunRecord` 之前返回错误（现状 RuntimeError 即如此），护栏是纯前置守卫。

## 风险

- **嵌套 spawn 能力缺口**：不先给 `_build_subagent_loop` 开 `expose_subagent_tools=True` 并加 depth 跟踪，hierarchical 模式与 max_depth 护栏都无法落地——这是设计宣称"天然支持"与代码事实的直接冲突，应列为 building 首个前置任务。
- **8 字符 subagent_id 落盘碰撞**：`subagent_id = uuid4().hex[:8]`（`manager.py:149`），内存态无碍，但一旦快照落盘到 `subagents/<id>/`，碰撞会静默覆盖他人快照。落盘 key 建议用完整 run_id 或校验存在性。
- **预算计数只到迭代边界**：token 预算检测在 LLM 调用完成后的 hook 点，单次调用可能超额一整轮（尤其长输出）；时间预算卡在工具调用内则 `after_llm_call` 检测不到，必须 monitor。二者超限误差需在 benchmark 数据里如实标注（"预算方差"指标才有意义）。
- **快照写入与消息追加的时序**：manager 外部 cancel 与 loop 内 append message 在同一事件循环交错；建议快照序列化保持同步（`json.dumps` 原子）且由单一写者（loop 异常处理器或 manager 的 cancel 路径）写，避免双写竞态。
- **总线不跨 run 持久化 + 快照记总线摘要**：恢复后新 orchestration run 是新 bus，唯一桥接是快照里的总线摘要，若该摘要在 kill 时未写全（比如 kill 发生在 publish 途中），恢复的 worker 会缺上下文。建议快照在每次 bus 写后同步维护一个紧凑 bus 摘要字段。
- **8.2 benchmark smoke verification（checker 要求项）**：这是 coding-agent core change，benchmark 层必须覆盖模式对比；design 的 "1 个协作任务多模式对比" 需要明确的成本/完成率指标与预算方差口径，否则任务 5.3 无法验收。
