## ADDED Requirements

### Requirement: 对标能力项应链接验证证据

当 reference-agent parity artifact 中的能力项涉及可运行的 coding-agent 行为时，项目 SHALL 为该能力项链接测试、benchmark、trace 或运行证据。

#### Scenario: 运行时能力标记为已支持

- **GIVEN** 一个对标能力项涉及 AgentLoop、工具协议、coding tools、workspace safety、memory/context、subagents、CLI/Web/TUI 或 benchmark 行为
- **WHEN** 该能力项被标记为 `supported` 或 `equivalent`
- **THEN** 条目 SHALL 链接到对应测试、benchmark、trace 或手动 smoke 证据

#### Scenario: 缺口转化为 runtime change

- **GIVEN** 一个 `gap` 或重要 `partial` 能力项被拆分为后续 OpenSpec change
- **WHEN** 该 change 涉及 AgentLoop、工具协议、coding tools、workspace safety、benchmark runner 或其他 coding-agent 核心路径
- **THEN** 该 change 的任务 SHALL 包含相关测试
- **AND** 该 change SHALL 包含 benchmark smoke 验证项或记录明确的不适用原因
