# Long-Term Memory Reversibility Spec

## ADDED Requirements

### Requirement: Reversible Writes

The long-term memory system SHALL snapshot the prior state before any
destructive write (save-overwrite, supplement, update), using git commit
before write, so that a wrong dedup judgment can be reverted to the prior
body. A change log entry SHALL be recorded for each write.

#### Scenario: update snapshots prior state before overwrite

- GIVEN a memory entry with existing content
- WHEN the write-time dedup judge classifies an incoming memory as "update"
- THEN the prior entry body is committed to git history before the overwrite
- AND a change log entry records the update

#### Scenario: supplement snapshots prior state before merge

- GIVEN a memory entry with existing content
- WHEN the write-time dedup judge classifies an incoming memory as "supplement"
- THEN the prior entry body is committed to git history before the merge
- AND a change log entry records the supplement

#### Scenario: wrong judgment can be reverted to prior body

- GIVEN a destructive write has overwritten a memory entry
- WHEN the user determines the write was a wrong judgment
- THEN the prior body can be restored from git history
- AND the revert is recorded in the change log

#### Scenario: revert keeps the index consistent

- GIVEN a memory entry whose body and description have been reverted to a
  prior revision
- WHEN the revert completes
- THEN the `MEMORY.md` index line for the entry is rebuilt to match the
  reverted description
- AND the change log entry for the revert is preserved (audit history is not
  rolled back)

#### Scenario: revert is committed as two steps

- GIVEN a memory entry with git-committed revisions
- WHEN the revert tool restores the entry to a prior commit
- THEN the current state is committed first (as the undo credential)
- AND the reverted body, rebuilt index line, and change log entry are
  committed again, so the revert history is immediately visible in
  `git log -- <name>.md`

### Requirement: Conflict Resolution

The long-term memory system SHALL provide a conflict resolution API that
clears the mutual `conflict_with` markers of two conflicting memories,
records a resolve event in the change log, and optionally archives the loser.
The loser SHALL be identified by an explicit `loser` parameter.

#### Scenario: resolved conflict clears mutual markers

- GIVEN two memories marked as conflicting via mutual `conflict_with` entries
- WHEN the conflict resolution API is called with both names
- THEN both `conflict_with` markers are cleared
- AND a change log entry records the resolve event

#### Scenario: conflict resolution can archive the loser

- GIVEN two conflicting memories
- WHEN the conflict resolution API is called with archive enabled and a
  `loser` parameter naming the losing memory
- THEN the losing memory is moved to the archive directory
- AND the winning memory keeps its content with markers cleared

### Requirement: Git Backend Access

The long-term memory system SHALL expose git-backed history, diff, and
revert operations as an optional tool so an agent can inspect and restore
memory revisions.

#### Scenario: agent inspects memory history

- GIVEN a memory entry with git-committed revisions
- WHEN the agent invokes the git backend history tool for that entry
- THEN the commit log for the entry is returned

#### Scenario: agent reverts to a prior revision

- GIVEN a memory entry with git-committed revisions
- WHEN the agent invokes the git backend revert tool with a target commit
- THEN the entry body is restored to that commit's version
- AND a change log entry records the revert
