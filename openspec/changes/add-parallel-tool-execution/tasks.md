## 1. 规格

- [ ] 1.1 更新 `agent-runtime` spec delta：定义并行工具执行行为和分组策略。
- [ ] 1.2 更新 `tool-system` spec delta：定义 `parallelizable` 属性和可并行工具列表。
- [ ] 1.3 开发前使用 `grill-with-docs` 审视 `design.md`。
- [ ] 1.4 维护 `## Impact Analysis`。
- [ ] 1.5 维护 `## Reference Implementation Research`。

- [ ] 1.7 同步 spec delta 到 `openspec/specs/<capability>/spec.md`（当前规格）。

## 2. 测试

- [ ] 2.1 AgentLoop 单元测试：全部可并行工具在一组中并发执行。
- [ ] 2.2 AgentLoop 单元测试：混合串行+并行工具的分组执行。
- [ ] 2.3 AgentLoop 单元测试：并行组中一个工具失败不影响其他。
- [ ] 2.4 AgentLoop 单元测试：并行组中任一需要审批时退化串行。
- [ ] 2.5 AgentLoop 单元测试：结果顺序与原始 tool call 顺序一致。
- [ ] 2.6 AgentLoop 单元测试：两个 Write 工具在不同组中串行执行。
- [ ] 2.7 与 Change 1 retry 交互测试：并行组中独立重试。

## 3. 实现

- [ ] 3.1 在 `Tool` 基类新增 `parallelizable: bool = False`。
- [ ] 3.2 标记所有只读工具的 `parallelizable = True`。
- [ ] 3.3 实现 `AgentLoop._execute_tool_calls` 分组并行逻辑。
- [ ] 3.4 实现并行组审批退化策略。
- [ ] 3.5 TraceRecorder 新增 `parallel_execution` step 类型。
- [ ] 3.6 如果 TUI/Web 展示受影响，同步更新。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行 artifact checker。
- [ ] 4.5 跑通至少一个 benchmark smoke，验证并行执行不影响正确性。

## 5. PR 收尾

- [ ] 5.1 归档到 `openspec/changes/archive/YYYY-MM-DD-add-parallel-tool-execution/`。
- [ ] 5.2 从 backlog 移除。
- [ ] 5.3 确认 Impact Analysis 无残留未知项。
- [ ] 5.4 运行全量校验。
