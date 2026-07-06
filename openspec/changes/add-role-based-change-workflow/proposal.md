## Why

当前 OpenSpec lifecycle 已经能支撑“一个 agent 从讨论到实现再到归档”的单线流程，但实际开发中经常需要把设计、实现、审阅和修改解耦：

- 一个模型或 agent 负责需求/设计，另一个模型或 agent 负责实现。
- 实现完成后，原设计者或更强审阅模型对实现做审阅。
- 审阅发现问题后，开发 agent 根据结构化 findings 修改，再进入下一轮审阅。
- 简单 change 仍然允许同一个 agent 从头做到尾，不应被强制多角色化。

如果不把这些阶段和交接 artifact 明确下来，多模型协作会退化成依赖聊天上下文：实现者不知道哪些设计结论是最终版，审阅者不知道实现偏离是否被接受，后续 agent 也无法从仓库内追溯每轮修改原因。

本 change 目标是把 change lifecycle 从“单 agent 顺序执行”升级为“角色化、可交接、可审阅”的流程规则，但暂不实现自动调度或模型分配系统。

## Change Type

- primary: process
- secondary: []

## What Changes

- OpenSpec change workflow SHALL 定义角色概念：Designer、Implementer、Reviewer、Closer。
- 同一个 agent MAY 扮演多个角色；不同 agent/model MAY 分别承担不同角色。
- 设计阶段 SHALL 产出足够让另一个 agent 独立实现的 handoff 信息。
- 实现阶段如果发现设计不成立，SHALL 先回写 change artifact，再继续无关实现。
- 审阅阶段 SHALL 使用结构化 Implementation Review 记录 blocking findings、non-blocking findings、spec mismatches、test gaps、architecture concerns、required changes 和 accepted deviations。
- 修改轮次 SHALL 回写 review findings 的处理结果，形成可追溯 revision loop。
- 归档前 SHALL 确认所有 blocking findings 已关闭或转为明确接受的 deviation。
- 本 change 不引入模型自动选择、任务派发、并发锁、外部 review 服务或 GitHub review automation。

## Capabilities

### Modified Capabilities

- `change-documentation`: OpenSpec change 文档流程增加角色化阶段、handoff、implementation review 和 revision loop。

## Impact Analysis

- AgentLoop: 不影响运行时。
- Tool system: 不影响工具协议。
- Workspace safety: 不影响路径或命令安全。
- Agent modes / permissions: 不影响 mode 权限。
- CLI: 不影响 CLI 行为。
- Web UI: 不影响 Web 行为。
- TUI: 不影响 TUI 行为。
- Benchmark: 不影响 benchmark runner。
- Trace / logs / artifacts: 不影响运行 trace；新增的 review/handoff 是 OpenSpec change artifact。
- Config / env: 不影响配置和环境变量。
- Specs: 修改 `change-documentation` capability。
- Tests: 需要覆盖 artifact checker 或模板规则，具体实现阶段确认。
- Docs: 影响 `AGENTS.md`、`docs/requirements-process.md`、`openspec/templates/tasks.md` 和相关 OpenSpec 文档。
- Migration / compatibility: 现有 active changes 不强制立即进入多角色流程；开始开发时按新规则补齐必要 review/handoff 结构。
- Explicitly not affected: 不实现自动模型调度，不要求所有 change 必须多人或多模型参与。
