## Context

CLI 单轮模式适合脚本调用，CLI 交互模式适合低依赖多轮终端入口，Web UI 适合浏览器调试，但本地长任务缺少一个多面板终端内实时视图。TUI 应展示 AgentLoop 运行事件、消息、工具调用和 planning state，而不是创建新的运行协议。

本 change 依赖已有 AgentLoop、structured planning state、runtime mode、tool display policy、skills 和 MCP 的事件语义。

## Goals / Non-Goals

**Goals:**

- 新增最小多轮 TUI 命令入口。
- 复用 AgentLoop、tool events、planning state 和 session 语义。
- 展示对话、工具调用进度、planning state 和最终摘要。
- 提供基本输入框、滚动 transcript、状态栏和退出路径。
- 支持与 Web UI 一致的 slash command 提示体验，包含内置命令和 skill command。
- 保持 CLI/Web/TUI 运行协议一致。

**Non-Goals:**

- 不实现 IDE 或文件编辑器。
- 不实现复杂鼠标工作台交互；首版保留 Textual 默认支持的基础点击聚焦和滚轮滚动。
- 不重新实现 AgentLoop。
- 不在本 change 中定义新的 planning 数据模型。
- 不实现会话恢复、复杂命令面板、多 tab、完整 diff viewer 或 TUI 内文件编辑器。

## Decisions

### Decision 1: TUI 消费统一运行事件

TUI 不直接解析内部 messages，而是消费 AgentLoop/Web/trace 共用的运行事件或轻量 adapter。

理由：减少 CLI、Web、TUI 三套展示逻辑分裂。

### Decision 2: 首版做基本多轮 TUI 会话

初版 TUI 不做单轮运行后退出，而是提供一个基本多轮对话界面：用户在底部输入区发送消息，TUI 复用同一个 session 的 message history 和 AgentLoop，每轮运行生成新的 run id。

理由：单轮 TUI 价值接近 CLI 换皮，无法证明终端工作台体验；但首版仍只做基础多轮，不扩展到完整 IDE 或复杂命令面板。

### Decision 3: 使用 Textual 作为 TUI 框架

首版 TUI 使用 `textual`，UI 代码放在 `agent/tui/`。Textual 只作为界面层依赖，核心 AgentLoop、ToolRegistry、planning state、tool display policy 和 trace 语义不得依赖 Textual。

理由：多轮 TUI 需要输入框、滚动 transcript、异步事件刷新、快捷键退出和布局管理。用标准库 `curses` 会较快演变成自建 UI 框架；参考实现中 Codex、opencode、Claude Code / Gemini CLI 也都采用框架化 TUI 或组件化终端 UI。

### Decision 4: 用事件 reducer 隔离 UI 与运行状态

新增 TUI event state / reducer，消费现有 `on_event(event_type, data)` 事件并产出可渲染状态。Textual widget 只读取 reducer state，不直接解析 AgentLoop 内部 messages。

理由：保持 CLI/Web/TUI 事件语义一致，并让测试重点落在纯状态转换上，降低终端渲染快照的脆弱性。

### Decision 5: 终端渲染与运行状态分离

TUI renderer 只负责布局和刷新，session/agent 状态仍由现有 runtime 管理。

理由：避免把终端 UI 状态混进 AgentLoop。

### Decision 6: Slash command 提示复用现有 registry

TUI 输入区在用户输入 `/` 开头内容时展示 slash command 提示，提示数据来自 `build_default_slash_command_registry(...).catalog()`。过滤规则与 Web UI 对齐：命令名或 alias 按当前前缀匹配；选中后把 `insert_text` 写回输入框。执行时复用现有 `SlashCommandRegistry.try_execute()`，skill command 继续通过 `run_agent` metadata 进入 AgentLoop。

理由：Web、CLI 和 TUI 应共享同一命令来源，避免 command catalog、skill command 和命令执行语义分裂。

### Decision 7: Building phase 交给 Claude Code

