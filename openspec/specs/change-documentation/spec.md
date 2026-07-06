# change-documentation 规格

## Purpose

定义 OpenSpec change 的设计、诊断、类型元数据和机械检查规则，确保需求、设计、根因分析、任务拆分和实现验收职责清晰分离。

## Requirements

### Requirement: Detailed design artifact
Every non-trivial OpenSpec change SHALL include a `design.md` artifact that
records the implementation approach and major technical decisions before
development starts.

#### Scenario: Feature change with implementation work
- **WHEN** an OpenSpec change introduces or modifies runtime behavior,
  architecture, configuration, dependencies, or tests
- **THEN** the change includes `design.md`
- **AND** the design documents goals, non-goals, decisions, risks, and testing
  strategy

#### Scenario: Design reviewed before implementation
- **WHEN** implementation work is about to start for a non-trivial change
- **THEN** the `design.md` has been reviewed and accepted by a human reviewer
- **AND** mechanical checks are not treated as design approval

#### Scenario: Trivial documentation-only change
- **WHEN** an OpenSpec change only fixes wording, broken links, or stale
  documentation without altering project behavior or process
- **THEN** the proposal may state that no separate detailed design is required

### Requirement: Pre-implementation design grilling
Every non-trivial OpenSpec change SHALL complete a pre-implementation design
grilling pass before tests or implementation begin.

#### Scenario: grill-with-docs is available
- **WHEN** implementation work is about to start for a non-trivial change
- **THEN** the agent uses `grill-with-docs` to challenge `design.md` against
  the current codebase, project vocabulary, spec delta, dependencies, risks,
  testing strategy, and documentation impact
- **AND** unresolved decisions are written back to the change artifacts or
  stable project documentation before implementation begins

#### Scenario: grill-with-docs is unavailable
- **WHEN** the current agent environment does not provide `grill-with-docs`
- **THEN** the agent performs an equivalent design grilling process manually
- **AND** every key implementation detail, dependency, risk, test strategy, and
  documentation impact has a recorded final decision before implementation
  begins

### Requirement: Diagnosis artifact
Bug, regression, incident, and research-driven OpenSpec changes SHALL include a
`diagnosis.md` artifact before implementation begins.

#### Scenario: Bug-driven change
- **WHEN** a change is created to fix a failing tool, UI defect, regression, or
  production-like incident
- **THEN** the change includes `diagnosis.md`
- **AND** the diagnosis records symptom, reproduction, evidence, hypotheses,
  root cause, fix options, and regression test expectations

#### Scenario: Diagnosis leads to design
- **WHEN** diagnosis shows that the fix requires a new architecture or
  substantial behavior change
- **THEN** the change also includes `design.md`
- **AND** the design references the diagnosis as the reason for the chosen
  approach

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

### Requirement: Change type metadata
Every OpenSpec change SHALL declare a primary change type and a secondary type
list in `proposal.md`.

#### Scenario: Single-type change
- **WHEN** a change has one clear work type
- **THEN** `proposal.md` includes `## Change Type`
- **AND** it declares `primary` as one allowed type
- **AND** it declares `secondary: []`

#### Scenario: Multi-type change
- **WHEN** a change is triggered by one type of work and also includes other
  work qualities
- **THEN** `primary` records the trigger
- **AND** `secondary` records additional types
- **AND** the change satisfies the artifact requirements for every declared
  type

### Requirement: Mechanical artifact checks
The project SHALL use a local artifact checker for mechanical document rules
without attempting to judge technical design quality.

#### Scenario: Artifact checker scope
- **WHEN** the project artifact checker validates an active change
- **THEN** it checks valid `Change Type` metadata, required files, required
  section headings, non-empty section bodies, and template placeholders
- **AND** it does not score design correctness, architecture quality, or
  implementation trade-offs

#### Scenario: Artifact checker combines type rules
- **WHEN** a change declares both `primary` and `secondary` types
- **THEN** the artifact checker applies the requirements for the union of all
  declared types

### Requirement: CI gate for project validation
The project SHALL provide a GitHub Actions CI workflow that runs the baseline
validation commands for pull requests and pushes.

#### Scenario: Baseline CI validation
- **WHEN** a pull request or push triggers the baseline CI workflow
- **THEN** the workflow runs the full pytest suite
- **AND** runs OpenSpec strict validation for all specs and active changes
- **AND** runs the project OpenSpec artifact checker

