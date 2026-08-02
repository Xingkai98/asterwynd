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
