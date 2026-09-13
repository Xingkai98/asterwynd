# multi-agent-collaboration spec delta: 并发护栏语义修订

## MODIFIED Requirements

### Requirement: Concurrency and Depth Guardrails

The subagent system SHALL enforce concurrency and nesting-depth limits. Spawns exceeding the **nesting depth** limit SHALL be rejected; spawns exceeding the **instantaneous concurrency** limit SHALL be queued (bounded by a queue limit that returns an explicit `queue_full` signal), rather than rejected.

#### Scenario: spawn rejected beyond depth limit

- Given a subagent spawn beyond the configured nesting depth
- When the guardrail detects the overrun
- Then the spawn is rejected with an error
- And no background task is started

#### Scenario: spawn queued beyond concurrency limit

- Given a subagent spawn while the instantaneous concurrency limit is reached but the queue is not full
- When the guardrail detects the concurrency saturation
- Then the spawn enters the queue
- And the run is marked `queued` until an execution slot frees
