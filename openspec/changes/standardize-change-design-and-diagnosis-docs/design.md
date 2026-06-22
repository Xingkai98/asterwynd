## Context

OpenSpec's bundled `spec-driven` schema already defines four artifacts:
`proposal`, `specs`, `design`, and `tasks`. The CLI can report missing design
artifacts through `openspec status --change <id>`, but the current project
documentation does not make detailed design mandatory for active changes.

The project also has a bug-investigation rule in `AGENTS.md`: identify root
cause and propose a solution before editing code. There is no durable artifact
for that work, so problem diagnosis can remain trapped in chat history.

## Goals / Non-Goals

**Goals:**

- Make detailed design a normal part of every non-trivial OpenSpec change.
- Make problem diagnosis a first-class artifact for bug and research-driven
  work.
- Require each change to declare `primary` and `secondary` change types.
- Apply artifact requirements from every declared type.
- Keep change-level design and diagnosis next to the change they explain.
- Preserve `docs/` for stable project documentation, not per-change planning.
- Define the boundary between mechanical artifact checks and human design
  review.

**Non-Goals:**

- Do not change OpenSpec CLI source code.
- Do not fork the OpenSpec workflow schema in this change.
- Do not require `diagnosis.md` for purely additive feature work.
- Do not backfill all existing eight active changes in this change.
- Do not make a script judge whether a design is technically correct.

## Decisions

### Decision 1: Store detailed design in each change

Each non-trivial OpenSpec change SHALL include `design.md` in the change
directory. This file owns implementation approach, architecture decisions,
interfaces, configuration, error handling, testing strategy, alternatives, and
risks.

Reasoning:

- The bundled `spec-driven` schema already models `design` as a standard
  artifact.
- Design decisions belong with the proposed delta until the change is
  archived.
- Stable docs can later summarize accepted designs without duplicating every
  planning detail.

### Decision 2: Store diagnosis beside the originating change

Bug, regression, incident, and research-driven changes SHALL include
`diagnosis.md`. The diagnosis file records symptoms, reproduction, evidence,
hypotheses, root cause, fix options, recommended direction, and regression test
expectations.

Reasoning:

- Root-cause analysis is evidence, not implementation detail.
- Some diagnosis work leads to a design; some ends in a small fix. Keeping it
  separate prevents `design.md` from becoming an incident log.
- The artifact follows the change into `openspec/changes/archive/`.

### Decision 3: Use primary and secondary change types

Each `proposal.md` SHALL include `## Change Type` with a `primary` type and a
`secondary` list. `primary` records the trigger for the change. `secondary`
records additional work qualities such as research or implementation.

Artifact requirements are evaluated over the union of `primary` and
`secondary`. For example, `primary: bugfix` with `secondary: [research,
feature]` requires both `diagnosis.md` and `design.md`.

Reasoning:

- Many real changes are bug-triggered, research-informed, and
  feature-implemented.
- A single label loses useful process information.
- Union semantics are simple enough for a mechanical checker and clear enough
  for humans reviewing the plan.

### Decision 4: Keep OpenSpec schema enforcement separate from project checks

This change will not fork the OpenSpec schema. The project will use three
separate gates:

- OpenSpec schema/status for standard artifact discovery and completion
  tracking.
- A project-local script for mechanical checks such as required files, required
  sections, non-empty section bodies, and absence of template placeholders.
- Human review for design quality and technical soundness.

Reasoning:

- The current schema format tracks fixed artifacts. Making `diagnosis` a schema
  artifact would show it as missing for every feature-only change.
- Mechanical checks can prevent empty shells, but they cannot reliably judge
  architecture quality.
- Human review is the right gate for whether a design is coherent and ready for
  development.

### Decision 5: Require human design approval before implementation

Implementation work SHALL NOT start until the relevant `design.md` has been
reviewed and accepted by a human reviewer.

Reasoning:

- The design document is meant to align trade-offs before code is written.
- A document can satisfy section checks while still being the wrong design.
- Human review keeps the quality bar explicit without pretending that script
  heuristics understand architecture.

## Risks / Trade-offs

- [Risk] More documents can slow down small changes.
  Mitigation: allow trivial documentation-only or typo changes to state that no
  separate design is needed in the proposal.

- [Risk] Conditional diagnosis rules may be missed by agents.
  Mitigation: document the rule in both `docs/requirements-process.md` and
  `openspec/project.md`; use the project artifact checker for mechanical
  enforcement.

- [Risk] Detailed design may duplicate stable docs.
  Mitigation: design stays change-local; only enduring conclusions are promoted
  to stable `docs/`.

- [Risk] A design can pass mechanical checks but still be weak.
  Mitigation: require human approval before implementation begins.

## Testing Strategy

- Unit-test the artifact checker with representative change directories.
- Cover `primary` plus `secondary` union semantics, including a bugfix that is
  also research-informed and feature-implemented.
- Cover docs-only changes that do not require design.
- Cover placeholder-only sections so template shells fail mechanically.
- Continue running `openspec validate --changes --strict` and
  `openspec validate --specs --strict` for OpenSpec-native validation.

## Migration Plan

1. Add this process spec and documentation.
2. Use the rule for new changes immediately.
3. Backfill `design.md` for existing active changes as a separate cleanup task.
4. Add `diagnosis.md` to the WebSearch hardening change because it is driven by
   a reproduced tool failure and external-provider research.
5. Add a small project-local artifact checker that verifies existence and
   non-empty required sections without judging design quality.
6. Add `Change Type` metadata to active changes so the checker has explicit
   inputs.

## Open Questions

- Whether a project-local OpenSpec schema should be forked after several
  changes prove the artifact pattern stable.
