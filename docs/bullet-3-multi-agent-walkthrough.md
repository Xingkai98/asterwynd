# Bullet 3: 多 Agent 编排模式 — 代码走读

> 简历原文：内置 4 种多 Agent 编排模式（orchestrator-worker / peer-review / hierarchical / bidding）+ 子 agent 消息总线、token/时间双维度预算硬 kill 与快照恢复

---

## 整体架构

多 Agent 能力域由 4 个模块构成，全部在 `agent/subagent/` 目录：

```
agent/subagent/
├── patterns.py       ← 4 种编排模式 + PATTERNS 注册表 + run_pattern 入口
├── bus.py            ← MessageBus：语义摘要交换 + 三层 token 预算
├── budget.py         ← BudgetTracker/Hook：token/时间双维度硬 kill
├── snapshot.py       ← SubagentSnapshotStore：快照持久化 + 恢复
├── manager.py        ← SubAgentManager：子 agent 全生命周期管理
├── context.py        ← ContextVar：spawn_depth / bus 上下文传递
├── protocol.py       ← ParentChannel：父子 agent 结果回传通道
└── parent_channel_hook.py ← ParentChannelHook：结果注入父 agent 消息

agent/tools/builtin/
└── subagents.py      ← 10 个 LLM 可见子 agent 工具
```

控制平面完全复用 `SubAgentManager`，不引入单独的 orchestration control plane（见 spec `scenario: orchestration-state-persists-without-dev-workflow-coupling`）。编排由 LLM 通过 `RunPattern` 工具（`subagents.py:320-354`）触发，模式内部执行确定性骨架（spawn N → wait → collect）。

---

## 1. 4 种多 Agent 编排模式

**文件**：`agent/subagent/patterns.py`

### 1.0 注册表：确认恰好 4 种模式

```python
# patterns.py:203-208
PATTERNS: dict[str, type[OrcPattern]] = {
    "orchestrator-worker": OrchestratorWorkerPattern,
    "peer-review": PeerReviewPattern,
    "hierarchical": HierarchicalPattern,
    "bidding": BiddingPattern,
}
```

`RunPattern` 工具（`subagents.py:328-329`）的 `pattern` 参数 `enum` 恰含此 4 个值，与 `PATTERNS` 一一对应。调用路径：

```
LLM 调 RunPattern 工具
  → RunPatternTool.execute()                  (:347-354)
    → run_pattern(manager, pattern, task, params) (:211-235)
      → 创建 MessageBus + set_bus contextvar    (:227-228)
      → PATTERNS[pattern](...).run()            (:230-231)
      → 结果附 bus.snapshot_payload()           (:232)
      → reset_bus                               (:235)
```

### 1.1 Orchestrator-Worker（`:100-111`）

**模式**：coordinator（即调用 agent）fan-out 到 N 个 parallel worker，所有 worker 执行相同 task，互不通信，最后 aggregate。

```python
class OrchestratorWorkerPattern(OrcPattern):
    name = "orchestrator-worker"

    async def run(self) -> dict:
        worker_count = max(1, int(self.params.get("workers", 3)))       # :104
        worker_ids = [
            self._spawn(f"worker-{i}", "parallel worker")
            for i in range(worker_count)
        ]                                                              # :105-107
        results = await asyncio.gather(
            *[self._run_worker(wid, self.task) for wid in worker_ids]  # :108-110
        )
        return self._aggregate(list(results))
```

**关键参数**（`:104`）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `workers` | 3 | 并行 worker 数，`max(1, ...)` 保底至少 1 个 |
| `worker_max_tokens` | None | 透传给 `_run_worker`（`:69`），覆盖每个 worker 的 token 预算 |
| `worker_max_time_s` | None | 透传给 `_run_worker`（`:70`），覆盖每个 worker 的时间预算 |

Worker 之间不通信（设计注释 line 12: "Workers do not talk to each other."）。

### 1.2 Peer-Review（`:114-149`）

