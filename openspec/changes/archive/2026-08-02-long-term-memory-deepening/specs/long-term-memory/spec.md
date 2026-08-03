# Long-Term Memory Spec

## ADDED Requirements

### Requirement: Write Dedup with Conflict Detection

The long-term memory system SHALL dedup incoming memories by embedding recall of top-5 similar memories, SHALL use LLM judgment to classify each as "supplement", "update", or "conflict", SHALL mark conflicts and maintain a change log.

#### Scenario: conflicting memory marked

- Given an incoming memory that conflicts with a recalled similar memory
- When the LLM judges the relationship as "conflict"
- Then the conflict is marked
- And a change log entry is recorded

### Requirement: Importance-Recency Decay

The long-term memory system SHALL score memories by importance × recency, SHALL auto-archive memories not retrieved for 30 days, and SHALL provide archive/restore APIs.

#### Scenario: stale memory archived

- Given a memory not retrieved for more than 30 days
- When the decay score falls below the threshold
- Then the memory is auto-archived
- And it can be restored via the restore API

### Requirement: On-Demand Semantic Retrieval

The long-term memory system SHALL inject only a ~50-token global summary into context and SHALL expose a `SearchMemory` tool for on-demand semantic retrieval.

#### Scenario: semantic search on demand

- Given a context with only the ~50-token global summary injected
- When the model invokes `SearchMemory` with a query
- Then top-k semantically similar memories are returned

### Requirement: Scope Isolation

The long-term memory system SHALL tag memories with project/repo scope and SHALL enforce scope isolation across projects.

#### Scenario: cross-project query blocked

- Given a memory tagged with project A scope
- When a query from project B tries to access it
- Then the access is blocked
- And no cross-project data leaks
