## Context

CLI 单轮模式适合脚本调用，Web UI 适合浏览器调试，但本地长任务缺少一个终端内实时视图。TUI 应展示 AgentLoop 运行事件、消息、工具调用和 planning state，而不是创建新的运行协议。

本 change 依赖已有 AgentLoop 和后续 structured planning state。

## Goals / Non-Goals

**Goals:**

- 新增最小 TUI 命令入口。
- 复用 AgentLoop、tool events、planning state 和 session 语义。
- 展示对话、工具调用进度、planning state 和最终摘要。
- 保持 CLI/Web/TUI 运行协议一致。

**Non-Goals:**

- 不实现 IDE 或文件编辑器。
- 不实现鼠标驱动复杂交互。
- 不重新实现 AgentLoop。
- 不在本 change 中定义新的 planning 数据模型。

## Decisions

### Decision 1: TUI 消费统一运行事件

TUI 不直接解析内部 messages，而是消费 AgentLoop/Web/trace 共用的运行事件或轻量 adapter。

理由：减少 CLI、Web、TUI 三套展示逻辑分裂。

### Decision 2: 先做只读 runtime view

初版 TUI 聚焦展示，不提供复杂输入控件、任务编辑或内置文件操作。

理由：先验证事件模型和展示价值，再扩展交互能力。

### Decision 3: 终端渲染与运行状态分离

TUI renderer 只负责布局和刷新，session/agent 状态仍由现有 runtime 管理。

理由：避免把终端 UI 状态混进 AgentLoop。

## Pre-Implementation Review

- Questions resolved:
  - 本 change 尚未按当前新增的 Impact Analysis / Pre-Implementation Review 规则完成开发前设计追问。
- Options considered:
  - 保留原设计，等待开始开发时完整追问。
  - 在本次流程治理 change 中伪造完整追问结论。
- Rejected alternatives:
  - 伪造完整追问结论。原因：TUI 依赖 runtime events、tool display policy、planning state 和权限展示的最新状态，必须在真正开发前重新确认。
- Final confirmations:
  - 开发前必须重新使用 `grill-with-docs` 或等价设计追问确认事件消费模型、终端降级策略、键盘交互、测试方式和非交互环境行为。
- Remaining risks:
  - TUI scope 容易扩大到交互控制面；开发前需要再次守住最小 runtime view 范围。

## Risks / Trade-offs

- [Risk] TUI 与 Web 展示语义不一致。Mitigation: 复用相同事件字段和 planning state。
- [Risk] 终端环境差异导致渲染不稳定。Mitigation: 单元测试覆盖状态转换，渲染快照保持最小。
- [Risk] 长输出撑坏布局。Mitigation: 默认折叠工具详情，保留展开入口。

## Testing Strategy

- CLI 命令测试覆盖 TUI 入口参数。
- TUI 状态 reducer 测试覆盖消息、工具调用、planning 更新。
- 快照或文本渲染测试覆盖关键布局。
- 手动 smoke 覆盖一次 fake agent 长任务展示。
