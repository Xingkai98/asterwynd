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
- `MessageBus`（53 行）：子 agent 间消息队列。
- `publish`（70 行）/`read`（92 行）：发布/读取（支持范围）。
- `compact_summary`（127 行）：总线内容压缩成摘要——防上下文爆炸。

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
