## Why

当前 agent 只能通过普通 assistant 文本表达计划。对于 coding agent，用户和调试工具需要知道 agent 当前拆成了哪些步骤、每步状态是什么、是否跳过了验证、最终失败卡在哪一步。

结构化 planning state 是 plan mode、TUI、Web 调试、trace 分析和 benchmark failure diagnosis 的共同基础。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 planning 数据模型，表达 plan items、状态、顺序和可选说明。
- AgentLoop SHALL 能接收 planning 事件或通过规划管理器更新状态。
- CLI/Web/trace SHALL 能观察 planning state 变化。
- planning state SHALL 不替代自然语言回复；它是可机器读取的运行状态。

## Capabilities

### New Capabilities

- `planning`: 结构化 todo / plan 状态机。

### Modified Capabilities

- `agent-runtime`: 运行循环可发出 planning state 事件。
- `web-ui`: Web Chat/Debug 可展示 planning state。
- `benchmark`: trace/result 可记录 planning state。

## Impact

- 影响代码：
  - `agent/planning/`
  - `agent/loop.py`
  - `agent/trace_recorder.py`
  - `web/`
  - `benchmarks/`
- 影响测试：
  - `tests/agent/planning/`
  - `tests/agent/test_loop.py`
  - `tests/web_tests/`
  - `tests/benchmark/`
- 不实现 plan mode 的只读执行策略；该能力由 `add-plan-mode` 处理。
