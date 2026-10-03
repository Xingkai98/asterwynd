# 上下文工程 规格

## Purpose

定义 上下文工程 能力域的规格。当前为基线状态；深化需求通过 OpenSpec change 的 spec delta 演进。
## Requirements
### Requirement: 上下文工程 能力域基线

上下文工程 能力域 SHALL 提供基础能力，深化需求通过 OpenSpec change 的 ADDED Requirements 合入演进。

#### Scenario: 能力域可扩展

- **GIVEN** 一个针对 上下文工程 能力域的 OpenSpec change
- **WHEN** 该 change 的 spec delta 被接受
- **THEN** 能力域的 requirement 随 ADDED Requirements 演进

### Requirement: Four-Field Structured Summary

The context summarizer SHALL produce summaries with four fields: completed items, pending items, difficulties and decisions, and currently in-progress work.

#### Scenario: summary with four fields

- Given a conversation with completed, pending, difficult, and in-progress items
- When the summarizer compacts the conversation
- Then the summary contains the four fields: completed items, pending items, difficulties and decisions, and currently in-progress work

### Requirement: Tool Call Pair Preservation

The context summarizer SHALL preserve tool_call/tool_result pairs, SHALL mark incomplete tool calls as `[call#<i>: <tool_call_id> pending]`, and SHALL not break the tool-call chain across compaction.

#### Scenario: incomplete tool call marked pending

- Given a conversation with a tool_call without a matching tool_result (interrupted by max_iterations)
- When the summarizer compacts the conversation
- Then the incomplete call is marked `[call#<i>: <tool_call_id> pending]`
- And the tool-call chain remains valid

### Requirement: Hierarchical Compaction

The context system SHALL support two-level hierarchical compaction: L1 summary of recent messages, then L2 compression of accumulated L1 summaries retaining only top-level conclusions, with summary tier metadata (tier/source range/generation time).

#### Scenario: L1 summaries accumulated then L2 compressed

- Given multiple L1 summaries accumulated beyond the threshold
- When the L2 compression is triggered
- Then only top-level conclusions are retained
- And the summary carries tier metadata

### Requirement: Pagination Progress Preservation

The Read tool SHALL support pagination with `(file, offset, total)` progress, and the context system SHALL persist this progress in the summary before compaction.

#### Scenario: large file pagination preserved

- Given a large file being read in pages
- When the context is compacted
- Then the summary persists `(file, offset, total)` progress
- And the read can resume from the saved offset

### Requirement: Read 默认输出有界

The Read tool SHALL, when invoked **without an explicit `limit`**, apply a **default output bound** so a single read cannot return an unbounded file into the context. This SHALL cover every path that omits an explicit `limit`: a plain read (no `limit`/`offset`), a read with `offset` but no `limit`, and a read with `limit` explicitly set to `0` — none of these SHALL return the whole file unbounded.

The bound SHALL constrain **both** dimensions: a default maximum number of lines **and** a default maximum byte size, whichever is reached first. The bound SHALL have a built-in default value and SHALL be overridable via configuration. A file exceeding the bound SHALL be returned as an at-most-bound prefix accompanied by a **progress note that explicitly states the content was truncated and gives the offset at which to continue**. A file within the bound SHALL be returned in full.

When `limit` is explicitly a positive integer, the Read tool SHALL behave as before (the default bound SHALL NOT apply, the caller controls the size).

The progress note's `total` SHALL always be the file's total line count, independent of `offset`. The progress note SHALL remain parseable by the component that extracts read progress for compaction; any change to the note's format SHALL be mirrored in that component.

#### Scenario: oversized file is bounded by default

- **GIVEN** a file whose line count exceeds the default line bound
- **WHEN** the Read tool is invoked with only `path`
- **THEN** the returned content SHALL be at most the default bound's leading lines
- **AND** the result SHALL carry a progress note that explicitly states truncation and the offset at which to continue

#### Scenario: few-but-huge-line file is bounded by bytes

- **GIVEN** a file whose line count is within the default line bound but whose byte size exceeds the default byte bound (e.g. a minified or single-line-huge file)
- **WHEN** the Read tool is invoked with only `path`
- **THEN** the returned content SHALL be bounded by the byte bound
- **AND** SHALL NOT return the whole file

#### Scenario: `limit=0` does not bypass the bound

