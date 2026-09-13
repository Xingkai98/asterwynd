# Design: subagent 并发队列化

## Context

当前 subagent 编排把「声明多少 worker」和「物理同时跑几个」耦合死：

- `agent/subagent/manager.py` 的 `_check_guardrails()`（`:714-732`）在 spawn 时 **fail-fast**，`max_concurrent_runs=4`（`agent/config.py:255`）让模型连「声明第 5 个」都做不到。
- `run_subagent` 在 `await waiter.wait()` 之前就把子任务注册进 `_active_tasks`（`manager.py:342-347`），父 agent 自己也占一个并发槽 → 父持槽等子自我饥饿：`orchestrator-worker` 默认 `workers=3` + 父 = 4 刚好卡满上限（`patterns.py:104`），模型自由设 `workers=4` 或嵌套一层就抛错。
- subagent 工具全未标 `parallelizable`（`agent/tools/builtin/subagents.py`），模型一轮发多个 `RunSubagent(wait=true)` 会被 `loop._execute_tool_calls`（`loop.py:1225-1255`）串行执行。

本 change 是 wayfinder 地图 #170（subagent 编排自由度）的 Phase 1 地基：把并发护栏从 fail-fast 改成「声明与执行解耦的队列运行时」。决策来源：R1 #171 调研、G2 #173 并发护栏决议、G5 #176 父子身份决议。

## Goals / Non-Goals

**Goals**

1. 并发护栏队列化：`max_active`（默认 5）+ `max_queued_runs`（默认 20）+ `queue_full` 信号，声明与执行解耦。
2. 并发许可绑「执行」不绑「等待」，修父持槽等子自我饥饿 + 免 Semaphore held-across-await 死锁。
3. 深度到限撤 spawn 工具（复用 `expose_subagent_tools`），而非抛错。
4. per-orchestration 累计 spawn 计数（`max_spawns=200`）。
5. run 状态机 `declared→queued→running→terminal`；父子身份显式字段。
6. `RunSubagent`/`GetSubagentRun` 标 parallelizable。

**Non-Goals**

- 不做 Workflow DSL / 声明式图（C2）。
- 不做 workflow 级总预算 / 成本归因（C4，本 change 仅预留 `workflow_id` 字段）。
- 不做结果引用 / 分层汇聚（C3）。
- 不做 benchmark replay（C5）。
- 不做每个 subagent 单独设模型（wayfinder #170 Out of scope）。

## Decisions

### D1 — 并发许可绑「执行」不绑「等待」

并发计数从「创建 task 即占槽」改为「实际执行 LLM/tool 时占槽」。父 agent 阻塞等待子 agent（`wait=True` 或 gather）时不持有并发许可。

- **动机**：当前 `manager.py:342-347` 在 `await waiter.wait()` 前注册 `_active_tasks`，父持槽等子自我饥饿；若用 `asyncio.Semaphore` 实现，父 acquire 后 await 子 = held-across-await 死锁（`max_active=1` 时父占唯一槽等子，子永拿不到槽）。
- **实现要点**：许可在 `_execute_run` 真正调用 `loop.run()` 前 acquire、返回后 release；`run_subagent` 排队/等待路径不持许可。

### D2 — 队列化并发（max_active + max_queued_runs）

`_check_guardrails` 拆两层：

1. **准入层**（仍 fail-fast）：session 不存在、同 session 已有 active run、`max_depth` 程序性超限、累计 spawn 超限、总预算耗尽（预留）、DSL 非法（预留）。
2. **排队层**（不再抛错）：瞬时并发 ≥ `max_active` → 进 `asyncio.Queue`；队列长度 ≥ `max_queued_runs` → 返回 `queue_full` 信号。

- **默认值**：`max_active=5`、`max_queued_runs=20`、`max_depth=3`（保留）、累计 `max_spawns=200`。
- **依据**：Codex `max_threads` 到限排队；Claude Code 只 fail + 计数洞是反例（#68110/#69206）。

### D3 — run 状态机 declared→queued→running→terminal

`SubagentRunRecord.status` 增加 `queued` 态：`run_subagent` 入队即返回 `queued` + `run_id`（`wait=false`）；`wait=true` 等该 run 到终态。`_active_tasks` 只记实际执行任务；排队 run 有独立 RunRecord。

### D4 — 深度到限撤 spawn 工具

spawn 深度到 `max_depth` 时，从子 agent 工具注册移除 spawn 类工具（`CreateSubagent`/`RunSubagent`/`RunPattern`/`ResumeSubagent`），让子 agent 自己做任务而非抛错。

