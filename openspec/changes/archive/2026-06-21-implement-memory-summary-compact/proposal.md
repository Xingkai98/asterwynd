## Why

当前 `MemoryManager.compact()` 只保留 system 消息和近期消息窗口。即使构造时传入了 `llm`，也不会调用 LLM 生成摘要，导致 AutoCompact 在长任务中直接丢失中间上下文。

这与 memory-context 能力域中的“上下文压缩”预期不一致。对于 Coding Agent，长任务中的问题定位、用户约束、已尝试方案和验证结果往往位于近期窗口之前，直接裁剪会降低后续决策质量。

## What Changes

- `MemoryManager` 在超过 token 上限且配置了 LLM 时 SHALL 使用 LLM 为被压缩的中间消息生成摘要。
- 摘要 SHALL 以 system 消息插入在原始 system 消息之后、近期上下文之前。
- 未配置 LLM 或摘要生成失败时，`MemoryManager` SHALL 保持现有降级行为：保留 system 消息和合法的近期上下文窗口。
- compact SHALL 保持 provider 可接受的 tool-call 链；如果近期 tool result 依赖窗口外 assistant tool call，必须连同 assistant tool call 一起保留。
- `compact_if_needed` / `compact` SHALL 支持异步调用，以便使用现有 async LLM provider 接口。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `memory-context`: AutoCompact 从纯裁剪升级为“有 LLM 时摘要压缩、无 LLM 时裁剪降级”。

## Impact

- 影响代码：
  - `agent/memory/manager.py`
  - `agent/loop.py`
- 影响测试：
  - `tests/agent/memory/test_memory.py`
  - `tests/agent/test_loop.py`
- 不处理 DebugHook 事件来源、benchmark artifact 文档和 InspectGitDiff 重构问题。
