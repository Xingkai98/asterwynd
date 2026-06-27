## Context

MyAgent 当前权限模型由 `Tool.read_only`、`Tool.dangerous`、`Tool.allowed_modes` 和 `ModePolicy.is_tool_allowed()` 组成。当前实现：

- `build` mode 默认允许所有已注册工具。
- `read_only` 和 `plan` mode 只允许 `read_only=True and dangerous=False`。
- `allowed_modes` 用于 plan-only 工具，例如 `UpdatePlan` / `ExitPlanMode`。
- `dangerous` 目前主要由 Bash 使用，但 MCP / browser 等外部高风险工具会继续放大这个字段的语义压力。

这个模型的问题不是代码复杂，而是概念混叠：工具能做什么、风险多高、来自哪里、哪些 profile 允许它们、哪些工具需要用户审批，是不同问题。

## Goals / Non-Goals

**Goals:**

- 拆分工具权限的三条基础元数据轴：capability、risk level、origin。
- 定义 mode permission profile，让 mode 通过 profile 判权。
- 将权限判定从 boolean 扩展为 `allow` / `deny` / `require_approval`。
- 支持用户在既有 Agent Mode 下选择或定义自定义 permission profile。
- 为 CLI interactive mode 和 Web UI 提供真实用户审批交互。
- 通过可注入审批抽象为未来 TUI 预留接入点。
- 保留兼容迁移路径，不一次性重写所有工具。
- 让 plan mode 在概念上从 read-only 中解耦，为后续低风险实验工具留空间。
- 为 MCP、browser、plugin/custom tool 和 subagent runtime 提供统一来源元数据。

**Non-Goals:**

- 本 change 不直接开放 plan mode 执行写入或 Bash。
- 本 change 不实现高权限 bypass 或“无需审计的全放开模式”。
- 本 change 不引入用户自定义 Agent Mode；用户扩展的是 permission profile，并绑定到现有 mode。
- 本 change 不实现 TUI 审批 UI，只保留 ApprovalHandler 抽象。
- 本 change 不把 WorkspacePolicy 的路径/命令校验替换成 capability 模型；workspace safety 仍是实际执行前的强制边界。
- 本 change 不要求一次删除 `read_only` / `dangerous` 字段；它们先作为兼容字段保留。

## Decisions

### Decision 1: 将权限语义拆成 capability、risk level、origin 三条轴

Tool capability 描述工具能做什么，risk level 描述默认风险多高，origin/provenance 描述工具从哪里来。三者不互相替代。

理由：`dangerous` 当前混合了风险、隔离需求和外部来源的暗示。MCP 和 browser 引入后，如果继续把来源和风险混在一起，会让默认策略、审计展示和 mode policy 难以解释。

审议确认：2026-06-25，grill-with-docs。

### Decision 2: Agent Mode 绑定 permission profile，而不是硬编码 boolean 组合

ModePolicy 后续 SHALL 通过 permission profile 判权。profile 至少表达 allowed capabilities、risk threshold、approval threshold 和 explicit deny override。

理由：`plan`、`read_only`、`build` 是运行意图，不应该永久绑定某个 Tool boolean 组合。profile 可以保持当前默认行为，同时为后续实验型 plan profile 和用户自定义 profile 留空间。

审议确认：2026-06-25，grill-with-docs。

### Decision 3: plan mode 概念上不等同 read_only，但默认 profile 保持保守

本 change 不默认开放 plan mode 写入、Bash 或外部副作用。plan 默认 profile 允许只读调研能力和 planning agent state 工具；后续如需“计划阶段实验”，通过单独 profile 和测试打开。

理由：计划阶段可能需要探索和实验，但默认 plan mode 仍应适合作为需求讨论和人工确认边界。把概念解耦和放权分开，可以避免一次改变用户可见安全边界。

审议确认：2026-06-25，grill-with-docs。

### Decision 4: 保留 legacy `read_only` / `dangerous` 兼容路径

迁移期继续保留 `read_only`、`dangerous` 和 `allowed_modes`，并从旧字段推导新 permission metadata。内置工具逐步显式标注 capability、risk level 和 origin。

理由：一次性改完所有工具和入口风险高。兼容路径可以让默认行为保持稳定，并支持 TDD 小步迁移。

审议确认：2026-06-25，grill-with-docs。

### Decision 5: 支持用户自定义 permission profile，但不支持自定义 Agent Mode

