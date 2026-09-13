# Proposal: subagent 并发队列化（subagent-concurrency-queue）

关联跟踪 issue：[#179](https://github.com/Xingkai98/asterwynd/issues/179)。wayfinder 地图：[#170](https://github.com/Xingkai98/asterwynd/issues/170)。决策票：R1 [#171](https://github.com/Xingkai98/asterwynd/issues/171)、G2 [#173](https://github.com/Xingkai98/asterwynd/issues/173)、G5 [#176](https://github.com/Xingkai98/asterwynd/issues/176)。

## Change Type

- primary: feature
- secondary:
  - agent-runtime
  - subagent

## Why

当前 subagent 编排把「声明多少 worker」和「物理同时跑几个」耦合死了：

- `agent/subagent/manager.py` 的 `_check_guardrails()`（`:714-732`）在 spawn 时 **fail-fast**，`max_concurrent_runs=4`（`agent/config.py:255`）让模型连「声明第 5 个」都做不到——不是真没资源，是护栏语义把「声明」和「执行」焊死了。
- `run_subagent` 在 `await waiter.wait()` 之前就把子任务注册进 `_active_tasks`（`manager.py:342-347`），而父 agent 自己也占一个并发槽 → **父持槽等子造成自我饥饿**：`orchestrator-worker` 默认 `workers=3` + 父 = 4 刚好卡满上限（`patterns.py:104`），模型一旦自由设 `workers=4` 或嵌套一层就抛 `concurrency limit exceeded`。
- subagent 工具全未标 `parallelizable`（`agent/tools/builtin/subagents.py`），模型一轮发多个 `RunSubagent(wait=true)` 会被 `agent/loop.py` `_execute_tool_calls`（`:1225-1255`）串行执行，无法真 fan-out。

这三个问题共同阻断了「模型自由构建几十~上百个 subagent 协作」的愿景（wayfinder #170 的 Destination）。本 change 是 Phase 1 地基：把并发护栏从「fail-fast」改成「声明与执行解耦的队列运行时」，为后续 Workflow DSL（C2，可选声明式编排）铺路。

业界依据（R1 #171 调研，`full` 档已闭环）：

- Codex 的 `max_threads` 到限后 **spawn 排队而非失败**（官方 docs）；Claude Code 到限仍是 fail，且 harness 自己承认 resume/subtask 会把计数顶穿（issue #68110）。
- Claude Code #68110 教训：子 agent 持 spawn 工具 + 无硬上限 = 48+ 并发烧 1.5M tokens；官方只限瞬时并发、**没做累计 spawn 计数**，翻车 #69206（218 spawned vs ~10 intended）。
- Claude Code v2.1.217+ 深度到限是**主动撤掉子 agent 的 spawn 工具**而非抛错。

## What Changes

- **队列化并发**：`run_subagent` 从「超限抛错」改为「超瞬时并发进 `asyncio.Queue`」；`max_active`（默认 5，可配置）物理上限 + `max_queued_runs`（默认 20，可配置）有界队列，队列满返回 `queue_full` 信号。
- **许可绑执行不绑等待**：并发许可只绑「实际 LLM/tool 执行」，父阻塞等待子时不持有许可——修自我饥饿 + 免 `asyncio.Semaphore` held-across-await 死锁。
- **深度到限撤工具**：spawn 深度到 `max_depth` 时，从子 agent 工具注册移除 spawn 类工具（复用 `expose_subagent_tools` 开关），而非抛异常。
- **累计 spawn 计数**：新增 per-orchestration 累计 spawn 上限（默认 200，可配置）。
- **run 状态机**：`declared→queued→running→completed/failed/cancelled/budget_exceeded`；`_active_tasks` 只记实际执行任务，排队 run 有独立 RunRecord。
- **父子身份显式字段**：`SubagentSessionRecord` 增 `parent_run_id`/`workflow_id`/`node_id`/`depth`（配合 G5 #176）。
- **工具并行**：`RunSubagent`/`GetSubagentRun` 标 `parallelizable=True`。

仍 fail-fast 的场景：session 不存在、同 session 已有 active run、`max_depth` 程序性超限（防御性保留）、workflow 总预算耗尽（本 change 仅预留接口，预算本体归 C4）、DSL 非法（本 change 无 DSL）。

## Capabilities

### New Capabilities

无新能力域；在既有 `subagents` 能力域上深化。

### Modified Capabilities

- `subagents`: 并发边界从「fail-fast」演进为「队列化解耦」；run 生命周期增加 queued 态；深度护栏从「抛错」演进为「撤工具」；新增累计 spawn 计数与父子身份字段。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 架构级改造（subagent 并发/护栏语义重构），走 grill 的非平凡 change，命中 `full` 判据。
- research questions:
  1. Claude Code 的 subagent 并发/深度护栏语义与 #68110 教训？
  2. Codex 的 `max_threads`/`max_depth` 排队语义？
  3. 父等待子时的死锁防护（并发许可释放）业界怎么处理？
- findings: 见 wayfinder R1 #171 决议（已关闭）。核心结论——
  - **排队替代 fail-fast**（抄 Codex `max_threads` 语义）：到限 spawn 排队、线程结束放行；避免 Claude Code「fail + 计数洞」的反面。
  - **累计 spawn 计数**（Claude Code 没做而翻车 #69206）：per-orchestration 累计上限，不只瞬时并发。
  - **深度到限撤工具**（Claude Code v2.1.217+）：到限从子 agent 工具注册移除 spawn 类工具，本仓已有 `expose_subagent_tools` 开关（`manager.py:503-540`/`loop.py:181-183`），改动量小。
  - **许可绑执行不绑等待**（本仓结构性缺陷，`manager.py:342-347` + `:727`）：父持槽等子自我饥饿；异步优先 + 许可绑实际执行。
  - **信息缺口（如实记录）**：Codex 官方 docs 未记载父等子时是否释放并发槽；上述死锁分析是基于本仓代码 + 框架通用约束的推断，非 Codex 实测。
- design impact: 见 design.md D1–D7；并发/护栏决策直接来自 G2 #173 决议，父子身份来自 G5 #176 决议。

## Impact Analysis

- **能力域**: `subagents`（并发队列化 + 护栏语义 + 身份字段）。
- **代码**: `agent/subagent/manager.py`（`_check_guardrails` 拆成准入/排队两层、run 状态机、`_active_tasks` 语义、`SubagentSessionRecord` 身份字段、深度撤工具接入 `_build_subagent_loop`）、`agent/config.py`（`SubagentsConfig` 增 `max_active`/`max_queued_runs`/`max_spawns` 默认值）、`agent/tools/builtin/subagents.py`（`RunSubagent`/`GetSubagentRun` 标 parallelizable）、`agent/subagent/context.py`（spawn 计数 contextvar，若有需要）。
- **测试**: 新增回归测试（G2 决议 §需补回归测试 7 条）：队列化、wait 语义、父等子不自我饥饿、深度撤工具、累计计数、queue_full、程序性 depth fail-fast。既有 `tests/agent/subagent/test_patterns.py`、`test_guardrails.py` 适配（guardrail fail-fast 行为变更为队列化）。
- **文档**: `docs/openspec-change-backlog.md`（登记 C1 + C2–C5 待实现队列）、wayfinder #170（引用）。
- **流程（process）**: 本 change 是 C1（Phase 1 地基）；C2 `workflow-dsl-scheduler` 等后续 change 依赖本 change 的队列化 + 身份字段。
