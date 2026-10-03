# memory-context 规格

## Purpose

定义消息历史、AutoCompact 和 tool-call 链保留策略。当前实现位于 `agent/memory/manager.py`。
## Requirements
### Requirement: MemoryManager 维护消息历史

MemoryManager SHALL 支持添加、读取和清空消息。

#### Scenario: 添加消息

- **GIVEN** MemoryManager 已创建
- **WHEN** 调用 `add(message)`
- **THEN** 该消息 SHALL 被追加到内部消息列表

### Requirement: 超过 90% token 阈值时触发压缩

MemoryManager SHALL 在估算 token 数达到 `max_tokens` 的 90% 时执行 compact。`compact_if_needed` SHALL 接受可选的 `iteration` 参数，在上一次压缩后的 `compaction_gap` 轮内不重复触发。`compact_if_needed` SHALL 返回是否实际触发了 compact；未达到阈值或间隔不足时 SHALL 返回 false 并保持消息列表不变。

`compaction_gap` 节流 SHALL 只用于避免频繁压缩的抖动，SHALL NOT 成为「允许上下文无界增长」的许可证：当估算占用量达到一个**硬上限**（高于常规阈值，为 `max_tokens` 的若干倍，或等价的明确常量/可配置上界）时，`compact_if_needed` SHALL **无视间隔限制强制执行 compact**，使**由工具结果主导**的常驻上下文有界。硬上限 SHALL NOT 为无限。

该硬上限 SHALL 同时约束两个维度：token 估算 **与** 常驻字节（尤其内容块类结果，其 token 估算可能远低于实际字节占用）——SHALL NOT 仅凭 token 估算判定而在字节维度已失控时放行。

对工具结果输入侧的有界化（工具结果生命周期处理）SHALL 在判定压缩**之前**发生：`compact_if_needed` 的判定 SHALL 看到的是有界化之后的占用量。

已知残余边界（**如实声明，不掩盖**）：本条款只保证「工具结果主导」的上下文有界；近期窗口内的**非工具大内容**（超大用户粘贴、超大工具调用参数、后台任务的注入输出）不在工具结果有界化范围内，其驻留由近期窗口的保留策略约束、SHALL NOT 被本条款的错误解读为「本机制已保证一切内容有界」。

#### Scenario: 未达到阈值

- **GIVEN** 消息 token 估算未达到 `max_tokens` 的 90%
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 保持消息列表不变
- **AND** 返回 false

#### Scenario: 达到阈值但间隔不足且未到硬上限

- **GIVEN** 消息占用量达到 `max_tokens` 的 90%
- **AND** 距离上一次 compaction 不足 `compaction_gap` 轮
- **AND** 消息占用量**未达到硬上限**
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 跳过 compaction（gap 防抖）
- **AND** 返回 false

#### Scenario: 达到硬上限时无视间隔强制执行

- **GIVEN** 消息占用量达到**硬上限**
- **AND** 距离上一次 compaction 不足 `compaction_gap` 轮
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL **无视间隔限制**执行 compact
- **AND** 返回 true
- **AND** 常驻上下文 SHALL 有界（SHALL NOT 因 gap 未到间隔就放任其无界增长）

#### Scenario: 字节维度驱动硬上限

- **GIVEN** 消息的 token 估算因内容块类结果而偏低，但**常驻字节**已达到硬上限
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 按字节维度认定达到硬上限并执行 compact
- **AND** SHALL NOT 仅因 token 估算未达上限而放行

#### Scenario: 达到阈值且间隔足够

- **GIVEN** 消息占用量达到 `max_tokens` 的 90%
- **AND** 距离上一次 compaction 已达到或超过 `compaction_gap` 轮
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 执行 compact
- **AND** 返回 true

### Requirement: compact 必须保留系统消息和近期上下文

MemoryManager SHALL 保留所有原始 system 消息和 recent window 内的近期非 system 消息。未配置 LLM 时，compact SHALL 使用 TruncationSummarizer 作为降级策略，产生截断摘要而非静默丢弃。当 Summarizer 返回空摘要（LLM 失败、空响应等）时，compact SHALL 降级为仅保留 system 消息和近期消息窗口。

#### Scenario: 无 LLM 时使用截断摘要

