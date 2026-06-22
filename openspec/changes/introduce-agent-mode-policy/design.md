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

### Decision 2: build 保持当前 coding-agent 默认模式

build 允许受 WorkspacePolicy 约束的编辑、写入和验证命令，工具集合保持当前 coding agent 默认能力。本 change 不重新设计 WorkspacePolicy，不收紧 Bash allowlist，也不改变现有 build 使用路径。

理由：保持现有开发工作流，同时为只读模式提供清晰边界。

### Decision 3: plan 在本 change 中只交付权限边界

plan mode 在本 change 中只定义为只读工具和文件权限边界，权限策略与 read_only mode 相同：只允许 `read_only=True` 且 `dangerous=False` 的工具。它不产出结构化 planning state，也不新增 PlanningManager、plan item 状态或 planning 事件。真正的 plan 功能由后续 plan mode / structured planning state change 接入。

理由：当前 change 的目标是先统一 mode policy；提前交付半成品 plan 产物会混淆“只读权限模式”和“可机器读取的计划能力”。

### Decision 4: read_only/plan 不允许 Bash

read_only 和当前阶段的 plan mode 不暴露 BashTool，即使命令看起来是只读命令。只读分析应使用 Read、Grep、ListFiles、Find、InspectGitDiff、WebSearch、WebFetch 等明确只读工具。

理由：Bash 命令的副作用难以通过命令文本稳定判断，测试、包管理和脚本命令都可能写缓存、修改环境或触发项目脚本。严格不暴露 Bash 让只读权限更容易解释和测试。

### Decision 5: read_only/plan 允许只读网络工具

WebSearch 和 WebFetch 当前标记为 `read_only=True`，在 read_only 和当前阶段的 plan mode 中允许使用。本 change 不引入独立 network policy，也不把网络访问和文件写权限混在同一个决策里。

理由：网络检索和网页读取对只读分析、资料核对和问题定位有价值；是否限制外部请求应由后续 network policy 或 sandbox change 单独处理。

### Decision 6: 入口记录实际 mode

CLI、Web session 和 benchmark runner 接受 `build`、`read_only`、`plan`，默认使用 `build`，并记录实际使用 mode，trace 中可见。用户入口不接受 `bypass`。

理由：默认 build 保持现有行为；read_only/plan 是显式收紧权限的模式；问题排查和 benchmark 分析需要知道工具权限上下文。

### Decision 7: bypass 预留但不可运行

bypass 在本 change 中只是未来高权限模式名称，不提供 CLI、Web 或 benchmark 用户入口，不绕过 ToolRegistry mode policy，也不绕过 WorkspacePolicy。如果内部代码尝试启用 bypass，应 fail closed 并返回可读错误。

理由：bypass 属于权限放大能力，必须先设计授权范围、用户确认、审计记录和测试。没有授权流程时直接放开权限，会让 mode policy 的边界变得不可解释。

## Risks / Trade-offs

- [Risk] 过滤逻辑分散。Mitigation: 集中在 mode policy / tool registry 边界。
- [Risk] 旧入口未传 mode。Mitigation: 默认 build，逐步显式化。
- [Risk] plan mode 被误解为完整计划功能。Mitigation: 文档和规格明确本 change 只交付只读权限边界。
- [Risk] 网络请求影响可复现性。Mitigation: 本 change 只处理工具权限边界；网络策略留给后续独立能力处理。
- [Risk] bypass 语义过早扩大。Mitigation: 本 change 将 bypass 定义为预留且不可运行，不实现授权或越权行为。

## Testing Strategy

- 单元测试覆盖每个 mode 可用工具集合。
- CLI/Web/benchmark 测试覆盖 mode 传入和记录。
- 负向测试覆盖 read_only 禁止写工具和 dangerous 工具。
- trace 测试覆盖 mode 元数据。
