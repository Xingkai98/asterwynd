## ADDED Requirements

### Requirement: benchmark 记录 agent mode

Benchmark runner SHALL 支持 `build`、`read_only` 或 `plan` agent mode，默认使用 `build`，记录每次任务运行使用的 agent mode，并把 mode 传入对应 agent runner。Benchmark 用户入口 SHALL NOT 接受 `bypass` mode。

#### Scenario: benchmark 使用 build mode

- **GIVEN** benchmark 默认运行 coding-agent 任务
- **WHEN** 创建 MyAgentRunner
- **THEN** runner SHALL 使用 `build` mode
- **AND** result 或 trace SHALL 记录该 mode
