# Design: 多Agent协作做深 — 状态快照 + 成本控制 + 编排模式库

## Context

当前多 Agent 协作是"单层角色子 agent + 顺序阶段工作流"雏形：`SubAgentManager` 的 `_sessions/_active_tasks/_run_waiters` 全在内存，cancel 只做 asyncio task.cancel()，无 kill 前 JSON 快照；`run_subagent(timeout_s)` 超时只是停止等待，后台子 agent 继续跑，无 kill 语义；无每子 agent token/时间预算；`ParentChannel` 是单 parent/subagent 一对一 Queue，未接入 loop/manager；编排只有硬编码 5 阶段顺序角色流水线，无通用模式。面试表现"Orchestrator-Worker 模式比较经济"但没实际踩坑经验。

## Goals / Non-Goals

**Goals:**

- 状态快照与恢复（子 agent 中断 → JSON 快照 → 断点继续）。
- 每子 agent token/时间预算，超限硬 kill + 失败摘要。
- 并发/嵌套深度护栏（max_concurrent_runs / max_depth），防"无护栏烧钱"（参考 Claude Code #68110：无递归上限跑出 48+ 并发 agent）。
- 轻量消息总线（多子 agent 交换摘要，严格 token 预算）。
- 编排模式库（orchestrator-worker / peer-review / hierarchical / 竞标）。

**Non-Goals:**

- 不引入 gRPC 跨节点调度（单机协作、快照和预算护栏跑通后再决策，第一版不交付）。
- 不重做 dev-workflow 编排（复用 #67 `agent/workflow/` 的持久化纪律，不耦合其阶段常量）。
- 不重做 SubAgentManager 既有接口（在其上扩展）。
- 不做整树共享 token 预算（per-run 预算 + session 累计展示；树级共享是跨节点调度的前置，后续）。
- 不做 web 端模式编排可视化（第一版只交付 API/测试/benchmark 数据，web 展示列为后续）。

## Decisions

### Decision 1: 复用 `agent/workflow/` 的持久化纪律，不耦合其阶段机器

**方案**：agent-runtime 子 agent 编排**不**把 `agent/workflow/` 的 dev-workflow 阶段状态机（wayfinding→planning→building→closing、PHASE_TO_ROLE）当作执行引擎——那些阶段词汇与四种编排模式（orchestrator-worker/peer-review/hierarchical/竞标）语义不匹配。本 change 复用的是 `agent/workflow/` 沉淀的**持久化纪律**：JSON 序列化 + schema_version + transitions 事件日志风格。模式执行状态落盘为简单 JSON 记录（pattern_type + 每 worker 的 status/result_ref + 聚合阶段），编排跑在 `SubAgentManager` 之上，不新建平行控制面（#63 教训）。spec delta 中 "reuse agent/workflow/ state machine" 措辞据此修正为 "reuse agent/workflow/ persistence discipline"。

**备选**：
- 真正泛化 `agent/workflow/state_machine.py` 为通用状态机库，四模式各定义阶段词汇——被拒：改动已硬化的 workflow 模块，爆炸半径过大（#63 教训）。
- 编排纯代码不落盘——被拒：无法恢复"中断到一半的编排"。

**理由**：快照/预算/总线/模式对比是面试与交付核心，不需要第二个状态机；持久化纪律复用保证架构一致性。

### Decision 2: 状态快照 = 扩展现有 SessionSnapshot 的会话级 JSON checkpoint，断点续跑

**方案**：子 agent 执行中断 → 序列化**会话级快照**到独立子代理目录 `<workspace_root>/.asterwynd/subagents/<id>/`（对齐 `SessionStore.sessions_root` 的 workspace 基准，非 HOME 基准——多 workspace 混用 HOME 会串）。快照形状 = **扩展现有 `SessionSnapshot`**（加可选 objective/blockers/next_steps 字段），子代理恢复直接走 `AgentLoop.run()` 已有 resume 路径（消费 SessionSnapshot），**不建平行恢复机制**；社区最小快照提案（#16375，<10KB）作为可选精简导出，不作为恢复主格式。「恢复」= 重建 transcript + 追加续接消息 + 重试进行中 tool_call_id（不恢复 asyncio 栈）；spec 措辞为"resumes from the checkpoint and continues toward the objective；进行中工具调用由模型重试"。

