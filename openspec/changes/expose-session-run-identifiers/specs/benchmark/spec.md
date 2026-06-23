## ADDED Requirements

### Requirement: benchmark artifact 记录 correlation id

Benchmark artifact SHALL 记录 agent run 的 correlation id，便于从 benchmark result 反查 trace 和日志。

#### Scenario: benchmark 任务完成

- **GIVEN** benchmark runner 完成一个任务
- **WHEN** 写入 result 和 trace artifact
- **THEN** artifact SHOULD 包含可关联运行标识
