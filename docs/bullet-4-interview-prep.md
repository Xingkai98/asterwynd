# Bullet 4 面试讲稿：ContextBuilder 上下文系统

> 实现 ContextBuilder 统一编排 8 个上下文源，稳定前缀分层注入、字节级不变命中 LLM Prefix Cache，搭配 AutoCompact L1/L2 层级压缩与 tool-call pending 标记防止工具链断裂

---

## 主讲述稿（~400 字）

上下文工程是 Agent 框架里最容易被低估的子系统。ContextBuilder 要解决的核心问题是：每次 LLM 调用前，怎么把系统提示词、项目规则、记忆、待办事项、技能信息、计划状态这些信息高效地注入到 system 消息里，既不能超预算，又要保证缓存命中。

代码在 `agent/context/builder.py`。我定义了 8 个 ContextSource，从 P0 到 P5 分层。SystemPrompt 和 AsterMd（项目规则）最高优先级，同时是 static 的——同 cwd、mode、user_system_prompt 下输出字节级不变，可以跨迭代缓存。加上 MemoryIndex（记忆索引），这三个是 cacheable 层，永不参与预算截断，成为稳定前缀。

注入预算默认 20000 token，如果 8 个源超预算，从最低优先级 tail-first 截断——先裁计划状态，再裁技能信息，再裁待办。cacheable 层不受影响。

AutoCompact 是上下文压缩系统，代码在 `agent/memory/manager.py`。对话超过阈值（100K 窗口下是 85K）时触发 L1 增量压缩——保留最近 10 条消息，中间部分送 LLM 做四段式摘要（已完成 / 待办 / 疑难点 / 进行中）。当 L1 累计超过 6000 token 且至少 2 个 chunk 时，触发 L2 高阶压缩，把 L1 摘要再压缩一次。

tool-call pending 标记是我特别在意的设计。压缩时如果有些工具调用还没完成，摘要会让模型"忘记"这些调用。我的三层保障：窗口扩展保证工具链不被切断，pending 标记显式标注未完成的调用，summarizer 的 prompt 要求逐字保留这些标记。

---

## 追问 1：为什么要分 P0-P5 而不是简单按类型分？预算截断为什么是 tail-first？

**回答（~250 字）：**

P0-P5 的分层是为了同时满足三个约束。第一，有些内容是生存必需的——没了 system prompt 和项目规则，agent 不知道该干什么。所以 P0/P1 是 critical+cacheable，永不截断。第二，有些内容是"越多越好但可以部分牺牲"——记忆索引和待办事项有助于决策但不致命。第三，有些内容是"锦上添花"——技能列表和计划状态缺失也能工作。

Tail-first 截断是从低优先级尾部开始裁，而不是均匀缩减所有源——因为低优先级信息即使不全也比压缩到不可读要强。例如把每个 skill 描述截成 10% 长度会导致描述完全失真实用，不如整体裁掉 P5 的计划状态。

这个设计受操作系统内存管理的启发——不是把每个进程都砍一刀，而是 swap out 低优先级进程。ContextBuilder 做的就是上下文的"页面置换"。

另外 P3 的位置是空着的——这是有意的，留给未来可能加入的中优先级上下文源。分层设计预留了扩展点。

---

## 追问 2：Prefix Cache 的"字节级不变"怎么保证？什么情况下会打破？

**回答（~250 字）：**

"字节级不变"由三层保障。第一层是 static 属性——P0 和 P1 的渲染输出由 `(name, cwd, mode, user_system_prompt)` 决定。只要这四个值不变，`_static_cache_key` 命中缓存，返回的就是字节级相同的内容。第二层是 cacheable 层不参与预算截断——不管 context 多满，P0/P1/MemoryIndex 永远不会被截断，所以它们在 messages 中的位置和内容始终确定。第三层是工具 schema 稳定——当 Selector OFF 时，全量 38 个工具 schema 按固定顺序排列，字节级不变。

以下场景会打破缓存：用户切换 mode（build → plan），cwd 在 subagent spawn 到新 workspace 时变化，user_system_prompt 被用户修改，或者 Selector ON 时变层工具变了位置。这些场景通常发生在会话开始或重大转折点，不在高频迭代中。

设计上的关键是让"打破缓存"的触发条件可预测——同一个 session 的大部分迭代命中缓存，成本集中在少数转折迭代上。

---

## 追问 3：L1 和 L2 压缩的全流程是怎样的？为什么需要两层？

**回答（~250 字）：**

压缩在每次迭代末触发，两个条件必须同时满足：总 token 超过阈值（默认 85K），且距上次压缩至少 5 轮（防抖动）。

L1 流程是：分离 system 消息、取最近 10 条 + 工具链保护的 recent window、确定需要压缩的 middle segment、给 middle segment 打上 pending 标记和分页进度、送 LLM 做四段式摘要。摘要以 user 角色（不是 system）注入，让模型把它当作"对话历史摘要"而非"系统约束"来处理。

L2 触发条件是至少 2 个 L1 chunk 且累计超过 6000 token。输入是已有 L2 基础 + 所有 L1 chunk，预算是 L1 累积的 30%。关键设计是每次 L2 都带上上次的 L2 基础——顶层结论永不丢失。

为什么需要两层？单层压缩的问题是历史被"扁平化"——第 100 轮的摘要和第 1 轮的摘要在 L1 里是平权的。L2 做的是对 L1 摘要的"摘要"，把多段 L1 提炼成更高层次的结论。类比就是 L1 是"每章小结"，L2 是"全书摘要"。

---

## 追问 4：tool-call pending 标记在压缩中怎么保证不丢失？

**回答（~200 字）：**

三层保障链。第一层：`_recent_with_tool_chains` 扩展 recent window——如果最近 10 条里有 3 个 tool result，但对应的 assistant tool_call 消息在第 12 位，window 自动前扩展到包含它们。保证工具链消息对不被切断。

第二层：`_annotate_pending_calls` 在压缩前全量扫描 middle + recent，收集所有已有结果的 tool_call_id，然后对 middle segment 中的 assistant 消息逐条检查——tool_call 没有对应 result 就打上 `[call#1: toolu_abc123 pending]`。其中 #1 是 1-based 位置编号，toolu_abc123 是工具调用 ID。

第三层：summarizer 的 system prompt 和 user prompt 明确要求逐字保留 pending 标记。L2 压缩的 prompt 同样要求。这意味着即使经过两级压缩，未完成的工具调用信息不会丢失。

---

## 追问 5：ContextBuilder 和其他 Agent 框架的上下文管理有什么不同？

**回答（~200 字）：**

两个核心差异。第一是"分层的 cacheable 前缀"——大多数框架要么不做 prefix cache 优化，要么全量缓存（一旦任何东西变化就全部失效）。我的做法是区分 cacheable 和 non-cacheable 层，只在 cacheable 前缀的末尾打断点。这意味着变层的待办事项或技能列表变化时，缓存仍然 90%+ 命中。这个设计直接来自对 Anthropic API 行为的深入理解。

第二是 pending 标记机制——大多数框架的压缩策略是"保留最近 N 条消息"，但不检查工具链完整性。这会导致压缩后出现 broken tool chains，LLM 下次调用时困惑于"我之前调用的工具怎么没结果"。我的三层保障专门解决这个痛点。

LangChain 的 ConversationSummaryBufferMemory 做的是纯摘要 + 最近 N 条，没有缓存分层。LlamaIndex 的 ChatMemoryBuffer 有 token 限制但没有分层压缩。Asterwynd 是把这三件事——分层缓存、分层压缩、工具链保护——整合在了一起。