**触发点**：cancel / 预算 kill / 异常退出前落盘。落盘 key 用 run_id（防 8 字符 subagent_id 碰撞覆盖，`manager.py:149` `uuid4().hex[:8]`）。恢复入口 = `ResumeSubagent` 工具。

**备选**：
- 仅 run.trace 记录——被拒：trace 是记录不是可恢复状态。
- 自建社区最小快照格式为主格式——被拒：与现有 SessionSnapshot resume 路径不匹配，会建平行恢复机制。

**理由**：快照是"故障恢复"面试证据的核心；复用现有 resume 路径避免平行机制，O(1) 恢复 = 读 JSON + 重建消息。

### Decision 3: 预算用 per-run token/时间双维度 + 硬 kill（两条 kill 路径）

**方案**：每 **run** 设 token（input+output 累计）与时间双预算。计数在 loop 每 iteration 经 hook 累加（复用 `TraceRecorder.record_iteration` 的 input/output_tokens 字段；`after_llm_call` hook 可拿 `response.usage`）。**两条 kill 路径**：

- **token 超限**：loop 内 `after_llm_call` 检测，抛 `BudgetExceededError`——`_execute_run` 的 except 分支捕获 → 写快照 → 标状态，task 自终止，无需外部 cancel。
- **时间超限**：子代理卡在长工具调用（如挂起的 Bash）时 hook 检测不到，由 manager 起并发 monitor task 到点 `task.cancel()`（cancel 前先落快照）。

两种超限都**先落快照** → 终态 `budget_exceeded`（区别于 cancelled；新增 `_mark_budget_exceeded`，优先于 `_mark_cancelled`——cancel 路径对非 running 终态 no-op，`manager.py:237` 的 `if run.status == "running"` 已保证此顺序）+ 失败/成本摘要（reason + usage + `CostLedger` 成本）。配置：`config` 新段 `subagents.budget`（default_max_tokens / default_max_time_s），`RunSubagent`/`ResumeSubagent` 可 per-run 覆盖。

**手动扩展预算入口**：不另做动态扩额——`ResumeSubagent` 从快照继续即满足（kill 前快照已落盘，扩额 = 以更高预算 resume）。

**备选**：仅 token 预算不做时间预算——被拒：时间失控也是成本，且 token 预算检测不到长工具调用内的卡死。

**理由**：硬 kill 是成本控制必备语义；参考 Codex close_agent（flush 记录 → shutdown → 持久化状态 → 回收）。

### Decision 4: 并发与嵌套深度护栏（前置：给子代理 loop 开嵌套 spawn）

**方案**：`SubAgentManager` 加 `max_concurrent_runs`（默认 4，统计 `_active_tasks` 全局活跃 run）+ `max_depth`（默认 3）。**前置任务**：`_build_subagent_loop` 增加 `expose_subagent_tools=True`（当前未设，`manager.py:331-360`——子代理无 CreateSubagent/RunSubagent 工具，无法嵌套 spawn，hierarchical 模式与 max_depth 都依赖此）+ depth contextvar（spawn_depth），每次 `run_subagent` depth+1 校验 `max_depth`。护栏是**纯前置守卫**：在创建 `SubagentRunRecord` 之前返回明确错误（现状 `run_subagent` 的 RuntimeError 即如此），不产生 run 记录。参考 Claude Code #68110（无递归上限跑出 48+ 并发 agent 疯狂烧 token）与 Codex（max_threads 4/6 + max_depth）。

**备选**：不做护栏——被拒：无护栏烧钱是行业真实事故，面试可讲。

