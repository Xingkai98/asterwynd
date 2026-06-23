## ADDED Requirements

### Requirement: benchmark artifact 记录 Agent 运行标识

Benchmark artifact SHALL 记录 `agent_run_id`，便于从 benchmark result 反查 trace 和日志，同时 SHALL 保持 benchmark 批次 `run_id` 的既有含义。

#### Scenario: benchmark 任务完成

- **GIVEN** benchmark runner 完成一个任务
- **WHEN** 写入 result 和 trace artifact
- **THEN** task result artifact SHALL 包含 `agent_run_id`
- **AND** trace artifact SHALL 包含 Agent 运行的 `run_id`
- **AND** benchmark run metadata SHALL 继续使用既有 `run_id` 表示 benchmark 批次
