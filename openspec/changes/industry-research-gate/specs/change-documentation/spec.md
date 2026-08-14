# Change Documentation Spec

## MODIFIED Requirements

### Requirement: Reference implementation research gate

Non-docs OpenSpec changes SHALL explicitly record whether reference implementation research is enabled or disabled before implementation begins, and SHALL declare the expected research tier as `research_tier: full|light|exempt`.

#### Scenario: Non-docs change records enabled research

- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** reference implementation research is enabled
- **THEN** the change records `## Reference Implementation Research` in `proposal.md` or `design.md`
- **AND** the section records `research_tier: full` or `research_tier: light`
- **AND** the section records `status: enabled`
- **AND** records the reason, research questions, findings, and design impact

#### Scenario: Non-docs change disables research

- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** the change owner decides reference implementation research is not useful or not applicable
- **THEN** the change records `## Reference Implementation Research` in `proposal.md` or `design.md`
- **AND** the section records `research_tier: exempt`
- **AND** the section records `status: disabled`
- **AND** records a non-empty reason that hits a structural exemption keyword (for example `docs-only`, `bugfix`, `上游决策锁定`, `无设计决策`) or cites evidence such as a closed decision issue (`#<number>`) or a review document path

#### Scenario: Research tier is validated in proposal phase

- **WHEN** the project artifact checker validates a non-docs change whose tasks are not all complete
- **THEN** it checks that `research_tier` is present and is one of `full`, `light`, `exempt`
- **AND** it does not enforce tier-specific content checks yet

#### Scenario: Completed full or light research change must be finished

- **WHEN** the project artifact checker validates a non-docs change whose tasks are all complete
- **AND** the section records `research_tier: full` or `research_tier: light`
- **THEN** the checker SHALL fail (exit 2) when findings or design impact contain self-admitted incomplete phrases from the `#123` word list (defined in `dev-workflow-state-machine/spec.md`; not restated here to avoid drift)
- **AND** the checker SHALL fail (exit 2) when `status` is `disabled`

#### Scenario: Completed exempt research change must justify exemption

- **WHEN** the project artifact checker validates a non-docs change whose tasks are all complete
- **AND** the section records `research_tier: exempt`
- **THEN** the checker SHALL fail (exit 2) when `status` is not `disabled`
- **AND** the checker SHALL fail (exit 2) when the reason is empty, hits a placeholder phrase from the `#123` word list, or neither hits a structural exemption keyword nor cites evidence

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

## ADDED Requirements

### Requirement: Research tier triage

OpenSpec changes SHALL triage the expected research depth before design, so that industry research is not skipped for design-bearing changes and is not mandated for changes with no design space. The triage SHALL be recorded as `research_tier` in the `## Reference Implementation Research` section.

#### Scenario: Architecture-level change requires full research

- **WHEN** a change involves architectural restructuring, introduces a new framework, dependency, or protocol, benchmarks against an industry product, or is non-trivial enough to require pre-implementation design grilling
- **THEN** the change SHALL record `research_tier: full`
- **AND** SHALL produce the complete research record (reason, research questions, findings, and design impact)

#### Scenario: Routine enhancement requires light research

- **WHEN** a change is a routine enhancement or applies an established pattern locally
- **THEN** the change SHALL record `research_tier: light`
- **AND** SHALL record a findings paragraph and a conclusion in the proposal, while research questions may be omitted

#### Scenario: Change with no design space is exempt with a reason

- **WHEN** a change is docs-only, a bugfix with no new capability surface and regression tests, or its design is locked by closed decision issues or architecture review conclusions with no open design item
- **THEN** the change MAY record `research_tier: exempt`
- **AND** SHALL record a non-empty reason that cites the objective basis
- **AND** placeholder text (such as `待确认` or self-admitted incomplete phrases) SHALL NOT count as a reason