**理由**：并发/深度护栏是成本控制的另一维度，实现极小（计数器）。

### Decision 5: 消息总线用局部轻量总线 + 三层 token 预算（contextvar 接线）

**方案**：**per-orchestration-run 的局部总线**（避免全局串扰），父代理与参与子代理都可通过工具读写。**接线机制**：仿 `current_sandbox_sink`（`agent/sandbox_events.py`）/`current_tool_call_id`（`agent/background.py`）用 contextvar 存当前 orchestration bus；`RunPattern` 创建 bus 并通过 contextvar 传播到 worker 子代理，`_build_subagent_loop` 注册总线工具时从 contextvar 取 bus。消息信封 `{sender, topic, summary, token_count, ts}`。三层预算控制（业界共识）：

1. **bounded 队列**：max 100 条 + drop-oldest（NATS DiscardOld 语义）+ 可选 TTL。
2. **发布方摘要化**：发布时 LLMSummarizer（#74）+ 严格 budget，交换摘要而非原始消息。
3. **消费端 token 窗口**：读方注入 ≤N token 摘要（LangGraph trim_messages 语义）。

**不跨 run 持久化**——只活到 orchestration run 结束；快照里记录总线摘要供恢复，且**每次 bus 写后同步维护紧凑 bus 摘要字段**（防 kill 时摘要在 publish 途中未写全导致恢复后缺上下文）。

**备选**：单 parent/subagent Queue——被拒：无法多子 agent 间交换。

**理由**：消息总线是协作模式的基础；三层预算是"防上下文爆炸"的可量化故事。

### Decision 6: 编排模式库四模式 + OrcPattern 混合驱动

**方案**：`OrcPattern` 基类提供确定性骨架（spawn N → wait → collect），模式内的"拆分/选择/评审"由 LLM 子代理承担。四模式：

- orchestrator-worker：coordinator 拆任务 → N worker 并发 → 聚合；
- peer-review：producer 产出 → reviewer 审 → 迭代到共识（参考 LangGraph reflection / AutoGen Reflection）；
- hierarchical：manager 再拆 sub-team（子代理嵌套 spawn，依赖 Decision 4 的 expose_subagent_tools 前置）；
- 竞标：N proposer 出方案 → selector（LLM 子代理）选优（**差异化故事**：LangGraph/crewAI/Swarm/AutoGen 均无原生竞标原语，全用 LLM 选人近似）。

快照/预算/总线作为运行时服务注入模式。新工具 `RunPattern`。

**运行语义**：`RunPattern` 第一版**默认阻塞**返回聚合 envelope（等价 wait=True），不提供 wait=False 半程返回；单 worker 进度经 `GetSubagentRun` 查询。**worker 失败聚合**：不 fail-fast，聚合返回每 worker `{status, summary/result_ref, usage}` + 模式级汇总（完成数/失败原因分布），使 benchmark 的"完成率/成本"可比。**竞标 selector 输入**：task = 各 proposal 紧凑摘要拼接（受消费端 token 窗口约束），proposal 全文落 artifact 供 selector 用 Read 读（不走总线——总线 drop-oldest 可能丢关键 proposal）。

**备选**：硬编码顺序流水线——被拒：无法讲"模式库"；纯 LLM 自由拼装——被拒：无可测骨架。

**理由**：四模式是面试核心答案与协作实际需求。

### Decision 7: 工具面与 benchmark 形态

**方案**：新增 4 工具：`ResumeSubagent`、`RunPattern`、`PublishBusMessage`、`ReadBus`。budget 状态并入 `GetSubagentRun` 返回字段（不单独建 QueryBudget 工具）。benchmark：**1 个协作任务多模式对比**（完成率/成本/预算方差），非 4 个独立 task。

**备选**：独立 QueryBudget 工具 + 4 个独立 benchmark task——被拒：工具面臃肿、数据不具可比性。

**理由**：最小工具面 + 可对比数据。

