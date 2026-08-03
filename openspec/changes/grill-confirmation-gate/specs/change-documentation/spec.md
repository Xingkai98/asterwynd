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

The grilling pass SHALL NOT be considered complete until every Open Question
raised in the decision record has been answered by a human user, with the
answers recorded in a `## User Confirmation` section. A change whose Open
Questions are not all confirmed SHALL be blocked from code writes by the write
guard and SHALL fail the artifact checker once its tasks are fully checked.

#### Scenario: grill evidence passes design review

- **GIVEN** a non-trivial change with a `reviews/grill-design.md`
- **WHEN** the record has at least 3 confirmed decisions, an empty Open
  Questions section, and a `## User Confirmation` section
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
