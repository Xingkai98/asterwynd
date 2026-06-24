## Why

`introduce-agent-mode-policy` 先定义单次运行的 mode policy 和入口默认 mode，但实际使用中用户可能需要在一个长会话中实时调整权限。例如先用 `read_only` 或 `plan` 分析仓库，确认方案后立即切到 `build` 执行修改；或者在 Web UI / 未来 TUI 中根据用户选择立即收紧到只读模式。

如果每次切换都要求重建 session 或丢弃当前上下文，CLI、Web UI 和未来 TUI 的交互体验会变差；如果允许隐式修改但没有统一运行时语义，工具 schema、待执行 tool call、trace 和 UI 状态又会不一致。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 支持在运行时实时修改当前 session / run context 的 agent mode。
- mode 修改后 SHALL 立即影响后续工具 schema 暴露和工具执行权限。
- CLI、Web UI 和未来 TUI SHALL 共享同一套 mode transition 语义。
- mode transition SHALL 产生可观察事件，并记录到 trace / session history / UI 状态。
- 运行中已发出的 tool call、并发执行工具和待处理权限拒绝 SHALL 有明确处理规则。

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `agent-modes`: 支持运行时实时切换 mode。
- `agent-runtime`: AgentLoop / session runtime 需要支持 mode 状态更新和事件发布。
- `tool-system`: 工具 schema 暴露和执行权限需要读取最新 mode。
- `cli`: CLI 交互模式需要支持用户触发 mode 切换。
- `web-ui`: Web session 和前端状态需要支持实时 mode 切换。
- `tui`: 未来 TUI 需要复用同一 mode transition 语义。
- `benchmark`: benchmark 默认仍使用固定 mode，除非任务显式测试 mode transition。

## Impact

- 影响代码：
  - `agent/`
  - `agent/tools/`
  - `cli.py`
  - `web/`
  - 未来 `tui/`
- 影响测试：
  - `tests/agent/`
  - `tests/test_cli.py`
  - `tests/web_tests/`
  - 未来 TUI 测试
- 依赖：
  - 需要先完成 `introduce-agent-mode-policy` 的基础 mode policy。
