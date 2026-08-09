# W03 · 多 Agent 编排模式

**对应简历 bullet 3**：*"内置 4 种多 Agent 编排模式（orchestrator-worker / peer-review / hierarchical / bidding）+ 子 agent 消息总线、token 预算硬 kill 与快照恢复"*

## 代码入口

```
agent/subagent/
├── manager.py       ← SubAgentManager（spawn / run / cancel / resume / inspect）
├── patterns.py      ← 4 种编排模式的确定性骨架
├── bus.py           ← 子 agent 消息总线（摘要交换 + 三层预算）
├── budget.py        ← 每 run token/time 预算 + 硬 kill 双路径
├── snapshot.py      ← 子 agent 运行检查点持久化
├── context.py       ← contextvar（bus、spawn_depth）
└── parent_channel_hook.py

工具面（loop.py:358-371 注入，10 个）：CreateSubagent / RunSubagent / ListSubagents /
  GetSubagentRun / CancelSubagentRun / InspectSubagentTranscript /
  PublishBusMessage / ReadBus / ResumeSubagent / RunPattern
```

## 核心逻辑

### 4 种编排模式（patterns.py）

统一骨架：**spawn N → wait → collect（确定性骨架）+ 模式内智能由 LLM 子 agent 承载**。

| 模式 | 文件行 | 讲法 |
|------|--------|------|
| **orchestrator-worker** | patterns.py:100 | 协调者扇出 N 并行 worker，聚合。worker 之间不通信 |
| **peer-review** | patterns.py:114 | producer → reviewer 批判 → 直到 APPROVED 或 max_rounds（默认 3）。critique 回喂下一轮 |
| **hierarchical** | patterns.py:152 | N 个 manager 各跑子任务，可再嵌套 spawn（depth 默认 3） |
| **bidding** | patterns.py:167 | N 个 proposer 独立产出 → 独立 selector 选最优。**故意不用 bus 传提案**（drop-oldest 会丢关键投标），用紧凑摘要 + 读 artifacts |

**worker 失败不 fail-fast**：聚合信封逐 worker 报 `{subagent_id, status, summary, usage}` + 模式级计数（_aggregate），保证 benchmark 完成率/成本可比。

### 消息总线三层预算（bus.py:9-18）

1. **有界队列**：max_messages=100，满了 drop-oldest（NATS DiscardOld 语义）
2. **发布侧摘要**：PublishBusMessageTool 用 `_summarize` 先把内容折叠到 `max_tokens`（默认 400）以下再发——调 `LLMSummarizer.summarize`，LLM 不可用时降级截断 `content[:max_tokens*4]`（subagents.py:222-237）
3. **消费侧 token 窗口**：read() 只返回最近、能装进 max_read_tokens=2000 的（LangGraph trim_messages 语义）；单条超窗消息仍会浮出（bus.py:114-119）

bus 每次编排 run 新建，contextvar 注入，run 结束 reset。**换语义摘要，不换原始转录**。

### 预算硬 kill 双路径（budget.py + manager.py:645）

```
路径 A: token 超限
  BudgetHook.after_llm_call → token_overrun() → raise BudgetExceededError
  → _execute_run 先写检查点再标记 budget_exceeded → 自然结束（无外部取消）

路径 B: 时间超限（卡在长时间工具调用，如挂死 Bash）
  hook 不触发 → _monitor_run_timeout 后台 monitor
  → 先把 _budget_kill_reason="time" 写在 run 上（manager.py:660）再 task.cancel()
  → CancelledError handler 见 reason 非空 → 记 budget_exceeded 而非 cancelled
```

**两条路径都先写检查点**，budget kill 永远可恢复。

### 快照恢复（snapshot.py + manager.py:242）

- 检查点 = 扩展版 `SessionSnapshot`（加 objective/blockers/next_steps/bus_summary），复用 SessionStore（schema 版本/哈希去重/原子写）。
- 路径 `<workspace>/.asterwynd/subagents/<run_id>/`，**用完整 run_id 做 key** 防碰撞覆盖。
- 恢复语义：**transcript 级而非 stack 级**——折叠历史，恢复时 model 重试 in-flight 工具调用。
- bus 摘要折叠进快照（manager.py:626-638）。

### 模式钳位 + 并发护栏

- **模式钳位**（manager.py:697）：子 agent 模式 ≤ 父模式，子代理永远不能比父代理高权限。
- **护栏**（manager.py:714）：max_concurrent_runs=4、max_depth=3（防无界烧钱）。

## 简历核实

| 简历 | 核实 | 结论 |
|------|------|------|
| "4 种多 Agent 编排模式" | PATTERNS dict 正好 4 种 | ✅ |
| "子 agent 消息总线" | bus.py 吻合 | ✅ |
| "token 预算硬 kill 与快照恢复" | budget.py 双路径 + snapshot.py | ✅ |

## 面试加分点

1. **"先标记后 cancel"**——time kill 先写 `_budget_kill_reason` 再 cancel，避免把预算 kill 误报成"用户取消"。
2. **bidding 故意绕开 bus 传提案**——"drop-oldest 会丢关键投标"的设计取舍。
3. **恢复是 transcript 级而非 stack 级**——诚实承认边界，比吹"完全恢复"可信。
