# context-engineering spec delta: Read 工具默认输出上界

## ADDED Requirements

### Requirement: Read 默认输出有界

The Read tool SHALL, when invoked **without an explicit `limit`**, apply a **default output bound** so a single read cannot return an unbounded file into the context. This SHALL cover every path that omits an explicit `limit`: a plain read (no `limit`/`offset`), a read with `offset` but no `limit`, and a read with `limit` explicitly set to `0` — none of these SHALL return the whole file unbounded.

The bound SHALL constrain **both** dimensions: a default maximum number of lines **and** a default maximum byte size, whichever is reached first. The bound SHALL have a built-in default value and SHALL be overridable via configuration. A file exceeding the bound SHALL be returned as an at-most-bound prefix accompanied by a **progress note that explicitly states the content was truncated and gives the offset at which to continue**. A file within the bound SHALL be returned in full.

When `limit` is explicitly a positive integer, the Read tool SHALL behave as before (the default bound SHALL NOT apply, the caller controls the size).

The progress note's `total` SHALL always be the file's total line count, independent of `offset`. The progress note SHALL remain parseable by the component that extracts read progress for compaction; any change to the note's format SHALL be mirrored in that component.

#### Scenario: oversized file is bounded by default

- **GIVEN** a file whose line count exceeds the default line bound
- **WHEN** the Read tool is invoked with only `path`
- **THEN** the returned content SHALL be at most the default bound's leading lines
- **AND** the result SHALL carry a progress note that explicitly states truncation and the offset at which to continue

#### Scenario: few-but-huge-line file is bounded by bytes

- **GIVEN** a file whose line count is within the default line bound but whose byte size exceeds the default byte bound (e.g. a minified or single-line-huge file)
- **WHEN** the Read tool is invoked with only `path`
- **THEN** the returned content SHALL be bounded by the byte bound
- **AND** SHALL NOT return the whole file

#### Scenario: `limit=0` does not bypass the bound

- **GIVEN** a file larger than the default bound
- **WHEN** the Read tool is invoked with `limit` explicitly `0` (and no positive limit)
- **THEN** the result SHALL NOT be the unbounded full content
- **AND** the default bound SHALL apply

#### Scenario: offset without an explicit limit stays bounded

- **GIVEN** a large file
- **WHEN** the Read tool is invoked with an `offset` but no explicit `limit`
- **THEN** the returned content SHALL be bounded (SHALL NOT read to end-of-file unbounded)
- **AND** the progress note SHALL give the offset at which to continue

#### Scenario: file within the bound is returned in full

- **GIVEN** a file whose line count and byte size are both within the default bound
- **WHEN** the Read tool is invoked with only `path`
- **THEN** the returned content SHALL be byte-for-byte identical to the current unbounded output
- **AND** SHALL NOT be truncated

#### Scenario: explicit positive limit is unchanged

- **GIVEN** a large file
- **WHEN** the Read tool is invoked with explicit positive `limit` (with or without `offset`)
- **THEN** the behavior SHALL be unchanged from before this bound was introduced
