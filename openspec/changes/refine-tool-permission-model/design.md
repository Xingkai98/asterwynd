## Context

MyAgent 当前权限模型由 `Tool.read_only`、`Tool.dangerous`、`Tool.allowed_modes` 和 `ModePolicy.is_tool_allowed()` 组成。当前实现：

- `build` mode 默认允许所有已注册工具。
- `read_only` 和 `plan` mode 只允许 `read_only=True and dangerous=False`。
- `allowed_modes` 用于 plan-only 工具，例如 `UpdatePlan` / `ExitPlanMode`。
- `dangerous` 目前主要由 Bash 使用，但 MCP / browser 等外部高风险工具会继续放大这个字段的语义压力。

这个模型的问题不是代码复杂，而是概念混叠：工具能做什么、风险多高、来自哪里、哪些 mode 允许它们，是四个不同问题。

## Goals / Non-Goals

**Goals:**

- 拆分工具权限的三条基础轴：capability、risk level、origin。
- 定义 mode permission profile，让 mode 通过 profile 判权。
- 保留兼容迁移路径，不一次性重写所有工具。
- 让 plan mode 在概念上从 read-only 中解耦，为后续低风险实验工具留空间。
- 为 MCP、browser、plugin/custom tool 和 subagent runtime 提供统一来源元数据。

**Non-Goals:**

- 本 change 不直接开放 plan mode 执行写入或 Bash。
- 本 change 不实现用户授权弹窗、approval workflow 或高权限 bypass。
- 本 change 不把 WorkspacePolicy 的路径/命令校验替换成 capability 模型；workspace safety 仍是实际执行前的强制边界。
- 本 change 不要求一次删除 `read_only` / `dangerous` 字段；它们先作为兼容字段保留。

## Decisions

### Decision 1: 将权限语义拆成 capability、risk level、origin 三条轴

Tool capability 描述工具能做什么，risk level 描述默认风险多高，origin/provenance 描述工具从哪里来。三者不互相替代。

理由：`dangerous` 当前混合了风险、隔离需求和外部来源的暗示。MCP 和 browser 引入后，如果继续把来源和风险混在一起，会让默认策略、审计展示和 mode policy 难以解释。

审议确认：2026-06-25，grill-with-docs。

### Decision 2: Agent Mode 绑定 permission profile，而不是硬编码 boolean 组合

ModePolicy 后续 SHALL 通过 permission profile 判权。profile 至少表达 allowed capabilities、max risk level 和 allow/deny override。

理由：`plan`、`read_only`、`build` 是运行意图，不应该永久绑定某个 Tool boolean 组合。profile 可以保持当前默认行为，同时为后续实验型 plan profile 和自定义 mode 留空间。

审议确认：2026-06-25，grill-with-docs。

### Decision 3: plan mode 概念上不等同 read_only，但默认 profile 保持保守

本 change 不默认开放 plan mode 写入、Bash 或外部副作用。plan 默认 profile 允许只读调研能力和 planning agent state 工具；后续如需“计划阶段实验”，通过单独 profile 和测试打开。

理由：计划阶段可能需要探索和实验，但默认 plan mode 仍应适合作为需求讨论和人工确认边界。把概念解耦和放权分开，可以避免一次改变用户可见安全边界。

审议确认：2026-06-25，grill-with-docs。

### Decision 4: 保留 legacy `read_only` / `dangerous` 兼容路径

迁移期继续保留 `read_only`、`dangerous` 和 `allowed_modes`，并从旧字段推导新 permission metadata。内置工具逐步显式标注 capability、risk level 和 origin。

理由：一次性改完所有工具和入口风险高。兼容路径可以让默认行为保持稳定，并支持 TDD 小步迁移。

审议确认：2026-06-25，grill-with-docs。

### Decision 5: 配置先支持内置 profiles 和 deny override，不立刻开放完整自定义 matrix

初始实现优先提供内置 permission profiles，并继续支持 `deny_tools`。完整自定义 capability/risk/origin matrix 需要额外 fail-fast 校验和测试，后续再开放。

理由：权限配置越灵活，测试矩阵越大。先把内部模型和默认 profile 稳定下来，再开放用户可配置矩阵更稳妥。

