## Context

用户经常需要 agent 先分析仓库、拆方案和评估风险，再决定是否允许修改代码。当前模式边界散在 prompt 和工具集合里，不能可靠保证“只计划、不修改”。

plan mode 应建立在 agent mode policy 和 structured planning state 之上。

## Goals / Non-Goals

**Goals:**

- 新增可执行 `plan` mode。
- plan mode 只暴露只读工具。
- 输出 Markdown Plan Document、结构化 planning state 和自然语言计划说明。
- CLI/Web 可启动 plan mode。

**Non-Goals:**

- 不实现 bypass 授权。
- 不允许 Write/Edit/dangerous Bash。
- 不替代 build mode。
- 不实现计划文档自动落盘、人工审批或自动切换到 build mode。
- 不解决 TUI 展示细节。

## Decisions

### Decision 1: plan mode 是 AgentMode 的一种

plan mode 使用统一 AgentMode 枚举和工具过滤逻辑，而不是单独 prompt 开关。

理由：权限边界必须可测试，不能只依赖模型遵守提示。

### Decision 2: 输出 Plan Document，并同步 planning state

AgentLoop 在 plan mode 中应支持多轮计划讨论，并产出人读的 Markdown Plan Document；Plan Document 可以先作为草案存在，定稿后成为后续 build mode 的输入。其中的高层实施步骤同步到 PlanningManager，形成机器可读 planning state。自然语言回复作为讨论和解释层。

理由：用户需要审阅详细方案，而 Web/TUI/trace/benchmark 需要机器可读步骤。Plan Document 是主要交付物，planning state 是可观察索引，不是执行期 todo list。

### Decision 3: 只读工具白名单

plan mode 初始只允许 Read/Grep/ListFiles/Find/InspectGitDiff/WebSearch/WebFetch 等只读工具，以及 mode-specific 的 `UpdatePlan` / `ExitPlanMode` 工具。这两个工具只保存计划文档和步骤，不写工作区文件、不执行命令。

理由：计划阶段不应产生代码或环境副作用。

### Decision 4: 通过 UpdatePlan 迭代草案，通过 ExitPlanMode 定稿计划

AgentLoop 在 plan mode 中注入 plan-mode system context，引导模型在计划草案发生实质变化时调用 `UpdatePlan(title, plan_markdown, steps)`，在用户确认或计划已可定稿时调用 `ExitPlanMode(title, plan_markdown, steps)`。`UpdatePlan` 会发布 `plan_document_updated` 事件、记录 trace，并将 `steps` 写入 PlanningManager；`ExitPlanMode` 会发布 `plan_document_submitted` 事件、记录 trace，并将最终 `steps` 写入 PlanningManager。

理由：plan mode 是讨论和收敛计划的会话模式，不应强制每轮一次性定稿。不从 Markdown 文本中反向解析计划，避免自然语言格式漂移；也不把 Plan Document 降级成简单 todo list。

### Decision 5: 初版不自动落盘和审批

Plan Document 初版只作为运行期产物进入 event、trace、CLI 和 Web 展示。不自动写入 `.md` 文件，不提供批准按钮，也不自动切换到 build mode。

理由：自动落盘会打破 plan mode 的只读边界；审批与同 session 切换属于后续 runtime mode switching / approval workflow 范围。

## Risks / Trade-offs

- [Risk] 只读限制让某些调研无法运行测试。Mitigation: plan mode 明确非执行模式，测试建议写入计划。
- [Risk] 模型仍可能建议执行修改。Mitigation: 工具层拒绝写操作，UI 展示 mode。
- [Risk] planning state 过细导致噪声。Mitigation: 初版只记录高层步骤和状态。
- [Risk] 模型频繁更新草案造成噪声。Mitigation: prompt 要求草案发生实质变化时调用 `UpdatePlan`；trace 保留事件序列，Web 展示最新版本。
- [Risk] Plan Document 与 steps 不一致。Mitigation: trace 同时记录两者，Web 以 Plan Document 为审阅主产物，planning state 只作为索引。

## Testing Strategy

- Agent mode 测试覆盖 plan mode 工具过滤。
- CLI/Web 测试覆盖启动 plan mode。
- AgentLoop 测试覆盖 plan mode 通过 `UpdatePlan` 更新草案、通过 `ExitPlanMode` 输出最终 Plan Document 和 planning state。
- 负向测试覆盖 Write/Edit/Bash dangerous 被拒绝。
