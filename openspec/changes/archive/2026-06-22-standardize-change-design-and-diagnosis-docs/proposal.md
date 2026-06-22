## Why

Current OpenSpec changes can carry proposal, specs, design, and tasks, but the
project process does not state when `design.md` and diagnosis notes are
required. This makes feature planning and bug investigation easy to scatter
across chat history instead of durable project artifacts.

## Change Type

- primary: process
- secondary: []

## What Changes

- Define `design.md` as the default detailed design artifact for every
  non-trivial OpenSpec change.
- Define `diagnosis.md` as the required investigation artifact for bug,
  regression, incident, and research-driven changes.
- Clarify how `proposal.md`, `design.md`, `diagnosis.md`, `tasks.md`, and spec
  delta files relate to each other.
- Document the current enforcement model: OpenSpec schema/status tracks
  standard artifacts, while project-level process rules define conditional
  artifacts such as diagnosis.

## Capabilities

### New Capabilities

- `change-documentation`: project process requirements for OpenSpec change
  artifacts and their relationships.

### Modified Capabilities

- None.

## Impact

- Affects project process documentation:
  - `docs/requirements-process.md`
  - `openspec/project.md`
- Adds a process spec:
  - `openspec/specs/change-documentation/spec.md` after archive
- Does not affect runtime code, CLI behavior, Web UI behavior, or tests.
