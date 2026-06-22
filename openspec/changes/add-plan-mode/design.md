## Context

用户经常需要 agent 先分析仓库、拆方案和评估风险，再决定是否允许修改代码。当前模式边界散在 prompt 和工具集合里，不能可靠保证“只计划、不修改”。

plan mode 应建立在 agent mode policy 和 structured planning state 之上。

## Goals / Non-Goals

**Goals:**

- 新增可执行 `plan` mode。
- plan mode 只暴露只读工具。
- 输出结构化 planning state 和自然语言计划。
- CLI/Web 可启动 plan mode。

**Non-Goals:**

- 不实现 bypass 授权。
- 不允许 Write/Edit/dangerous Bash。
- 不替代 build mode。
- 不解决 TUI 展示细节。

## Decisions

### Decision 1: plan mode 是 AgentMode 的一种

plan mode 使用统一 AgentMode 枚举和工具过滤逻辑，而不是单独 prompt 开关。

理由：权限边界必须可测试，不能只依赖模型遵守提示。

### Decision 2: 输出 planning state 而不是仅自然语言

AgentLoop 在 plan mode 中应产出结构化 plan items，文本回复作为解释层。

理由：Web/TUI/trace/benchmark 都需要机器可读计划。

### Decision 3: 只读工具白名单

plan mode 初始只允许 Read/Grep/ListFiles/Find/InspectGitDiff 等只读工具。

理由：计划阶段不应产生代码或环境副作用。

## Risks / Trade-offs

- [Risk] 只读限制让某些调研无法运行测试。Mitigation: plan mode 明确非执行模式，测试建议写入计划。
- [Risk] 模型仍可能建议执行修改。Mitigation: 工具层拒绝写操作，UI 展示 mode。
- [Risk] planning state 过细导致噪声。Mitigation: 初版只记录高层步骤和状态。

## Testing Strategy

- Agent mode 测试覆盖 plan mode 工具过滤。
- CLI/Web 测试覆盖启动 plan mode。
- AgentLoop 测试覆盖 plan mode 输出 planning state。
- 负向测试覆盖 Write/Edit/Bash dangerous 被拒绝。