**模式**：一个 producer 产出 proposal，一个 reviewer 评审；送代至 reviewer 回复 APPROVED 或达到 max_rounds。

```python
class PeerReviewPattern(OrcPattern):
    name = "peer-review"
    max_rounds = max(1, int(self.params.get("max_rounds", 3)))   # :118
```

**送代流程**（`:124-144`）：

```
for round in range(max_rounds):
    ① producer 执行 self.task
    ② 如果 producer 失败（status != "completed"）→ 立即返回
    ③ reviewer 收到："Review the following proposal. Reply with exactly one line
       starting with APPROVED if it is acceptable, or CRITIQUE followed by
       the specific issues if it needs revision.\n\nPROPOSAL:\n<summary>"
    ④ reviewer 回复以 "APPROVED" 开头 → 返回 producer + reviewer 的 aggregate
    ⑤ 否则：self.task 追加 "Address the reviewer's critique:\n<review>"，
       下一轮 producer 重新执行
```

**max_rounds 耗尽未批准**（`:147-149`）：返回最后一次真实的 producer + reviewer 结果（不丢信息）。

**关键参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_rounds` | 3 | 最多送代轮次 |

### 1.3 Hierarchical（`:152-164`）

**模式**：N 个 manager 子 agent 各自执行 task，每个 manager 可以继续 spawn 自己的 worker（嵌套 spawn）。

```python
class HierarchicalPattern(OrcPattern):
    name = "hierarchical"
    team_count = max(1, int(self.params.get("teams", 2)))       # :156
```

嵌套 spawn 能力由 decision D4 启用（`manager.py:130-131, :143-155` 中的 `max_concurrent_runs` / `max_depth` guardrails 为此而设）。Manager 子 agent（subagent）在 loop 中通过 `CreateSubagent` + `RunSubagent` 工具递归创建孙子 agent，形成树状工作组。

**关键参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `teams` | 2 | 并行 manager 数 |

**嵌套深度上限**（`:722-726`）：`max_depth` 默认 3，即 root → child → grandchild 最深 3 层。`hierarchical` 模式中 manager 子 agent 本身占用一层 depth，所以在其下最多再 deep 2 层。

### 1.4 Bidding（`:167-200`）

**模式**：N 个 proposer 独立产出方案 → 一个 selector 子 agent 读取 compact summary，选出最佳 proposal。

```python
class BiddingPattern(OrcPattern):
    name = "bidding"
    proposer_count = max(2, int(self.params.get("proposers", 3)))  # :171
```

**与 bus 的关系**（`:179-180` 注释）：

> "Selector input = compact proposal summaries (not the bus — drop-oldest could lose a key bid)"

bidding 的 proposal 传递**故意不走 MessageBus**，而是直接拼接到 selector 的 task prompt 中。原因是 bus 的 `drop-oldest` 丢旧策略可能丢弃关键 bid（bus 为限制爆炸设计，牺牲完整性保预算）。

**关键参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `proposers` | 3 | 独立 proposer 数，`max(2, ...)` 确保至少 2 个 |
| `worker_max_tokens` | None | 透传 token 预算 |
| `worker_max_time_s` | None | 透传时间预算 |

### 1.5 共性基础设施

**基类 `OrcPattern`**（`:38-97`）：所有模式继承，提供：

| 方法 | 行号 | 功能 |
|------|------|------|
| `_spawn(name, description)` | `:59-62` | 调 `manager.create_subagent()` 创建子 agent session，返回 `subagent_id` |
| `_run_worker(subagent_id, task)` | `:64-71` | 调 `manager.run_subagent(wait=True)` 阻塞等待子 agent 完成 |
| `_aggregate(results)` | `:73-97` | 按统一格式汇总：`pattern / task / completed / failed / workers / summary` |

**统一 envelope 格式**（`:90-97`）：

```python
{
    "pattern": self.name,           # 模式名
    "task": self.task,              # 原始任务
    "completed": N,                 # 成功 worker 数
    "failed": N,                    # 失败 worker 数
    "workers": [...],               # 每个 worker 的 {subagent_id, status, summary, reason, usage}
    "summary": "\n".join(parts),    # 文本摘要
}
```

bidding 模式额外附 `"selected"` + `"selector"` 字段（`:194-199`）。

**并行执行**：所有模式的 worker 通过 `asyncio.gather` 并行执行（`:108, :161, :176`），而非串行。这是 "spawn N → wait → collect" 的确定性骨架。

---

## 2. 子 Agent 消息总线

**文件**：`agent/subagent/bus.py`

### 2.1 设计定位

每个编排 run 创建一个 `MessageBus` 实例（`run_pattern()` 中 `:227`），通过 contextvar `_bus`（`context.py:25`）对所有 worker 可见。bus 只存活于 run 期间，不跨 run 持久化。交换的是**语义摘要**，从来不是原始 transcript。

### 2.2 三层 Token 预算（`:12-16` 注释 + 代码实现）

#### Layer 1: Bounded Queue — 容量约束（`:53-64, :78`）

```python
class MessageBus:
    def __init__(self, *, max_messages: int = 100, ...):  # :57
        self.max_messages = max_messages
        self._messages: deque[BusMessage] = deque()

    def publish(self, ...):
        if len(self._messages) >= self.max_messages:       # :78
            self._messages.popleft()  # drop-oldest         # :79
