# Change Documentation Spec

## MODIFIED Requirements

### Requirement: Pre-implementation design grilling

Every non-trivial OpenSpec change SHALL complete a pre-implementation design grilling pass before tests or implementation begin.

#### Scenario: batch-grill-me is available

- **WHEN** implementation work is about to start for a non-trivial change
- **THEN** the agent uses `batch-grill-me` to challenge `design.md` against the current codebase, project vocabulary, spec delta, dependencies, risks, testing strategy, and documentation impact
- **AND** unresolved decisions are written back to the change artifacts or stable project documentation before implementation begins

#### Scenario: batch-grill-me is unavailable

- **WHEN** the current agent environment does not provide `batch-grill-me`
- **THEN** the agent performs an equivalent design grilling process manually
- **AND** every key implementation detail, dependency, risk, test strategy, and documentation impact has a recorded final decision before implementation begins
