## Context

MyAgent 已有 CLI、Web、benchmark 等入口，但没有统一 agent mode。只读分析、构建、计划和未来 bypass 的边界散落在 prompt、工具注册和入口参数中，难以解释和测试。

后续 plan mode、TUI、subagent 和 MCP 都需要统一 mode policy。

## Goals / Non-Goals

**Goals:**

- 新增 AgentMode 概念。
- 根据 mode 过滤或拒绝工具。
- CLI/Web/benchmark 能传入并记录 mode。
- 定义 read_only、build、plan、bypass 的初始边界。

**Non-Goals:**

- 不实现 plan mode 的计划产物。
- 不实现 bypass 授权流程。
- 不实现 structured planning state。
- 不改变现有 build 默认能力的合理使用路径。

## Decisions

### Decision 1: Mode policy 靠代码执行而非 prompt

工具 schema 暴露和工具执行都必须根据 AgentMode 做权限判断。schema 暴露层过滤不允许的工具，执行层再次 fail closed；执行被 mode 禁止的工具时返回可读 tool result，不让 AgentLoop 崩溃，也不破坏 tool-call 消息链。

理由：权限边界必须可验证，不能只靠模型提示。

### Decision 2: AgentRunConfig 是运行上下文事实来源

新增轻量 `AgentRunConfig` 作为一次 Agent 运行的上下文事实来源，当前至少包含 `mode: AgentMode = build`。AgentLoop 持有 `AgentRunConfig`，并负责把实际 mode 写入 trace、event、CLI/Web/benchmark 记录。ToolRegistry 只消费由 `AgentRunConfig` 派生出的 ModePolicy，用于 schema 过滤和执行层拒绝；ToolRegistry 不作为 mode 的唯一事实来源。

理由：mode 后续可能被 planning、subagent、MCP、Web UI 和 benchmark 共同使用。如果把 mode 挂死在 ToolRegistry 上，其他模块要么反向依赖工具注册表，要么重复维护 mode 状态。参考实现也普遍将运行权限上下文放在 session/turn/config 层，工具 registry/runtime 只负责工具查找、dispatch 和错误转换。

### Decision 3: run config 类型集中在 agent/run_config.py

新增 `agent/run_config.py` 承载 mode 相关运行配置类型，包含 `AgentMode`、`AgentRunConfig`、`parse_agent_mode` 和 `ModePolicy`。当前不拆分多个文件，等后续 YAML 配置、approval policy、network policy 或 runtime mode switching 扩展时再按职责拆分。

理由：mode policy 初期规模较小，集中在一个模块便于测试和引用；文件名使用 run_config 而非 modes，是为了给后续运行上下文字段留出扩展空间。

### Decision 4: 当前 change 中 session mode 不可变

本 change 中 mode 在 session / AgentLoop 构造时确定，并在该 session 内保持不变。CLI、Web session 和 benchmark runner 可以在创建 AgentLoop 时传入初始 mode，但本 change 不提供 `set_mode`、`mode_changed` event、WebSocket mode 切换消息或 CLI `/mode` 命令。运行时实时切换 mode 的需求由后续 `add-runtime-mode-switching` change 承载。

理由：当前 change 的目标是建立基础 mode policy 和入口传参语义。实时切换会引入可变 runtime state、并发 tool call、UI 同步和 trace transition 等额外问题，需要单独设计。

### Decision 5: ModePolicy 以工具元数据为主，预留 deny override

read_only 和当前阶段的 plan mode 默认允许 `tool.read_only=True` 且 `tool.dangerous=False` 的工具；build mode 默认允许已注册工具；bypass mode fail closed。ModePolicy 可以预留代码级 `deny_by_mode` 扩展点，但本 change 不提供用户配置入口。用户可配置的 deny override 由后续 `add-yaml-configuration` change 通过 `myagent.yaml` 交付。

理由：当前 Tool 已有 `read_only` 和 `dangerous` 元数据，继续维护完整白名单会造成双重事实来源。deny override 适合做安全阀，但配置格式和优先级属于独立配置系统问题，不应混入本 change。

### Decision 6: 用户输入字符串解析为 AgentMode 枚举

CLI、Web 和 benchmark 用户入口接收字符串形式的 mode，并通过统一解析函数转换为 `AgentMode` 枚举。入口 SHALL 接受 `build`、`read_only`、`read-only`、`plan`；内部统一保存为枚举值，序列化和记录时使用规范字符串，例如 `read_only`。`bypass` 可作为内部枚举预留，但用户入口 SHALL 拒绝。

理由：用户入口需要兼容命令行常见写法，内部逻辑需要类型稳定。统一解析函数可以避免 CLI、Web、benchmark 各自实现不一致的字符串处理。

### Decision 7: ToolRegistry 注册全量工具并动态执行 mode policy