```

- **默认上限**：100 条消息
- **溢出策略**：drop-oldest（丢弃最旧消息）
- **TTL 可选**（`:59`）：`ttl_s: float | None = None`，在 `read()` 中检查过期（`:112`），默认关闭

#### Layer 2: Publish-Side Summarization — 发布端压缩（`subagents.py:208-237`）

```python
# subagents.py:208
max_tokens = kwargs.get("max_tokens", 400)    # 默认每条约 400 token
summary = content
token_count = estimate_tokens(content)         # ~4 chars/token
if token_count > max_tokens:
    summary = await self._summarize(content, max_tokens)   # LLM 摘要
```

`_summarize()` 调 `LLMSummarizer` 做真正的摘要（`:222-237`），LLM 不可用时退化到 `content[:max_tokens * 4]` 截断。

#### Layer 3: Consume-Side Token Window — 消费端窗口（`bus.py:92-125`）

```python
def read(self, *, max_tokens: int | None = None, ...):
    budget = max_tokens if max_tokens is not None else self.max_read_tokens  # :105
    # 默认 max_read_tokens = 2000                                             # :58
    for msg in reversed(self._messages):  # 从最新开始                        # :109
        if used + msg.token_count > budget:
            if not collected:
                collected.append(msg)       # 单条超预算也保留最新一条         # :117-118
            break
        collected.append(msg)
        used += msg.token_count
    collected.reverse()  # 返回时 oldest-first                              # :124
```

**核心语义**（LangGraph `trim_messages` 风格）：
- 从最新消息开始往前累加，直到 token 预算耗尽
- 单条消息即使超过整个窗口，也保留最新一条（消费者不盲目于最新状态）
- 支持 `topics` 过滤、`limit` 截断、`ttl_s` 过期检查

### 2.3 Bus 生命周期与上下文传递

```python
# patterns.py:227-235
async def run_pattern(...):
    bus = MessageBus()
    token = set_bus(bus)          # 注入 contextvar
    try:
        instance = PATTERNS[pattern](...)
        result = await instance.run()
        result["bus"] = bus.snapshot_payload()  # 快照 payload 附在结果
        return result
    finally:
        reset_bus(token)           # 清理 contextvar
