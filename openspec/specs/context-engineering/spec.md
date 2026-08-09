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

