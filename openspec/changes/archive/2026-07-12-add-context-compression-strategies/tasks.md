## 1. 规格

- [ ] 1.1 修改 `memory-context` spec delta，定义多策略压缩和硬预算。
- [ ] 1.2 修改 `coding-tools` spec delta，定义 `compact_context` 工具。
- [ ] 1.3 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.4 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认压缩触发、工具调用链保留和预算策略。
- [ ] 1.5 开发前补实 `## Reference Implementation Research`。

## 2. 测试

- [ ] 2.1 新增 LLM、truncation、sliding window summarizer 测试。
- [ ] 2.2 新增 tool call/result 配对合法性测试。
- [ ] 2.3 新增无 LLM 降级和硬预算测试。
- [ ] 2.4 新增 `compact_context` 工具测试。

## 3. 实现

- [ ] 3.1 新增 Summarizer 抽象和三类策略。
- [ ] 3.2 改造 `MemoryManager.compact()` 使用策略接口。
- [ ] 3.3 增加 `compact_context` 内置工具。
- [ ] 3.4 记录压缩 report 和 trace metadata。

## 4. 验证

- [ ] 4.1 运行 memory/context 和 tool 相关测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行项目 OpenSpec artifact checker。
- [ ] 4.5 跑通长上下文 benchmark smoke。

## 5. PR 收尾

- [ ] 5.1 PR 发起前归档本 change。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change。
- [ ] 5.3 确认 Impact Analysis 和 Reference Implementation Research 已更新为最终结论。
