## ADDED Requirements

### Requirement: CLI 入口回归复用共享测试 LLM harness

CLI 测试 SHALL 覆盖通过真实 `build_agent` 和 AgentLoop 执行的 fake LLM runtime smoke。已有 adapter 级 `FakeAgent` 测试 MAY 保留，但不得作为 CLI 入口逻辑的唯一回归形态。

#### Scenario: CLI 单轮 fake LLM smoke

- **GIVEN** CLI 测试注入共享 fake LLM harness
- **WHEN** 执行 CLI 单轮 prompt
- **THEN** CLI SHALL 通过真实 `build_agent` 构造 AgentLoop
- **AND** 输出 fake LLM 返回的 assistant 内容
- **AND** 测试 SHALL 能断言 fake LLM 收到的用户消息

#### Scenario: CLI streaming fake LLM smoke

- **GIVEN** fake LLM 脚本返回 streaming delta 和 streamed completion
- **WHEN** CLI 执行单轮 prompt
- **THEN** CLI SHALL 实时输出 delta
- **AND** SHALL NOT 重复打印最终完整文本

#### Scenario: CLI control command 不触发 LLM

- **GIVEN** CLI 交互模式使用共享 fake LLM harness
- **WHEN** 用户输入 `/status`、`/clear` 或未知独立 slash command
- **THEN** CLI SHALL 按控制面输入处理该命令
- **AND** fake LLM 调用次数 SHALL 保持不变
