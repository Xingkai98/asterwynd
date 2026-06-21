## Why

`docs/architecture.md`、`README.md` 和 `docs/benchmark-plan.md` 中仍有旧口径：

- 把 memory compact 事件描述为 DebugHook 直接捕获。
- 把 benchmark artifact 描述为每个任务总会写入 `final.diff` 和 `test_output.txt`。

当前 OpenSpec 和实现已经更细：

- DebugHook 捕获 AgentLoop hook 生命周期事件；Web 运行事件中的 `memory_compaction` 由 AgentLoop 通过 `on_event` 发给 Web session。
- `result.json`、`trace.json`、`runner.log` 是核心 artifact；`final.diff` 只有 agent 运行并完成 diff capture 后写入，`test_output.txt` 只有验证命令实际执行后写入。

## What Changes

- 修正架构文档中的 DebugHook 事件来源描述。
- 修正 README benchmark 流程中的 artifact 描述。
- 修正 benchmark plan 中 artifact 按阶段生成的描述。
- 更新 audit 文档，标记 P2 文档口径对齐已完成。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- 无。本文档 change 不改变业务实现和 OpenSpec specs。

## Impact

- 影响文档：
  - `docs/architecture.md`
  - `README.md`
  - `docs/benchmark-plan.md`
  - `docs/audits/spec-implementation-gaps.md`
- 不影响代码、测试和 benchmark runner 行为。
