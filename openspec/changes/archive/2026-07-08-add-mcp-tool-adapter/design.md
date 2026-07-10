## Context

Asterwynd 当前工具系统只支持本地 Python `Tool`。MCP 是外部工具生态的通用协议，但直接接入 MCP server 会引入 transport、schema 映射、连接生命周期、超时、错误格式和权限边界问题。

本 change 目标是基础可测试 MCP client adapter，覆盖 stdio、Streamable HTTP、tools、prompts 和 resources 的核心闭环，但不追求完整 MCP 管理平台。

## Goals / Non-Goals

**Goals:**

- 配置一个或多个 stdio / Streamable HTTP MCP server。
- 发现 MCP tools 并映射为 ToolRegistry 可注册工具。
- 执行 MCP tool call 并返回可读错误。
- 发现和读取 MCP prompts / resources，为后续 slash command、workflow 和上下文注入集成提供基础能力。
- MCP tools / prompts / resources 带权限元数据，受 mode policy 和 workspace safety 约束。

**Non-Goals:**

- 不实现 MCP server 管理 UI。
- 不支持 legacy SSE transport 作为独立 transport；远程 MCP 只支持 Streamable HTTP。
- 不实现 OAuth browser login、token refresh、credential store 或授权撤销；Streamable HTTP 首版只支持无认证和本地配置的 header/env header。
- 不把 MCP 权限视为可信输入。
- 不引入真实外部 MCP server 作为单元测试依赖。

## Decisions

### Decision 1: 新增 `agent/mcp/` adapter 层

MCP 连接、工具发现、schema 映射和调用逻辑集中在 `agent/mcp/`，ToolRegistry 只看到包装后的 Tool。

理由：保持现有 ToolRegistry 简单，并隔离协议细节。

### Decision 2: 使用 fake MCP server 做测试

测试优先覆盖 fake server 的发现、调用、错误和超时，不依赖真实网络服务。

理由：MCP 集成必须可重复，不能让外部服务决定测试结果。

### Decision 3: 权限由 Asterwynd 再判定

MCP tool 可以声明权限提示，但最终是否可执行由 Asterwynd 的 mode policy 和 workspace policy 决定。

理由：外部 server 不应绕过本地安全模型。

### Decision 4: Streamable HTTP 首版只支持静态认证输入

Streamable HTTP server 可以配置 `auth: none` 或静态 HTTP headers；header 值可直接配置，也可从环境变量展开。首版不做 OAuth browser login、token refresh、credential store 或授权撤销。

理由：OAuth 会引入回调 server、token 生命周期、凭据存储和多端交互，复杂度足以单独作为后续 change。当前 change 先验证远程 MCP transport、发现和调用闭环。

### Decision 5: MCP 使用顶层 `mcp.servers` 配置域

MCP 配置独立于 `tools`，使用顶层 `mcp.servers` 定义 server。server 必须声明 `type`，首版支持 `stdio` 与 `streamable_http`。协议级默认超时放在 `mcp.default_timeout_seconds`，server 可以覆盖 `startup_timeout_seconds` 和 `tool_timeout_seconds`。

理由：MCP 配置描述外部 server 生命周期、transport 和认证输入，不只是本地工具开关；`tools` 继续承载内置工具配置和展示行为。

### Decision 6: MCP tool 使用 `mcp__<server>__<tool>` 作为模型可见名

MCP adapter 内部保留原始 `(server_name, tool_name)` 用于协议路由；暴露给模型、deny/approval 配置、日志和审批提示时，统一使用安全化后的 `mcp__<server>__<tool>`。如果安全化后重名，追加短 hash 避免覆盖。

Prompts 和 resources 首版不混入 ToolRegistry；它们使用同类 namespace 做诊断和后续集成标识，例如 `mcp__docs__prompt__review_pr`、`mcp__docs__resource__file_tree`。

理由：模型可见工具名需要满足 provider 命名限制，并避免不同 MCP server 的 tool 重名；同时保留原始 MCP 身份可以保证 `tools/call` 路由正确。

### Decision 7: MCP 权限默认保守，只能由本地配置降权

MCP tools / prompts / resources 默认使用 `origin=mcp`、`capabilities=[external_side_effect]`、`risk_level=high`。在 `build` 模式下默认可见但执行前需要 approval；在 `read_only` / `plan` 模式下默认不可见或不可执行，除非本地配置显式降权。

Server 或单个 tool/prompt/resource 可以通过本地配置声明更低权限，例如 `network_read` + `low`。MCP server 自身的 annotation（例如 read-only hint）只能作为诊断或展示信息，不参与最终权限判定。

理由：MCP server 是外部输入，不应绕过 Asterwynd 的 mode policy；权限边界必须由本地受信配置控制。

### Decision 8: 启动时 discovery，单 server 失败默认降级

构建 runtime / registry 时连接所有 `enabled` MCP server，并在 `startup_timeout_seconds` 内完成 initialize 与 tools/prompts/resources discovery。成功后缓存 metadata；单个 server 启动失败时默认记录错误并跳过该 server，不中止整个 agent。