- **实现要点**：`_build_subagent_loop`（`manager.py:503-540`）按 `current_spawn_depth() >= max_depth` 决定 `expose_subagent_tools` 开/关。本仓已有该开关（`loop.py:181-183`），改动量小。
- **依据**：Claude Code v2.1.217+ 到限主动撤工具；「抛异常」会诱使模型重试/换名再试。
- **保留**：`max_depth` 程序性超限仍 fail-fast（防御性）。

### D5 — 累计 spawn 计数

新增 per-orchestration 累计 spawn 上限（`max_spawns=200`）。用 contextvar 或显式计数器挂在 orchestration 根上下文，每次 `create_subagent`/`run_subagent` 递增，超限拒绝。区别于瞬时并发 `max_active`。

- **依据**：Claude Code 只限瞬时并发、无累计计数 → #69206 翻车（218 spawned）。
- **实现注记（scope 载体，用户 2026-09-13 拍板）**：本 change 取 **manager 生命周期为 orchestration 边界**（manager 内单一 `_spawn_count`，无复位通道）：CLI 一次 `asterwynd run`、benchmark 单 task、web 单 session 各自正好构造一个 manager（`agent/main.py:289`、`benchmarks/agent_runner.py:308`、`web/session.py:447`），前两者与「per-orchestration 根 run 起算」等价；web 长会话跨 turn 累计、不复位——**保守护栏语义，`max_spawns=200` 为巨量、几乎不会误伤**。**后续项（记 C2 `workflow-dsl-scheduler` 前置）**：正确语义应为「每 orchestration 复位 + `root_run_id` 计数桶」——`max_spawns` 防的是 #69206 式单次展开爆炸（218 spawned 是一次任务递归展开），非长会话累积；但队列化后「根 run 终结即复位」会让排队子 run（活过父 run 终结）的迟到 spawn 归错预算桶，需按 `root_run_id` 归因到各自顶层 run 的计数桶，这与 C2 引入的 workflow/orchestration 身份概念天然配套，故推迟到 C2 一起做。

### D6 — 父子身份显式字段

`SubagentSessionRecord` 增 `parent_run_id`/`workflow_id`/`node_id`/`depth` 显式字段；`depth` 由 ContextVar 改显式 RunRequest 字段传递。ContextVar 只作当前执行上下文的便利访问。

- **动机**：队列 worker 延迟执行时（父可能已结束），ContextVar 传递的父子关系会丢；显式字段保证逻辑父子关系、支撑后续（C4）按子树取消/归因。

### D7 — 工具 parallelizable

`RunSubagent`/`GetSubagentRun` 标 `parallelizable=True`，使模型一轮发多个时可被 `loop._execute_tool_calls` 的 gather 并发。`RunPattern` 不标（复合调度，留给 C2 调度器管理）。

## Pre-Implementation Review

> 本 change 为架构级改造（subagent 并发/护栏语义重构），实现前需按 AGENTS.md 走 `batch-grill-me`（或等价独立 subagent 设计追问）审视本 design.md 的 D1–D7，逐项确认实现细节、依赖、风险与测试策略，产出结构化决策记录到 `reviews/grill-design.md`，并经停轮确认（grill-confirmation-gate）。本节为占位声明，实际 review 记录以 `reviews/grill-design.md` 为准。

## Risks / Trade-offs

- **风险**：队列化后「父等子」若实现成父持许可等待，会复现 held-across-await 死锁 → D1 + 回归测试「父等子不自我饥饿」覆盖。
- **风险**：累计 spawn 计数作用域不清（per-session vs per-orchestration）→ D5 明确 per-orchestration（根 run 起算）+ 回归测试。
- **Trade-off**：队列化让「声明」永成功（受累计计数约束），换来的是 `wait=false` 调用方必须感知 `queued` 态并主动 `GetSubagentRun(wait=true)` 收结果——比 fail-fast 多一层异步语义。接受，这是「自由 fan-out」的必要代价。
- **Trade-off**：深度到限撤工具（而非抛错）让子 agent「静默降级自己做」，调用方不再收到明确报错——但避免了模型重试/换名再试的无效消耗（Claude Code 先例）。

## Testing Strategy

- 新增回归测试（G2 决议 7 条）：队列化、wait 语义、父等子不自我饥饿、深度撤工具、累计计数、queue_full、depth 程序性 fail-fast。
- 适配既有测试：`tests/agent/subagent/test_guardrails.py`（fail-fast → 队列化断言更新）、`tests/agent/subagent/test_patterns.py`（4 pattern 行为不回归）。
- 全量 `uv run pytest -q` 绿；OpenSpec strict validate + artifact checker 通过。