ToolRegistry SHALL 保存入口注册的全量工具集合，不在注册阶段按 mode 删除工具。`get_all_schemas()` 根据 ModePolicy 过滤暴露给 LLM 的 schema；`execute()` 在工具存在但当前 mode 不允许时返回可读权限错误作为 tool result。

理由：注册阶段过滤会把“工具不存在”和“mode 禁止工具”混在一起，直接执行被禁工具时只能得到 unknown tool 或 KeyError。动态判断能保持错误可解释，并覆盖 schema 暴露和执行层 fail closed 两条防线。

### Decision 8: ToolRegistry 依赖 ModePolicy 而不是完整 AgentRunConfig

ToolRegistry 构造时接收 ModePolicy 或等价的工具权限策略对象，而不是直接依赖完整 AgentRunConfig。ModePolicy 至少提供当前 mode、`is_tool_allowed(tool)` 和 `permission_denied_message(tool_name)`。AgentRunConfig 负责表达运行上下文，ModePolicy 负责把运行上下文转换成工具权限判断。

理由：ToolRegistry 只需要判断工具是否可见、可执行，不应耦合未来可能加入 AgentRunConfig 的 model、network、approval、planning 等字段。后续实时 mode 切换也可以将 ModePolicy 的来源替换为 runtime state，而不改变 ToolRegistry 接口。

### Decision 9: mode 禁止工具返回权限拒绝 tool result

当工具存在但被当前 mode 禁止时，ToolRegistry SHALL 返回形如 `[Permission denied: tool <name> is not allowed in <mode> mode]` 的字符串结果，不抛异常，不调用真实工具 `execute()`，并保持 tool-call 消息链合法。

理由：权限拒绝属于受控工具结果，不是运行时崩溃。结果中包含工具名和 mode，便于 trace、测试和用户理解。

### Decision 10: build 保持当前 coding-agent 默认模式

build 允许受 WorkspacePolicy 约束的编辑、写入和验证命令，工具集合保持当前 coding agent 默认能力。本 change 不重新设计 WorkspacePolicy，不收紧 Bash allowlist，也不改变现有 build 使用路径。

理由：保持现有开发工作流，同时为只读模式提供清晰边界。

### Decision 11: 工具构造 helper 放在 agent/tools/factory.py

新增 `agent/tools/factory.py` 承载工具 registry 构造函数。CLI 和 Web SHALL 复用 `build_default_tool_registry(...)`；benchmark SHALL 使用 `build_coding_tool_registry(...)` 或等价 helper 注入 worktree WorkspacePolicy。`agent/tools/__init__.py` 可继续导出常用类型，但不继续堆叠构造逻辑。

理由：CLI/Web/benchmark 都需要组装工具、WorkspacePolicy 和 ModePolicy。把构造逻辑集中到 factory 模块可以减少入口重复，也避免 `agent/tools/__init__.py` 继续变重。

### Decision 12: CLI/Web 统一默认工具集合，benchmark 保持评测工具集合

CLI 和 Web SHALL 使用同一套默认工具构造路径，保证用户直接运行 MyAgent 时，CLI 和 Web 具备一致的默认 agent 能力。benchmark 的 MyAgentRunner MAY 继续使用 benchmark-specific `get_coding_tools(policy=workspace_policy)`，以便针对 isolated worktree 注入 WorkspacePolicy 并避免不稳定外部依赖。mode policy SHALL 在 CLI、Web 和 benchmark 的工具集合上统一生效。

理由：CLI 和 Web 都是用户交互入口，默认能力不一致会让同一任务在不同入口下表现难以解释。benchmark 是评测入口，保留独立 coding tools 有助于可复现和隔离，但不应绕过统一 mode policy。

### Decision 13: plan 在本 change 中只交付权限边界

plan mode 在本 change 中只定义为只读工具和文件权限边界，权限策略与 read_only mode 相同：只允许 `read_only=True` 且 `dangerous=False` 的工具。它不产出结构化 planning state，也不新增 PlanningManager、plan item 状态或 planning 事件。真正的 plan 功能由后续 plan mode / structured planning state change 接入。

理由：当前 change 的目标是先统一 mode policy；提前交付半成品 plan 产物会混淆“只读权限模式”和“可机器读取的计划能力”。

### Decision 14: plan mode 不修改 prompt

本 change 中 plan mode 不增加特殊 system prompt，不要求模型输出计划格式，也不注入 plan workflow 提示。plan 当前只作为权限边界存在，真正计划行为、prompt 和 structured planning state 由后续 `add-plan-mode` / `implement-structured-planning-state` change 定义。

理由：prompt 层行为会让用户误以为 plan 功能已经交付。本 change 只交付可测试的工具权限边界。

### Decision 15: read_only/plan 不允许 Bash

read_only 和当前阶段的 plan mode 不暴露 BashTool，即使命令看起来是只读命令。只读分析应使用 Read、Grep、ListFiles、Find、InspectGitDiff、WebSearch、WebFetch 等明确只读工具。