#### Scenario: Expensive validation remains change-scoped
- **WHEN** a change requires benchmark smoke, browser smoke, real API
  validation, or Docker/SWE-bench validation
- **THEN** those checks are recorded in the change tasks and final
  verification notes
- **AND** they are not required as part of the baseline CI workflow unless a
  later change explicitly adds that policy

### Requirement: Impact Analysis lifecycle
Non-trivial OpenSpec changes SHALL maintain a structured Impact Analysis
throughout the change lifecycle.

#### Scenario: Proposal captures initial impact
- **WHEN** a non-trivial change is proposed
- **THEN** the change records an initial `## Impact Analysis` in `proposal.md`
  or `design.md`
- **AND** the analysis identifies affected capabilities, code modules, tests,
  docs, and relevant user-facing or runtime entry points

#### Scenario: Design review resolves uncertain impact
- **WHEN** implementation is about to begin for a non-trivial change
- **THEN** pre-implementation design review revisits Impact Analysis
- **AND** unresolved impact questions are either resolved in the change
  artifacts or recorded as explicit blockers before implementation begins

#### Scenario: Implementation discovers a new impact
- **WHEN** implementation reveals a new affected module, entry point,
  validation path, compatibility concern, or documentation obligation
- **THEN** the agent updates Impact Analysis and the corresponding tasks before
  continuing with unrelated implementation work

#### Scenario: Archive confirms final impact
- **WHEN** a change is ready to archive
- **THEN** Impact Analysis no longer contains unexplained `unknown`, `TBD`, or
  `待确认` placeholders
- **AND** every affected entry point has a corresponding test, validation,
  documentation update, or recorded reason for no action

### Requirement: Reference implementation research gate
Non-docs OpenSpec changes SHALL explicitly record whether reference
implementation research is enabled or disabled before implementation begins.

#### Scenario: Non-docs change records enabled research
- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** reference implementation research is enabled
- **THEN** the change records `## Reference Implementation Research` in
  `proposal.md` or `design.md`
- **AND** the section records `status: enabled`
- **AND** records the reason, research questions, findings, and design impact

#### Scenario: Non-docs change disables research
- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** the change owner decides reference implementation research is not
  useful or not applicable
- **THEN** the change records `## Reference Implementation Research` in
  `proposal.md` or `design.md`
- **AND** the section records `status: disabled`
- **AND** records a non-empty reason

#### Scenario: Local reference repositories are unavailable
- **WHEN** reference implementation research is enabled
- **AND** `.dev/reference-repos.txt` is missing, empty, or points only to
  unavailable repositories in the current workspace
- **THEN** the change records that local reference repositories are unavailable
- **AND** the change records the alternative basis used for the design decision
- **AND** CI does not require those local paths to exist

#### Scenario: Docs-only change is exempt
- **WHEN** an OpenSpec change has `primary: docs`
- **THEN** the artifact checker does not require
  `## Reference Implementation Research`

#### Scenario: Artifact checker enforces record shape
- **WHEN** the project artifact checker validates an active non-docs change
- **THEN** it checks that reference implementation research status is present
  and is either `enabled` or `disabled`
- **AND** it checks that enabled research has non-empty reason, research
  questions, findings, and design impact
- **AND** it checks that disabled research has a non-empty reason
- **AND** it does not judge research quality or verify local reference
  repository paths

### Requirement: Pre-implementation review record
Non-trivial OpenSpec changes SHALL record a concise pre-implementation review
summary in `design.md`.

#### Scenario: Review summary records decision process
- **WHEN** pre-implementation design review completes
- **THEN** `design.md` records the resolved questions, options considered,
  rejected alternatives, final confirmations, and remaining risks
- **AND** the record summarizes decision-relevant process without requiring the
  full chat transcript

### Requirement: OpenSpec command context configuration
The project SHALL maintain OpenSpec command context in `openspec/config.yaml`
while preserving `openspec/project.md` as the human-readable project
description.

#### Scenario: OpenSpec config provides short machine context
- **WHEN** OpenSpec commands generate or update change artifacts
- **THEN** `openspec/config.yaml` provides concise project context and
  artifact rules suitable for command injection
- **AND** detailed project conventions, capability maps, and documentation
  rules remain in `openspec/project.md` or linked stable docs

#### Scenario: Project description remains available
- **WHEN** an agent or maintainer needs the full OpenSpec project explanation
- **THEN** `openspec/project.md` remains available as a human-readable source
- **AND** it is not deleted merely because `openspec/config.yaml` exists
