## ADDED Requirements

### Requirement: 会话上下文支持多策略压缩

MemoryManager SHALL 支持可插拔 Summarizer 策略，包括 LLM 摘要、确定性截断和滑动窗口。

#### Scenario: LLM 不可用时压缩上下文

- **GIVEN** 当前 provider 不可用于摘要
- **WHEN** 系统需要压缩会话上下文
- **THEN** MemoryManager SHALL 使用确定性降级策略

### Requirement: 压缩结果满足硬 token 预算

上下文压缩 SHALL 生成不超过目标 token 预算的结果，或返回明确失败状态。

#### Scenario: 输入历史超过预算

- **GIVEN** 会话历史超过目标 token 预算
- **WHEN** 压缩策略执行成功
- **THEN** 输出上下文 SHALL 不超过目标预算

### Requirement: 压缩保持工具消息链合法

压缩策略 SHALL 保持 tool call 与 tool result 的配对合法性，不得产生违反 provider 协议的消息链。

#### Scenario: 历史中包含工具调用

- **GIVEN** 会话历史包含 tool call 和对应 tool result
- **WHEN** 压缩策略裁剪历史
- **THEN** 系统 SHALL 一起保留、摘要或移除配对消息
