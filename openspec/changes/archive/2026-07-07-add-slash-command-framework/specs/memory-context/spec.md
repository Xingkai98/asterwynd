## ADDED Requirements

### Requirement: Manual clear keeps system context

MemoryManager SHALL support manual clearing of conversation history while preserving system messages.

#### Scenario: Manual clear removes non-system messages

- **GIVEN** conversation memory contains system, user, assistant, and tool messages
- **WHEN** manual clear is requested
- **THEN** memory SHALL retain system messages
- **AND** remove non-system messages

### Requirement: Manual compact can be forced

MemoryManager SHALL support a manual compact operation for the current conversation history.

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