- **GIVEN** 消息历史达到 90% token 阈值
- **AND** MemoryManager 未配置 LLM
- **WHEN** compact 被触发
- **THEN** 系统 SHALL 使用 TruncationSummarizer 生成截断摘要
- **AND** 截断摘要 SHALL 以 user 消息注入
- **AND** 保留 system 消息和近期消息窗口

#### Scenario: LLM 摘要生成失败时执行裁剪降级

- **GIVEN** 消息历史达到 90% token 阈值
- **AND** MemoryManager 配置了 LLM
- **WHEN** LLM 调用失败或返回空摘要
- **THEN** 系统 SHALL 保留 system 消息和近期消息窗口
- **AND** 不插入空 summary 消息

### Requirement: compact 不得破坏 tool-call 链

MemoryManager SHALL 在保留近期消息时连同相关 assistant tool call 和 tool result 一起保留。

#### Scenario: 近期 tool result 依赖更早 assistant tool call

- **GIVEN** recent window 包含 tool result
- **WHEN** 对应 assistant tool call 位于 recent window 之前
- **THEN** compact SHALL 额外保留该 assistant 消息
- **AND** 保持 provider 可接受的消息链

### Requirement: compact 通过可插拔 Summarizer 生成摘要

MemoryManager SHALL 支持通过 `summarizer` 参数注入可插拔 `Summarizer`。`Summarizer` SHALL 实现 `async summarize(messages, budget=0) -> str`。MemoryManager SHALL 在存在待压缩中间消息时调用 Summarizer 生成摘要，并将 `summary_budget`（中间消息 token 数的 30%）作为 advisory budget 传入。LLMSummarizer 生成四段式结构化摘要（已完成/关键决策/进行中/阻塞与待办）；TruncationSummarizer 在无 LLM 时作为降级策略，截断工具输出至 500 字符并记录一次性警告。

#### Scenario: 有 LLM 时生成 summary user 消息

- **GIVEN** 消息历史达到 90% token 阈值
- **AND** MemoryManager 配置了 LLM（或外部注入的 LLMSummarizer）
- **AND** recent window 之前存在非 system 消息
- **WHEN** compact 被触发且 LLM 返回非空摘要
- **THEN** 系统 SHALL 插入一条 summary **user** 消息（语义上为"前序会话上下文"而非 system 约束）
- **AND** summary user 消息 SHALL 位于原始 system 消息之后
- **AND** summary user 消息 SHALL 位于近期消息窗口之前
- **AND** summary 内容 SHALL 为四段式结构化 Markdown 摘要

#### Scenario: 无 LLM 时使用截断降级

- **GIVEN** MemoryManager 未配置 LLM
- **AND** 存在待压缩中间消息
- **WHEN** compact 被触发
- **THEN** 系统 SHALL 使用 TruncationSummarizer 生成截断摘要
- **AND** 首次使用时 SHALL 记录一次性截断降级警告
- **AND** summary 同样以 user 消息注入

### Requirement: 手动 clear 保留 system 上下文

MemoryManager SHALL 支持手动清理会话历史，并保留 system messages。

#### Scenario: 手动 clear 移除非 system messages

- **GIVEN** 会话 memory 包含 system、user、assistant 和 tool messages
- **WHEN** 用户请求手动 clear
- **THEN** memory SHALL 保留 system messages
- **AND** 移除非 system messages

### Requirement: 手动 compact 可以主动触发

MemoryManager SHALL 支持对当前会话历史执行手动 compact。手动 compact SHALL 忽略自动 compact token 阈值，并使用保留的 recent window 判断是否存在可压缩的旧非 system messages。

#### Scenario: token budget 内请求手动 compact

- **GIVEN** 会话历史低于自动 compact token 阈值
- **WHEN** 用户手动请求 compact
- **THEN** 系统 SHALL 压缩符合条件的旧 messages，或返回清晰的 no-op result
- **AND** 调用方 SHALL 能观察到该结果

#### Scenario: 手动 compact 没有可压缩旧 messages

- **GIVEN** 会话历史在保留的 recent window 之外没有非 system messages
- **WHEN** 用户手动请求 compact
- **THEN** 系统 SHALL 保持会话历史不变
- **AND** 返回可观察的 no-op result

#### Scenario: 手动 compact 保留 tool-call chains

- **GIVEN** 会话历史包含 assistant tool calls 和 tool results
- **WHEN** 用户请求手动 compact
- **THEN** compact SHALL 使用与自动 compact 相同的不变量，保留 provider-valid tool-call chains