审议确认：2026-06-25，grill-with-docs。

### Decision 6: 本 change 仍是方向性设计，开发前必须继续确认

当前文档只确认了重构方向：Tool 提供 capability、risk level、origin 等多维元数据；Agent Mode 通过 permission profile 综合这些维度和 override 判定权限；未来用户可以组合不同维度取值形成扩展 profile。

具体实现细节还没有完全定稿。开发前必须再次使用 `grill-with-docs` 逐项确认 capability 枚举、risk level 取值、origin 枚举、profile 配置 schema、默认 profile 行为、兼容迁移顺序和测试矩阵，不得把本文档中的示例直接当成最终实现承诺。

理由：权限模型是安全边界，过早固化配置 matrix 会放大测试面和误配风险。先沉淀共同语言，再在实现前收敛细节。

审议确认：2026-06-25，grill-with-docs。

## Proposed Model

### Tool Capability

Capability 描述工具“能做什么”，不是风险等级，也不是来源。首批建议枚举：

- `workspace_read`: 读取 workspace 内文件、目录、git diff 或代码结构。
- `workspace_write`: 创建或修改 workspace 文件。
- `command_execute`: 执行 shell / subprocess 命令。
- `network_read`: 读取公网或内网远程资源。
- `external_side_effect`: 对外部系统产生写入、副作用或状态变更。
- `agent_state`: 修改 MyAgent 本地运行状态，例如 Plan Document、planning state、session mode。
- `subagent_control`: 创建、运行、取消或查看子 session。
- `browser_control`: 驱动浏览器或桌面环境。

一个工具可以有多个 capability。示例：

- Read: `{workspace_read}`
- Edit: `{workspace_write}`
- Bash: `{command_execute}`
- WebSearch: `{network_read}`
- UpdatePlan: `{agent_state}`
- MCP read file: `{workspace_read}` 或 `{network_read}`，取决于 server/tool 配置。
- Browser click: `{browser_control, external_side_effect}` 或 `{browser_control}`，取决于动作边界。

### Risk Level

Risk level 描述工具默认风险等级，独立于 capability 和 origin。建议从三档开始：

- `low`: 只读、可重复、失败影响局部。
- `medium`: 会修改本地 workspace 或 agent state，但边界清楚、可回滚或可审计。
- `high`: 命令执行、外部副作用不可控、浏览器/桌面操作、凭据/环境风险高，或能力未知。

`dangerous` 作为 legacy compatibility flag 保留，迁移期可由 `risk_level == high` 推导；新代码不应把 `dangerous` 当作来源标志。

### Tool Origin

Origin/provenance 描述工具“从哪里来”，不直接决定权限。首批建议：

- `builtin`: MyAgent 内置工具。
- `mcp`: MCP-backed tool。
- `plugin`: 本地插件或用户自定义扩展。
- `subagent`: subagent runtime tool。
- `browser`: browser/computer-use adapter tool。

origin 用于 trace、audit、UI 展示、默认风险推导和配置定位。比如 MCP tool 默认 `risk_level=high` 是因为能力未知，而不是因为 `origin=mcp` 永远高风险；用户显式配置后可以降低。

### Permission Profile / Mode Matrix

Agent Mode 不直接硬编码 `read_only and not dangerous`，而是绑定 permission profile。profile 至少包含：

- allowed capabilities
- max risk level
- denied tool names
- mode-specific allowed tool names 或 allowed origin（谨慎使用）

换句话说，未来权限判定会由 Tool 的多维元数据和 Mode 的 permission profile 共同完成：

```text
Tool metadata(capability, risk level, origin)
        +
Mode permission profile
        +
显式 allow/deny override
        +
WorkspacePolicy 执行前强制校验
        =
是否暴露 schema / 是否允许执行
```

用户未来可以通过配置选择或扩展 profile，组合不同 capability、risk level 和 origin 取值来表达新的 mode。但完整自定义 matrix 是否在首版开放、开放到什么粒度、如何校验非法组合，仍是开发前必须确认的问题。

建议默认 profile：

