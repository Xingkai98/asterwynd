## ADDED Requirements

### Requirement: Role-based change workflow

Non-trivial OpenSpec changes SHALL support role-based execution without requiring different agents for each role.

#### Scenario: One agent performs all roles

- **WHEN** a single agent designs, implements, reviews, and closes a change
- **THEN** the same agent MAY act as Designer, Implementer, Reviewer, and Closer
- **AND** the required change artifacts still record the decisions, implementation notes, review findings, validation, and closeout state

#### Scenario: Multiple agents split roles

- **WHEN** different agents or models split design, implementation, review, and closeout work
- **THEN** each agent treats the committed OpenSpec artifacts as the source of truth
- **AND** handoff and review conclusions are written back to the change artifacts before the next role continues

### Requirement: Implementation handoff

Non-trivial OpenSpec changes SHALL provide enough design handoff information for an Implementer to work without relying on prior chat context.

#### Scenario: Design is handed to implementation

- **WHEN** a change moves from design to implementation
- **THEN** the design artifacts identify final goals, non-goals, accepted decisions, rejected alternatives, testing strategy, Impact Analysis, remaining risks, and unresolved blockers
- **AND** unresolved blockers prevent implementation until they are resolved or explicitly accepted

### Requirement: Implementation review and revision loop

Non-trivial OpenSpec changes SHALL record implementation review findings and their resolution before closeout.

#### Scenario: Reviewer finds blocking issues

- **WHEN** implementation review finds blocking findings
- **THEN** the findings are recorded with required changes
- **AND** the change does not proceed to archive until those findings are fixed or explicitly accepted as deviations

#### Scenario: Reviewer finds non-blocking issues

- **WHEN** implementation review finds non-blocking findings
- **THEN** the findings are either fixed, converted into follow-up work, or accepted with rationale
- **AND** the final PR notes summarize any residual risk

#### Scenario: Implementation deviates from design

- **WHEN** implementation intentionally differs from the accepted design
- **THEN** the deviation is recorded in the implementation review or design artifacts
- **AND** the Reviewer or human maintainer explicitly accepts the deviation before closeout
