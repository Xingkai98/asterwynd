## Why

当前 `AgentLoop._execute_tool_calls()` 在单次迭代内串行执行所有 tool call。当 agent 在同一轮发出多个独立的只读工具调用（例如 Read + Grep + Find），它们应该可以并行执行以缩短迭代耗时。

Claude Code 的 AgentLoop 支持并行执行独立工具调用（例如同时读多个文件），Codex 和 Aider 同理。这直接减少 agent 完成任务的总轮次和耗时，对 benchmark `max_iterations` 失败类有直接改善。

## What Changes

- `AgentLoop._execute_tool_calls()` 改为：识别可并行工具 → `asyncio.gather` 并发执行 → 不可并行工具串行执行 → 结果按原始顺序返回。
- `Tool` 基类新增 `parallelizable: bool` 属性（默认 `False`），只读工具（Read/Write?No, Read/Grep/Find/ListFiles/Lsp*/WebFetch/WebSearch/RepoMap/SymbolSearch）标记为 `True`。
- 写工具（Write/Edit/Bash）和状态工具（UpdatePlan/ExitPlanMode/TodoWrite/subagent tools）保持串行。
- TraceRecorder 记录每个并行执行段的开始和结束，保持调用顺序语义。

不被认为是一个 breaking change——工具执行的结果语义不变，仅执行时序变化。

## Capabilities

### Modified Capabilities

- `agent-runtime`: `AgentLoop` 工具执行路径从串行改为可并行。
- `tool-system`: `Tool` 基类新增 `parallelizable` 声明。

## Impact

- 影响代码：
  - `agent/loop.py`（核心改动）
  - `agent/tools/base.py`（`parallelizable` 属性）
  - `agent/tools/builtin/*.py`（各工具标记）
  - `agent/trace_recorder.py`
- 影响测试：
  - `tests/agent/test_loop.py`
  - `tests/agent/tools/test_*`
- 不影响：LLM provider 协议、workspace safety、benchmark runner、MCP 集成、审批链路。

## Change Type

- primary: feature
- secondary: refactor
