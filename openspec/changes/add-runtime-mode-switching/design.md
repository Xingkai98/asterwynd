## Context

基础 agent mode policy 可以解决“本次运行以什么权限启动”的问题，但不能解决长会话中用户实时调整权限的问题。实时切换 mode 会影响多个层面：

- 下一轮 LLM 可见的工具 schema。
- 后续 tool call 的执行权限。
- Web UI / CLI / 未来 TUI 展示的当前 mode。
- trace、session event 和调试信息。
- 已经生成但尚未执行的 tool call 如何处理。

## Goals / Non-Goals

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

## Decisions

### Decision 1: mode 状态从不可变 run config 升级为 session runtime state

基础 mode policy 中的 `AgentRunConfig` 适合表达初始配置；实时切换需要新增可变的 session runtime state，例如 `AgentRuntimeState.current_mode`。AgentLoop、ToolRegistry 和 UI 读取当前 mode 时应通过统一 runtime state 或其快照。

理由：如果继续把 mode 放在 frozen config 中，就无法支持实时修改；如果每个入口各自维护 mode，会导致 CLI/Web/TUI 状态不一致。

`AgentRunConfig.mode` SHALL 继续表示入口选择的初始 mode；`AgentRuntimeState.current_mode` SHALL 表示当前 session 的实际 mode。Trace、run_started 和 UI 展示 SHALL 使用当前 mode。Benchmark 默认仍以初始 mode 固定运行，除非后续任务显式调用 runtime transition API。

### Decision 2: mode transition 必须通过统一 API

运行时切换 SHALL 通过类似 `set_mode(new_mode, source, reason)` 的统一 API 完成。该 API 负责校验目标 mode、更新状态、发布事件并写入 trace。

理由：避免 UI、CLI 或工具层直接改字段，绕过校验和审计。

`set_mode` SHALL 接收 `build`、`read_only` 和 `plan`，并拒绝用户切换到 `bypass`。`mode_changed` 事件 payload SHALL 至少包含 `old_mode`、`new_mode` 和 `source`；`reason`、`session_id` 和 `run_id` 在调用方可提供时附带。mode transition SHALL NOT 写入 provider `messages` 历史，避免破坏 tool-call 消息链；审计和 UI 同步通过事件与 trace 完成。

### Decision 3: 切换后立即影响后续 schema 和执行

ToolRegistry 的 `get_all_schemas()` 和 `execute()` SHALL 读取最新 mode，而不是 AgentLoop 启动时的旧 mode。mode 更新完成后，下一次 schema 获取和下一次 tool execution 必须使用新 mode。

理由：用户要求“修改后立刻生效”；只在下一次 run 生效不能满足交互需求。

当前 CLI 交互模式和 WebSocket 入口在一次 Agent run 期间都会等待该 run 完成后才继续处理用户输入或 WebSocket 消息。因此第一版用户可触发的 CLI/Web mode 切换只保证对同一 session 的后续 run 生效。runtime state 和 ToolRegistry 仍按“transition 完成后立即影响后续 schema / execute”实现和测试，未来 TUI 或重构后的控制面可以在 run 中复用同一 API。

### Decision 4: 已开始执行的工具不被中途抢占

初始策略：mode 切换不取消已经开始执行的工具；但尚未开始执行的 tool call 必须按最新 mode 重新判断。对于同一 assistant 消息中的多个 tool call，执行每个 tool call 前都重新读取当前 mode。

理由：中途取消工具需要额外的取消协议和幂等保证；逐个 tool call 前重新判断能满足“后续立即生效”并控制复杂度。

如果 LLM 已经基于旧 mode 看到了工具 schema，而用户在工具执行前切到更严格的 mode，执行层 SHALL 按最新 mode fail closed，并返回权限拒绝 tool result。本次不向 LLM 追加额外系统提示说明 mode 已变化。

### Decision 5: bypass 仍不可通过动态切换启用

