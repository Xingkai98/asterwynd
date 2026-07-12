## 1. 规格

- [ ] 1.1 修改 `agent-runtime` spec delta，定义 ContextBuilder 和 ContextSource contract。
- [ ] 1.2 修改 `memory-context`、`skills`、`planning` spec delta，定义对应 ContextSource adapter。
- [ ] 1.3 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.4 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认 source priority、预算和 build report schema。
- [ ] 1.5 开发前补实 `## Reference Implementation Research`。

## 2. 测试

- [ ] 2.1 新增 ContextSource 排序和预算分配测试。
- [ ] 2.2 新增可裁剪/不可裁剪来源测试。
- [ ] 2.3 新增 AgentLoop message 构造回归测试。
- [ ] 2.4 新增 build report 和 trace metadata 测试。

## 3. 实现

- [ ] 3.1 新增 `agent/context/`。
- [ ] 3.2 将 `_messages_with_run_context()` 迁移到 ContextBuilder。
- [ ] 3.3 为 memory、skills、plan/todo 增加 source adapter。
- [ ] 3.4 输出 build report 并接入 trace。

## 4. 验证

- [ ] 4.1 运行 context、AgentLoop、memory、skills、planning 相关测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行项目 OpenSpec artifact checker。
- [ ] 4.5 跑通至少一个 AgentLoop benchmark smoke。

## 5. PR 收尾

- [ ] 5.1 PR 发起前归档本 change。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change。
- [ ] 5.3 确认 Impact Analysis 和 Reference Implementation Research 已更新为最终结论。