## Pre-Implementation Review

batch-grill-me 已与用户确认以下决策（2026-08-03）：

- Q1 复用 `agent/workflow/` 持久化纪律而非阶段机器 → Decision 1
- Q2 会话级快照 + 断点续跑 + 不含进行中工具调用完整状态 → Decision 2
- Q3 per-run token/时间双预算 + 硬 kill + 快照续跑代替动态扩额 → Decision 3
- Q4 发布方摘要化 + bounded + 消费端 token 窗口 → Decision 5
- Q5 OrcPattern 混合驱动 + 第一版不做 web 可视化 → Decision 6 + Non-Goals
- Q6 4 新工具 + 1 协作任务多模式 benchmark → Decision 7
- Q7 并发/深度护栏进第一版 → Decision 4
- Q8 per-run 预算，不做树级共享 → Decision 3 + Non-Goals

独立 grill 审阅（run id: grill-subagent-independent-design-review，2026-08-03）已产出 `reviews/grill-design.md`，确认 5 个核心决策 + 提出 5 个必须修改项，已整合进本设计：

- 快照格式改扩展现有 SessionSnapshot（复用 loop.run resume 路径），目录对齐 workspace 基准 → Decision 2
- kill 区分 token 自终止 / 时间 monitor 两条路径 + budget_exceeded 终态 → Decision 3
- 嵌套 spawn 前置（expose_subagent_tools + depth contextvar）→ Decision 4
- 总线 contextvar 接线 + 快照紧凑 bus 摘要 → Decision 5
- RunPattern 阻塞语义 + worker 失败聚合 + 竞标 selector 输入 → Decision 6

## Reference Implementation Research

- status: enabled
- reason: 多 Agent 协作是 agent 编排成熟领域，需参考 Claude Code/Codex subagent、LangGraph/crewAI/Swarm 的状态快照、预算控制、编排模式实现。
- research questions:
  - Claude Code / Codex 的 subagent 状态快照与恢复？
  - LangGraph/crewAI/OpenAI Swarm 的编排模式与 token 预算控制？
  - 消息总线的 token 预算语义？
- findings:
  - **子代理生命周期**：仅 OpenAI Codex 有真正的子代理 checkpoint/resume（`agent-graph-store` SQLite 存 spawn 边 Open/Closed + per-thread JSONL rollout；`/resume` 遍历图重开 Open 子线程）。Claude Code 子代理不可 checkpoint（Task resume 参数坏，issue #15315/#10856），context 超限毁掉全部子代理工作、父代理只收失败无部分结果（issue #44067）。社区提案 #16375：最小快照 <10KB（objective/completed/blockers/next_steps + 文件引用）。
  - **cancel/kill 语义**：行业普遍协作式中断而非硬杀（Claude Code TaskStop 在 tool boundary；Codex interrupt 保留线程可续跑）。Codex close_agent 是真正关闭 = flush 记录 + shutdown + 持久化 Closed 边 + 递归回收后代。无框架硬杀底层任务；本 change 的 asyncio task.cancel() 已比协作式更硬。
  - **预算控制**：Claude Code 无 per-subagent token 预算（只有 maxTurns + 会话级 --max-budget-usd）；issue #68110 记录无递归上限跑出 48+ 并发 agent 疯狂烧 token。Codex：整树共享加权 rollout_budget（超限 SessionBudgetExceeded 硬失败）+ 并发上限 max_threads（4/6）+ max_depth。LangGraph：recursion_limit 硬上限（默认 25，超限抛异常）；token 预算 DIY。AutoGen：max_turns + TokenUsageTermination + 每 agent Buffered/TokenLimited 上下文（防 O(T²) 烧 token）。
  - **编排模式**：orchestrator-worker 有 LangGraph supervisor / crewAI hierarchical / Swarm agent-as-tools 参照；peer-review 有 LangGraph reflection / AutoGen Reflection 参照；hierarchical = 嵌套 subgraph / nested teams（LangGraph 建议每 team 独立 checkpointer namespace）；**竞标模式四框架均无原生原语**，全用 LLM 选人近似（supervisor 路由 / handoff 选择 / SelectorGroupChat）——本 change 的竞标是差异化故事。
  - **消息总线 token 预算**：业界共识三层——bounded 共享状态（reducer + drop-oldest / token-hysteresis，NATS DiscardOld vs DiscardNew）、投递前摘要化（LangMem summarize_messages：max_tokens_before_summary/max_tokens/max_summary_tokens 硬上限）、消费端 token 窗口（LangGraph trim_messages：max_tokens + strategy='last' + allow_partial=False）。消息信封带 tokenCount；压力阈值 ~70%/85% 分级压缩 + 熔断。