如果 server 配置 `required: true`，启动失败 SHALL 报错中止。Tool call 和 prompt/resource 读取复用已连接 client，并按 `tool_timeout_seconds` 超时。Runtime 关闭时必须关闭 stdio 子进程和 Streamable HTTP session。

理由：模型首轮前需要看到 MCP tool schema，因此 discovery 不能完全懒加载；但外部 server 不稳定不应默认阻塞 agent 启动。

### Decision 9: 协议层使用官方 Python MCP SDK

MCP 协议通信使用官方 `mcp` Python SDK。SDK 负责 stdio、Streamable HTTP、initialize、tools、prompts、resources 等协议细节；Asterwynd 的 `agent/mcp/` 层只负责本地配置解析、连接编排、模型可见命名、权限元数据、ToolRegistry 包装和错误格式。

理由：本 change 已确认同时覆盖 stdio、Streamable HTTP、tools、prompts 和 resources；手写 JSON-RPC client 会把项目拉入协议兼容性维护。协议交给 SDK，测试仍使用 fake MCP server 覆盖 Asterwynd adapter 行为。

### Decision 10: Prompts/resources 首版提供显式 `/mcp-*` 命令

MCP tools 进入 ToolRegistry；prompts/resources 不自动注册为大量 slash command。首版提供基础 manager API，并新增显式用户入口：

- `/mcp`: 查看 MCP server 状态和 tools/prompts/resources 数量。
- `/mcp-prompt <server> <prompt> [json args]`: 读取 prompt，并将返回 messages 注入当前会话或下一轮上下文。
- `/mcp-resource <server> <uri>`: 读取 resource，并将返回内容注入当前会话或下一轮上下文。

理由：显式命令清楚、可测试，避免首版处理远端 prompt 自动命名、参数 schema 展示、权限审批和动态 reload 的复杂度。

### Decision 11: MCP prompt/resource 读取也走 mode policy

`/mcp-prompt` 和 `/mcp-resource` 读取前必须按 MCP action 的 `ToolPermission` 走 mode policy。默认 MCP prompt/resource 为 `origin=mcp`、`external_side_effect`、`high`，因此 `build` 默认需要 approval，`read_only` / `plan` 默认拒绝；本地配置可将指定 server/prompt/resource 降为 `network_read` + `low`。

审批提示应包含 server、prompt/resource 名称、参数或 URI。原因是远端读取可能触发审计、计费、外部请求，返回内容也可能包含 prompt injection，不能绕过现有权限模型。

### Decision 12: Prompt/resource 结果以带来源的 system context 注入

`/mcp-prompt` 和 `/mcp-resource` 读取结果首版注入为带来源标记的 `system` 消息，不伪装成历史 user/assistant 消息。

`/mcp-prompt` 注入格式：

```text
[MCP prompt: <server>/<prompt>]
Arguments: <json args>

<server returned messages>
```

`/mcp-resource` 注入格式：

```text
[MCP resource: <server> <uri>]

<resource content>
```

Command result metadata 记录 `mcp_server`、`mcp_kind`、`mcp_name` 或 `uri`、`permission_decision` 和 `injected_messages`。

理由：现有消息模型没有独立 context item / attachment 类型；使用带来源的 system context 可以保持 tool-call 消息链合法，并保证后续讨论与开发过程可追溯。

## Pre-Implementation Review

- Questions resolved:
  - 本 change 尚未按当前新增的 Impact Analysis / Pre-Implementation Review 规则完成开发前设计追问。
- Options considered:
  - 保留原设计，等待开始开发时完整追问。
  - 在本次流程治理 change 中伪造完整追问结论。
- Rejected alternatives:
  - 伪造完整追问结论。原因：该 change 依赖工具权限模型等前置决策，必须在真正开发前重新结合当前代码确认。
- Final confirmations:
  - 开发前必须重新使用 `grill-with-docs` 或等价设计追问确认 MCP schema 映射、fake server 范围、超时错误模型、权限元数据和配置边界。
- Remaining risks:
  - 工具权限模型尚未实现，MCP adapter 的最终接口可能随前置 change 调整。

## Risks / Trade-offs

- [Risk] MCP schema 与本地 tool schema 不完全一致。Mitigation: 先支持 JSON Schema 子集，不支持项返回清晰错误。
- [Risk] 外部 server 卡住或不可用。Mitigation: 每次调用设置超时，并返回结构化错误。
- [Risk] 权限声明不可信。Mitigation: 默认保守，未知 MCP tool 不自动获得 dangerous 权限。

## Testing Strategy

- fake MCP server 覆盖 initialize、tools/list、tools/call。
- ToolRegistry 测试覆盖 MCP-backed tool 注册与 schema 暴露。
- 错误测试覆盖 server 不可用、超时、未知 tool、无效参数。
- 权限测试覆盖 mode policy 拒绝危险 MCP tool。
