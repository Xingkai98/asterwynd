## ADDED Requirements

### Requirement: benchmark artifact 记录 planning state

Benchmark trace SHALL 记录 planning state 事件，便于分析 agent 未完成任务时卡在哪个步骤。

#### Scenario: benchmark 任务包含 planning 事件

- **GIVEN** MyAgentRunner 运行任务时产生 planning state
- **WHEN** 写入 trace artifact
- **THEN** trace SHALL 包含 planning state 事件序列
