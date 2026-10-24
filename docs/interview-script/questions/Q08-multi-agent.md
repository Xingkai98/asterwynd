# Q08: 多 Agent 协作——spawn、快照、预算、消息总线、编排模式

## 讲稿

多 Agent 协作解决"复杂任务拆给多个 agent 并行做"。Asterwynd 的 SubAgentManager 提供四块能力：**spawn、快照恢复、预算硬 kill、消息总线**，外加**编排模式库**。

**spawn 与运行**。`create_subagent` 创建子 session，`run_subagent` 执行——子 agent 是独立的 AgentLoop 实例，有自己的模式（build/read_only/plan），与父 agent 共享 workspace/sandbox。支持多次 run、查询状态、取消。

**状态快照与恢复**（#79 核心）。子 agent 执行中断时，把 session 状态序列化为 JSON 快照（`SubagentSnapshotStore`），恢复时从断点继续——复用主 session 的 schema_version/fingerprint/dedup 模式。这是"断点续跑"，不是重跑整个任务。

**预算硬 kill**。每个子 agent 有 token/时间预算（`BudgetTracker` + `BudgetHook`），超限抛 `BudgetExceededError` 硬 kill，返回失败摘要。防止子 agent 失控烧 token。

**消息总线**。子 agent 间通过轻量 `MessageBus` 交换摘要（严格 token 预算防上下文爆炸）。消息有 type/payload 结构，读消息支持范围查询，`compact_summary` 把总线内容压缩成摘要。

**编排模式库**。提供 orchestrator-worker / peer-review / hierarchical / 竞标（auction）四种模式。面试亮点是竞标模式——多个子 agent 各自出方案，父 agent 选最优。

## 代码走读

### 入口与调用链

```
SubAgentManager.create_subagent (manager.py:175) → run_subagent (209) → _launch_run (319)
  → _execute_run (433) → 独立 AgentLoop → _complete_run (542)
  BudgetHook 监控 token/时间 → 超限 _mark_budget_exceeded (592)
  _write_checkpoint (621) → SubagentSnapshotStore 序列化 → resume_subagent (242)
```

### 关键文件逐段

**`agent/subagent/manager.py` `class SubAgentManager`**
- `create_subagent`（175 行）：创建子 session 记录。
- `run_subagent`（209 行）：执行子 agent。
- `resume_subagent`（242 行）：从快照恢复。
- `_execute_run`（433 行）：构造子 AgentLoop 并运行。
- `_build_subagent_loop`（503 行）：子 loop 装配（复用主 loop 构造 + BudgetHook + ParentChannel）。
- `_write_checkpoint`（621 行）：写快照。
- `_monitor_run_timeout`（645 行）：时间超限监控。
- `_mark_budget_exceeded`（592 行）：预算超限标记。

**`agent/subagent/snapshot.py`**
- `SubagentSnapshotStore`：session 状态 → JSON 快照序列化/恢复。
- 复用主 session 的 `SessionSnapshot` schema（schema_version/fingerprint/dedup）。

**`agent/subagent/budget.py`**
- `BudgetTracker`（43 行）：累计 input/output token + 时间，`token_overrun`/`time_overrun`。
- `BudgetHook`（69 行）：Hook 监控每个生命周期点（run started / iteration / LLM call / tool execute / completion），超限抛 `BudgetExceededError`。

**`agent/subagent/bus.py`**
- `MessageBus`（224 行）：子 agent 间消息队列。**模型面出口一律 bounded**（issue #224）——`BusMessage`
  单条 ≤ `TRANSCRIPT_ITEM_LIMIT`（4000）、单次投影条数 ≤ `BUS_SNAPSHOT_LIMIT`（20），截断带
  `summary_truncated` 标志。
- `publish`（131 行）/`read`（153 行）：发布/读取；`read()` 的 `max_tokens`/`limit` 被钳到固定上界
  （调用方不能放大返回体）。
- `snapshot_payload`（207 行）：`ReadBus` 出口与调度器权威 `_envelope()` 的 bus 快照来源，二维有界并报告 `messages_omitted`。
- `compact_summary`（199 行）：总线内容压缩成摘要——防上下文爆炸；走队列全文，不受出口截断影响。

**`agent/subagent/patterns.py`**
- 编排模式库：orchestrator-worker / peer-review / hierarchical / 竞标（auction）。
- 各模式定义子 agent 如何 spawn、如何汇总结果。

