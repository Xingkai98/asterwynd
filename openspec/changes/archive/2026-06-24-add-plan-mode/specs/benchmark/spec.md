## MODIFIED Requirements

### Requirement: benchmark artifact 记录 planning state 和 Plan Document

Benchmark trace SHALL 记录 planning state 和 Plan Document 事件，便于分析 agent 未完成任务时卡在哪个步骤以及计划阶段的方案。Benchmark result artifact SHOULD 包含最终 planning summary；如果运行中没有 planning state 或 Plan Document，artifact SHALL 保持向后兼容。

#### Scenario: benchmark 任务包含 planning 事件

- **GIVEN** MyAgentRunner 运行任务时产生 planning state
- **WHEN** 写入 trace artifact
- **THEN** trace SHALL 包含 planning state 事件序列

#### Scenario: benchmark 任务包含 Plan Document 事件

- **GIVEN** MyAgentRunner 运行任务时产生 Plan Document
- **WHEN** 写入 trace artifact
- **THEN** trace SHALL 包含 Plan Document 事件

#### Scenario: benchmark 任务完成后保存 planning 摘要

- **GIVEN** MyAgentRunner 运行任务时产生 planning state
- **WHEN** 写入 result artifact
- **THEN** result SHALL 包含最终 planning summary
