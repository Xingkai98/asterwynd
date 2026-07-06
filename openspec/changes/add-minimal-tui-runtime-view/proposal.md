## Why

CLI 单轮和 Web UI 已存在，但终端中缺少一个适合 coding-agent 长任务的实时视图。TUI 可以展示消息、工具调用、planning state 和测试结果，便于本地开发和面试演示。

本 change 只做最小 runtime view，不重新实现 AgentLoop 或规划协议。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 TUI 命令入口。
- TUI SHALL 复用 AgentLoop、tool events、planning state 和 session 语义。
- TUI SHALL 展示对话、工具调用进度、planning state 和最终测试/trace 摘要。
- TUI SHALL 不引入与 CLI/Web 不兼容的运行协议。

## Capabilities

### Modified Capabilities

- `tui`: 从预留能力域升级为最小可用终端运行视图。
- `planning`: TUI 展示现有 planning state。
- `agent-runtime`: TUI 消费现有运行事件。

## Dependencies

- 依赖 `implement-structured-planning-state`。
- 建议依赖 `introduce-agent-mode-policy`。

## Impact Analysis

- 影响代码：
  - `cli.py`
  - `tui/` 或 `agent/tui/`
  - 事件输出路径
- 影响测试：
  - TUI 渲染或快照测试
  - CLI 命令测试
- 不实现完整 IDE，不实现鼠标驱动编辑器。
