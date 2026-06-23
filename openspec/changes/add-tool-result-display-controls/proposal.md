## Why

WebFetch 等工具可能返回很长内容。当前展示层容易把对话冲散，CLI 也缺少一致的折叠策略。需要定义跨 Web UI、CLI 和未来 TUI 的工具结果展示控制：默认折叠长结果，允许展开查看，同时 trace 保留完整内容。

## Change Type

- primary: feature
- secondary: []

## What Changes

- WebFetch 结果默认折叠展示，可展开查看。
- 长工具结果在 Web UI / CLI / TUI 中采用一致摘要和展开语义。
- trace 和 benchmark artifact 保留完整工具结果，不受展示折叠影响。

## Capabilities

### Modified Capabilities

- `web-ui`: 支持工具结果折叠/展开。
- `cli`: 定义长工具结果摘要显示。
- `tui`: 未来 TUI 复用相同 display policy。

## Impact

- 影响代码：
  - `web/static/`
  - `cli.py`
  - 未来 `tui/`
- 影响测试：
  - Web 展示测试
  - CLI 输出测试
- 后续需要确认折叠阈值和哪些工具默认折叠。
