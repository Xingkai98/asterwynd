# Change Documentation Spec

## MODIFIED Requirements

### Requirement: Pre-implementation design grilling

Every non-trivial OpenSpec change SHALL complete a pre-implementation design
grilling pass before tests or implementation begin. The grilling pass SHALL be
performed by an independent zero-memory subagent (not self-attested by the
implementing agent), SHALL produce a structured decision record at
`openspec/changes/<id>/reviews/grill-design.md`, and SHALL be mechanically
enforced: the PreToolUse write guard blocks code writes for a change whose
grilling evidence is missing, and the artifact checker fails a completed change
whose grilling evidence is absent or insufficient.

#### Scenario: batch-grill-me is available

- **WHEN** implementation work is about to start for a non-trivial change
- **THEN** the agent spawns an independent zero-memory subagent to challenge
  `design.md` against the current codebase, project vocabulary, spec delta,
  dependencies, risks, testing strategy, and documentation impact
- **AND** the subagent writes a structured decision record to
  `openspec/changes/<id>/reviews/grill-design.md` with `## Confirmed Decisions`
  (each `- **决策**: ...；理由: ...；来源: <run id>`, at least 3) and
  `## Open Questions`
- **AND** unresolved decisions are written back to the change artifacts or
  stable project documentation before implementation begins

#### Scenario: grilling evidence missing blocks code writes

- **GIVEN** a non-docs change with a spec delta
- **WHEN** the agent attempts a code write (agent/, tests/, scripts/) before a
  `reviews/grill-design.md` exists
- **THEN** the PreToolUse write guard SHALL exit 2 and block the write
- **AND** document writes (`proposal.md`, `design.md`, `tasks.md`, `specs/**`,
  `reviews/**`) are exempt

#### Scenario: completed change without grilling evidence fails checker

- **GIVEN** a non-docs change with a spec delta and fully-checked tasks
- **WHEN** the artifact checker runs on a completed change that has no
  `reviews/grill-design.md` (or fewer than 3 confirmed decisions)
- **THEN** the checker SHALL report the missing/insufficient grilling evidence
- **AND** a change with only a literal "batch-grill" task marker but no
  structured evidence SHALL fail

#### Scenario: batch-grill-me is unavailable

- **WHEN** the current agent environment does not provide `batch-grill-me`
- **THEN** the agent performs an equivalent independent design grilling
  process (spawn zero-memory subagent or equivalent) and records the decision
- **AND** every key implementation detail, dependency, risk, test strategy, and
  documentation impact has a recorded final decision before implementation
  begins