理由：Bash 命令的副作用难以通过命令文本稳定判断，测试、包管理和脚本命令都可能写缓存、修改环境或触发项目脚本。严格不暴露 Bash 让只读权限更容易解释和测试。

### Decision 16: read_only/plan 允许只读网络工具

WebSearch 和 WebFetch 当前标记为 `read_only=True`，在 read_only 和当前阶段的 plan mode 中允许使用。本 change 不引入独立 network policy，也不把网络访问和文件写权限混在同一个决策里。

理由：网络检索和网页读取对只读分析、资料核对和问题定位有价值；是否限制外部请求应由后续 network policy 或 sandbox change 单独处理。

### Decision 17: 入口记录实际 mode

CLI、Web session 和 benchmark runner 接受 `build`、`read_only`、`plan`，默认使用 `build`，并记录实际使用 mode，trace 中可见。用户入口不接受 `bypass`。

理由：默认 build 保持现有行为；read_only/plan 是显式收紧权限的模式；问题排查和 benchmark 分析需要知道工具权限上下文。

### Decision 18: 通过统一 run_started 生命周期事件记录 mode

AgentLoop.run() 开始时 SHALL 发布 `run_started` 生命周期事件，事件数据至少包含 `mode`。HookManager MAY 增加对应 `on_run_started` 钩子，LoggingHook 通过该钩子记录 `[Run] mode=<mode>`。`on_event`、TraceRecorder、benchmark artifact、WebSocket 和未来 TUI 都应从同一核心事件或同一 run metadata 派生 mode 记录，而不是各入口手写不一致的记录逻辑。

TraceRecorder SHALL 在顶层记录 `mode`，并记录 `run_started` step，兼顾 artifact 查询和时序回放。benchmark 的 `run.json` 和每个 task `result.json` SHALL 记录 mode。Web 的 `session_created` 或首次 `run_started` 事件 SHALL 向前端暴露当前 mode。CLI 单轮和交互模式 SHALL 通过日志记录实际 mode。

理由：CLI、Web、benchmark 和未来 TUI 的展示形式不同，但运行语义应一致。统一生命周期事件能保证 mode 记录可扩展、可测试，并避免多个入口重复实现不同格式的 mode 日志。

### Decision 19: bypass 预留但不可运行

bypass 在本 change 中只是未来高权限模式名称，不提供 CLI、Web 或 benchmark 用户入口，不绕过 ToolRegistry mode policy，也不绕过 WorkspacePolicy。如果内部代码尝试启用 bypass，应 fail closed 并返回可读错误。

理由：bypass 属于权限放大能力，必须先设计授权范围、用户确认、审计记录和测试。没有授权流程时直接放开权限，会让 mode policy 的边界变得不可解释。

## Reference Implementation Notes

- Codex 将 `approval_policy`、`permission_profile`、network、tool mode 等运行权限上下文放在 session/turn context，ToolRegistry 主要负责工具查找、dispatch、hook 和错误返回。
- Claude Code 的 plan mode 修改 app state 中的 `toolPermissionContext`，QueryEngine 通过 config 接收 `tools` 和 `canUseTool`，工具本身只是触发权限上下文转换。
- opencode 的 ToolRuntime 只做工具查找、参数解码、执行和 error-to-result 转换，不拥有权限配置事实来源。
- nanobot 从全局 config 构造 AgentLoop 的 workspace、tools、limits 等运行上下文，ToolRegistry 保持注册、schema 和调用准备职责。

结论：MyAgent 应把 mode 建模为 Agent 运行上下文的一部分，而不是 ToolRegistry 私有状态。

## Risks / Trade-offs

- [风险] 过滤逻辑分散。缓解：集中在 mode policy / tool registry 边界。
- [风险] 旧入口未传 mode。缓解：默认 build，逐步显式化。
- [风险] plan mode 被误解为完整计划功能。缓解：文档和规格明确本 change 只交付只读权限边界。
- [风险] 网络请求影响可复现性。缓解：本 change 只处理工具权限边界；网络策略留给后续独立能力处理。
- [风险] bypass 语义过早扩大。缓解：本 change 将 bypass 定义为预留且不可运行，不实现授权或越权行为。

## Testing Strategy

- 实现采用 TDD：先补 mode parsing、ModePolicy、ToolRegistry、入口传参和记录相关测试，再写实现。
- 单元测试覆盖每个 mode 可用工具集合。
- 单元测试覆盖用户输入字符串解析为 AgentMode 枚举，包括 `read-only` 到 `read_only` 的规范化。
- CLI/Web/benchmark 测试覆盖 mode 传入和记录。
- 负向测试覆盖 read_only 禁止写工具和 dangerous 工具。
- trace 测试覆盖 mode 元数据。
