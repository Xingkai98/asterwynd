## 背景

基础 agent mode policy 可以解决“本次运行以什么权限启动”的问题，但不能解决长会话中用户实时调整权限的问题。实时切换 mode 会影响多个层面：

- 下一轮 LLM 可见的工具 schema。
- 后续 tool call 的执行权限。
- Web UI / CLI / 未来 TUI 展示的当前 mode。
- trace、session event 和调试信息。
- 已经生成但尚未执行的 tool call 如何处理。

## 目标 / 非目标

**目标：**

- 允许用户在运行时实时切换当前 session 的 mode。
- mode 修改后立即影响后续 schema 暴露和工具执行。
- CLI、Web UI 和未来 TUI 复用同一 mode transition API。
- 记录 mode transition 事件，便于调试和审计。
- 明确运行中 tool call、并发工具和切换竞态的处理规则。

**非目标：**

- 不实现 bypass 授权流程。
- 不改变每个 mode 的权限定义。
- 不把 mode transition 当作 plan approval 的完整工作流；plan approval 可在后续 change 中基于本能力实现。
- 不要求 benchmark 默认执行动态 mode 切换。

## 初步设计方向

### Decision 1: mode 状态从不可变 run config 升级为 session runtime state

基础 mode policy 中的 `AgentRunConfig` 适合表达初始配置；实时切换需要新增可变的 session runtime state，例如 `AgentRuntimeState.current_mode`。AgentLoop、ToolRegistry 和 UI 读取当前 mode 时应通过统一 runtime state 或其快照。

理由：如果继续把 mode 放在 frozen config 中，就无法支持实时修改；如果每个入口各自维护 mode，会导致 CLI/Web/TUI 状态不一致。

### Decision 2: mode transition 必须通过统一 API

运行时切换 SHALL 通过类似 `set_mode(new_mode, source, reason)` 的统一 API 完成。该 API 负责校验目标 mode、更新状态、发布事件并写入 trace。

理由：避免 UI、CLI 或工具层直接改字段，绕过校验和审计。

### Decision 3: 切换后立即影响后续 schema 和执行

ToolRegistry 的 `get_all_schemas()` 和 `execute()` SHALL 读取最新 mode，而不是 AgentLoop 启动时的旧 mode。mode 更新完成后，下一次 schema 获取和下一次 tool execution 必须使用新 mode。

理由：用户要求“修改后立刻生效”；只在下一次 run 生效不能满足交互需求。

### Decision 4: 已开始执行的工具不被中途抢占

初始策略：mode 切换不取消已经开始执行的工具；但尚未开始执行的 tool call 必须按最新 mode 重新判断。对于同一 assistant 消息中的多个 tool call，执行每个 tool call 前都重新读取当前 mode。

理由：中途取消工具需要额外的取消协议和幂等保证；逐个 tool call 前重新判断能满足“后续立即生效”并控制复杂度。

### Decision 5: bypass 仍不可通过动态切换启用

在 bypass 授权流程实现前，动态 mode 切换 API SHALL 拒绝切换到 `bypass`。

理由：实时切换不能成为绕过用户入口限制的高权限后门。

## 待讨论问题

- CLI 中 mode 切换使用命令语法还是交互式控制命令，例如 `/mode read_only`？
- Web UI 中 mode 切换是 session 级、单轮级，还是二者都支持？
- 如果 LLM 已经收到 build 工具 schema，用户在执行前切到 read_only，是否要向 LLM 追加系统提示说明权限已变化？
- mode transition 是否需要持久化到 session history，供恢复会话使用？
- 未来 TUI 的 mode 状态展示和快捷键如何复用 Web/CLI 语义？

## 测试策略

- Agent runtime 测试覆盖 `set_mode` 更新状态和事件发布。
- ToolRegistry 测试覆盖切换后 schema 立即变化。
- ToolRegistry / AgentLoop 测试覆盖切换后尚未执行的被禁工具返回权限拒绝。
- CLI 交互测试覆盖 mode 切换命令。
- Web session 测试覆盖 WebSocket mode 切换消息和 session_created / mode_changed 事件。
- 未来 TUI 测试覆盖相同 transition API。