配置应允许用户在既有 mode 下选择内置 profile，或定义自定义 profile。自定义 profile 由 capability、risk threshold、approval threshold 和 explicit deny 组成；本 change 不让用户新增任意 mode 名称或改变 AgentLoop 的 mode 语义。

理由：用户需要灵活组合权限边界，例如“build 里 high risk 都要审批”或“plan 里允许低风险实验工具”。但 mode 影响 prompt、工具集合、运行流程和 UI 行为，自定义 mode 会把范围扩大到 agent runtime 语义，不适合与本次权限重构混在一起。

审议确认：2026-06-25，grill-with-docs。

### Decision 6: Profile 判权结果是三值，而不是 boolean

Permission profile 的最终工具权限判定 SHALL 是：

- `allow`: 可以暴露 schema，并可在执行前再次判权后直接执行。
- `deny`: 不暴露 schema；如果模型仍调用，返回可读权限错误作为 tool result。
- `require_approval`: 可暴露 schema；执行前必须通过 ApprovalHandler 获得用户批准。

建议 profile 字段：

- `allowed_capabilities`: profile 允许考虑的 capability 集合。
- `auto_approve_max_risk`: 不需要用户确认即可执行的最高风险等级。
- `approval_required_max_risk`: 可以通过用户审批执行的最高风险等级。
- `denied_tools`: 显式拒绝的 tool name 集合。

判定顺序建议：

1. `allowed_modes` 是 tool 侧硬门槛；当前 mode 不匹配则 `deny`。
2. `denied_tools` 是 profile 侧显式拒绝；命中则 `deny`。
3. tool capability 不在 `allowed_capabilities` 内则 `deny`。
4. risk level 小于等于 `auto_approve_max_risk` 则 `allow`。
5. risk level 小于等于 `approval_required_max_risk` 则 `require_approval`。
6. 其他情况 `deny`。

理由：最终 runtime 关心的不是抽象分数，而是“能不能执行、是否需要人工确认”。三值判定可以保持模型简单，同时覆盖高风险但可审计的工具场景。

审议确认：2026-06-25，grill-with-docs。

### Decision 7: ApprovalHandler 由 AgentLoop 注入，CLI/Web 实现真实审批

AgentLoop SHALL 依赖一个审批抽象，例如：

```python
class ApprovalHandler(Protocol):
    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        ...
```

CLI interactive mode 和 Web UI SHALL 提供真实审批 handler。CLI single-prompt、benchmark、无 UI runtime 和默认测试 handler SHALL fail closed。TUI 后续可以实现同一接口。

subagent 的审批策略尚未最终确认：首版推荐 fail closed，或者由 parent session 显式委托审批。开发前必须再次确认，不能默认让 subagent 自行绕过审批。

理由：审批是 runtime 交互，不应塞进 ToolRegistry 或工具实现。通过 handler 注入可以让不同入口按交互能力处理，同时保持 AgentLoop 的工具调用链一致。

审议确认：2026-06-25，grill-with-docs。

### Decision 8: 审批必须保持 tool-call 消息链合法并可审计

当模型调用 `require_approval` 工具时：

- 用户批准后，AgentLoop 执行工具，并追加正常 tool result。
- 用户拒绝、审批超时或当前入口不支持审批时，AgentLoop 不执行工具，并追加可读的拒绝/不可用 tool result。
- 审批请求、用户决定、风险等级、capability、origin、tool name 和必要参数摘要 SHALL 进入 trace/debug/display 可见路径。

理由：LLM tool-call 协议要求每个工具调用有对应结果。审批拒绝也必须作为 tool result 返回，而不是中断后伪造 assistant 回复或丢失 tool-call 链。

审议确认：2026-06-25，grill-with-docs。

### Decision 9: 本 change 仍需开发前再次确认细节

当前文档确认了权限 profile 和审批流的主方向，但具体枚举、配置 schema、审批 UI 文案、参数预览和 subagent 策略还没有完全定稿。开发前必须再次使用 `grill-with-docs` 逐项确认，不得把本文档中的示例直接当成最终实现承诺。

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

Risk level 描述工具默认风险等级，独立于 capability 和 origin。它不是精确业务分类，而是 profile 用来决定直接执行、审批或拒绝的粗粒度输入。建议从三档开始：