本 change 的 planning、设计记录、handoff 和后续 closing 由当前 Codex 会话继续负责；building phase 由 Claude Code 在新 session 中执行。`handoff.json` 的 per-change routing 已将 `building.executor` 设置为 `claude-code`，`building.session_mode` 设置为 `new`。

理由：本 change 正好用于验证多 agent 开发流程；实现阶段交给 Claude Code，可以验证 handoff note、phase routing 和后续 code review/closing 的协作边界。

### Decision 8: 非交互环境只清晰报错

首版 TUI 在 stdin 或 stdout 不是 TTY，或终端不支持 Textual 交互渲染时，直接拒绝启动并输出可读原因，不实现 `--plain` 文本事件流降级。

理由：项目已有 CLI 单轮和 CLI 交互模式覆盖非 TTY、脚本和低依赖终端路径；TUI 首版应聚焦交互式终端体验，避免再维护一套文本事件流。

### Decision 9: Approval 必须可用，slash/skill 复用现有命令语义

TUI 首版必须支持 approval request 的基本 approve/deny 流程。slash command 和 skill command 使用现有 registry/catalog：输入区展示提示，提交后调用 `try_execute()`；当命令返回 `run_agent` metadata 时，TUI 按现有 CLI/Web 语义把 `agent_input` 追加为用户消息并启动一轮 AgentLoop。

理由：approval 是高风险工具执行的安全边界，TUI 不能绕过；slash/skill 是当前交互入口的一等能力，TUI 不应低于 Web UI 的基本体验。

实现约束：TUI 可以复用 approval handler 的请求/响应语义，但不能直接调用 CLI 的阻塞式 stdin prompt。TUI 应提供独立的异步等待型 approval handler，接收 approval request、展示脱敏摘要、等待用户 approve/deny 操作，并把决策返回给 AgentLoop。

### Decision 10: Handoff note 默认不提交

`.handoff/<change-id>/` 下的 handoff note 是本地协作临时材料，默认不进入 Git。`handoff.json` transition 可以记录本地 handoff note 路径，后续同工作区 agent 可直接读取该文件；但需要长期留存的关键结论必须写入 OpenSpec 文档、`handoff.json`、评审报告或稳定项目文档。只有用户明确要求把某份 handoff note 纳入 PR 时，才使用 `git add -f .handoff/...` 强制提交。

理由：`.handoff/` 已在 `.gitignore` 中，交接文件更接近当前工作区的上下文缓存；把每次交接文件都提交会制造过程噪音。PR #47 中提交 `.handoff` 是因为 ignore 规则是在同一变更中追加，不能作为长期默认约定。

## Pre-Implementation Review

- Questions resolved:
  - TUI 首版形态：用户确认单轮 TUI 意义不足，首版应做基本多轮 TUI 对话。
  - 框架选择：用户确认采用 `textual`，而不是 `curses` 或纯文本事件 renderer。
  - 基础鼠标能力：用户确认 transcript 基础滚动和输入区点击聚焦应纳入首版；复杂鼠标工作台交互仍不做。
  - Slash command 提示：用户确认 TUI 应像 Web UI 一样支持 slash 命令提示。
  - 非交互环境：用户确认首版 TUI 非 TTY 时清晰报错退出，不做 `--plain` 文本降级。
  - Approval / skill：用户确认 approval 必须支持基本 approve/deny；slash command 和 skill command 支持提示、选择和执行，但不做复杂命令面板。
  - Handoff 提交策略：用户确认 `.handoff/` 默认不提交，PR #47 提交 `.handoff` 是历史原因；本 change 只提交长期规则和 `handoff.json`。
  - 开发分工：用户确认 building phase 交给 Claude Code，当前 Codex 负责其他阶段和交接。
  - 运行协议：继续复用 AgentLoop 的 `on_event(event_type, data)`，不新增不兼容协议。
  - 状态边界：新增 TUI reducer/controller，Textual app 不直接持有核心 runtime 状态。
  - workflow 状态：PR #47 合入后，本 change 已补齐 `handoff.json`，当前处于 `planning.grilling_design`。
