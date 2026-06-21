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

MemoryManager SHALL 在估算 token 数超过上限时执行 compact。

#### Scenario: 未超过上限

- **GIVEN** 消息 token 估算未超过 `max_tokens`
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 保持消息列表不变

### Requirement: compact 必须保留系统消息和近期上下文

MemoryManager SHALL 保留所有 system 消息和 recent window 内的近期非 system 消息。当前 compact 不生成摘要消息，即使构造时提供了 llm。

#### Scenario: 执行 compact

- **GIVEN** 消息历史超过上限
- **WHEN** compact 被触发
- **THEN** 系统 SHALL 丢弃 recent window 之前的非 system 消息
- **AND** 保留 system 消息和近期消息窗口

### Requirement: compact 不得破坏 tool-call 链

MemoryManager SHALL 在保留近期消息时连同相关 assistant tool call 和 tool result 一起保留。

#### Scenario: 近期 tool result 依赖更早 assistant tool call

- **GIVEN** recent window 包含 tool result
- **WHEN** 对应 assistant tool call 位于 recent window 之前
- **THEN** compact SHALL 额外保留该 assistant 消息
- **AND** 保持 provider 可接受的消息链