```

**snapshot_payload**（`:135-139`）：包含 messages 列表 + `max_read_tokens`。这个 payload 可以被 recovery 路径注入到续传上下文（`snapshot.py:46-73` 中 `bus_summary` 字段）。

### 2.4 LLM 可见工具

| 工具 | 文件:行号 | 功能 |
|------|-----------|------|
| `PublishBusMessage` | `subagents.py:181-237` | 发布摘要到 bus（sender/topic/content/max_tokens） |
| `ReadBus` | `subagents.py:240-280` | 消费 bus 摘要（topics/max_tokens/limit 过滤） |

这两个工具是子 agent 通过 bus 协作的唯一接口。所有消息经过 `PublishBusMessage` 的统一摘要压缩才进入 bus。

### 2.5 数据结构

```python
# bus.py:33-40
@dataclass
class BusMessage:
    message_id: str           # uuid4().hex[:8]
    sender: str               # 发送者标识
    topic: str                # 主题标签
    summary: str              # 语义摘要内容
    token_count: int          # 估算 token 数（~4 chars/token）
    timestamp: float          # time.time()
```

---

## 3. Token/时间双维度预算硬 Kill

**文件**：`agent/subagent/budget.py` + `agent/subagent/manager.py`

### 3.1 BudgetTracker — 预算累加器（`budget.py:43-66`）

```python
class BudgetTracker:
    def __init__(self, max_tokens: int | None = None, max_time_s: float | None = None):
        self.max_tokens = max_tokens       # 可为 None（不限）
        self.max_time_s = max_time_s       # 可为 None（不限）
        self.tokens = 0                     # 累加计数器
        self.started_at = time.time()

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.tokens += input_tokens + output_tokens    # :57-58

    def token_overrun(self) -> bool:       # :60-61
        return self.max_tokens is not None and self.tokens > self.max_tokens

    def time_overrun(self) -> bool:        # :63-66
        if self.max_time_s is None:
            return False
        return time.time() - self.started_at > self.max_time_s
```

**每次 LLM 调用后累加**（`:86-94`）：`BudgetHook.after_llm_call()` 读取 `response.usage.input_tokens + output_tokens` 并累加到 tracker。

**配置来源**（`config.py:246-258`）：

```python
@dataclass(frozen=True)
class SubagentsConfig:
    max_concurrent_runs: int = 4
    max_depth: int = 3
    default_max_tokens: int | None = None       # 默认无 token 限制
    default_max_time_s: float | None = None     # 默认无时间限制
```

**预算默认关闭**：`default_max_tokens` 和 `default_max_time_s` 默认都是 `None`。需要用户在 `asterwynd.yaml` 中配置 `subagents.budget.max_tokens` / `subagents.budget.max_time_s` 或在 `RunSubagent` 调用时显式传参，预算限制才生效。

### 3.2 两条 Kill 路径

设计中严格区分两类超限场景及其触发路径（`budget.py:5-15` 注释）：

#### 路径 1: Token 超限 — Hook 内检测（`budget.py:86-94`）

```
AgentLoop 每次 LLM 调用后:
  BudgetHook.after_llm_call(response)
    → tracker.add(input_tokens, output_tokens)           # :88
    → if tracker.token_overrun():                        # :89
        raise BudgetExceededError("token", used, limit)  # :90-94

_execute_run (manager.py:457-461):
  except BudgetExceededError as exc:
    self._write_checkpoint(session, run)                  # 快照
    self._mark_budget_exceeded(session, run, exc.dimension, ...)
```

Token 超限在 LLM 调用边界（`after_llm_call` hook）被捕到。不需要外部 cancel —— `BudgetExceededError` 直接 unwinds loop，manager 在 exception handler 中写 checkpoint + 标记 `budget_exceeded`。

#### 路径 2: 时间超限 — Monitor 协程硬杀（`manager.py:645-666`）

```
run_subagent → _launch_run:
  if run.max_time_s is not None:                           # :352
    asyncio.create_task(self._monitor_run_timeout(session, run))

_monitor_run_timeout:
  await asyncio.sleep(run.max_time_s)                      # :656
  task = self._active_tasks.get(run.run_id)
  run._budget_kill_reason = "time"                         # :660  ← 先标记
  self._write_checkpoint(session, run)                     # :661  ← 先快照
  task.cancel()                                            # :662  ← 再取消

