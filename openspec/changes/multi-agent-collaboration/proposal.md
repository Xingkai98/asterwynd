# Proposal: 多Agent协作做深 — 状态快照 + 成本控制 + 编排模式库

## Change Type

primary: feature
secondary:
  - agent-runtime
  - subagent

## 需求

1. 状态快照与恢复：子 agent 执行中断 → 序列化为 JSON 快照 → 恢复时从断点继续
2. 成本控制：每个子 agent 预算上限（token/时间），超限自动 kill + 失败摘要
3. 消息总线：子 agent 间通过轻量消息队列交换摘要（严格 token 预算防上下文爆炸）
4. 编排模式库：orchestrator-worker / peer-review / hierarchical / 竞标模式
5. 负载均衡：仅作为可选的后续探索项，第一版不交付

## 背景

当前多 Agent 协作是"单层角色子 agent + 顺序阶段工作流"雏形：`SubAgentManager` 的 `_sessions/_active_tasks/_run_waiters` 全在内存，cancel 只做 asyncio task.cancel()，无 kill 前 JSON 快照；`run_subagent(timeout_s)` 超时只是停止等待，后台子 agent 继续跑，无 kill 语义；无每子 agent token/时间预算；`ParentChannel` 是单 parent/subagent 一对一 Queue，未接入 loop/manager；编排只有硬编码 5 阶段顺序角色流水线，无通用模式。

面试表现：只能说"Orchestrator-Worker 模式比较经济、去中心化会上下文炸"，但没实际踩坑经验。

## 非目标

- 不引入 gRPC 跨节点调度（单机协作、快照和预算护栏跑通后再决策，第一版不交付）。
- 不重做 dev-workflow 编排（复用 #67 合入的 `agent/workflow/` 四阶段状态机，本 change 只做 agent-runtime 子 agent 编排）。
- 不重做 `SubAgentManager` 既有接口（在其上扩展）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/subagent/manager.py` | 状态快照/恢复、预算硬 kill、失败摘要 |
| `agent/subagent/protocol.py` | 消息总线（多子 agent 间交换摘要，token 预算） |
| `agent/tools/builtin/subagents.py` | 新工具（resume/budget-query/pattern-spawn） |
| `agent/loop.py` | 子 agent 事件流（依赖 #78 稳定） |
| `agent/memory/` | 消息摘要生成（依赖 #74 压缩能力） |
| `agent/config.py` | 预算配置段 |
| `web/` | 子 agent 状态/预算展示 |

## Reference Implementation Research

- status: enabled
- reason: 多 Agent 协作（状态快照、预算控制、编排模式库）是 agent 编排成熟领域，应参考 Claude Code/Codex subagent、LangGraph/crewAI/OpenAI Swarm 的实现。
- research questions:
  - Claude Code / Codex 的 subagent 状态快照与恢复？
  - LangGraph/crewAI/OpenAI Swarm 的编排模式与 token 预算控制？
  - 消息总线的 token 预算语义（bounded/可丢弃/摘要化）？
- findings:
  - 待 planning 阶段补充（本 proposal 阶段完成 status/reason/questions 登记；实质调研在本 change planning 阶段完成）。
- design impact:
  - 待 planning 阶段补充；先决条件：明确复用 `agent/workflow/`（#67）而非重建控制面；区分 dev-workflow 编排与 agent-runtime 子 agent 编排两个 scope。

## Dependencies

- 依赖 #74 上下文工程（消息摘要生成复用压缩能力）。
- 依赖 #78 可观测性（子 agent run 事件流、总线事件需 on_event/trace 语义稳定）。
- 复用 #67 合入的 `agent/workflow/` 状态机（不另建独立控制面）。

## 验收

- 先能讲清单机多 session 的协作与故障恢复，跨节点调度只作为后续决策项。
- 面试可引用预算 vs 无预算成本方差、O(1) 快照恢复、模式对比完成率/成本数据。
