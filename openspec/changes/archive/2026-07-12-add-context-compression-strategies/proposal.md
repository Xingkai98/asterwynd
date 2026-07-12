## Why

当前 `MemoryManager.compact()` 只有 LLM 摘要一种主要策略；无 LLM 时会丢弃中间消息，且缺少滑动窗口、优先级保留和硬 token 上限。长任务中这会导致上下文不可控、工具链断裂或关键信息丢失。

本 change 引入可插拔上下文压缩策略，让系统在不同模型、预算和运行模式下都能有明确降级行为。

## Change Type

- primary: feature
- secondary: [refactor]

## What Changes

- 新增 Summarizer 抽象，支持 LLM 摘要、纯截断和滑动窗口策略。
- 压缩策略 SHALL 保留 system message、完整工具调用链、最近用户意图和关键运行状态。
- 压缩结果 SHALL 满足硬 token 预算；无法满足时返回明确错误或采用更强降级策略。
- 新增 `compact_context` 工具，让 agent 可以主动请求压缩当前上下文。
- 压缩过程 SHALL 记录策略、输入规模、输出规模和被丢弃范围。

## Capabilities

### Modified Capabilities

- `memory-context`: 会话内记忆支持多策略压缩和硬预算。
- `coding-tools`: 新增 agent 主动压缩上下文的工具能力。

## Dependencies

- 建议在 `add-context-builder-architecture` 后实现，以复用统一 token 预算和来源 metadata。

## Impact Analysis

- 影响代码：
  - `agent/memory/manager.py` 抽离压缩策略。
  - 新增 `agent/memory/summarizers/`。
  - 新增或扩展内置工具注册 `compact_context`。
- 影响测试：
  - 各 summarizer 策略单元测试。
  - 工具调用链完整性回归测试。
  - 无 LLM 降级和硬预算测试。
- 不影响：
  - 不改变持久记忆文件格式。
  - 不在本 change 中实现语义记忆召回。
  - 不把压缩摘要写入长期记忆，除非用户或后续 change 明确要求。

## Reference Implementation Research

- status: enabled
- reason: 长上下文压缩已有 SWE-agent、Aider 等参考实现，需借鉴其 summarizer 抽象、降级策略和工具链保留规则。
- research questions:
  - SWE-agent 如何封装不同 summarizer，并在预算不足时触发？
  - Aider 的轻量 ChatSummary 如何保留编辑和文件上下文？
  - tool call / tool result 的配对完整性如何在压缩中保证？
- findings:
  - `/tmp/research-to-propose.md` 已记录初步调研：SWE-agent 使用可插拔 Summarizer，Aider 使用轻量聊天摘要。
  - 开发前必须结合当前 Message 模型和 tool-call 协议补实具体迁移风险。
- design impact:
  - 本 proposal 要求策略抽象和硬预算，而不是只优化现有 LLM 摘要 prompt。
