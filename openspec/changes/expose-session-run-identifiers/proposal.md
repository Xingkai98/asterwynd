## Why

排查 Agent 运行问题时，需要从 Web UI、CLI 输出、日志、trace 和 benchmark artifact 之间建立关联。当前 Web session 有 session id，但展示和日志关联不够统一；CLI 单次运行也缺少清晰 run id。

## Change Type

- primary: feature
- secondary: []

## What Changes

- Web UI 显示当前 session id。
- CLI 显示当前 run id 或 session id。
- 未来 TUI 复用同一 session id / run id 模型。
- 日志、trace 和 benchmark artifact 写入 session id / run id，便于排查。

## Capabilities

### Modified Capabilities

- `agent-runtime`: 定义运行标识和事件关联。
- `web-ui`: 展示 session id。
- `cli`: 展示 run id。
- `tui`: 未来 TUI 复用标识。
- `benchmark`: artifact 记录 agent run id。

## Impact

- 影响代码：
  - `agent/`
  - `cli.py`
  - `web/`
  - `benchmarks/`
- 影响测试：
  - CLI/Web/session/trace/benchmark 测试。
- 后续需要统一术语：交互式会话为 session id，一次 Agent 运行为 run id；不引入独立 correlation id。
