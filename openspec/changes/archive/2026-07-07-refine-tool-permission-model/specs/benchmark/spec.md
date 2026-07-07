## ADDED Requirements

### Requirement: Benchmark runs SHALL fail closed for approval-required tools

Benchmark run 是无人值守运行，SHALL NOT 阻塞等待用户审批。当 benchmark task 触发被判定为 `require_approval` 的工具时，runtime SHALL fail closed，并记录 approval-unavailable 结果。

#### Scenario: benchmark 工具调用需要审批

- **GIVEN** 一个 benchmark run 正在执行
- **AND** 模型调用的工具被判定为 `require_approval`
- **WHEN** AgentLoop 请求审批
- **THEN** benchmark runtime SHALL 返回 approval unavailable
- **AND** 工具 SHALL NOT 执行
- **AND** benchmark result SHALL 记录被阻止的工具调用
