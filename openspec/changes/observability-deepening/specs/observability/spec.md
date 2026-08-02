# Observability Spec

## ADDED Requirements

### Requirement: Structured Token Metrics

The trace recorder SHALL record token usage for each LLM iteration (input/output tokens, model, finish_reason), SHALL attach a wall-clock timestamp to each trace step, and SHALL expose the event schema version.

#### Scenario: LLM iteration token recorded

- **GIVEN** an LLM iteration with token usage
- **WHEN** the trace recorder records the iteration
- **THEN** input/output tokens, model, and finish_reason are recorded
- **AND** each trace step carries a timestamp
- **AND** the serialized trace includes a schema version

### Requirement: Cost Attribution (CostLedger)

The observability system SHALL attribute token costs by session, phase, and tool via a `CostLedger`, SHALL output a billable breakdown (`by_session`/`by_phase`/`by_tool`), and SHALL persist records to JSONL for cross-session historical stats.

#### Scenario: session cost breakdown

- **GIVEN** a session with multiple phases and tools
- **WHEN** the ledger records LLM calls
- **THEN** token costs are grouped by session, phase, and tool
- **AND** a billable breakdown is output
- **AND** flushing to JSONL and reloading restores the same totals

### Requirement: Error Auto-Classification

The observability system SHALL classify system-level errors into four categories (permission denied, network timeout, model error, parameter error) using structured attributes first (error_type/finish_reason) with text fallback, SHALL assign each category an alert policy, and SHALL NOT auto-classify semantic errors (hallucination) — that is deferred to an LLM judge.

#### Scenario: structured error classified

- **GIVEN** an error with `error_type=permission_denied`
- **WHEN** the classifier processes it
- **THEN** it is classified as permission_denied
- **AND** its alert policy is `immediate`

#### Scenario: text fallback for unstructured error

- **GIVEN** an error text containing "timed out"
- **WHEN** the classifier processes it with no structured field
- **THEN** it is classified as network_timeout
- **AND** its alert policy is `warn`

## MODIFIED Requirements

### Requirement: 事件 schema 扩展

`agent-runtime` 的 trace 事件 SHALL 增加 timestamp（TraceStep 字段，不污染 data 负载）、schema_version、llm_iteration 的 token/model/finish_reason 字段、tool_result 的 error_type 字段——全部向后兼容扩展（新参数带默认值，不破坏既有事件结构）。

#### Scenario: 既有事件结构不破坏

- **GIVEN** 一个既有 trace 事件（无 token/timestamp 字段）
- **WHEN** 新 recorder 序列化它
- **THEN** data 负载保持不变（timestamp 是 step 字段）
- **AND** schema_version 附加在顶层

### Requirement: Benchmark Regression Gate

The observability system SHALL provide a benchmark regression gate that persists baseline metrics (success rate, p95 latency), compares a new run against the baseline, and returns a non-zero exit when success rate drops more than 5 percentage points or p95 latency exceeds `max(baseline * 1.05, baseline + 1.0s)` (relative 5% with an absolute 1-second floor so sub-second baselines are not subject to meaningless jitter).

#### Scenario: gate blocks a degraded run

- **GIVEN** a baseline with `success_rate=0.95` and `p95_latency_s=10.0`
- **WHEN** a new run has `success_rate=0.85` or `p95_latency_s=11.5`
- **THEN** the gate returns non-zero
- **AND** the report lists per-metric deltas

#### Scenario: p95 exactly at the absolute floor ceiling passes

- **GIVEN** a baseline with `p95_latency_s=10.0`
- **WHEN** a new run has `p95_latency_s=11.0`
- **THEN** the gate passes (ceiling is `max(10.5, 11.0)=11.0`, strict `>`)

#### Scenario: update baseline from a trusted run

- **GIVEN** a trusted run
- **WHEN** the gate is run with `--update-baseline`
- **THEN** the baseline file is rewritten with the run's metrics
- **AND** subsequent runs compare against the new baseline

### Requirement: Session Timeline

The observability system SHALL expose a per-session timeline of tool calls ordered by duration (ms) with success status, shaping bar-width data for the web UI.

#### Scenario: session timeline query

- **GIVEN** a session with tool calls of varying durations
- **WHEN** the timeline endpoint is queried
- **THEN** calls are returned sorted by duration descending
- **AND** each call carries `tool_name`, `duration_ms`, `success`, `arguments`, `index`, and `bar_pct`
