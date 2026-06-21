## 背景

`LLM.chat()` 是 async 接口，而当前 `MemoryManager.compact_if_needed()` / `compact()` 是同步方法。要真正调用 LLM 生成摘要，需要把 compact 路径改为 async，并同步调整 AgentLoop 调用点。

## 设计决策

### 1. compact 路径改为 async

`compact_if_needed(messages=None)` 和 `compact(messages=None)` 改为 async 方法。调用者需要 `await`。

原因：

- 现有 LLM provider 协议就是 async。
- 不引入新的同步 LLM 适配层，避免在已有事件循环内阻塞或嵌套运行事件循环。

### 2. 返回是否实际压缩

`compact_if_needed()` 返回 `bool`：

- `False`: 未超过 token 上限，消息列表不变。
- `True`: 已触发 compact，可能是摘要压缩，也可能是无 LLM / LLM 失败后的裁剪降级。

AgentLoop 只在返回 `True` 时发出 `memory_compaction` 事件，避免把每一轮工具调用都误报为压缩。

### 3. 摘要消息格式

摘要消息使用：

- `role="system"`
- 内容前缀：`Previous conversation summary:\n`
- 位置：所有原始 system 消息之后、近期上下文之前
- 内容来源：只总结将被移出近期窗口的非 system 消息

摘要提示会把待压缩消息序列化为简洁文本，要求保留用户目标、约束、关键决策、工具结果和未完成事项。

### 4. 降级行为

以下情况使用裁剪降级：

- `llm is None`
- 待压缩中间消息为空
- LLM 调用异常
- LLM 返回空摘要

降级时保留所有原始 system 消息和合法的近期上下文窗口。

### 5. tool-call 链保留

近期窗口通过 `_recent_with_tool_chains()` 计算。若窗口内存在 tool result，且对应 assistant tool call 位于窗口之前，则窗口起点扩展到该 assistant 消息，确保发送给 provider 的消息链合法。

摘要只覆盖被移出窗口的中间消息，不替代仍需保留的 assistant tool call / tool result 链。

## 非目标

- 不改变消息 token 估算策略。
- 不引入多轮或分块摘要。
- 不改 Web debug hook 协议。
- 不处理持久化 memory 或跨会话 memory。
