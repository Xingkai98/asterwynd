## ADDED Requirements

### Requirement: benchmark 记录 agent mode

Benchmark runner SHALL 支持 `build`、`read_only` 或 `plan` agent mode，默认使用 `build`，记录每次任务运行使用的 agent mode，并把 mode 传入对应 agent runner。Benchmark SHALL 接受 `read_only` 和 `read-only` 两种用户输入，并在内部规范化为 `read_only`。Benchmark 用户入口 SHALL NOT 接受 `bypass` mode。

#### Scenario: benchmark 使用 build mode

- **GIVEN** benchmark 默认运行 coding-agent 任务
- **WHEN** 创建 MyAgentRunner
- **THEN** runner SHALL 使用 `build` mode
- **AND** result 或 trace SHALL 记录该 mode

#### Scenario: benchmark artifact 记录 mode

- **GIVEN** benchmark 运行任一任务
- **WHEN** 写入 run.json、result.json 和 trace.json
- **THEN** artifact SHALL 记录该运行实际使用的 mode