_execute_run (manager.py:462-471):
  except asyncio.CancelledError:
    if run._budget_kill_reason is not None:
      self._mark_budget_exceeded(session, run, run._budget_kill_reason, ...)
    else:
      self._mark_cancelled(session, run, trace)             # 普通取消
```

时间超限使用独立协程 `asyncio.sleep(run.max_time_s)` 后 cancel 跑趟 task。关键顺序是 **先标记 `_budget_kill_reason` + 先写 checkpoint，再 cancel**，这样被取消后 handler 能区分 "预算杀" vs "普通取消"（`:464`），终止状态正确标记为 `budget_exceeded` 而非 `cancelled`。

时间超限处理的是"tool 卡死"场景（如 hung Bash），此时 hook 永远不触发，只能用外部协程硬杀。

### 3.3 双路径的共同行为

1. **都先写 checkpoint 再杀**（`:458, :463, :473`），保证预算 kill 后的 run 总是可恢复的
2. **都标记 `status = "budget_exceeded"`**（`manager.py:602`），reason 格式 `"budget exceeded (token)"` / `"budget exceeded (time)"`
3. **都回填 token 使用量**（`:609-610`）：即使未正常完成，`run.usage` 也记录实际消耗的 token，用于 benchmark 成本归因

### 3.4 BudgetHook 的注册（`:527-528`）

```python
# manager.py:527-528
if budget is not None:
    hooks.hooks.append(BudgetHook(budget))
```

`BudgetHook` 是 per-run 实例化（`:442-446`），每个 run 独立一个 `BudgetTracker`，不共享跨 run 状态。必须实现所有 7 个 Hook 方法（`:80-111`），因为 `HookManager` 按属性名分发，缺方法会抛 `AttributeError`。

---

## 4. 快照恢复

**文件**：`agent/subagent/snapshot.py` + `agent/subagent/manager.py`

### 4.1 存储后端

```python
# snapshot.py:27-35
class SubagentSnapshotStore:
    def __init__(self, root: str | Path):
        self._store = SessionStore(str(root))       # 复用主 session 的 SessionStore

    @classmethod
    def for_workspace(cls, workspace_root):
        return cls(Path(workspace_root) / ".asterwynd" / "subagents")
```

**关键设计**：
- 复用 `SessionStore`（`snapshot.py:31`），继承其 `schema_version` 兼容、SHA-256 去重、`tmp+replace` 原子写入机制
- 存储路径 `:35`：`<workspace_root>/.asterwynd/subagents/<run_id>/`
- key 为**完整 `run_id`**（非 8 字符 `subagent_id`），不可能与其他 run 碰撞（`:13` 注释）

### 4.2 快照结构

```python
# snapshot.py:46-73
def snapshot_for_run(self, session, run, bus_summary=""):
    return SessionSnapshot(
        schema_version="1.0",
        session_id=run.run_id,         # ← key 是 run_id
        messages=list(session.messages),  # 完整 transcript
        mode=session.mode,
        todos=[],                      # 子 agent 快照无待办
        active_skills=[],
        run_id=run.run_id,
        iteration=_iteration_from_run(run),  # 从 trace 计算已执行步数
        objective=run.task,
        blockers=[],
        next_steps=[],
        bus_summary=bus_summary,        # 编排 bus 摘要（compact_summary()）
    )
```

`bus_summary` 字段（`:72`）：快照时把活跃 bus 的 `compact_summary()` 折叠进快照，续传后 agent 能看到之前的协作上下文。

### 4.3 Checkpoint 写入时机（`manager.py:621-643`）

```python
def _write_checkpoint(self, session, run):
    # 在以下 4 个位置调用：
    store = self._snapshot_store()
    bus_summary = ""
    bus = current_bus()
    if bus is not None:
        bus_summary = bus.compact_summary()        # 折叠 bus 摘要
    store.save(store.snapshot_for_run(session, run, bus_summary))
