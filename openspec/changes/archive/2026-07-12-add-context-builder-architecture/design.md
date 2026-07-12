## Context

上下文来源正在增长：system prompt、AGENTS.md、memory、skills、plan/todo、未来自动召回和压缩摘要。继续在 `AgentLoop._messages_with_run_context()` 内串行拼接会让优先级、预算、裁剪和 trace 变得不可维护。

## Goals / Non-Goals

**Goals:**

- 定义 `ContextSource` contract。
- 定义 `ContextBuilder` 的注册、排序、预算、裁剪和渲染流程。
- 将现有 memory index、skill context、plan/todo 迁移到 source adapter。
- 为 AGENTS.md 和自动召回预留 source 类型。
- 输出可测试的 build report。

**Non-Goals:**

- 不重写 AgentLoop。
- 不改变 memory、skill、planning 的业务数据结构。
- 不在本 change 中实现向量检索或智能压缩。
- 不把 ContextBuilder 暴露成用户可直接操作的工具。

## Decisions

### Decision 1: Source 自描述优先级和预算

每个 ContextSource 声明 id、priority、budget、trim policy、render 方法和 metadata。

理由：新增来源时不需要继续修改中心方法的拼接顺序。

### Decision 2: Builder 输出 messages 和 build report

ContextBuilder 返回最终 message 列表或 context fragments，同时返回来源、token 估算、裁剪和错误信息。

理由：上下文构建问题需要可观测性；测试也可以断言 report 而非解析长文本。

### Decision 3: 裁剪只发生在允许裁剪的来源

system prompt 和硬性规则默认不可裁剪；memory index、skill list、plan/todo 等低优先级来源可按策略裁剪。

理由：预算压力下应保护行为边界和当前用户意图。

## Pre-Implementation Review

- Questions resolved:
  - propose 阶段确认 ContextBuilder 是后续上下文能力的中枢。
  - 初始 source 列表覆盖现有 `_messages_with_run_context()` 的全部动态内容。
- Options considered:
  - 继续维护 AgentLoop 内拼接。
  - 只提取几个 helper 函数。
  - 建立 ContextSource/ContextBuilder 抽象。
- Rejected alternatives:
  - 继续拼接无法支撑后续自动召回和预算治理。
  - helper 函数不能表达跨来源优先级和统一 report。
- Final confirmations:
  - 开发前必须确认 source priority、默认预算、build report schema 和迁移顺序。
- Remaining risks:
  - 抽象过重会拖慢交付；实现应先覆盖现有来源，避免预建复杂插件系统。

## Risks / Trade-offs

- [Risk] 迁移后 prompt 行为出现隐性变化。Mitigation: 增加 before/after message 构造回归测试。
- [Risk] token 估算不准。Mitigation: 将估算作为预算近似，并记录实际 provider 限制错误。
- [Risk] 来源之间重复内容。Mitigation: source id 和 report 支持定位重复注入。

## Testing Strategy

- 单元测试覆盖 source 排序、预算分配、裁剪和不可裁剪来源。
- 集成测试覆盖 memory、skills、plan/todo 同时存在时的 message 构造。
- 回归测试覆盖空来源、异常来源和超预算来源。
- Trace/report 测试覆盖来源 id、token 估算和裁剪原因。