- Options considered:
  - `curses`：依赖少、标准库可用，但多轮输入、滚动、异步刷新和布局维护成本较高。
  - `prompt_toolkit + rich`：适合增强 CLI/REPL，但多面板 app 和长期运行状态管理不如 Textual 直接。
  - `textual`：新增依赖，但更适合多轮 TUI app。
  - 单轮 runtime view：实现简单，但用户确认价值不足。
- Rejected alternatives:
  - 单轮 TUI。原因：更像 CLI 输出换皮，无法体现 TUI 会话价值。
  - `curses` 首版。原因：会把输入、滚动、异步任务和布局维护压力推给项目自己。
  - 将 Textual 引入 AgentLoop。原因：UI 框架不得污染核心运行协议。
- Final confirmations:
  - 首版 TUI 是基本多轮会话：输入、transcript、工具事件摘要、planning state、状态栏和退出。
  - 首版保留 Textual 默认支持的基础点击聚焦和滚轮滚动。
  - 首版支持 slash command 提示，复用现有 command catalog 和 skill command catalog；不做复杂命令面板。
  - 首版支持 approval 基本 approve/deny，保证高风险工具仍经过审批链路。
  - 首版非交互环境直接清晰报错，不实现 `--plain` 文本事件流降级。
  - 首版使用 `textual`，但不做会话恢复、复杂命令面板、鼠标、完整 diff viewer 或 TUI 内编辑器。
  - `building` phase 路由为 `claude-code/new`；进入实现前需要生成 handoff note，明确 Claude Code 的实现范围、测试要求和不可改动边界。
  - `.handoff/` 交接文件默认不提交；关键结论必须沉淀到可提交文档和 `handoff.json`。
  - 设计审查和代码审查按 `handoff.json` 的 workflow gate 执行。
- Remaining risks:
  - Textual 依赖会扩大测试面，需要将核心行为放在 reducer/controller 测试，避免过度依赖 UI 快照。
  - TUI scope 容易扩大到完整工作台，必须守住首版边界。
  - Approval UI 不应复杂化为完整权限管理面板；首版只做当前请求的 approve/deny。

## Risks / Trade-offs

- [Risk] TUI 与 Web 展示语义不一致。Mitigation: 复用相同事件字段和 planning state。
- [Risk] 终端环境差异导致渲染不稳定。Mitigation: 单元测试覆盖状态转换，渲染快照保持最小。
- [Risk] 长输出撑坏布局。Mitigation: 默认折叠工具详情，保留展开入口。
- [Risk] Textual 依赖把核心 runtime 变重。Mitigation: 依赖只在 TUI 层使用，核心模块不 import Textual。
- [Risk] 多轮 TUI 与 CLI 交互模式职责重叠。Mitigation: CLI 交互模式继续作为低依赖 REPL，TUI 承接多面板 runtime view。
- [Risk] Slash command catalog 在 Web/TUI 中分裂。Mitigation: TUI 复用 `SlashCommandRegistry.catalog()` 和 `try_execute()`，不维护独立命令列表。
- [Risk] TUI 绕过高风险工具审批。Mitigation: TUI 提供 approval approve/deny 流程，并复用现有 approval handler 语义。

## Testing Strategy

- CLI 命令测试覆盖 TUI 入口参数。
- TUI 状态 reducer 测试覆盖消息、assistant streaming、工具调用、planning 更新、approval、memory compaction 和 done。
- TUI session/controller 测试覆盖多轮 message history、session id 复用、run id 更新、退出命令和错误事件。
- TUI slash command 测试覆盖前缀过滤、alias 匹配、skill command 提示、选择后填充和命令执行不启动 agent 的路径。
- TUI approval 测试覆盖 approval request 展示、approve、deny 和无响应时的失败路径。
- TUI 入口 smoke 复用 `tests/support/llm_harness.py` 中的共享 `ScriptedLLM`，覆盖真实 AgentLoop 输入、运行事件消费和屏幕状态更新。
- Textual app 保持轻量 smoke，不把主要行为锁死在渲染快照上。
- 非交互环境 graceful failure 测试；首版不做 `--plain` 文本降级。
- 手动 smoke 覆盖一次 fake agent 长任务展示。