```

| 触发场景 | 行号 | 说明 |
|----------|------|------|
| `BudgetExceededError`（token 超限） | `:458` | in-loop 检测到 token 超限 |
| `asyncio.CancelledError`（超时 kill + 人工 cancel） | `:463` | 时间超限 monitor 杀 / 用户取消 |
| 其他异常 | `:473` | 任何未处理异常 |
| 时间超限 monitor 中 | `:661` | monitor kill 前的额外保护 |

### 4.4 恢复路径（`manager.py:242-296`）

```python
async def resume_subagent(self, *, subagent_id, task, run_id, ...):
    snapshot = self._snapshot_store().load(run_id)   # 加载快照
    if snapshot is None:
        raise KeyError(f"no checkpoint found for run {run_id}")
    # 重置 session transcript 为 system + continue prompt
    session.messages = [
        system_message("你是一个受限的子 agent。...")
    ]
    # _launch_run 传入 resume_snapshot
    await self._launch_run(session, run, resume_snapshot=snapshot)
```

**恢复是 transcript 级，非 call-stack 级**（`:256-258` 注释）：

```
"Resume is transcript-level, not stack-level (issue 79, decision D2)"
```

这意味着：
- 快照恢复后，AgentLoop 接收 `resume_snapshot`（`manager.py:454`）：传入 `loop.run()` 的 `resume_snapshot` 参数
- AgentLoop 的 resume 路径（`loop.py:557-584`）从快照重建 transcript，附加续传标记
- **未完成的 tool_call**：对话历史中 assistant tool_call 消息存在但 tool_result 缺失 → 模型看到不完整的工具链 → 自然地重新发起工具调用
- **不存在代码级别的工具栈恢复**：不尝试重新执行未完成的 tool_call

### 4.5 LLM 可见的 Resume 工具

```python
# subagents.py:283-317
class ResumeSubagentTool(Tool):
    name = "ResumeSubagent"
    # params: subagent_id, run_id, task, wait, timeout_s, max_tokens, max_time_s
```

主 agent 可以通过此工具主动 resume 任何有 checkpoint 的已中断 run。

---

## 5. 并发与深度护栏

**文件**：`agent/subagent/manager.py`

### 5.1 护栏参数

```python
# manager.py:146-155
self.max_concurrent_runs = max_concurrent_runs or getattr(guardrails, "max_concurrent_runs", 4)
self.max_depth = max_depth or getattr(guardrails, "max_depth", 3)
```

默认值来自 `SubagentsConfig`（`config.py:255-256`）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_concurrent_runs` | 4 | 最大并行子 agent 数 |
| `max_depth` | 3 | 最大嵌套深度（root = 0） |

### 5.2 拦截时机（`:714-732`）

```python
def _check_guardrails(self):     # Pure pre-spawn guard
    depth = current_spawn_depth() + 1
    if depth > self.max_depth:
        raise RuntimeError(f"depth {depth} > max_depth {self.max_depth}")
    active = len(self._active_tasks)
    if active >= self.max_concurrent_runs:
        raise RuntimeError(f"{active} active runs >= max_concurrent_runs {self.max_concurrent_runs}")
```

在 `run_subagent` 的 `:222` 调用，创建 run record 之前，所以被拒的 spawn 不留痕迹。

---

## 6. 子 Agent 工具清单

**文件**：`agent/tools/builtin/subagents.py`

共 10 个 LLM 可见工具，全部权限 `SUBAGENT_CONTROL_PERMISSION`：

