# Proposal: 开发流程自动化 — 验收 Gate + 状态追踪 + ADR 嵌入

## Change Type

- primary: process
- secondary: []

## Context

当前 Asterwynd 有 1800 行五阶段状态机（`agent/workflow/`），定义了 planning → reviewing → building → code-review → closing 五个 phase 及各自的 sub_state 序列，但存在两个关键缺口：

1. **Agent 不知道状态**：状态机代码和 `handoff.json` 已存在，但 agent 冷启动时从不读取。每次新会话从零开始，不知道当前在哪个 phase、该做什么、什么时候该停。
2. **ADR 飘在设计文档里**：设计决策散落在 `design.md` 的自由文本中，没有标准化的 ADR 格式。备选方案、拒绝原因、重访条件不可机械追溯。
3. **没有强制停止点**：agent 一直推进，没有机制在关键节点停止并等待人工审核。

目标：让 agent 每次启动自动感知状态、知道在哪里停、设计决策可追溯。

## Goals

- 会话启动协议：agent 每次进入仓库自动执行状态检查，根据结果决定行为
- Gate 机制：每个 phase 的 `ready_for_review` sub_state 是强制停止点，必须运行机械验证并等待人工批准
- 阶段内自动推进：非 gate 状态下 agent 可自动完成 sub_state 任务并推进
- Worktree 隔离：building phase 必须在独立 git worktree 中进行
- ADR 嵌入：handoff note 的 Key Decisions 支持 ADR 格式，有 ≥2 备选方案的决策必须建 ADR
- 机械验证可脚本化：每个 phase 的完成条件可通过 CLI 脚本验证

## Non-Goals

- 不修改现有五阶段状态机的 phase 定义和 sub_state 序列
- 不改变 OpenSpec 的 spec delta 格式或校验规则
- 不改变 agent/workflow 的 routing/dispatch 机制
- 不给已有 active change（缺 handoff.json）自动补齐状态文件

## Impact Analysis

- AgentLoop: 不受影响
- Tool system: 不受影响
- Workspace safety: 不受影响（worktree 隔离增强了安全性）
- Agent modes / permissions: 不受影响
- CLI: 不受影响
- Web UI: 不受影响
- TUI: 不受影响
- Benchmark: 不受影响（building phase 验证中包含可选 benchmark smoke）
- Trace / logs / artifacts: 新增 `.handoff/` 下的 gate-approvals.json 和 handoff notes
- Config / env: 不受影响
- Specs: 不受影响
- Tests: 新增 `tests/test_check_phase_done.py`
- Docs: 修改 AGENTS.md、requirements-process.md、role_registry.py system prompts
- Migration / compatibility: 完全向后兼容——无 handoff.json 的旧 change 不受影响
- Explicitly not affected: AgentLoop 运行时、工具协议、WebSocket、benchmark runner

## Reference Implementation Research

- status: enabled
- reason: 业界 coding-agent 项目有成熟的 workflow state tracking 模式
- research questions:
  - 业界 coding agent 如何管理开发流程状态的持久化和自动感知？
  - Gate/review 机制在 SDD（Spec-Driven Development）项目中如何落地？
  - ADR 如何嵌入 agent 工作流？
- findings:
  - Anthropic Claude Code 的 CLAUDE.md / AGENTS.md 作为 pre-flight checklist，每次会话自动加载
  - OpenSpec 生态通过 handoff.json 追踪 change lifecycle，但 agent 执行侧缺乏自动读取
  - SDD 核心原则：operator 决策前置（planning phase），AI 执行在后（building phase），中间通过机械 gate 分隔
  - ADR 在业界是成熟模式（Michael Nygard 2011），嵌入 handoff 流程使决策可追溯、可重访
- design impact:
  - 采用 AGENTS.md 驱动模式：每次冷启动运行 `workflow_state.py discover`
  - 状态与验证分离：`workflow_state.py`（CRUD）≠ `check_phase_done.py`（只读）
  - ADR 嵌入 handoff note，通过 `FALLBACK_HANDOFF_PROMPT` 要求格式
