## 1. 规格

- [x] 1.1 修改 memory-context 规格，定义有 LLM / 无 LLM 的 compact 行为。
- [x] 1.2 明确摘要消息 role、位置和降级语义。
- [x] 1.3 明确 tool-call 链保留要求。

## 2. 回归测试

- [x] 2.1 新增有 LLM 且超过预算时生成 summary message 的测试。
- [x] 2.2 新增无 LLM 时仍裁剪降级的测试。
- [x] 2.3 新增近期 tool result 依赖更早 assistant tool call 时链路保持合法的测试。
- [x] 2.4 新增 AgentLoop 只在实际压缩时发送 memory_compaction 事件的测试。

## 3. 实现

- [x] 3.1 将 MemoryManager compact 路径改为 async。
- [x] 3.2 实现 LLM summary prompt 和 summary message 插入。
- [x] 3.3 实现 LLM 失败 / 空摘要的裁剪降级。
- [x] 3.4 更新 AgentLoop 调用和事件发送逻辑。

## 4. 验证

- [x] 4.1 运行 memory / loop 相关测试。
- [x] 4.2 运行全量测试。
- [x] 4.3 运行 OpenSpec strict validate。
- [x] 4.4 跑通至少一个 benchmark smoke。
