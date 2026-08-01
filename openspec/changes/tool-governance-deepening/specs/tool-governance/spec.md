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

The tool governance system SHALL compute a quality score per tool from aggregated call success rate, average duration, and user confirmation rate, and SHALL auto-degrade tools below a quality threshold.

#### Scenario: low-quality tool auto-degraded

- Given a tool with low call success rate and high average duration
- When the quality score is computed below the threshold
- Then the tool is auto-degraded (excluded from `get_all_schemas` or lowered priority)

### Requirement: Lifecycle State Machine

The tool governance system SHALL manage tool lifecycle through states `low_traffic`, `deprecation`, `grace`, and `removed`, with deprecation notices injected into the schema/context and automatic removal from `get_all_schemas` after grace period.

#### Scenario: deprecated tool removed after grace

- Given a tool in `low_traffic` state that triggers deprecation
- When the grace period elapses
- Then the tool transitions to `removed`
- And it is no longer returned by `get_all_schemas`

### Requirement: MCP Runtime Health

The tool governance system SHALL monitor MCP server runtime health with health pings and failure-rate windows, and SHALL auto-degrade servers exceeding failure thresholds by hiding their tools.

#### Scenario: failing MCP server degraded

- Given an MCP server with failure rate above threshold in the window
- When the health monitor evaluates the server
- Then the server is marked `degraded`
- And its tools are hidden from the registry

## MODIFIED Requirements

- `agent-runtime`: tool injection SHALL use Top-K selection instead of unconditional full schema injection, while preserving the permission model.
