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

工具集合构造或 ToolRegistry 执行时根据 AgentMode 做过滤/拒绝。

理由：权限边界必须可验证，不能只靠模型提示。

### Decision 2: build 保持当前 coding-agent 默认模式

build 允许受 WorkspacePolicy 约束的编辑和验证命令，read_only/plan 更严格。

理由：保持现有开发工作流，同时为只读模式提供清晰边界。

### Decision 3: 入口记录实际 mode

CLI、Web session 和 benchmark runner 记录实际使用 mode，trace 中可见。

理由：问题排查和 benchmark 分析需要知道工具权限上下文。

## Risks / Trade-offs

- [Risk] 过滤逻辑分散。Mitigation: 集中在 mode policy / tool registry 边界。
- [Risk] 旧入口未传 mode。Mitigation: 默认 build，逐步显式化。
- [Risk] bypass 语义过早扩大。Mitigation: 本 change 只定义边界，不实现授权。

## Testing Strategy

- 单元测试覆盖每个 mode 可用工具集合。
- CLI/Web/benchmark 测试覆盖 mode 传入和记录。
- 负向测试覆盖 read_only 禁止写工具和 dangerous 工具。
- trace 测试覆盖 mode 元数据。
