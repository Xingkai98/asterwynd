## Why

当前 MyAgent 已有 CLI 单轮、交互、Web 和 benchmark 入口，但没有显式 agent mode。只读分析、实际构建、计划生成和高权限 bypass 的边界仍然散落在 prompt、工具注册和运行入口里。

后续 `plan mode`、TUI、subagent 和外部工具接入都需要统一的 mode 语义。如果不先定义 mode policy，后续功能会各自决定哪些工具可用、是否允许写文件、是否允许执行命令，导致行为难以解释和测试。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 `AgentMode` 概念，至少覆盖 `read_only`、`build`、`plan` 和 `bypass` 的语义边界。
- ToolRegistry 或构造工具集合时 SHALL 根据 mode 过滤或拒绝不允许的工具。
- CLI、Web session 和 benchmark runner SHALL 能传入 mode，并记录实际使用的 mode。
- `read_only` SHALL 禁止写工具和 dangerous 工具。
- `build` SHALL 保持当前 coding-agent 能力，允许受 WorkspacePolicy 约束的编辑和验证命令。
- `plan` 和 `bypass` 在本 change 中只定义边界；具体 plan 行为和 bypass 授权流程可由后续 change 实现。

## Capabilities

### New Capabilities

- `agent-modes`: 显式运行模式和工具权限策略。

### Modified Capabilities

- `tool-system`: 工具暴露和执行需要受 mode policy 约束。
- `cli`: CLI 构造 AgentLoop 时可选择 mode。
- `web-ui`: Web session 构造 AgentLoop 时可携带 mode。
- `benchmark`: benchmark 记录和 runner 构造时可携带 mode。

## Impact

- 影响代码：
  - `agent/`
  - `agent/tools/`
  - `cli.py`
  - `web/session.py`
  - `benchmarks/`
- 影响测试：
  - `tests/agent/`
  - `tests/web_tests/`
  - `tests/benchmark/`
- 不实现结构化 planning state，不实现 plan mode 的计划产物，也不实现 bypass 授权流程。
