## ADDED Requirements

### Requirement: 手动 clear 保留 system 上下文

MemoryManager SHALL 支持手动清理会话历史，并保留 system messages。

#### Scenario: 手动 clear 移除非 system messages

- **GIVEN** 会话 memory 包含 system、user、assistant 和 tool messages
- **WHEN** 用户请求手动 clear
- **THEN** memory SHALL 保留 system messages
- **AND** 移除非 system messages

### Requirement: 手动 compact 可以主动触发

MemoryManager SHALL 支持对当前会话历史执行手动 compact。

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
