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

### Requirement: 超过 token 上限时压缩

MemoryManager SHALL 在估算 token 数超过上限时执行 compact。`compact_if_needed` SHALL 返回是否实际触发了 compact；未超过上限时 SHALL 返回 false 并保持消息列表不变。

#### Scenario: 未超过上限

- **GIVEN** 消息 token 估算未超过 `max_tokens`
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 保持消息列表不变
- **AND** 返回 false

#### Scenario: 超过上限

- **GIVEN** 消息 token 估算超过 `max_tokens`
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 执行 compact
- **AND** 返回 true

### Requirement: compact 必须保留系统消息和近期上下文

MemoryManager SHALL 保留所有原始 system 消息和 recent window 内的近期非 system 消息。未配置 LLM 或无法生成有效摘要时，compact SHALL 降级为裁剪 recent window 之前的非 system 消息。

#### Scenario: 无 LLM 时执行裁剪降级

- **GIVEN** 消息历史超过上限
- **AND** MemoryManager 未配置 LLM
- **WHEN** compact 被触发
- **THEN** 系统 SHALL 丢弃 recent window 之前的非 system 消息
- **AND** 保留 system 消息和近期消息窗口

#### Scenario: LLM 摘要生成失败时执行裁剪降级

- **GIVEN** 消息历史超过上限
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

### Requirement: compact 配置 LLM 时生成摘要

MemoryManager SHALL 在配置 LLM 且存在待压缩中间消息时调用 LLM 生成摘要。摘要 SHALL 以 system 消息插入在原始 system 消息之后、近期上下文之前，内容 SHALL 使用 `Previous conversation summary:` 前缀。

#### Scenario: 有 LLM 时生成 summary message

- **GIVEN** 消息历史超过上限
- **AND** MemoryManager 配置了 LLM
- **AND** recent window 之前存在非 system 消息
- **WHEN** compact 被触发且 LLM 返回非空摘要
- **THEN** 系统 SHALL 插入一条 summary system 消息
- **AND** summary system 消息 SHALL 位于原始 system 消息之后
- **AND** summary system 消息 SHALL 位于近期消息窗口之前
- **AND** summary 内容 SHALL 包含 LLM 返回的摘要文本

### Requirement: Manual clear keeps system context

MemoryManager SHALL support manual clearing of conversation history while preserving system messages.

#### Scenario: Manual clear removes non-system messages

- **GIVEN** conversation memory contains system, user, assistant, and tool messages
- **WHEN** manual clear is requested
- **THEN** memory SHALL retain system messages
- **AND** remove non-system messages

### Requirement: Manual compact can be forced

MemoryManager SHALL support a manual compact operation for the current conversation history. Manual compact SHALL ignore the automatic compact token threshold and use the retained recent window to decide whether older non-system messages are eligible.

#### Scenario: Manual compact requested under token budget

- **GIVEN** conversation history is below the automatic compact token threshold
- **WHEN** the user manually requests compact
- **THEN** the system SHALL either compact eligible older messages or return a clear no-op result
- **AND** the result SHALL be observable by the caller

#### Scenario: Manual compact has no eligible older messages

- **GIVEN** conversation history contains no non-system messages beyond the retained recent window
- **WHEN** the user manually requests compact
- **THEN** the system SHALL leave conversation history unchanged
- **AND** return an observable no-op result

#### Scenario: Manual compact preserves tool-call chains

- **GIVEN** conversation history contains assistant tool calls and tool results
- **WHEN** manual compact is requested
- **THEN** compact SHALL preserve provider-valid tool-call chains using the same invariant as automatic compact