- design impact:
  - 快照格式对齐社区最小快照提案（#16375，<10KB）→ Decision 2。
  - 硬 kill = 落快照 → cancel → 标状态 → 写摘要（对齐 Codex close_agent）→ Decision 3。
  - 新增并发/深度护栏（对齐 Codex max_threads/max_depth，回击 #68110）→ Decision 4。
  - 消息总线三层预算（bounded + 发布方摘要化 + 消费端 token 窗口）→ Decision 5。
  - 竞标模式定位为差异化实现（无原生参照）→ Decision 6。

## Risks / Trade-offs

- **[与 dev-workflow 编排重复] → 复用 `agent/workflow/` 持久化纪律，不耦合阶段机器，区分两个 scope，禁止重复造轮子（#63 教训）。**
- **[快照恢复失败] → 快照 schema_version/fingerprint 校验，失败时回退从零重跑。**
- **[预算硬 kill 误杀] → 预算阈值可配置，kill 前落快照 + 记录失败/成本摘要，`ResumeSubagent` 以更高预算续跑。**
- **[消息总线 token 预算] → bounded/drop-oldest/发布方摘要化/消费端 token 窗口，防上下文爆炸。**
- **[并发护栏误拦] → max_concurrent_runs/max_depth 可配置，超限返回明确错误而非静默丢弃。**
- **[依赖 #74/#78] → 消息摘要生成依赖 #74 LLMSummarizer，预算计数依赖 loop hook + TraceRecorder token 字段，事件流依赖 #78 稳定。**
- **[嵌套 spawn 能力缺口] → `_build_subagent_loop` 开 `expose_subagent_tools=True` + depth contextvar 是 building 首个前置任务，否则 hierarchical 模式与 max_depth 护栏无法落地。**
- **[8 字符 subagent_id 落盘碰撞] → 快照落盘 key 用 run_id（完整），校验存在性，防静默覆盖。**
- **[预算计数只到迭代边界] → 单次 LLM 调用可超额一整轮；时间预算卡在长工具调用内需 monitor；超限误差在 benchmark 数据如实标注（"预算方差"指标才有意义）。**

## Testing Strategy

- 单元测试：快照序列化/恢复、预算硬 kill、并发/深度护栏、消息总线 token 预算、编排模式状态机。
- 集成测试：子 agent 快照恢复端到端、竞标模式。
- 回归测试：既有 SubAgentManager 测试不回归。
- benchmark 层级：1 个协作任务多模式对比（完成率/成本/预算方差）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/subagent/manager.py` | 快照/预算/kill/并发深度护栏 |
| `agent/subagent/protocol.py` | 消息总线（多子 agent 间交换摘要，token 预算） |
| `agent/tools/builtin/subagents.py` | 新工具（ResumeSubagent/RunPattern/PublishBusMessage/ReadBus） |
| `agent/loop.py` | 预算计数（复用 hook + TraceRecorder token 字段） |
| `agent/memory/` | 消息摘要生成（复用 #74 LLMSummarizer） |
| `agent/config.py` | 预算配置段 |
| `web/` | 子 agent 状态/预算展示（第一版不做，列为后续） |
