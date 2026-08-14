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
grilling pass before tests or implementation begin. The grilling pass SHALL be
performed by an independent zero-memory subagent (not self-attested by the
implementing agent), SHALL produce a structured decision record at
`openspec/changes/<id>/reviews/grill-design.md`, and SHALL be mechanically
enforced: the PreToolUse write guard blocks code writes for a change whose
grilling evidence is missing, and the artifact checker fails a completed change
whose grilling evidence is absent or insufficient.

The grilling pass SHALL NOT be considered complete until every Open Question
raised in the decision record has been answered by a human user, with the
answers recorded in a `## User Confirmation` section. A change whose Open
Questions are not all confirmed SHALL be blocked from code writes by the write
guard and SHALL fail the artifact checker once its tasks are fully checked.

#### Scenario: grill evidence passes design review

- **GIVEN** a non-trivial change with a `reviews/grill-design.md`
- **WHEN** the record has at least 3 confirmed decisions
- **AND** either the Open Questions section is empty, or every listed Open
  Question has a matching `## User Confirmation` entry
- **THEN** the design review is satisfied and code writes are allowed

#### Scenario: open question not confirmed blocks code writes

- **GIVEN** a non-trivial change with a `reviews/grill-design.md`
- **WHEN** the record has at least 3 confirmed decisions but lists Open
  Questions that lack matching `## User Confirmation` entries
- **THEN** the PreToolUse write guard SHALL exit 2 and block the write
- **AND** the artifact checker SHALL fail once the change's tasks are fully
  checked

#### Scenario: completed change with unconfirmed open questions fails checker

- **GIVEN** a non-docs change with a spec delta and fully-checked tasks
- **WHEN** the artifact checker runs on a completed change whose
  `reviews/grill-design.md` lists Open Questions without matching
  `## User Confirmation` entries
- **THEN** the checker SHALL report the unconfirmed Open Questions

#### Scenario: batch-grill-me is unavailable

- **WHEN** the current agent environment does not provide `batch-grill-me`
- **THEN** the agent performs an equivalent independent design grilling

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
- **AND** `handoff.json` records the current state machine state of the change lifecycle

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
implementation research is enabled or disabled before implementation begins,
and SHALL declare the expected research tier as
`research_tier: full|light|exempt`.

#### Scenario: Non-docs change records enabled research
- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** reference implementation research is enabled
- **THEN** the change records `## Reference Implementation Research` in
  `proposal.md` or `design.md`
- **AND** the section records `research_tier: full` or `research_tier: light`
- **AND** the section records `status: enabled`
- **AND** records the reason, findings, and design impact
- **AND** records research questions when `research_tier: full` (omittable
  for `research_tier: light`)

#### Scenario: Non-docs change disables research
- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** the change owner decides reference implementation research is not
  useful or not applicable
- **THEN** the change records `## Reference Implementation Research` in
  `proposal.md` or `design.md`
- **AND** the section records `research_tier: exempt`
- **AND** the section records `status: disabled`
- **AND** records a non-empty reason that hits a structural exemption keyword
  (for example `docs-only`, `bugfix`, `上游决策锁定`, `无设计决策`) or cites
  evidence such as a closed decision issue (`#<number>`) or a review/decision
  document path (`docs/`, `openspec/changes/archive/`, `reviews/`)

#### Scenario: Research tier is validated in proposal phase
- **WHEN** the project artifact checker validates a non-docs change whose tasks
  are not all complete
- **THEN** it checks that `research_tier` is present and is one of `full`,
  `light`, `exempt`
- **AND** it does not enforce tier-specific content checks yet

#### Scenario: Completed full or light research change must be finished
- **WHEN** the project artifact checker validates a non-docs change whose tasks
  are all complete
- **AND** the section records `research_tier: full` or `research_tier: light`
- **THEN** the checker SHALL fail (exit 2) when findings or design impact
  contain self-admitted incomplete phrases from the `#123` word list (defined
  in `dev-workflow-state-machine/spec.md`; not restated here to avoid drift)
- **AND** the checker SHALL fail (exit 2) when `status` is `disabled`

#### Scenario: Completed exempt research change must justify exemption
- **WHEN** the project artifact checker validates a non-docs change whose tasks
  are all complete
- **AND** the section records `research_tier: exempt`
- **THEN** the checker SHALL fail (exit 2) when `status` is not `disabled`
- **AND** the checker SHALL fail (exit 2) when the reason is empty, hits a
  placeholder phrase from the `#123` word list, or neither hits a structural
  exemption keyword nor cites evidence

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
- **AND** it checks that enabled research has non-empty reason, findings, and
  design impact
- **AND** it checks that research questions are non-empty when
  `research_tier: full`
- **AND** it checks that disabled research has a non-empty reason
- **AND** it does not judge research quality or verify local reference
  repository paths

### Requirement: Research tier triage
OpenSpec changes SHALL triage the expected research depth before design, so that
industry research is not skipped for design-bearing changes and is not mandated
for changes with no design space. The triage SHALL be recorded as
`research_tier` in the `## Reference Implementation Research` section.

#### Scenario: Architecture-level change requires full research
- **WHEN** a change involves architectural restructuring, introduces a new
  framework, dependency, or protocol, benchmarks against an industry product,
  or is non-trivial enough to require pre-implementation design grilling
- **THEN** the change SHALL record `research_tier: full`
- **AND** SHALL produce the complete research record (reason, research
  questions, findings, and design impact)

#### Scenario: Routine enhancement requires light research
- **WHEN** a change is a routine enhancement or applies an established pattern
  locally
- **THEN** the change SHALL record `research_tier: light`
- **AND** SHALL record a findings paragraph and a conclusion in the proposal,
  while research questions may be omitted

#### Scenario: Change with no design space is exempt with a reason
- **WHEN** a change is docs-only, a bugfix with no new capability surface and
  regression tests, or its design is locked by closed decision issues or
  architecture review conclusions with no open design item
- **THEN** the change MAY record `research_tier: exempt`
- **AND** SHALL record a non-empty reason that cites the objective basis
- **AND** placeholder text (such as `待确认` or self-admitted incomplete
  phrases) SHALL NOT count as a reason

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

