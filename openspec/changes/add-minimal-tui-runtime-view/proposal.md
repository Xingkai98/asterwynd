## Why

CLI 单轮和 Web UI 已存在，但终端中缺少一个适合 coding-agent 长任务的多轮实时视图。TUI 可以在不打开浏览器的情况下承载持续对话、工具调用、planning state 和测试结果，便于本地开发和面试演示。

本 change 只做最小多轮 TUI runtime view，不重新实现 AgentLoop 或规划协议。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 TUI 命令入口，启动基本多轮终端对话界面。
- TUI SHALL 复用 AgentLoop、tool events、planning state 和 session 语义。
- TUI SHALL 像 Web UI 一样展示 slash command 提示，并复用同一 slash command registry/catalog。
- TUI SHALL 展示对话、工具调用进度、planning state 和最终测试/trace 摘要。
- TUI SHALL 不引入与 CLI/Web 不兼容的运行协议。

## Capabilities

### Modified Capabilities

- `tui`: 从预留能力域升级为最小可用终端运行视图。
- `planning`: TUI 展示现有 planning state。
- `agent-runtime`: TUI 消费现有运行事件。
- `dev-workflow-state-machine`: 明确 `.handoff/` 是本地交接材料，默认不作为 PR artifact 提交。

## Dependencies

- 依赖 `implement-structured-planning-state`。
- 建议依赖 `introduce-agent-mode-policy`。

## Impact Analysis

- 影响代码：
  - `cli.py`
  - `agent/tui/`：Textual app、事件 reducer、session/controller。
  - Agent 构造路径：复用现有 `build_agent_async` / `build_agent` 和 `on_event` 回调。
  - Slash command：复用 `agent.commands.SlashCommandRegistry` 和技能注册到命令 catalog 的机制。
  - 依赖：新增 Python TUI 框架 `textual`。
- 影响测试：
  - TUI 状态 reducer / controller 测试
  - Textual app 轻量 smoke 或非交互降级测试
  - CLI 命令测试
- 影响文档：
  - `docs/development-guide.md` 记录 TUI 启动命令。
  - `docs/testing-guide.md` 记录 TUI 回归测试策略。
  - `docs/architecture.md` 记录 TUI 复用 AgentLoop 事件语义。
  - `AGENTS.md` 和 `docs/requirements-process.md` 明确 `.handoff/` 默认不提交，长期结论沉淀到 OpenSpec / `handoff.json` / review report。
- 不实现完整 IDE、不实现复杂鼠标工作台交互、不实现会话恢复、不实现复杂命令面板。

## Reference Implementation Research

- status: enabled
- reason: TUI 是成熟 coding agent 的核心交互面，应参考其他项目对实时运行视图、命令入口、工具调用展示和降级策略的处理。
- research questions:
  - Codex、Claude Code、opencode 等项目如何组织 TUI 命令、状态流和工具调用展示？
  - 非交互终端、窄屏和长任务输出如何降级？
  - TUI 是否复用既有 runtime event，还是引入独立 UI 状态模型？
- findings:
  - Codex 的 `codex-rs/tui` 是独立 Rust TUI crate，底层使用 `ratatui`、`crossterm` 和 terminal capability 检测；TUI 被作为产品级交互面维护，而不是 CLI 输出的简单包装。
  - opencode 拥有独立 `packages/tui`，基于 `@opentui/core` / `@opentui/solid`，按 app / route / component / plugin 拆分，说明复杂 TUI 倾向使用框架化 UI 子系统。
  - Claude Code 和 Gemini CLI 走 React/Ink 风格终端 UI；它们都将终端交互建模为组件状态，而不是裸日志流。
  - aider 更偏增强 CLI/REPL，使用 `prompt_toolkit` 和 `rich`，适合输入补全和 Markdown 输出，但不是多面板 TUI 工作台。
  - 对 Asterwynd 当前 Python 技术栈，`textual` 比 `curses` 更适合基本多轮 TUI：它提供输入框、滚动 transcript、异步任务、键盘绑定和组件布局；同时比自建 curses UI 更接近参考实现的“框架化终端 app”路线。
- design impact:
  - 首版 TUI 采用 `textual`，但只在 `agent/tui/` UI 层使用；AgentLoop、ToolRegistry、planning state 和工具协议不得依赖 Textual。
  - TUI app 通过一个事件 reducer 消费现有 `on_event(event_type, data)`，不从 message history 反推运行状态，也不定义第二套 runtime protocol。
  - 首版范围从单轮 runtime view 调整为基本多轮 TUI 会话；不做会话恢复、复杂鼠标工作台交互、完整命令面板或复杂 diff viewer。
  - TUI 的 slash command 提示应复用现有命令 catalog；当输入以 `/` 开头时按当前前缀过滤命令和 skill command，并支持键盘选择后填充 `insert_text`。
