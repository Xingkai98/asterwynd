# change-documentation 规格 delta

## MODIFIED Requirements

### Requirement: Artifact responsibility boundaries
OpenSpec change artifacts SHALL have distinct responsibilities so that
requirements, design decisions, investigation evidence, and implementation
tasks do not overwrite each other.

#### Scenario: Change artifact separation
- **WHEN** an agent prepares an OpenSpec change
- **THEN** `proposal.md` explains why and what changes
- **AND** spec delta files define normative behavior
- **AND** `design.md` explains how the change will be implemented
- **AND** `diagnosis.md` records root-cause evidence when applicable
- **AND** `tasks.md` lists ordered implementation steps
- **AND** `handoff.json` records the current state machine state of the change lifecycle

## ADDED Requirements

### Requirement: Handoff state file artifact

Every OpenSpec change SHALL include a `handoff.json` artifact that records the
current state machine state and transition history of the change lifecycle.

#### Scenario: handoff.json is created with the change

- **WHEN** a new OpenSpec change is created
- **THEN** `handoff.json` is initialized alongside the change
- **AND** the initial state is `planning.exploring`

#### Scenario: handoff.json is updated on state change

- **WHEN** any agent completes a sub-state or phase transition
- **THEN** `handoff.json` state and transitions are updated accordingly

#### Scenario: handoff.json is submitted with the change

- **WHEN** a change is ready for PR
- **THEN** `handoff.json` reflects the final state of the change
- **AND** it is committed as part of the change directory

### Requirement: Handoff notes directory

Agent-to-agent handoff notes SHALL be stored in `.handoff/<change-id>/` and
SHALL be excluded from version control.

#### Scenario: handoff notes are generated on phase transition

- **WHEN** an agent completes a phase and hands off to the next agent
- **THEN** a handoff note is written to `.handoff/<change-id>/<from_phase>-to-<to_phase>.md`

#### Scenario: handoff directory is gitignored

- **WHEN** `.handoff/` directory exists in the repository
- **THEN** it is listed in `.gitignore`
- **AND** handoff notes are not committed to version control
