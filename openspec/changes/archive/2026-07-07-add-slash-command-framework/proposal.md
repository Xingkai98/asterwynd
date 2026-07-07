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
- Web UI SHALL 提供 slash command suggestion 面板：输入 `/` 时展示命令，继续输入时按当前前缀实时过滤。
- Web 后端 SHALL 提供 command catalog，并在 WebSocket chat 路径中拦截独立 slash command，避免控制命令作为普通聊天消息进入 AgentLoop/LLM。
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
  - `web/server.py`
  - `web/static/chat.js`
  - `web/static/style.css`
  - 可能新增 `agent/commands/` 或等价 command registry 模块。
  - `agent/memory/manager.py` 可能需要补充可报告的 clear/compact 结果。
- 影响测试：
  - `tests/test_cli.py`
  - `tests/web_tests/test_server.py`
  - 新增 command registry 单元测试。
  - MemoryManager clear/compact 入口测试。
- 影响文档：
  - `openspec/specs/cli/spec.md`
  - `openspec/specs/memory-context/spec.md`
  - `docs/development-guide.md`
  - `docs/testing-guide.md`
- 不影响：
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
  - Codex 的 `codex-rs/tui/src/slash_command.rs` 用 enum 集中定义内置 slash command、展示描述、inline args 支持、side conversation 可用性和 task-running 可用性；`bottom_pane/slash_commands.rs` 再统一做 feature gating、service-tier 动态命令插入和 fuzzy lookup。
  - Codex 的 app-server 文档定义 `thread/compact/start` 作为 thread 级手动 compact 请求，请求立即返回，进度通过 `turn/*` 和 `item/*` 通知流体现；这说明 manual compact 是运行时控制动作，不应作为普通用户聊天消息。
  - Claude Code 的 `src/types/command.ts` 把命令建模为统一 `Command` 元数据和 lazy-loaded handler，并区分 `local`、`local-jsx`、`prompt` 命令；`src/commands.ts` 再把 built-in、skills、plugins、MCP 等多个来源合并、过滤和缓存。
  - Claude Code 的 `/clear` 不只是清消息，还会清 command/skill、文件建议、prompt cache、WebFetch、ToolSearch、agent definitions 等 session cache，并重新生成 session id；Asterwynd 首版没有这些缓存层，但必须明确清理当前 CLI `messages` 和 `MemoryManager` 状态。
  - Claude Code 的 `/compact` 是本地命令，会绕过普通模型对话路径并返回专门的 compaction result；它支持自定义摘要指令、pre/post compact hooks 和 post-compact cleanup。Asterwynd 首版只需要主动调用现有 `MemoryManager.compact()`，但命令结果应说明压缩前后状态；未来如果 compact 摘要需要 LLM，应由 command handler 显式调用 LLM-backed 服务。
  - Nanobot 的 `nanobot/command/router.py` 使用独立 `CommandRouter` 和 `CommandContext`，区分 priority、exact、prefix 三类路由；`nanobot/command/builtin.py` 用结构化 `BuiltinCommandSpec` 同时服务 `/help` 和 UI command palette。
  - Nanobot 的 `/new` 会取消当前任务、清 session、保存并失效化 session；这说明清上下文命令应属于交互/会话控制层，而不是普通 LLM tool。
  - OpenClaw 文档把 slash command、directive、inline shortcut 分为不同命令类型，并说明 `/status`、`/new`、`/reset`、`/compact` 等命令保持本地会话控制语义；它的 session 文档也强调 gateway/session store 是状态权威。
  - Opencode v2 规格把 manual compaction 作为 automatic compaction 之上的显式能力，并强调 compaction 完成后替换活跃 model context 表示、完整 transcript 仍保留；这支持把 `/compact` 定义成上下文控制命令，而不是普通用户消息。
  - Pi TUI changelog 多次记录 slash-command autocomplete、`argumentHint` 和异步 argument completion 的问题；Asterwynd 首版不做 autocomplete，但 command metadata 应保留 usage/argument hint，避免未来 TUI 命令面板重新定义命令。
- design impact:
  - 本 change 只做 built-in command registry 和上下文命令，不做多源动态命令加载；但 registry 类型要允许后续 skill/plugin/MCP command source 接入。
  - command metadata 除帮助文本外，还应表达参数形态和可用性边界；首版先用简单字段承载，不引入复杂 feature gating。
  - `/clear` 和 `/compact` 作为交互命令调用 MemoryManager，不建成 LLM 可调用 tool，避免模型自行清上下文。
  - 命令处理结果应是结构化对象，方便未来 TUI/Web 复用，而 CLI 首版只做文本渲染。
  - `/clear` 首版不生成新 session id，也不处理尚不存在的 command/skill/cache 层；但必须保留 system messages，并同步当前 CLI 消息列表与 MemoryManager。
  - `/compact` 首版不实现 custom instructions、hook、持久 transcript checkpoint；但必须强制触发一次当前会话压缩，并报告是否有可压缩内容、压缩前后 message/token 摘要。
