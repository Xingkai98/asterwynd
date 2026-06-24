## Why

用户经常需要 agent 先理解仓库、拆方案、评估风险，再决定是否进入开发。当前系统没有“只计划、不修改”的运行模式，容易把需求澄清和实际编辑混在一次运行里。

`plan mode` 应基于已存在的 agent mode policy 和 structured planning state，实现可验证的只读计划产物。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 `plan` mode 的实际行为。
- plan mode SHALL 只暴露只读工具，不允许 Write/Edit/Bash dangerous 操作。
- AgentLoop 在 plan mode 中 SHALL 产出人读的 Markdown Plan Document、结构化 planning state 和自然语言计划说明。
- CLI/Web SHALL 能启动 plan mode。

## Capabilities

### Modified Capabilities

- `agent-modes`: `plan` 从预留边界升级为可执行 mode。
- `agent-runtime`: AgentLoop 发出 Plan Document 事件并写入 trace。
- `planning`: plan mode 使用 Plan Document，并将高层步骤同步到结构化 planning state。
- `tool-system`: 支持 mode-specific 工具元数据，用于只在 plan mode 暴露 `UpdatePlan` / `ExitPlanMode`。
- `cli`: 支持启动 plan mode。
- `web-ui`: 支持 session 使用 plan mode。
- `benchmark`: trace artifact 记录 Plan Document 事件。

## Dependencies

- 依赖 `introduce-agent-mode-policy`。
- 依赖 `implement-structured-planning-state`。

## Impact

- 影响代码：
  - `agent/`
  - `cli.py`
  - `web/`
- 影响测试：
  - `tests/agent/`
  - `tests/web_tests/`
- 不处理 bypass 授权，不处理 TUI。