在 bypass 授权流程实现前，动态 mode 切换 API SHALL 拒绝切换到 `bypass`。

理由：实时切换不能成为绕过用户入口限制的高权限后门。

### Decision 6: mode transition 是 session 级，不做单轮 override

CLI 交互、Web UI 和未来 TUI 中的 mode 切换 SHALL 修改当前 session mode，并影响该 session 后续 run。单轮临时 mode override 不在本 change 范围内。

理由：`Session ID` 已定义为交互式长会话标识；mode 跟随 session 能保持 CLI/Web/TUI 一致。单轮 override 需要额外定义 session 默认 mode、run override 和 transition 发生时序之间的优先级，适合后续单独设计。

### Decision 7: plan mode 工具按需注册，按 mode policy 暴露

当 session 从其他 mode 切换到 `plan` 时，AgentLoop SHALL 确保 `UpdatePlan` 和 `ExitPlanMode` 已注册。切出 `plan` 后无需删除这两个工具；现有 `allowed_modes=("plan",)` SHALL 保证它们在非 plan mode 下不暴露且不可执行。

理由：如果只在 AgentLoop 初始 mode 为 `plan` 时注册 plan-only 工具，动态切到 `plan` 后会缺少 Plan Document 和 Planning State 的核心工具。保留注册、由 mode policy 控制可见性和执行权限，行为更稳定。

### Decision 8: 本次不做 session 持久化和恢复

mode transition SHALL 保存在进程内 session runtime state，并记录到事件和 trace。本次不实现 session history 持久化，也不承诺进程结束后的 mode 恢复。

理由：当前 CLI 交互和 Web session 都没有持久化恢复机制。把 mode transition 写入可恢复 session history 会引入存储格式、恢复顺序和兼容性问题，超出本 change 范围。

## Resolved Questions

- CLI 交互模式使用 `/mode <build|read_only|plan>` 控制命令切换当前 session mode；`/mode bypass` 必须拒绝。
- Web UI 使用 session 级 mode 切换，不做单轮 override。
- CLI 单次运行不提供运行中人工切换入口，仍通过 `--mode` 指定初始 mode。
- mode transition 不写入 provider `messages` 历史，不向 LLM 追加系统提示；执行层按最新 mode fail closed。
- mode transition 不做 session history 持久化和恢复。
- 未来 TUI SHALL 复用统一 runtime transition API 和 `mode_changed` 事件，不单独实现一套不兼容语义。

## Risks / Trade-offs

- [风险] 动态切换 mode 与正在执行的工具存在竞态。缓解：初始策略不取消已开始工具，但每个尚未开始的 tool call 执行前重新读取最新 mode。
- [风险] CLI、Web 和未来 TUI 各自实现切换逻辑导致行为不一致。缓解：必须通过统一 mode transition API 修改 mode，并由 runtime 发布统一事件。
- [风险] bypass 被实时切换绕过入口限制。缓解：在 bypass 授权流程完成前，transition API 必须拒绝切换到 bypass。
- [风险] LLM 已看到旧 schema 后权限发生变化。缓解：执行层始终按最新 mode fail closed，本次不追加权限变化提示。
- [风险] 用户期待 CLI/Web 在 run 中即时处理 mode 切换。缓解：文档明确第一版 CLI/Web 控制面只保证后续 run 生效；runtime API 保持立即生效语义，供未来 TUI 或控制面重构复用。

## Testing Strategy

- Agent runtime 测试覆盖 `set_mode` 更新状态和事件发布。
- ToolRegistry 测试覆盖切换后 schema 立即变化。
- ToolRegistry / AgentLoop 测试覆盖切换后尚未执行的被禁工具返回权限拒绝。
- CLI 交互测试覆盖 mode 切换命令。
- Web session 测试覆盖 WebSocket mode 切换消息和 session_created / mode_changed 事件。
- 未来 TUI 测试覆盖相同 transition API。
