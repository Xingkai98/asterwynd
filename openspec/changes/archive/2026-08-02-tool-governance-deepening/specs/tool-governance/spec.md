# Tool Governance Spec

## ADDED Requirements

### Requirement: Semantic Dedup

The tool governance system SHALL detect semantically duplicate tool descriptions using embedding cosine similarity, SHALL mark tools with cosine similarity > 0.9 as `duplicate_of`, and SHALL inject a difference explanation into the prompt.

#### Scenario: two tools with same description

- Given a registry with two tools whose description embeddings have cosine similarity > 0.9
- When the tool governance system processes the registry
- Then the second tool is marked as `duplicate_of` the first
- And a difference explanation is injected into the prompt

### Requirement: Dynamic Tool Selection

The tool governance system SHALL select a Top-K subset of tools for LLM injection using a pipeline of BM25 coarse filter (Top50), embedding re-rank, and reranker re-rank to Top5, with selection latency recorded in the trace.

#### Scenario: thousand tools reduced to Top5

- Given a registry with 1000 tools
- When the LLM requests tool schemas
- Then the BM25 coarse filter selects Top50
- And embedding re-rank and reranker produce Top5 for injection
- And selection latency is recorded in the trace

### Requirement: Quality Score

The tool governance system SHALL compute a quality score per tool from aggregated call success rate, average duration factor, and user approval rate (configurable weights, default 0.5/0.3/0.2), and SHALL soft-degrade tools below a configurable threshold (default 0.4, requiring a min-sample count): degraded tools SHALL be excluded from the variable-layer selection candidates while staying visible in `get_all_schemas` and callable; quality SHALL NOT override the permission model; window state SHALL support JSON persistence across runs.

#### Scenario: low-quality tool soft-degraded out of selection

- Given a tool with quality score below the threshold
- When `select_schemas` runs
- Then the tool is excluded from variable-layer candidates
- And stable-layer tools remain injected even when degraded
- And the tool is still returned by `get_all_schemas` (soft degradation)

### Requirement: Lifecycle State Machine

The tool governance system SHALL manage tool lifecycle through states `low_traffic`, `deprecation`, `grace`, and `removed`, with deprecation notices injected into the schema/context and automatic removal from `get_all_schemas` after grace period.

#### Scenario: deprecated tool removed after grace

- Given a tool in `low_traffic` state that triggers deprecation
- When the grace period elapses
- Then the tool transitions to `removed`
- And it is no longer returned by `get_all_schemas`

### Requirement: MCP Runtime Health

The tool governance system SHALL monitor MCP server runtime health with a background periodic `ping` (configurable interval, default 30s) and a real-call failure-rate sliding window (default 20); a server SHALL be marked `degraded` when its ping fails or its failure rate crosses a configurable threshold (default 0.5 over a min-call count), and SHALL auto-recover once the window slides below the threshold and pings succeed. Degraded servers' tools SHALL be hidden from `get_all_schemas`/`select_schemas`. `McpServerStatus` SHALL expose `health_ok`, `last_health_check`, `calls`, `failures`, `failure_rate`, and `degraded`.

#### Scenario: failing MCP server degraded

- Given an MCP server with failure rate above threshold in the window
- When the health monitor evaluates the server
- Then the server is marked `degraded`
- And its tools are hidden from `get_all_schemas`/`select_schemas`

#### Scenario: health recovery auto-restores

- Given a degraded server whose failure-rate window slides below the threshold and ping succeeds again
- When the health monitor evaluates the server
- Then `degraded` is cleared
- And its tools are visible again

## MODIFIED Requirements

- `agent-runtime`: tool injection SHALL use Top-K selection instead of unconditional full schema injection, while preserving the permission model.
