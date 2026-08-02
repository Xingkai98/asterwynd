# Context Engineering Spec

## ADDED Requirements

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

## MODIFIED Requirements

- `context-injection`: injection ordering SHALL follow the stable-prefix layering (system/MD/core tools as stable layer, selected tools as variable tail).
