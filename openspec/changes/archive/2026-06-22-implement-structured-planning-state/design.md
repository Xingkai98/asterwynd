## Context

当前 agent 只能用自然语言表达计划，UI、trace 和 benchmark 无法稳定知道任务步骤、状态和失败位置。structured planning state 是 plan mode、TUI、Web 调试和 benchmark 诊断的共同基础。

本 change 定义可机器读取的 plan item 状态模型。

## Goals / Non-Goals

**Goals:**

- 新增 planning 数据模型。
- AgentLoop 能更新和发布 planning state。
- CLI/Web/trace 能观察 planning state 变化。
- planning state 与自然语言回复并存。

**Non-Goals:**

- 不实现 plan mode 的只读策略。
- 不实现 TUI。
- 不强制所有模型每轮都更新 plan。
- 不把 planning state 当作任务调度器。

## Decisions

### Decision 1: Planning State 独立于 messages

新增 `agent/planning/` 模型保存 plan items、状态、顺序和说明，不把它编码进对话文本。

理由：UI 和 trace 需要稳定结构，messages 主要服务 LLM 协议。Planning State 的权威状态由 PlanningManager 维护；AgentLoop 可以在调用 LLM 前临时注入只读 planning context，但不把该 context append 回 `messages`。

### Decision 2: 通过事件发布状态变化

AgentLoop 在 planning state 变化时发出事件，Web/trace/benchmark 订阅事件。

理由：避免展示层轮询内部对象，也保持多入口一致。

### Decision 3: 状态集合保持小而明确

初始状态使用 pending/in_progress/completed/failed/skipped 等有限集合。

理由：状态过多会增加 UI 和测试复杂度；failed 覆盖已执行但失败的步骤，skipped 覆盖因计划调整或前置失败而不再执行的步骤。本 change 不引入 blocked，避免把 planning state 扩展成任务调度或人工审批状态机。

### Decision 4: planning 事件发布完整快照

planning state 变化时发布 `planning_state_updated` 事件，payload 包含完整 state snapshot，而不是只发布单条 item diff。

理由：Web、trace 和 benchmark 都可以用同一事件重建当前计划状态，不需要维护复杂的 diff replay 逻辑。计划规模通常较小，完整快照成本可控。

### Decision 5: AgentLoop 暴露受控 mutation API，不解析自然语言计划

AgentLoop 内部持有 PlanningManager，对外暴露 `set_plan` / `update_plan_item` 等受控 async mutation API 和只读 planning state；不鼓励外部直接修改 manager。本 change 不解析 assistant 文本来自动生成 plan items。

理由：proposal 已明确 planning state 不替代自然语言回复，plan mode 的 prompt 和计划生成策略由后续 `add-plan-mode` 定义。当前实现应先交付稳定的数据模型、事件、trace 和展示通道。

### Decision 6: PlanningManager 不直接发布事件

PlanningManager 只负责同步校验和更新状态，mutation 后返回完整 snapshot。AgentLoop 在运行上下文中负责将 snapshot 发布到 `on_event("planning_state_updated", snapshot)`，并写入 TraceRecorder。

理由：PlanningManager 是纯状态对象，便于单元测试；Web、trace 和 benchmark 是运行时观察者，不应反向耦合进 manager。

### Decision 7: plan item id 由 manager 单调生成

Plan Item id 使用 `item-1`、`item-2` 等格式，在同一个 PlanningManager 生命周期内单调自增且不复用。`set_plan()` 替换整个计划，并为新 items 分配新 id。

理由：trace 会保留历史 snapshot；如果 id 被复用，同一 id 在不同时间代表不同步骤，会降低事后分析可信度。

### Decision 8: 第一版不实现 plan 执行策略

本 change 不规定先执行哪个步骤、失败后是否重规划、是否自动跳过后续步骤或是否等待用户确认。这些属于后续 `add-plan-mode` 的行为设计。

理由：当前 change 交付 plan mode 需要的基础设施，不把 Planning State 扩展成任务调度器或确定性执行器。

## Risks / Trade-offs

- [Risk] 模型输出计划不稳定。Mitigation: 初版允许显式 API 或 manager 更新，文本计划不直接解析为唯一来源。
- [Risk] planning state 与自然语言不一致。Mitigation: trace 同时记录两者，UI 以结构化状态为准。
- [Risk] 过度设计状态机。Mitigation: 先保持最小字段，后续按 plan mode/TUI 需求扩展。

## Testing Strategy

- 数据模型单元测试覆盖状态转换和序列化。
- AgentLoop 测试覆盖 planning 事件发布。
- Web session 测试覆盖事件转发。
- benchmark/trace 测试覆盖 artifact 中记录 planning state。
