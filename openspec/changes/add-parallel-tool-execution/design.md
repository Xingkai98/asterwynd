## Context

`AgentLoop._execute_tool_calls()` 当前实现（`agent/loop.py:284-340`）对每个 tool call 逐个 await，即使多个 call 之间完全独立。在 coding-agent 场景中，agent 经常在第一步发出多个只读探索调用（读多个文件、搜索代码、检查目录），这些调用之间没有数据依赖，并行执行可显著加速。

## Decisions

### 1. 可并行工具识别

`Tool` 基类新增 `parallelizable: bool = False`。

只读且无副作用的工具标记为 `True`：
- `Read`, `Grep`, `Find`, `ListFiles`
- `LspDefinition`, `LspReferences`, `LspHover`, `LspDocumentSymbols`, `LspWorkspaceSymbols`, `LspDiagnostics`
- `WebFetch`, `WebSearch`
- `RepoMap`, `SymbolSearch`
- `InspectGitDiff`

以下工具保持 `False`：
- `Write`, `Edit` — 文件写操作，两个并发写可能冲突
- `Bash` — 命令可能有文件副作用
- `UpdatePlan`, `ExitPlanMode`, `TodoWrite` — 改变 agent state
- 所有 subagent 工具 — 启动子 agent 有副作用
- `ActivateSkill` — 状态变更

### 2. 执行策略：分组并行

```python
async def _execute_tool_calls(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
    groups = self._group_by_parallelizable(tool_calls)
    results = []
    for group in groups:
        if group[0].parallelizable:
            group_results = await asyncio.gather(*[self._execute_one(tc) for tc in group])
        else:
            group_results = [await self._execute_one(tc) for tc in group]
        results.extend(group_results)
    return results
```

分组逻辑：连续的可并行 call 归入一组（从第一个可并行 call 开始到最后一个连续的可并行 call 结束），可并行组前面的串行 call 自成一组，可并行组后面的串行 call 自成一组。

例如：`[Bash, Read, Read, Grep, Write, Read]` → 分组为 `[[Bash], [Read, Read, Grep], [Write], [Read]]`。

### 3. 结果顺序保持

无论执行顺序如何，最终 tool result 列表必须与原始 tool call 顺序一致。TraceRecorder 在每个并行段开始时记录 `parallel_execution_start` step，段结束时记录每个 call 的 `tool_result` step。

### 4. 错误隔离

并行组内某个 tool call 失败不影响其他 call 继续执行。`asyncio.gather(return_exceptions=True)` 确保一个超时不拖慢整个组。

### 5. 与审批系统的交互

并行组中如果任意 tool call 需要审批，整组分两种策略：
- **简单策略（先采用）**：并行组中任一需要审批时，退化为串行逐一通过审批 gate。
- **优化策略（后续）**：一次审批列出组内所有 tool call，用户一次性批准/拒绝整个组。

考虑到并行组通常只包含只读工具（low risk, auto-approve），大部分情况不触发审批。先采用简单策略。

### 6. 与错误重试的交互

并行组中的工具独立重试。如果组内两个 call 都因瞬时错误失败，各自独立走 Change 1 的 retry 路径。

## Goals / Non-Goals

- 不改变 LLM 调用层面的并发（仍然是单次 LLM 调用 → 多 tool call → 执行 → 下一次 LLM 调用）。
- 不引入跨迭代的并行（不同 iteration 仍然串行）。
- 不支持工具间的依赖声明或编排。
- 不支持 Bash 命令的并行执行。

## Reference Implementation Research

- status: enabled
- reason: 与主流 coding agent 对比后识别的基础能力差距，需调研行业参考实现以指导设计方案。

- research questions:

1. Claude Code 如何实现并行工具执行？
2. Codex 的工具执行模型是怎样的？
3. 并行执行是否需要工具级声明，还是全部自动并行？

- findings:

- Claude Code 的 AgentLoop 在一次迭代内对独立的 Read/Grep/Glob 调用做并行执行。工具协议中没有显式的 "parallelizable" 标记，而是基于工具能力判断：READ 类操作可并行，WRITE 类不可。
- Codex 模型本身在单个响应中发出多个 tool call 时，runtime 对只读做并行。
- Aider 不使用并行 tool calls，其 edit format 是序列化的。

- design impact:

- 选择显式 `parallelizable` 标记而非自动推断，避免向模型暴露不必要的实现细节，同时给未来扩展保留空间。
- 分组并行策略（连续只读合并为一组）是最简单且安全的方式。

## Impact Analysis

| 影响面 | 状态 |
|--------|------|
| AgentLoop 工具执行路径 | 核心改动，需充分测试 |
| Tool 基类 | 新增属性，向后兼容 |
| TraceRecorder | 新增并行段 step 类型 |
| 审批链路 | 并行组退化策略 |
| 错误重试（Change 1） | 并行组中独立重试 |
| Benchmark | 可能导致相同任务耗时变短、轮次减少 |
| MCP 工具 | MCP 工具默认 `parallelizable=False` |
| TUI/Web | 并行执行展示可能需要调整 |


## Risks / Trade-offs

- [Risk] 并行 Read + 串行 Write 的分组逻辑在复杂 tool call 序列下可能产生意外顺序。Mitigation: 充分测试混合分组，TUI trace 面板清楚展示分组边界。
- [Risk] LLM 不知道工具是并行执行的，可能发出有隐式数据依赖的调用。Mitigation: 文档说明模型不应依赖执行时序，所有只读工具语义上独立。
- [Risk] 并行组审批退化可能让用户体验不一致。Mitigation: 大部分并行组是只读工具（auto-approve），退化实际很少触发。

## Testing Strategy

- 分组逻辑单元测试：全并行、混合分组、连续可并行+串行。
- AgentLoop 集成测试：并行组错误隔离、结果顺序保持、审批退化。
- 只读工具标记测试：Read/Grep/Find 等标记为 parallelizable。
- 写工具标记测试：Write/Edit/Bash 不标记为 parallelizable。
- 与 retry 交互测试：并行组内独立重试。
## Pre-Implementation Review

待 `grill-with-docs` 执行后填写。