| # | 工具 | 行号 | 功能 |
|---|------|------|------|
| 1 | `CreateSubagent` | `:14-40` | 创建子 agent session（name / description / mode） |
| 2 | `RunSubagent` | `:43-71` | 启动子 agent 执行 task（wait / timeout_s） |
| 3 | `ListSubagents` | `:74-87` | 列出当前可见子 agent |
| 4 | `GetSubagentRun` | `:90-118` | 查询子 agent run 状态/结果 |
| 5 | `CancelSubagentRun` | `:120-145` | 取消活跃子 agent run |
| 6 | `InspectSubagentTranscript` | `:148-178` | 查看子 agent transcript（summary / recent_messages） |
| 7 | `PublishBusMessage` | `:181-237` | 发布摘要到消息总线 |
| 8 | `ReadBus` | `:240-280` | 消费消息总线摘要 |
| 9 | `ResumeSubagent` | `:283-317` | 从 checkpoint 恢复中断的 run |
| 10 | `RunPattern` | `:320-354` | 运行编排模式（4 种枚举 pattern） |

---

## 7. 事实核查汇总

对简历表述的每个事实点进行代码级确认：

| 简历事实 | 代码确认 |
|----------|----------|
| "内置 4 种多 Agent 编排模式" | `patterns.py:203-208` — `PATTERNS` dict 恰好 4 个 key |
| "orchestrator-worker" | `patterns.py:100-111` — `OrchestratorWorkerPattern`，默认 3 worker 并行 |
| "peer-review" | `patterns.py:114-149` — `PeerReviewPattern`，最多 3 轮送代 |
| "hierarchical" | `patterns.py:152-164` — `HierarchicalPattern`，默认 2 个 manager，可嵌套 spawn（D4） |
| "bidding" | `patterns.py:167-200` — `BiddingPattern`，默认 3 proposer + 1 selector |
| "子 agent 消息总线" | `bus.py:53-139` — `MessageBus`，三层 token 预算，三层语义：bounded queue / publish summarization / consume token window |
| "token/时间双维度" | `budget.py:46-66` — `BudgetTracker` 同时跟踪 `max_tokens` 和 `max_time_s` |
| "硬 kill" | `budget.py:86-94` token overrun → `BudgetExceededError`，`manager.py:645-666` time overrun → `task.cancel()` |
| "快照恢复" | `snapshot.py:27-73` — `SubagentSnapshotStore`，`manager.py:242-296` — `resume_subagent` |

**标注"默认关闭"或"需配置启用"：**

| 功能 | 默认状态 | 说明 |
|------|----------|------|
| Token 预算限制 | **关闭** | `config.py:257` — `default_max_tokens: int \| None = None` |
| 时间预算限制 | **关闭** | `config.py:258` — `default_max_time_s: float \| None = None` |
| 消息总线 | **按 run 创建** | 仅 `run_pattern()` 内部创建（`patterns.py:227`），直接调子 agent 工具的 run 不创建 bus |
| Checkpoint 快照 | **中断时自动** | 异常/取消/预算杀路径自动写，正常完成不写 |

---

## 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/subagent/patterns.py` | 4 种编排模式（OrcPattern 基类 + 4 子类 + PATTERNS + run_pattern 入口） |
| `agent/subagent/bus.py` | MessageBus：三层 token 预算（bounded queue / publish summarization / consume window） |
| `agent/subagent/budget.py` | BudgetTracker + BudgetHook + BudgetExceededError：双维度预算硬 kill |
| `agent/subagent/snapshot.py` | SubagentSnapshotStore：快照持久化 + SessionStore 复用 |
| `agent/subagent/manager.py` | SubAgentManager：全生命周期（create / run / resume / cancel / transcript）+ guardrails |
| `agent/subagent/context.py` | ContextVar：spawn_depth + bus 上下文传递 |
| `agent/subagent/protocol.py` | ParentChannel：父子 agent 结果回传 |
| `agent/subagent/parent_channel_hook.py` | ParentChannelHook：结果注入父 agent 消息 |
| `agent/tools/builtin/subagents.py` | 10 个 LLM 可见子 agent 工具（含 RunPattern / ResumeSubagent / PublishBusMessage / ReadBus） |
| `agent/config.py:246-258` | SubagentsConfig：max_concurrent_runs=4 / max_depth=3 / budget defaults=None |
| `openspec/specs/multi-agent-collaboration/spec.md` | 多 Agent 协作能力域规格（6 requirements） |
