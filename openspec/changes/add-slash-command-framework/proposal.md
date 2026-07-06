## Why

CLI 交互模式目前只有内联解析的 `/mode`，`exit/quit/q` 也只是特殊字符串判断。随着后续需要补齐 `/clear`、`/compact`、`/status`、`/skills`、TUI 命令面板和 Web 命令入口，如果继续在各入口里散写字符串判断，会出现以下问题：

- 命令帮助、参数校验、错误提示和测试分散，新增命令容易行为不一致。
- MemoryManager 已有 `clear()`、`compact()` 能力，但用户没有明确交互命令入口。
- `compact`、`clear` 等上下文操作会影响会话历史，必须有统一的行为定义和验证。
- 后续 skills runtime 需要 `/skills`、`/skills reload` 等命令，应该复用同一个 command registry，而不是单独解析。

本 change 目标是先建立最小 slash command 框架，并补齐 coding agent 基本上下文命令。

## Change Type

- primary: feature
- secondary: [refactor]

## What Changes

- 新增交互式 slash command registry，统一声明命令名、别名、帮助文本、参数解析、执行结果和是否继续会话。
- CLI 交互模式 SHALL 通过 command registry 处理 slash commands，不再只内联识别 `/mode`。
- 首批内置命令：
  - `/help`：列出可用命令及简短说明。
  - `/exit`、`/quit`：退出交互会话；保留裸 `exit`、`quit`、`q` 兼容。
  - `/status`：展示 session id、当前 mode、模型、provider，以及可用时的 token/message 摘要。
  - `/mode <build|read_only|plan>`：复用现有 mode transition 语义，继续拒绝 `bypass`。
  - `/clear`：清空当前交互会话中的非 system 消息，保留 system prompt 和必要运行上下文。
  - `/compact`：主动触发 MemoryManager compact，并输出是否压缩、压缩前后摘要或可读原因。
- 本 change 不实现 `/skills`；`/skills` 由后续 `integrate-skill-runtime` 接入同一 command registry。

## Capabilities

### Modified Capabilities

- `cli`: CLI 交互模式新增统一 slash command 框架和首批内置命令。
- `memory-context`: 明确定义用户手动触发 clear/compact 的上下文行为。

## Impact Analysis

- 影响代码：
  - `cli.py`
  - 可能新增 `agent/commands/` 或等价 command registry 模块。
  - `agent/memory/manager.py` 可能需要补充可报告的 clear/compact 结果。
- 影响测试：
  - `tests/test_cli.py`
  - 新增 command registry 单元测试。
  - MemoryManager clear/compact 入口测试。
- 影响文档：
  - `openspec/specs/cli/spec.md`
  - `openspec/specs/memory-context/spec.md`
  - `docs/development-guide.md`
  - `docs/testing-guide.md`
- 不影响：
  - Web UI 命令输入。
  - TUI 命令面板。
  - skills 加载和匹配逻辑。
  - MCP、browser 和工具权限模型。

## Reference Implementation Research

- status: enabled
- reason: Slash command 和上下文命令是 coding agent 交互面的基础，应参考其他 agent 对命令注册、帮助、上下文压缩和退出/清空行为的处理。
- research questions:
  - 其他 coding-agent 是否将 slash command 列表集中声明，而不是散落在输入循环里？
  - `/compact`、`/clear`、`/status` 这类上下文命令应属于 CLI/TUI 操作面还是 AgentLoop 工具？
  - skills 相关命令是否应与 slash command 框架解耦？
- findings:
  - 当前环境没有可调用的 `codegraph` 命令，本次按流程降级使用 `rg` 和定点文件阅读。
  - 本地参考仓库中 Claude Code 在提示中暴露 `/help` 等 slash command，并有 compact 相关服务；Nanobot README 记录 `/status`、context compact 和 skills；OpenClaw 文档记录 `/model`、`/models` 等会话命令；Pi TUI changelog 多次提到 slash-command autocomplete 和命令菜单。
  - 这些参考实现支持把 slash command 作为独立交互层，而不是把每个命令硬编码在输入循环里。
  - Skills 在 Claude Code、Hermes、Nanobot 中通常是单独能力域；命令只负责展示/刷新/调用入口，不应让 command registry 直接承担 skill 匹配。
- design impact:
  - 本 change 只做通用 command registry 和上下文命令，把 `/skills` 留给 skill runtime change。
  - `/clear` 和 `/compact` 作为交互命令调用 MemoryManager，不建成 LLM 可调用 tool，避免模型自行清上下文。
  - 命令处理结果应是结构化对象，方便未来 TUI/Web 复用，而 CLI 首版只做文本渲染。