- **GIVEN** a file larger than the default bound
- **WHEN** the Read tool is invoked with `limit` explicitly `0` (and no positive limit)
- **THEN** the result SHALL NOT be the unbounded full content
- **AND** the default bound SHALL apply

#### Scenario: offset without an explicit limit stays bounded

- **GIVEN** a large file
- **WHEN** the Read tool is invoked with an `offset` but no explicit `limit`
- **THEN** the returned content SHALL be bounded (SHALL NOT read to end-of-file unbounded)
- **AND** the progress note SHALL give the offset at which to continue

#### Scenario: file within the bound is returned in full

- **GIVEN** a file whose line count and byte size are both within the default bound
- **WHEN** the Read tool is invoked with only `path`
- **THEN** the returned content SHALL be byte-for-byte identical to the current unbounded output
- **AND** SHALL NOT be truncated

#### Scenario: explicit positive limit is unchanged

- **GIVEN** a large file
- **WHEN** the Read tool is invoked with explicit positive `limit` (with or without `offset`)
- **THEN** the behavior SHALL be unchanged from before this bound was introduced

### Requirement: Prefix Cache Ordering

The context system SHALL order injection on the wire as system (prompt → MD → memory index) → tools (core stable → selected variable tail) → user messages, with cache_control breakpoints for Anthropic providers and stable-prefix ordering. The memory index is a stable, cached system block; its position relative to tool descriptions is governed by the provider wire format (the system field precedes the tools field).

#### Scenario: stable prefix ordering

- Given a conversation with system, MD, tools, memory index, and user messages
- When the context is injected
- Then the wire order is system (prompt → MD → memory index) → tools (core stable → selected variable tail) → user messages
- And the stable system prefix and core tools are byte-identical across iterations
- And cache_control breakpoints are set for the Anthropic provider on the last stable system block (selector off) or on the last core tool (selector on)

### Requirement: On-Demand Deep MD Loading

The context system SHALL inject only root MD and expose deep MD as an on-demand loading tool.

#### Scenario: deep MD loaded on demand

- Given a deep markdown document not in the root MD chain
- When the model invokes the on-demand loading tool
- Then the deep MD content is loaded into context

### Requirement: 执行进度保留（Todo 层级保护）

注入层预算超限时，上下文系统 SHALL 将执行进度 todo 层排在 P4（技能）和 P5（规划）可变层之后才裁剪。Todo 层优先级 SHALL 为 P2（与持久记忆索引同级，非 critical、非 cacheable），即在 P4/P5 全部裁完、预算仍超限时才可被裁剪。

#### Scenario: 超预算时 todo 先于技能/规划层保留

- **GIVEN** 注入层总 token 超过预算，且存在 P4 技能层、P5 规划层和 P2 Todo 层
- **WHEN** ContextBuilder 的预算裁剪从最低优先级层尾部开始
- **THEN** P5 规划层先被裁剪，接着 P4 技能层被裁剪
- **AND** Todo 层在这些可变层裁完后仍完整保留
- **AND** cacheable 稳定前缀层（P0/P1/P2 记忆索引）不被裁剪

#### Scenario: 预算极端紧张时 todo 最后才被裁

- **GIVEN** P4/P5 可变层全部被裁剪后预算仍超限
- **WHEN** 预算裁剪继续
- **THEN** Todo 层（P2，非 cacheable）作为下一个可裁剪层从尾部被裁
- **AND** P0/P1 critical 层与 P2 记忆索引 cacheable 层仍不被裁剪


### Requirement: 工具结果全文的单受管持有与释放

系统的上下文管线 SHALL 保证：任何持有工具结果全文的常驻池（对话消息 `messages`、执行账本 `trace`、运行结果 `tool_calls_made`）都 SHALL 有界，SHALL NOT 存在「只增不减且无上限」的工具结果全文副本。

当一个池把工具结果的正文替换为有界预览（或随生命周期释放）时，SHALL 使该全文**可被垃圾回收**——SHALL NOT 出现「把一处引用换成预览，而另一池仍持同一全文对象」从而使全文继续常驻内存的情况。

对话消息中的替换 SHALL 保证模型仍能获取全文：被替换的工具结果 SHALL 可**按引用（ref）完整、无损地回读**（区别于压缩摘要的有损）。SHALL NOT 仅以 ref 替代正文却使该 ref 不可解析——若落盘未成功，标记 SHALL 如实反映「全文不可回读」，SHALL NOT 声称存在可读的 ref。