| Mode | Profile | 初始语义 |
| --- | --- | --- |
| `build` | `build_default` | 允许 low/medium，大多数内置写工具可用；high 工具按现有行为可用，后续可接 approval。 |
| `read_only` | `read_only_default` | 允许 `workspace_read`、`network_read`，max risk `low`，拒绝 workspace write / command / external side effect。 |
| `plan` | `plan_default` | 允许 read-only 调研能力和 `agent_state` 中的 planning tools，默认不允许 workspace write / command。它不是 read_only 的同义词，只是当前 profile 很接近 read_only。 |
| `bypass` | `fail_closed` | 继续内部保留，默认 fail closed。 |

后续如果要支持“计划阶段实验”，可以新增 profile，例如 `plan_with_experiments`：

- 允许 `workspace_read`、`network_read`、`agent_state`。
- 允许明确标注为 `safe_experiment` 或 medium risk 的短时本地验证工具。
- 仍拒绝 destructive、external side effect 和未审计 high risk 工具。

这个 profile 必须单独设计和测试，不在本 change 默认打开。

## Migration Strategy

### Phase 1: Additive metadata

- 新增 `ToolPermission` 或等价 dataclass，包含 capabilities、risk_level、origin、allowed_modes。
- `Tool` 保留 `read_only` / `dangerous`，并提供从 legacy 字段推导新 metadata 的默认逻辑。
- ToolRegistry 和 ModePolicy 先支持新旧模型并存。

### Phase 2: Builtin tool annotation

- 为内置工具显式标注 capabilities、risk_level、origin。
- 测试覆盖现有 mode 行为不变。
- `dangerous` 继续由新 metadata 推导或保持兼容。

### Phase 3: Mode profile

- ModePolicy 改为读取 permission profile。
- 默认 profile 必须保持现有用户可见行为基本不变：read_only/plan 仍不暴露 Write/Edit/Bash。
- 配置中仍保留 deny_tools；新增 profile 配置作为后续可选能力。

### Phase 4: External adapters

- MCP/browser/plugin/subagent tools 使用 origin + capabilities + risk_level。
- 外部工具默认 high risk，除非配置或 adapter 规则明确降低风险。

## Decisions To Confirm Before Implementation

1. capability 枚举是否足够表达首批内置工具、MCP 和 browser。
2. risk level 是否使用 `low/medium/high` 三档，还是需要 `critical` 或 approval requirement。
3. plan 默认 profile 是否保持当前保守行为，只在后续 profile 中允许实验。
4. `dangerous` 是否在迁移期保留为 derived/legacy 字段，而不是立即删除。
5. 用户配置是否先只支持 deny_tools + 内置 profiles，还是允许完整自定义 matrix。
6. 用户可扩展 profile 的 schema 和校验规则，包括未知 capability、risk level、origin、tool name 和互相矛盾配置的 fail-fast 行为。

当前推荐：先做 additive metadata + 默认 profiles，不立即开放完整自定义 matrix。这样能把概念拆开，又不一次性放大配置和测试矩阵。

## Risks / Trade-offs

- [Risk] 权限模型过度抽象，短期实现成本高。Mitigation: 分阶段迁移，第一阶段保持现有行为不变。
- [Risk] capability 枚举不完整。Mitigation: 从内置工具、MCP、browser 的已知需求出发，只引入必要枚举，后续可扩展。
- [Risk] plan mode 语义变化造成用户困惑。Mitigation: 概念上解耦，但默认 profile 保持当前保守行为。
- [Risk] 配置矩阵太灵活导致安全边界难测。Mitigation: 初期只提供内置 profiles 和 deny override，完整自定义 matrix 后续再开放。

## Testing Strategy

- ModePolicy 单元测试覆盖新 metadata 和 legacy 字段等价行为。
- ToolRegistry 测试覆盖 schema filter 和 execute 前重新判权。
- 内置工具测试覆盖 capabilities、risk_level、origin 标注。
- CLI/Web/benchmark mode 入口测试确认 read_only/plan/build 行为保持不变。
- 外部 tool fake 测试覆盖 origin 不直接决定权限。
- benchmark smoke 确认核心 agent loop 仍能完成任务。
