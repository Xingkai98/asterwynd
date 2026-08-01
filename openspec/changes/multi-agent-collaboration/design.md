# Design: 多Agent协作做深 — 状态快照 + 成本控制 + 编排模式库

## Context

当前多 Agent 协作是"单层角色子 agent + 顺序阶段工作流"雏形：`SubAgentManager` 的 `_sessions/_active_tasks/_run_waiters` 全在内存，cancel 只做 asyncio task.cancel()，无 kill 前 JSON 快照；`run_subagent(timeout_s)` 超时只是停止等待，后台子 agent 继续跑，无 kill 语义；无每子 agent token/时间预算；`ParentChannel` 是单 parent/subagent 一对一 Queue，未接入 loop/manager；编排只有硬编码 5 阶段顺序角色流水线。面试表现"Orchestrator-Worker 模式比较经济"但没实际踩坑经验。

## Goals / Non-Goals

**Goals:**

- 状态快照与恢复（子 agent 中断 → JSON 快照 → 断点继续）。
- 每子 agent token/时间预算，超限硬 kill + 失败摘要。
- 轻量消息总线（多子 agent 交换摘要，严格 token 预算）。
- 编排模式库（orchestrator-worker / peer-review / hierarchical / 竞标）。

**Non-Goals:**

- 不引入 gRPC 跨节点调度（第一版不交付）。
- 不重做 dev-workflow 编排（复用 #67 `agent/workflow/`）。
- 不重做 SubAgentManager 既有接口。

## Decisions

### Decision 1: 复用 `agent/workflow/` 状态机，不另建独立控制面

**方案**：本 change 的 agent-runtime 子 agent 编排复用 #67 合入的 `agent/workflow/` 四阶段状态机与既有 subagent 基建（upgrade-subagents-to-agentloop），区分「dev-workflow 编排」与「agent-runtime 子 agent 编排」两个 scope，禁止重复造轮子（#63 教训）。

**备选**：另建独立控制面。被拒：#63 已证明独立控制面与 #67 重复且被弃用。

**理由**：复用既有状态机是架构一致性与避免重复的必然选择。

### Decision 2: 状态快照用 JSON 序列化 + 断点恢复

**方案**：子 agent 执行中断 → 序列化为 JSON 快照（迭代/工具状态/对话）→ 恢复时从断点继续。复用主会话 SessionStore 的 schema_version/fingerprint/dedup 模式。

**备选**：仅 run.trace 记录。被拒：trace 是记录不是可恢复状态。

**理由**：快照是"故障恢复"面试证据的核心。

### Decision 3: 预算用硬 kill + 失败摘要

**方案**：每子 agent 设 token/时间预算上限，超限硬 kill（真正终止后台任务，而非仅停止等待）+ 生成失败/成本摘要。

**备选**：仅停止等待。被拒：后台继续跑无 kill 语义。

**理由**：硬 kill 是成本控制的必备语义。

### Decision 4: 消息总线用轻量 Queue + 严格 token 预算

**方案**：多子 agent 间轻量消息总线（bounded/可丢弃/摘要化），交换摘要而非原始消息，严格 token 预算防上下文爆炸。

**备选**：单 parent/subagent Queue。被拒：无法多子 agent 间交换。

**理由**：消息总线是协作模式的基础。

### Decision 5: 编排模式库四模式

**方案**：orchestrator-worker（coordinator 拆 N 并行再聚合）、peer-review（双 agent 互审）、hierarchical（嵌套团队）、竞标（多 agent 出方案由选择器挑选）。抽象 OrcPattern 接口。

**备选**：硬编码顺序流水线。被拒：无法讲"模式库"。

**理由**：四模式是面试核心答案与协作实际需求。

## Pre-Implementation Review

- 待 planning 阶段（grill-with-docs）确认本设计，并补齐 Reference Implementation Research 实质 findings 与 design impact。

## Reference Implementation Research

- status: enabled
- reason: 多 Agent 协作是 agent 编排成熟领域，需参考 Claude Code/Codex subagent、LangGraph/crewAI/OpenAI Swarm 的状态快照、预算控制、编排模式实现。
- research questions:
  - Claude Code / Codex 的 subagent 状态快照与恢复？
  - LangGraph/crewAI/OpenAI Swarm 的编排模式与 token 预算控制？
  - 消息总线的 token 预算语义？
- findings: 待 planning 阶段补充（proposal 阶段已登记；实质调研在本 change planning 阶段完成）。
- design impact: 待 planning 阶段补充；先决条件是复用 `agent/workflow/`（#67），区分两个 scope。

## Risks / Trade-offs

- **[与 dev-workflow 编排重复] → 复用 `agent/workflow/`（#67），区分两个 scope，禁止重复造轮子（#63 教训）。**
- **[快照恢复失败] → 快照 schema_version/fingerprint 校验，失败时回退从零重跑。**
- **[预算硬 kill 误杀] → 预算阈值可配置，kill 前记录失败/成本摘要，提供手动扩展预算入口。**
- **[消息总线 token 预算] → bounded/可丢弃/摘要化语义，防上下文爆炸。**
- **[依赖 #74/#78] → 消息摘要生成依赖 #74 压缩能力，事件流依赖 #78 on_event/trace 语义稳定。**

## Testing Strategy

- 单元测试：快照序列化/恢复、预算硬 kill、消息总线 token 预算、编排模式状态机。
- 集成测试：子 agent 快照恢复端到端、竞标模式。
- 回归测试：既有 SubAgentManager 测试不回归。
- benchmark 层级：协作收益量化（预算方差、快照恢复、模式对比）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/subagent/manager.py` | 快照/预算/kill |
| `agent/subagent/protocol.py` | 消息总线 |
| `agent/tools/builtin/subagents.py` | 新工具 |
| `agent/loop.py` | 子 agent 事件流 |
| `agent/memory/` | 消息摘要 |
| `agent/config.py` | 预算配置 |
| `web/` | 状态/预算展示 |
