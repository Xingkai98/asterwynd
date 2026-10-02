# context-engineering spec delta: Read 工具默认输出上界

## MODIFIED Requirements

### Requirement: Pagination Progress Preservation

The Read tool SHALL support pagination with `(file, offset, total)` progress, and the context system SHALL persist this progress in the summary before compaction.

The Read tool SHALL, **when invoked without explicit `limit`/`offset`**, apply a **default output bound**: it SHALL return at most a bounded number of leading lines and, when the file exceeds that bound, SHALL append a progress note stating the offset read and the file's total line count so the caller can continue reading. SHALL NOT return an unbounded full file by default.

When the file does **not** exceed the default bound, the Read tool SHALL return the file content in full, byte-for-byte identical to reading without a bound.

When the caller passes explicit `limit`/`offset`, the Read tool SHALL behave as before (the default bound SHALL NOT apply). The default bound SHALL be a defined, non-magic constant.

#### Scenario: large file pagination preserved

- Given a large file being read in pages
- When the context is compacted
- Then the summary persists `(file, offset, total)` progress
- And the read can resume from the saved offset

#### Scenario: oversized file is bounded by default

- **GIVEN** a file whose line count exceeds the default output bound
- **WHEN** the Read tool is invoked with only `path` (no `limit`/`offset`)
- **THEN** the returned content SHALL be at most the default bound's leading lines
- **AND** the result SHALL carry a progress note with the file's total line count
- **AND** SHALL NOT return the unbounded full content

#### Scenario: small file is returned in full

- **GIVEN** a file whose line count is within the default output bound
- **WHEN** the Read tool is invoked with only `path`
- **THEN** the returned content SHALL be byte-for-byte identical to the file's full content
- **AND** SHALL NOT be truncated

#### Scenario: explicit pagination unchanged

- **GIVEN** a large file
- **WHEN** the Read tool is invoked with explicit `limit` or `offset`
- **THEN** the behavior SHALL be unchanged from before this bound was introduced