**`agent/subagent/parent_channel_hook.py` / `context.py` / `protocol.py`**
- ParentChannelHook：把父 agent 上下文注入子 agent。
- protocol：子 agent 与父 agent 的通信协议。

### 设计理由

- **子 agent = 独立 AgentLoop**：复用主循环所有能力（上下文/工具/记忆/trace），不需要第二套运行时。
- **快照恢复而非重跑**：中断后从断点续，避免重跑浪费 token；序列化格式复用主 session，统一 schema。
- **预算硬 kill 是护栏**：子 agent 失控是最贵的失败模式，`BudgetExceededError` 硬 kill + 失败摘要比软提示可靠。
- **消息总线防上下文爆炸**：子 agent 间不直接传完整 transcript，而是传摘要（`compact_summary`），严格 token 预算。
- **编排模式库是面试杀伤力**：能讲出"orchestrator-worker 比较经济、去中心化会上下文炸、竞标模式的实际 case"——这是踩过坑的深度（issue #79 面试表现观察）。

### 另一条线：长期人设 + 会话式群聊（`agent/team/`）

上面那套是**DAG 批处理**（一次性委托、图跑完即止）。`web-agent-group-chat` 加的是**并列**的第二形态：长期存在、面向用户、可交互轮次的多 agent——每个「人设 × 会话面」是一个普通 `AgentSession`，由 `RoomOrchestrator` 按发言位（slot）序列推进。

- **不复用 `SubAgentManager` 的三条代码级否证**：child session 被父 `AgentLoop` 拥有（构造时就绑到父 loop 的 llm）、system prompt 硬编码为「受限的子 agent」、无会话快照（`_sessions` 是进程内存字典）。面试里这比「架构上更干净」有力得多。
- **分层靠依赖倒置**：编排器在 `agent/team/`，只依赖 `SessionRunner`（`run(session_id, message) -> TurnOutcome` 四态返回值）与 `SessionResolver` 两个抽象，由 `web/team.py` 实现并注入——`agent/` 不需要反向 import `web/`（全仓唯一反向点是 CLI 入口的延迟 import）。
- **一条我特意设计成「返回值而非异常」的契约**：`TurnOutcome.status` 四态（`text`/`silent`/`failed`/`timeout`），且 `text` **只来自本次 run**。反例是「读 session 最后一条 assistant」——同 session 并发 run 被 `run_lock` 拒时那次 run 不产生任何新文本，取「最后一条」会把**陈旧内容**当本轮发言写进房间日志。这类「看起来等价、实际会静默错答」的坑适合当面试的深挖点。
- **成本控制**：静默哨兵（`[PASS]` 文本，不新增控制工具污染工具面）、每轮每成员发言上限 + 轮次上限（**单轮三出口**：走完 / 达上限 / 全部剩余成员失败或超时）、单轮超时 240s；`group-unlimited-discussion` 追加**讨论链**形态（无限轮）时，用「全员静默收敛 + 用户停止 + `team:` 三档安全阀（轮数/回合/墙钟）」把成本从「禁止续轮」换成「有界收敛」，并保持 `single` 默认关闭。
- **成员状态可观测**（issue #307）：编排器把 AgentLoop 钩子与流式事件归约成 `idle` / `running` / `thinking` / `typing` / `tool`（优先级 `tool > typing > thinking > running > idle`），只发**完整状态表 + 房间级 `status_seq`**、不转发 token；终态按 seq 权威重置，重连用 `room_state` 快照；桌面左侧 presence，390px 下为顶部 56px 横向成员条。
- **游标是两份、不互相替代**：注入游标 `seen` 在**回合开始**推进（含静默回合，否则连续静默成员的切片边界永不前进、同一段内容被反复注入、上下文无界增长——与 issue #278 同类）；review 游标 `reviewed` 只被记忆 review 推进。用 `seen` 当「落后补齐」的基准会让落后恒为 0、补齐永不触发。
- **单聊 scope 的记忆游标不能用消息表下标**：上下文压缩会就地缩短消息表、session resume 会重建消息表，下标语义必漂移（压缩后游标越过表尾 ⇒ review 永久停摆）。改用 scope 目录内的**持久化待 review 缓冲**，与消息表下标解耦。
