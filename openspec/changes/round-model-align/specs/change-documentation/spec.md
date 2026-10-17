# change-documentation 规格 delta

## MODIFIED Requirements

### Requirement: Pre-implementation design grilling

Every non-trivial OpenSpec change SHALL complete a pre-implementation design
grilling pass before tests or implementation begin. The grilling pass SHALL be
performed by an independent zero-memory subagent (not self-attested by the
implementing agent) — using the `grilling` skill, or an equivalent independent
design interview where the environment does not provide it — SHALL produce a
structured decision record at `openspec/changes/<id>/reviews/grill-design.md`,
and SHALL be mechanically enforced: the PreToolUse write guard blocks code
writes for a change whose grilling evidence is missing, and the artifact checker
fails a completed change whose grilling evidence is absent or insufficient.

Following the grilling pass and **before** the stop-turn user confirmation, the
change SHALL run a **design-phase review loop**: an independent zero-memory
reviewer that performs **adversarial analysis** (defaulting to the assumption
that the design is wrong, attempting to refute each Confirmed Decision and the
design's assumptions), returns a **verdict** (`PASS` / `CHANGES_REQUESTED` /
`BLOCKED`), and on `CHANGES_REQUESTED` the design SHALL be revised and re-verified under the
**bounded-batch round model** defined in the `dev-workflow-state-machine`
capability: a round is one non-empty medium+ batch closure (open batch -> fix
all -> verify only -> close), at most 20 closed rounds apply, new medium+ issues
found during verification SHALL be deferred to the next batch rather than raised
as current blockers, and the exits are `PASS` / `BLOCKED` + cause / over-limit
`BLOCKED` with "revise the design". `CHANGES_REQUESTED` is an in-round state,
not an exit. If round 20 itself reaches the verification-retry termination
point, or the closing check after round 20 still finds medium+ issues, the exit
SHALL be over-limit `BLOCKED` with "revise the design". The loop SHALL produce a
structured record
at `openspec/changes/<id>/reviews/grill-adversarial.md`. This loop is
**isomorphic to the implementation-phase `/review-loop`** — same bounded-batch
model (independent zero-memory reviewer -> open batch -> fix all -> verify only
-> close; deferred issues enter the next batch), not an open-ended loop — but
reviews the **design**, not code. The implementation-phase `/review-loop` (which
reviews code and produces `building-review.md`) SHALL continue to exist as a
separate implementation-phase loop; **both loops SHALL use the same bounded-batch
round model**, and neither loop SHALL replace the other.

Within the design-phase review loop, for every Open Question the grilling raised
the reviewer SHALL either resolve it from the codebase when the answer is
**code-decidable**, or classify it as a **user decision** when it is not.
**Code-decidable** Open Questions SHALL be answered with evidence
(`file:line`), recorded under a `## Code-Resolved Questions` section in
`grill-design.md`, and SHALL NOT be carried into `## Open Questions` or the
stop-turn queue. Only **user decisions** SHALL remain in `## Open Questions`.

The grilling pass SHALL NOT be considered complete until every Open Question
remaining in `## Open Questions` has been answered by a human user, with the
answers recorded in a `## User Confirmation` section. A change whose Open
Questions are not all confirmed SHALL be blocked from code writes by the write
guard and SHALL fail the artifact checker once its tasks are fully checked.

The design-phase review loop's exit SHALL be a precondition for implementation:
a `BLOCKED` exit SHALL NOT be treated as permission to write code. Only `PASS`,
or `BLOCKED` + cause + **an explicit user ruling to continue**, SHALL allow
implementation to start; the ruling SHALL be recorded in
`grill-design.md`'s `## User Confirmation` (or a `## Blocked Ruling` section).

#### Scenario: grill evidence passes design review

- **GIVEN** a non-trivial change with a `reviews/grill-design.md`
- **WHEN** the record has at least 3 confirmed decisions
- **AND** either the Open Questions section is empty, or every listed Open
  Question has a matching `## User Confirmation` entry
- **THEN** the design review is satisfied and code writes are allowed

#### Scenario: design-phase review loop resolves code-decidable questions

- **GIVEN** a change whose `grill-design.md` lists an Open Question answerable
  from the codebase (e.g. "does `_find_scope_root` walk past a non-git tmp dir?")
- **WHEN** the design-phase review loop runs
- **THEN** the question SHALL be answered with `file:line` evidence
- **AND** it SHALL be recorded under `## Code-Resolved Questions`
- **AND** it SHALL NOT appear in `## Open Questions` or require `## User Confirmation`

#### Scenario: design-phase review loop challenges confirmed decisions under the bounded-batch model

- **GIVEN** a change whose `grill-design.md` records Confirmed Decisions
- **WHEN** the design-phase review loop runs
- **THEN** the reviewer SHALL attempt to refute each Confirmed Decision
- **AND** it SHALL record a verdict (`PASS` / `CHANGES_REQUESTED` / `BLOCKED`)
  with per-issue `file:line` evidence in `reviews/grill-adversarial.md`
- **AND** on `CHANGES_REQUESTED`, the design SHALL be revised and verified within
  the same round; the batch SHALL close only when every medium+ item in it is
  verified fixed
- **AND** new medium+ issues found during verification SHALL be deferred to the
  next batch, not raised as current blockers
- **AND** the loop SHALL stop after at most 20 closed rounds; if the closing
  check after round 20 still finds medium+ issues, the exit SHALL be over-limit
  `BLOCKED` with "revise the design"
- **AND** any refuted decision SHALL be corrected in `grill-design.md` before
  the stop-turn confirmation

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

#### Scenario: grilling skill is unavailable

- **WHEN** the current agent environment does not provide the `grilling` skill
- **THEN** the agent performs an equivalent independent design grilling
