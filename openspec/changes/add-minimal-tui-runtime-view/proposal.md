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

## Reference Implementation Research

- status: enabled
- reason: TUI 是成熟 coding agent 的核心交互面，应参考其他项目对实时运行视图、命令入口、工具调用展示和降级策略的处理。
- research questions:
  - Codex、Claude Code、opencode 等项目如何组织 TUI 命令、状态流和工具调用展示？
  - 非交互终端、窄屏和长任务输出如何降级？
  - TUI 是否复用既有 runtime event，还是引入独立 UI 状态模型？
- findings:
  - 本次仅为参考实现调研门禁的结构迁移，尚未完成本 change 的针对性横向调研。
  - 当前工作区 `.dev/reference-repos.txt` 存在，可用于开发前调研；真正开始实现前必须补充具体参考仓库发现。
- design impact:
  - 当前方案仍坚持复用 AgentLoop、tool events 和 planning state；实现前需要用参考实现调研确认事件粒度、渲染边界和降级策略。