- `low`: 只读、可重复、失败影响局部。
- `medium`: 会修改本地 workspace 或 agent state，但边界清楚、可回滚或可审计。
- `high`: 命令执行、外部副作用不可控、浏览器/桌面操作、凭据/环境风险高，或能力未知。

`dangerous` 作为 legacy compatibility flag 保留，迁移期可由 `risk_level == high` 推导；新代码不应把 `dangerous` 当作来源标志。

是否需要 `critical` 暂不确定。当前倾向先使用 `high + require_approval` 表达“可用但必须审批”，避免 risk level 同时承担“风险大小”和“审批要求”两种语义。

### Tool Origin

Origin/provenance 描述工具“从哪里来”，初始不直接决定权限。首批建议：

- `builtin`: MyAgent 内置工具。
- `mcp`: MCP-backed tool。
- `plugin`: 本地插件或用户自定义扩展。
- `subagent`: subagent runtime tool。
- `browser`: browser/computer-use adapter tool。

origin 用于 trace、audit、UI 展示、默认风险推导和配置定位。比如 MCP tool 默认 `risk_level=high` 是因为能力未知，而不是因为 `origin=mcp` 永远高风险；用户显式配置后可以降低。

### Permission Profile / Mode Matrix

Agent Mode 不直接硬编码 `read_only and not dangerous`，而是绑定 permission profile。profile 至少包含：

- `allowed_capabilities`
- `auto_approve_max_risk`
- `approval_required_max_risk`
- `denied_tools`

换句话说，未来权限判定会由 Tool 的多维元数据和 Mode 的 permission profile 共同完成：

```text
Tool metadata(capability, risk level, origin)
        +
Mode permission profile
        +
显式 deny override
        +
ApprovalHandler(仅 require_approval 时)
        +
WorkspacePolicy 执行前强制校验
        =
是否暴露 schema / 是否直接执行 / 是否请求审批 / 是否拒绝
```

用户可以通过配置选择或扩展 profile，组合不同 capability 和 risk threshold 来表达新的权限边界。origin 初始不作为 profile allow/deny 条件，除非后续明确需要 origin-specific policy；这样可以避免“外部来源天然危险”的误解。

建议默认 profile：

| Mode | Profile | 初始语义 |
| --- | --- | --- |
| `build` | `build_default` | 允许常用 build capability；low/medium 自动执行；high 需要审批。为兼容现有行为，是否首版让 Bash 从自动执行改为审批必须开发前再次确认。 |
| `read_only` | `read_only_default` | 允许 `workspace_read`、`network_read`，low 自动执行；不通过审批升级到 workspace write / command / external side effect。 |
| `plan` | `plan_default` | 允许 read-only 调研能力和 `agent_state` 中的 planning tools，low 自动执行；默认不允许 workspace write / command。它不是 read_only 的同义词，只是当前 profile 很接近 read_only。 |
| `bypass` | `fail_closed` | 继续内部保留，默认 fail closed。 |

后续如果要支持“计划阶段实验”，可以新增 profile，例如 `plan_with_experiments`：

- 允许 `workspace_read`、`network_read`、`agent_state`。
- 允许明确标注为 medium risk 的短时本地验证工具进入审批或自动执行，取决于 profile 阈值。
- 仍拒绝 destructive、external side effect 和未审计 high risk 工具。

这个 profile 必须单独设计和测试，不在本 change 默认打开。

### Approval Request

ApprovalRequest 至少应携带：

- run/session id 和 current mode。
- tool name、origin、capabilities、risk level。
- tool arguments 的可展示摘要。
- profile 判定原因，例如命中 high risk 或超过 auto approval threshold。
- timeout 或 unavailable 行为。

ApprovalResponse 至少表达：

- approved / denied / unavailable / timeout。
- 决策来源，例如 CLI user、Web user、fail-closed handler。
- 可选用户备注或拒绝理由。

参数摘要需要开发前确认截断、敏感字段隐藏和大对象展示规则。

## Migration Strategy

### Phase 1: Additive metadata

- 新增 `ToolPermission` 或等价 dataclass，包含 capabilities、risk_level、origin、allowed_modes。
- 新增 PermissionDecision 类型，表达 `allow` / `deny` / `require_approval`。
- `Tool` 保留 `read_only` / `dangerous`，并提供从 legacy 字段推导新 metadata 的默认逻辑。
- ToolRegistry 和 ModePolicy 先支持新旧模型并存。

### Phase 2: Profile and approval skeleton

