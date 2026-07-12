## Context

会话历史压缩当前主要依赖 LLM 摘要，缺少无 LLM 降级和硬预算保证。随着工具调用、图片输入、长任务和自动上下文来源增多，压缩策略必须明确保护哪些内容、可以丢弃哪些内容，以及失败时如何降级。

## Goals / Non-Goals

**Goals:**

- 抽象 Summarizer interface。
- 提供 LLM、truncation、sliding window 三类策略。
- 保证压缩结果满足硬预算或返回明确失败。
- 保留工具调用链完整性和最近用户意图。
- 提供 `compact_context` 主动压缩工具。

**Non-Goals:**

- 不把压缩摘要自动写入长期记忆。
- 不在本 change 中实现语义记忆召回。
- 不改变 tool-call 消息链合法性要求。
- 不引入 provider 专属压缩 API 依赖。

## Decisions

### Decision 1: Summarizer 返回结构化结果

结果包含压缩后 messages、summary、dropped_ranges、token_estimate、strategy 和 warnings。

理由：AgentLoop 和 trace 需要理解压缩影响，而不是只拿到一段文本。

### Decision 2: 工具调用链作为不可拆分单元

压缩时 tool call 与 tool result 必须一起保留、一起摘要或一起移除，不能产生不合法消息链。

理由：协议合法性是最高优先级约束。

### Decision 3: LLM 不可用时使用确定性降级

Truncation 和 SlidingWindow 不依赖模型，用于 provider 不可用、测试和低成本模式。

理由：压缩能力不能完全依赖 LLM。

## Pre-Implementation Review

- Questions resolved:
  - propose 阶段确认多策略和硬预算是核心目标。
  - `compact_context` 属于本 change 范围。
- Options considered:
  - 只优化现有 LLM 摘要 prompt。
  - 增加一个简单截断 fallback。
  - 引入可插拔 Summarizer 抽象。
- Rejected alternatives:
  - 只改 prompt 不能解决无 LLM 和硬预算问题。
  - 单一 fallback 难以覆盖不同运行模式。
- Final confirmations:
  - 开发前必须确认工具调用链保留规则、预算估算来源、工具权限和压缩触发条件。
- Remaining risks:
  - 压缩摘要可能丢失隐含决策；需要用回归场景覆盖长任务关键事实。

## Risks / Trade-offs

- [Risk] 过度压缩导致 agent 忘记约束。Mitigation: system、AGENTS Always 和当前用户消息不可被低优先级策略删除。
- [Risk] `compact_context` 被频繁调用增加成本。Mitigation: 工具实现限流或基于预算触发。
- [Risk] 摘要幻觉。Mitigation: LLM 摘要 prompt 要求只总结已出现事实，并保留来源范围。

## Testing Strategy

- Summarizer contract 测试覆盖三类策略。
- 测试 tool call/result 配对在压缩后仍合法。
- 无 LLM 模式测试覆盖确定性输出。
- Agent 主动调用 `compact_context` 的工具测试。
- 超预算输入测试覆盖硬预算成功和明确失败路径。
