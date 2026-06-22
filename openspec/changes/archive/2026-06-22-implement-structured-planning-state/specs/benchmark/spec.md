## ADDED Requirements

### Requirement: benchmark artifact 记录 planning state

Benchmark trace SHALL 记录 planning state 事件，便于分析 agent 未完成任务时卡在哪个步骤。Benchmark result artifact SHOULD 包含最终 planning summary；如果运行中没有 planning state，artifact SHALL 保持向后兼容。

#### Scenario: benchmark 任务包含 planning 事件

- **GIVEN** MyAgentRunner 运行任务时产生 planning state
- **WHEN** 写入 trace artifact
- **THEN** trace SHALL 包含 planning state 事件序列

#### Scenario: benchmark 任务完成后保存 planning 摘要

- **GIVEN** MyAgentRunner 运行任务时产生 planning state
- **WHEN** 写入 result artifact
- **THEN** result SHALL 包含最终 planning summary
