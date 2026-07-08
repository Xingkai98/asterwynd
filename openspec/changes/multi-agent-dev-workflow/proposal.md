## Why

当前开发流程（explore → propose → grill-with-docs → apply → sync → archive）是一条单 agent 线性流水线，没有正式的状态机模型、没有 agent 角色拆分、没有 agent 间交接机制，也没有结构化的人工审批 gate。每次 agent 启动都需要人手动描述上下文或让 agent 自己去读文档冷启动。将流程建模为状态机、拆分为可独立执行的阶段角色，并引入 agent 间 handoff 和 human-in-the-loop gate，可以让多个专门化 agent 协作完成一个 change，也可以让一个 agent 从头做到尾，同时让整个流程可追踪、可校验、可路由。

## What Changes

- 新增 **开发流程状态机**：定义 change 全生命周期的 phase、sub_state、合法流转路径和 gate 点
- 新增 **`handoff.json`**：change 目录下的结构化全局状态文件，作为 agent 交接和工具链校验的唯一数据源
- 新增 **四个 agent 角色**：Planner（规划）、Reviewer（审查）、Builder（构建）、Closer（收尾），分别对应开发流程的阶段组合
- 新增 **handoff note 机制**：agent 间交接时生成自然语言上下文文档（优先使用 handoff skill，不可用时内置等价 prompt fallback），与 `handoff.json` 互补
- 新增 **human review gate**：每个 phase 末端设置人工审批点，人在 gate 点可确认通过、跳过下一阶段或回退
- 新增 **回退路径**：人在任意阶段可发起回退到之前的 phase + sub_state，或 agent 在实现中发现问题时可建议回退

## Capabilities

### New Capabilities

- `dev-workflow-state-machine`: 开发流程状态机，定义 change 生命周期的 phase/sub_state、handoff.json schema、流转规则、human review gate 和回退机制

### Modified Capabilities

- `change-documentation`: change 目录下新增 `handoff.json` 状态机文件；新增 `.handoff/` 目录存放自然语言交接笔记
- `subagents`: 新增 Planner / Reviewer / Builder / Closer 四个角色 agent 的类型定义和路由规则

## Change Type

- primary: feature
- secondary: [process]

## Impact Analysis

- **AgentLoop**: 影响 — 角色 agent 作为 subagent 运行，复用现有 AgentLoop 和 subagent runtime
- **Tool system**: 不影响 — 角色 agent 使用现有工具集
- **Workspace safety**: 不影响
- **Agent modes / permissions**: 影响 — 角色 agent 是新的 agent mode 类型，需要权限模型对应适配
- **CLI**: 影响 — 可能需要新增路由命令或 change 状态查询命令
- **Web UI**: 影响 — gate 审批点需要在 Web UI 中展示待审批 change
- **TUI**: 不影响（预留能力）
- **Benchmark**: 不影响 — 但后续可能需要多 agent 协作场景的 benchmark 任务
- **Trace / logs / artifacts**: 影响 — transition log 和 handoff note 需纳入可观测体系
- **Config / env**: 影响 — 可能需要配置 handoff 目录路径、是否强制 gate 审批
- **Specs**: 影响 — 新增 `dev-workflow-state-machine` capability；更新 `change-documentation` 和 `subagents` capability
- **Tests**: 新增 — 状态机流转单测、handoff.json schema 校验测试、角色 agent 路由测试
- **Docs**: 影响 — 更新 `docs/requirements-process.md` 开发流程章节，更新 `AGENTS.md` 自然语言路由表
- **Migration / compatibility**: 不影响 — 现有单 agent 全流程执行路径保持不变，状态机为增量引入
- **Explicitly not affected**: `tool-system`, `coding-tools`, `research-tools`, `mcp-integration`, `code-intelligence`, `memory-context`, `skills`, `configuration`

## Reference Implementation Research

- status: disabled
- reason: 本 change 的核心是项目自身的开发流程建模，外部参考仓库（如 Claude Code、Codex）的开发流程与 Asterwynd 的 OpenSpec + grill-with-docs + human review gate 流程差异较大，参考价值有限。状态机 schema 设计和 agent 角色拆分主要依赖项目内部的流程定义和讨论中已确认的设计方向。
