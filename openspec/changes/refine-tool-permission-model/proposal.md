## Why

当前 Tool 权限模型只有 `read_only`、`dangerous` 和 `allowed_modes`。这个模型能支撑早期 read-only/build/plan 边界，但随着 MCP、browser/computer use、自定义扩展、subagent runtime 和未来可实验 plan mode 增加，两个 boolean 开始承载过多语义：

- `dangerous` 同时像风险等级、隔离需求和高副作用标记。
- 外部来源的 tool 容易被误解为天然 dangerous，但来源和风险是两条不同概念轴。
- `plan` mode 当前被实现为 read-only 同义策略，难以表达“允许低风险实验，但仍不允许提交写入”的计划阶段。
- 用户自定义 profile 只能通过 deny list 收紧，不能用清晰的能力矩阵表达允许范围。
- 高风险工具目前只有允许/拒绝两种结果，无法表达“当前 profile 可用，但必须由用户审批”的交互。

本 change 目标是重构工具权限模型，让 Tool metadata、mode policy、workspace safety、用户审批和外部工具接入有可扩展的共同语言。

当前 change 已确认权限模型的主方向：工具提供多维元数据，mode 绑定 permission profile，profile 产出 `allow` / `deny` / `require_approval` 三值判定，CLI 和 Web UI 支持真实审批交互。它仍不是可直接实现的最终方案；真正开始开发前，必须继续用 `grill-with-docs` 充分讨论 capability 枚举、risk 分级、profile 配置 schema、审批数据展示、subagent 审批策略、默认行为兼容策略和测试矩阵。

## Change Type

- primary: feature
- secondary: [refactor]

## What Changes

- 引入 Tool capability、risk level 和 origin/provenance 三条独立元数据轴。
- Agent mode SHALL 通过 permission profile / policy matrix 判定工具可见性和执行权限，而不是硬编码 `read_only and not dangerous`。
- Permission profile SHALL 综合 capability、risk level 和显式 override，产出 `allow`、`deny` 或 `require_approval`；origin 初始不直接参与 allow/deny，只用于审计、展示、默认推导和配置定位。
- 用户 SHALL 可以在既有 Agent Mode 下选择或定义自定义 permission profile；本 change 不引入用户自定义 Agent Mode。
- 引入可注入的 ApprovalHandler 抽象，AgentLoop 在执行 `require_approval` 工具前请求审批。
- CLI interactive mode 和 Web UI SHALL 支持真实审批交互；CLI single-prompt、benchmark 和没有审批通道的 runtime SHALL fail closed；TUI 预留同一抽象但不实现 UI。
- 保留兼容层，把现有 `read_only` / `dangerous` 映射到新模型，分阶段迁移内置工具。
- `dangerous` 语义 SHALL 收敛为 legacy compatibility flag；新实现应优先使用 capability + risk level。
- `plan` mode SHALL 不再在概念上等同 `read_only`，而是绑定默认保守 permission profile；是否允许实验型工具由 profile 明确表达。

## Capabilities

### Modified Capabilities

- `tool-system`: 工具权限元数据从两个 boolean 演进为 capability / risk / origin 模型。
- `agent-modes`: mode policy 从硬编码规则演进为 profile / matrix。
- `agent-runtime`: AgentLoop 在工具执行前处理三值权限判定和用户审批。
- `workspace-safety`: workspace policy 与 tool capability 的关系需要明确。
- `configuration`: 后续支持 mode profile 和 tool permission override 的配置结构。
- `cli`: interactive CLI 支持工具审批，single-prompt 入口对需审批工具 fail closed。
- `web-ui`: Web session 支持审批请求、用户决定和结果回传。

## Impact Analysis

- 影响代码：
  - `agent/tools/base.py`
  - `agent/tools/registry.py`
  - `agent/run_config.py`
  - `agent/loop.py`
  - `agent/approval.py` 或等价审批抽象
  - `agent/tools/factory.py`
  - 内置工具 metadata
  - 配置解析路径
  - CLI interactive / single-prompt 入口
  - Web UI session 和工具调用事件路径
- 影响测试：
  - `tests/agent/test_run_config.py`
  - AgentLoop approval 相关测试
  - `tests/agent/tools/test_registry.py`
  - `tests/agent/tools/test_factory.py`
  - CLI/Web/benchmark mode 和审批入口测试
- 影响文档：
  - `CONTEXT.md`
  - `openspec/specs/tool-system/spec.md`
  - `openspec/specs/agent-modes/spec.md`
  - `docs/architecture.md`
  - `docs/testing-guide.md`

## Reference Implementation Research

- status: enabled
- reason: 工具权限模型会影响 MCP、browser、自定义工具和 mode policy，应参考其他 coding-agent 对工具风险、权限审批和外部工具来源的建模方式。
- research questions:
  - Codex、Claude Code、opencode、OpenClaw 等项目如何表达工具能力、风险和来源？
  - 需审批工具如何在 CLI/Web/TUI 或 headless 场景中 fail closed？
  - 外部工具协议接入时，权限 metadata 应归属 registry、tool schema 还是 runtime policy？
- findings:
  - 本次仅为参考实现调研门禁的结构迁移，尚未完成本 change 的针对性横向调研。
  - 当前工作区 `.dev/reference-repos.txt` 存在，可用于开发前调研；真正开始实现前必须补充具体参考仓库发现。
- design impact:
  - 当前 proposal 已保留 capability、risk、origin 和 approval 的设计方向；实现前需要用参考实现调研校验这些轴是否足以覆盖 MCP、browser 和自定义工具。
  - 如果调研发现更合适的权限模型，应先回写本 change 的 design/spec/tasks，再进入实现。
