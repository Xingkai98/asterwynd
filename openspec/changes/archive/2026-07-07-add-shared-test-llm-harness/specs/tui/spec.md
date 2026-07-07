## ADDED Requirements

### Requirement: 未来 TUI 回归复用共享测试 LLM harness

未来 TUI 实现 SHALL 使用共享测试 LLM harness 做入口 smoke，覆盖 TUI 输入、AgentLoop runtime event 消费和屏幕状态展示。TUI SHALL NOT 定义与 CLI/Web 不兼容的 fake runtime。

#### Scenario: TUI fake LLM smoke

- **GIVEN** 未来 TUI 已实现
- **WHEN** TUI 测试注入共享 fake LLM harness 并发送用户输入
- **THEN** TUI SHALL 通过真实 AgentLoop 运行
- **AND** 屏幕状态 SHALL 展示 fake assistant 回复、session id 和 run id

#### Scenario: TUI 不使用私有 fake runtime

- **GIVEN** TUI change 准备进入实现
- **WHEN** 设计测试策略
- **THEN** 测试 SHALL 复用共享 fake LLM harness
- **AND** 不得用只服务于 TUI 的私有 fake AgentLoop 替代入口 smoke
