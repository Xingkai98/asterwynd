## ADDED Requirements

### Requirement: Reference implementation research gate

Non-docs OpenSpec changes SHALL explicitly record whether reference implementation research is enabled or disabled before implementation begins.

#### Scenario: Non-docs change records enabled research

- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** reference implementation research is enabled
- **THEN** `proposal.md` or `design.md` includes `## Reference Implementation Research`
- **AND** the section records `status: enabled`
- **AND** records the reason, research questions, findings, and design impact

#### Scenario: Non-docs change disables research

- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** the change owner decides reference implementation research is not useful or not applicable
- **THEN** `proposal.md` or `design.md` includes `## Reference Implementation Research`
- **AND** the section records `status: disabled`
- **AND** records a non-empty reason

#### Scenario: Local reference repositories are unavailable

- **WHEN** reference implementation research is enabled
- **AND** `.dev/reference-repos.txt` is missing, empty, or points only to unavailable repositories in the current workspace
- **THEN** the change records that local reference repositories are unavailable
- **AND** the change records the alternative basis used for the design decision
- **AND** CI does not require those local paths to exist

#### Scenario: Docs-only change is exempt

- **WHEN** an OpenSpec change has `primary: docs`
- **THEN** the artifact checker does not require `## Reference Implementation Research`

#### Scenario: Artifact checker enforces record shape

- **WHEN** the project artifact checker validates an active non-docs change
- **THEN** it checks that reference implementation research status is present and is either `enabled` or `disabled`
- **AND** it checks that enabled research has non-empty reason, research questions, findings, and design impact
- **AND** it checks that disabled research has a non-empty reason
- **AND** it does not judge research quality or verify local reference repository paths
