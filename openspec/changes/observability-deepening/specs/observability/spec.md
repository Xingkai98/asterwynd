# Observability Spec

## ADDED Requirements

### Requirement: Structured Token Metrics

The trace recorder SHALL record token usage for each LLM iteration and tool result, and SHALL expose structured event metrics with token/phase/tool dimensions as time series.

#### Scenario: tool token usage recorded

- Given a tool result with token usage
- When the trace recorder records the tool result
- Then the token usage is recorded with token/phase/tool dimensions
- And the metrics are exposed as time series

### Requirement: Cost Attribution

The observability system SHALL attribute token costs by session, phase, and tool, and SHALL output a billable breakdown.

#### Scenario: session cost breakdown

- Given a session with multiple phases and tools
- When the cost attribution runs
- Then token costs are grouped by session, phase, and tool
- And a billable breakdown is output

### Requirement: Error Auto-Classification

The observability system SHALL classify errors into four categories (permission denied, network timeout, model hallucination, parameter error) with distinct alerting policies.

#### Scenario: permission error classified

- Given an error message indicating a permission denial
- When the classifier processes the error
- Then it is classified as "permission denied"
- And the permission-denied alerting policy is applied

### Requirement: Performance Regression Gate

The CI pipeline SHALL run benchmarks, compare against a persisted baseline (P95 latency / success rate), and SHALL block on >5% degradation by returning non-zero.

#### Scenario: >5% P95 degradation blocks CI

- Given a benchmark run with P95 latency degradation >5% vs baseline
- When the regression gate evaluates the run
- Then the gate blocks (returns non-zero)
- And the pipeline is stopped

### Requirement: Session Timeline Dashboard

The observability system SHALL provide a per-session timeline visualization showing tool call durations.

#### Scenario: timeline shows slowest tool calls

- Given a session with tool calls of varying durations
- When the timeline dashboard renders
- Then tool calls are shown with their durations
- And the slowest calls are identifiable

## MODIFIED Requirements

- `observability`: metrics SHALL be recorded in a structured event schema integrated with the trace recorder rather than a separate monitoring stack.
