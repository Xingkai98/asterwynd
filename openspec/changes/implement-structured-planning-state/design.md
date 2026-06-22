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

### Decision 1: Planning state 独立于 messages

新增 `agent/planning/` 模型保存 plan items、状态、顺序和说明，不把它编码进对话文本。

理由：UI 和 trace 需要稳定结构，messages 主要服务 LLM 协议。

### Decision 2: 通过事件发布状态变化

AgentLoop 在 planning state 变化时发出事件，Web/trace/benchmark 订阅事件。

理由：避免展示层轮询内部对象，也保持多入口一致。

### Decision 3: 状态集合保持小而明确

初始状态使用 pending/in_progress/completed/blocked 等有限集合。

理由：状态过多会增加 UI 和测试复杂度。

## Risks / Trade-offs

- [Risk] 模型输出计划不稳定。Mitigation: 初版允许显式 API 或 manager 更新，文本计划不直接解析为唯一来源。
- [Risk] planning state 与自然语言不一致。Mitigation: trace 同时记录两者，UI 以结构化状态为准。
- [Risk] 过度设计状态机。Mitigation: 先保持最小字段，后续按 plan mode/TUI 需求扩展。

## Testing Strategy

- 数据模型单元测试覆盖状态转换和序列化。
- AgentLoop 测试覆盖 planning 事件发布。
- Web session 测试覆盖事件转发。
- benchmark/trace 测试覆盖 artifact 中记录 planning state。
