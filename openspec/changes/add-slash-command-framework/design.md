## Context

当前 CLI 交互模式位于 `cli.py::run_interactive`。它直接在输入循环中处理裸 `exit/quit/q`，并用 `_handle_interactive_command` 内联解析 `/mode`。MemoryManager 已提供 `clear()` 和 `compact()`，但只有自动 compact 路径，没有用户主动触发命令。

后续基本能力补全会继续增加交互入口：skills 需要 `/skills`，TUI 需要命令面板，MCP 和 browser 后续也可能需要状态/权限相关命令。先建立 command registry，可以避免每个入口重复解析。

## Goals / Non-Goals

Goals:

- 建立最小 slash command registry。
- 将 CLI 交互模式现有 `/mode` 迁移到 registry。
- 增加 `/help`、`/exit`、`/status`、`/clear`、`/compact`。
- 明确 `/clear` 和 `/compact` 对 MemoryManager 与当前 `messages` 列表的影响。
- 保持现有 CLI 交互模式兼容，裸 `exit`、`quit`、`q` 仍可退出。

Non-Goals:

- 不实现 `/skills`，只为后续 change 预留注册机制。
- 不实现 TUI 命令面板或 Web slash command。
- 不改变 AgentLoop 的 tool-call 协议。
- 不允许 LLM 通过 tool 自行执行 `/clear` 或 `/compact`。
- 不引入复杂 autocomplete；未来 TUI 可单独增强。

## Decisions

### Decision 1: Slash command registry 独立于 CLI 输入循环

新增 command registry 模块，命令以对象或 dataclass 注册，至少包含 name、aliases、usage、description 和 handler。CLI 输入循环只负责判断输入是否为 slash command，并把 session context 交给 registry 执行。

理由：后续 TUI/Web 可以复用命令定义；测试也能绕开 `input()` 循环直接验证命令行为。

### Decision 2: 命令返回结构化结果

命令 handler 返回结构化结果，例如 message、continue_session、mutated_messages、metadata。CLI 首版把 message 渲染为文本。

理由：`/exit`、`/clear`、`/compact` 都不只是输出文本，它们会影响会话控制或上下文状态。结构化结果比约定字符串更稳。

### Decision 3: `/clear` 操作当前交互消息列表和 MemoryManager

`/clear` SHALL 保留 system messages，移除当前交互会话中累计的 user/assistant/tool 消息，并调用 MemoryManager 的等价清理能力保持状态一致。

理由：当前 CLI run 使用本地 `messages` 列表传入 AgentLoop；只清 MemoryManager 或只清本地列表都会造成用户观察和下轮上下文不一致。

### Decision 4: `/compact` 主动压缩当前交互消息列表

`/compact` SHALL 调用 MemoryManager 对当前 `messages` 列表执行 compact，即使未超过自动 token 阈值也允许用户主动请求。命令输出应说明是否执行压缩以及压缩后的消息数量；如无可压缩内容，应返回可读提示。

理由：用户显式输入 `/compact` 时期待主动整理上下文，不应受自动阈值限制。自动 compact 仍由 AgentLoop 在运行前执行。

### Decision 5: `/status` 首版只展示本地可得信息

`/status` 展示 session id、当前 mode、provider、model、message count 和 token 估算。无法获取的字段显示为 unavailable 或省略。

理由：先提供可稳定测试的信息；trace 路径、最新 run id、tool permission profile 等可在后续 change 扩展。

## Pre-Implementation Review

- Questions resolved:
  - `/clear`、`/compact` 并入本 change，不单独建第三个 change。
  - `/skills` 不并入本 change 的首批命令，由 `integrate-skill-runtime` 后续接入。
  - command registry 应独立于 CLI 输入循环，便于未来 TUI/Web 复用。
  - `/clear` 和 `/compact` 不暴露为 LLM tool。
- Options considered:
  - 继续在 `run_interactive` 中用 if/else 解析每个命令。
  - 新增独立 command registry。
  - 把 `/skills` 一起实现。
  - 先只做 `/help` 和 `/mode`，把 clear/compact 后置。
- Rejected alternatives:
  - 继续 if/else。原因：后续命令会快速增长，测试和帮助文本会分裂。
  - 把 `/skills` 一起实现。原因：skills runtime 本身还需要配置、注入和匹配设计，混入会扩大首个 change。
  - 后置 clear/compact。原因：用户已明确把 compact、clear 视为常见命令，且 MemoryManager 已具备基础能力。
- Final confirmations:
  - 第一批命令为 `/help`、`/exit`、`/status`、`/mode`、`/clear`、`/compact`。
  - 裸 `exit/quit/q` 保持兼容。
  - 实现前需要再次用 `grill-with-docs` 确认命令结果结构、MemoryManager 清理细节和测试矩阵。
- Remaining risks:
  - CLI 本地 `messages` 和 AgentLoop memory 双状态可能不一致，开发时必须用测试锁住。
  - 主动 compact 是否强制摘要取决于 LLM 可用性，用户提示文案需要准确。

## Risks / Trade-offs

- [Risk] 过早设计通用 command abstraction 可能过度工程。Mitigation: 首版只覆盖 name/aliases/help/handler/result，避免复杂 plugin command。
- [Risk] `/clear` 清理不彻底导致旧上下文泄漏到下一轮。Mitigation: 测试同时检查 CLI messages 和 MemoryManager。
- [Risk] `/compact` 在无 LLM 时只裁剪上下文，用户可能误解为摘要。Mitigation: 输出明确说明 compact 方式和结果。
- [Risk] 后续 TUI/Web 复用需求变化。Mitigation: 返回结构化结果，渲染留给入口层。

## Testing Strategy

- command registry 单元测试：
  - 注册、别名、未知命令、帮助文本。
  - 参数缺失和错误提示。
- CLI 交互测试：
  - `/help` 输出命令列表。
  - `/mode read_only` 保持现有行为。
  - `/mode bypass` 继续拒绝。
  - `/exit` 和裸 `exit` 均退出。
  - `/status` 展示 session/mode/model。
  - `/clear` 后下一轮不携带历史 user 消息。
  - `/compact` 调用 MemoryManager compact 并输出结果。
- MemoryManager 测试：
  - clear 保留 system messages。
  - forced compact 在有/无 LLM 场景行为明确。
- 验证：
  - `uv run pytest tests/test_cli.py -q`
  - 相关 memory/command 测试。
  - `uv run pytest -q`
  - OpenSpec strict validate 和 artifact checker。