账本类池（`trace`、`tool_calls_made`）的正文在超阈时 SHALL 以有界预览驻留，且 SHALL 保留其分析所依赖的结构字段（工具名、状态、错误类型），SHALL NOT 因有界化而丢失这些字段。有界化 SHALL 覆盖工具结果的**结果正文与工具调用参数（arguments）两者**——SHALL NOT 只约束结果正文而使超大的调用参数（如一次写入的大正文）无限期常驻。

替换 SHALL 对模型与观察者可见：被替换处 SHALL 带有可识别标记使模型知悉曾有更完整的内容及其获取方式；有界化的发生 SHALL 可被计数、可被观察，SHALL NOT 静默丢弃。

工具结果在消息中的替换 SHALL NOT 破坏 tool-call 消息链的合法性（`tool_call_id` 等结构 SHALL NOT 因此改变）。

回读入口 SHALL 对**任意 agent** 可用（含根 agent 与因深度到限而被撤除 spawn 工具的子 agent），SHALL NOT 仅限 workflow 身份。

#### Scenario: 陈旧的工具结果被替换为预览与引用

- **GIVEN** 一次对话中较早轮次产生了一个体积很大的工具结果，其已被模型消费过且滑出近期窗口
- **WHEN** 上下文管线处理
- **THEN** 该工具结果在 `messages` 中的正文 SHALL 被替换为有界预览 + ref
- **AND** 其 `tool_call_id` SHALL 保持不变，tool-call 链仍合法

#### Scenario: 当轮工具结果不被替换

- **GIVEN** 模型在本轮刚产生一个工具结果并将在本轮或下一轮使用
- **WHEN** 上下文管线处理
- **THEN** 该工具结果的正文 SHALL 保留全文
- **AND** SHALL NOT 在模型消费之前被替换为预览

#### Scenario: 超大单条结果在消费一轮后穿透近期窗口被替换

- **GIVEN** 一个体积远超单条阈值的工具结果，已被模型消费过至少一轮，但仍落在近期窗口内
- **WHEN** 上下文管线处理
- **THEN** 该结果 SHALL 被替换为有界预览 + ref（单条阈值 SHALL 独立于近期窗口生效）
- **AND** SHALL NOT 因其仍在近期窗口内而保留全文驻留

#### Scenario: 预览保留分页进度注记

- **GIVEN** 一个被 spill 的工具结果正文尾部带有 `[ReadProgress ...]` 进度注记
- **WHEN** 该结果被替换为有界预览
- **THEN** 预览 SHALL 保留该进度注记（或其等价的可解析形式）
- **AND** 压缩时的分页进度提取 SHALL 仍能识别该文件的续读位点

#### Scenario: 替换后全文可被回收

- **GIVEN** 同一工具结果全文被 `messages` 与账本池（`trace` / `tool_calls_made`）共同持有
- **WHEN** 所有持有者都已把正文替换为有界预览
- **THEN** 原工具结果全文 SHALL 不再被任何池强引用（可被垃圾回收）
- **AND** SHALL NOT 出现「仅替换了一处、全文仍被另一处持有」的情形

#### Scenario: 账本池有界但保留分析字段

- **GIVEN** 一个体积很大的工具结果被写入 `trace` / `tool_calls_made`
- **WHEN** 其正文超过阈值
- **THEN** 正文 SHALL 以有界预览驻留
- **AND** 工具名、状态、错误类型、参数等分析字段 SHALL 保持不变

#### Scenario: 被替换的结果可按引用无损回读

- **GIVEN** 一个已被替换为 ref 的工具结果
- **WHEN** 调用方按该 ref 回读
- **THEN** 系统 SHALL 返回与原始完全一致的内容（逐字节相等）
- **AND** 该回读入口 SHALL 对根 agent 与子 agent 均可用

#### Scenario: 无引用时不谎称可回读

- **GIVEN** 一个工具结果因超过阈值被截断，但其落盘未成功（无 ref）
- **WHEN** 上下文管线替换其正文
- **THEN** 标记 SHALL 如实表示为「已截断、全文不可回读」
- **AND** SHALL NOT 声称存在可解析的 ref

#### Scenario: 有界化不静默

- **GIVEN** 上下文管线对若干工具结果执行了有界化
- **WHEN** 一次 run 结束
- **THEN** 有界化的发生与量（条数、释放的字节）SHALL 可被观察
- **AND** SHALL NOT 静默发生