- ModePolicy 改为读取 permission profile 并返回三值判定。
- 新增 ApprovalRequest / ApprovalResponse / ApprovalHandler 和 FailClosedApprovalHandler。
- AgentLoop 在工具执行前处理 `require_approval`。
- ToolRegistry 继续在 schema filter 和 execute 前重新判权，避免过期 schema 绕过。

### Phase 3: Builtin tool annotation

- 为内置工具显式标注 capabilities、risk_level、origin。
- 测试覆盖现有 mode 行为和审批行为。
- `dangerous` 继续由新 metadata 推导或保持兼容。

### Phase 4: CLI/Web approval

- CLI interactive mode 实现阻塞式审批提示。
- CLI single-prompt、benchmark 和无审批 handler 的入口使用 fail closed。
- Web UI 通过 session/run 事件暴露审批请求，并把用户决定路由回对应 run。
- TUI 仅保留接口，不实现 UI。

### Phase 5: External adapters

- MCP/browser/plugin/subagent tools 使用 origin + capabilities + risk_level。
- 外部工具默认 high risk，除非配置或 adapter 规则明确降低风险。

## Decisions To Confirm Before Implementation

1. capability 枚举是否足够表达首批内置工具、MCP 和 browser。
2. risk level 是否使用 `low/medium/high` 三档，还是需要 `critical`。
3. build 默认 profile 是否将 high risk 工具改为 `require_approval`，以及这是否算用户可见行为变化。
4. plan 默认 profile 是否保持当前保守行为，只在后续 profile 中允许实验。
5. `dangerous` 是否在迁移期保留为 derived/legacy 字段，而不是立即删除。
6. 用户自定义 profile 的 YAML/schema 结构和校验规则，包括未知 capability、risk level、profile、tool name 和互相矛盾配置的 fail-fast 行为。
7. subagent 遇到 `require_approval` 时是 fail closed，还是显式委托 parent session 审批。
8. 审批请求中 tool arguments 如何预览、截断和隐藏敏感值。
9. CLI interactive 审批的超时、默认选项和非 TTY 行为。
10. Web UI 审批请求如何绑定 session/run，多个 pending approval 如何展示和取消。

当前推荐：先做 additive metadata + 三值 profile + CLI/Web 审批，开放用户自定义 profile 但不开放自定义 mode。高风险审批的默认 profile 需要在开发前再确认一次，尤其是是否改变 build mode 下 Bash 的默认执行体验。

## Risks / Trade-offs

- [Risk] 权限模型过度抽象，短期实现成本高。Mitigation: 分阶段迁移，第一阶段保持现有行为不变。
- [Risk] capability 枚举不完整。Mitigation: 从内置工具、MCP、browser 的已知需求出发，只引入必要枚举，后续可扩展。
- [Risk] plan mode 语义变化造成用户困惑。Mitigation: 概念上解耦，但默认 profile 保持当前保守行为。
- [Risk] 配置矩阵太灵活导致安全边界难测。Mitigation: 自定义 profile 仅开放有限字段，未知值和矛盾配置 fail fast。
- [Risk] 审批引入 tool-call 链路错误。Mitigation: AgentLoop 统一处理批准、拒绝、超时和不可用，并为每个 tool call 追加合法 tool result。
- [Risk] Web 多 session 审批路由错误。Mitigation: ApprovalRequest 必须携带 run/session id，测试覆盖并发 pending approval。

## Testing Strategy

- ModePolicy 单元测试覆盖新 metadata、legacy 字段等价行为和三值 PermissionDecision。
- ToolRegistry 测试覆盖 schema filter 和 execute 前重新判权。
- AgentLoop 测试覆盖 approval approved / denied / timeout / unavailable，并验证 tool-call 消息链合法。
- 内置工具测试覆盖 capabilities、risk_level、origin 标注。
- 配置解析测试覆盖内置 profile、自定义 profile、deny override 和非法配置 fail fast。
- CLI interactive 测试覆盖审批提示和用户批准/拒绝；CLI single-prompt 测试覆盖 require_approval fail closed。
- Web UI 测试覆盖审批请求事件、用户决定回传和多 session 路由。
- benchmark 测试覆盖 require_approval fail closed，避免无人值守任务卡住。
- 外部 tool fake 测试覆盖 origin 不直接决定权限。
- benchmark smoke 确认核心 agent loop 仍能完成任务。
