## ADDED Requirements

### Requirement: CI gate for project validation

The project SHALL provide a GitHub Actions CI workflow that runs the baseline validation commands for pull requests and pushes.

#### Scenario: Baseline CI validation

- **WHEN** a pull request or push triggers the baseline CI workflow
- **THEN** the workflow runs the full pytest suite
- **AND** runs OpenSpec strict validation for all specs and active changes
- **AND** runs the project OpenSpec artifact checker

#### Scenario: Expensive validation remains change-scoped

- **WHEN** a change requires benchmark smoke, browser smoke, real API validation, or Docker/SWE-bench validation
- **THEN** those checks are recorded in the change tasks and final verification notes
- **AND** they are not required as part of the baseline CI workflow unless a later change explicitly adds that policy

### Requirement: Impact Analysis lifecycle

Non-trivial OpenSpec changes SHALL maintain a structured Impact Analysis throughout the change lifecycle.

#### Scenario: Proposal captures initial impact

- **WHEN** a non-trivial change is proposed
- **THEN** the change records an initial `## Impact Analysis` in `proposal.md` or `design.md`
- **AND** the analysis identifies affected capabilities, code modules, tests, docs, and relevant user-facing or runtime entry points

#### Scenario: Design review resolves uncertain impact

- **WHEN** implementation is about to begin for a non-trivial change
- **THEN** pre-implementation design review revisits Impact Analysis
- **AND** unresolved impact questions are either resolved in the change artifacts or recorded as explicit blockers before implementation begins

#### Scenario: Implementation discovers a new impact

- **WHEN** implementation reveals a new affected module, entry point, validation path, compatibility concern, or documentation obligation
- **THEN** the agent updates Impact Analysis and the corresponding tasks before continuing with unrelated implementation work

#### Scenario: Archive confirms final impact

- **WHEN** a change is ready to archive
- **THEN** Impact Analysis no longer contains unexplained `unknown`, `TBD`, or `待确认` placeholders
- **AND** every affected entry point has a corresponding test, validation, documentation update, or recorded reason for no action

### Requirement: Pre-implementation review record

Non-trivial OpenSpec changes SHALL record a concise pre-implementation review summary in `design.md`.

#### Scenario: Review summary records decision process

- **WHEN** pre-implementation design review completes
- **THEN** `design.md` records the resolved questions, options considered, rejected alternatives, final confirmations, and remaining risks
- **AND** the record summarizes decision-relevant process without requiring the full chat transcript

### Requirement: OpenSpec command context configuration

The project SHALL maintain OpenSpec command context in `openspec/config.yaml` while preserving `openspec/project.md` as the human-readable project description.

#### Scenario: OpenSpec config provides short machine context

- **WHEN** OpenSpec commands generate or update change artifacts
- **THEN** `openspec/config.yaml` provides concise project context and artifact rules suitable for command injection
- **AND** detailed project conventions, capability maps, and documentation rules remain in `openspec/project.md` or linked stable docs

#### Scenario: Project description remains available

- **WHEN** an agent or maintainer needs the full OpenSpec project explanation
- **THEN** `openspec/project.md` remains available as a human-readable source
- **AND** it is not deleted merely because `openspec/config.yaml` exists
