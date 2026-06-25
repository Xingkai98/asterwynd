## Context

MyAgent 当前工具系统只支持本地 Python `Tool`。MCP 是外部工具生态的通用协议，但直接接入 MCP server 会引入 schema 映射、连接生命周期、超时、错误格式和权限边界问题。

本 change 目标是最小可测试 MCP adapter，不追求完整 MCP client 平台。

## Goals / Non-Goals

**Goals:**

- 配置一个或多个 MCP server（stdio 和 Streamable HTTP transport）。
- 发现 MCP tools 并映射为 ToolRegistry 可注册工具。
- 执行 MCP tool call 并返回可读错误。
- MCP tools 带权限元数据，受 mode policy 和 workspace safety 约束。

**Non-Goals:**

- 不实现 MCP server 管理 UI。
- 不把 MCP 权限视为可信输入。
- 不引入真实外部 MCP server 作为单元测试依赖。
- 不支持 legacy HTTP+SSE transport；后续如有真实兼容需求再单独设计。

## Decisions

### Decision 1: 使用官方 `mcp` Python SDK 做协议层

使用 `mcp` 包（PyPI）处理 transport、initialize 握手、capability 协商、ping 和 error 编码。`agent/mcp/` 层只做发现、schema 映射、结果转换和权限包装。

依赖版本使用 `mcp>=1.27,<2`。截至 2026-06-25，Python SDK README 说明 v1 是当前稳定版本，v2 仍处于 alpha，且官方建议依赖方在 v2 stable 发布前添加 `<2` 上界。

理由：避免自己实现 JSON-RPC 协议细节，减少维护成本。SDK v1 已支持 stdio 和 Streamable HTTP client；锁定 `<2` 可以避免 SDK v2 API 变更在实现完成后破坏运行时。

审议确认：2026-06-25，grill-with-docs。

### Decision 2: 支持 stdio + Streamable HTTP 两种 transport

stdio server 通过 `command` + `args` + `env` 启动子进程，使用 SDK 的 `stdio_client`。Streamable HTTP server 通过 `url` + `headers` 连接，使用 SDK 的 `streamable_http_client`。

配置中的 transport 值为 `stdio` 或 `streamable_http`。不使用模糊的 `http` 值，避免与 legacy HTTP+SSE 混淆。

理由：stdio 覆盖本地 MCP server，Streamable HTTP 覆盖远程场景。两者是当前 MCP 2025-06-18 transport 规格的核心路径；legacy HTTP+SSE 仅作为旧协议兼容路径，不进入本 change。

审议确认：2026-06-25，grill-with-docs。

### Decision 3: 配置格式 — `tools.mcp` YAML 段

MCP server 配置放在 `myagent.yaml` 的 `tools.mcp` 下，使用 frozen dataclass 建模（参照 `LspServerConfig` 风格）。

```yaml
tools:
  mcp:
    default_timeout_seconds: 30
    servers:
      - name: filesystem
        transport: stdio
        command: [npx, -y, @anthropic/mcp-server-filesystem, /tmp]
        default_read_only: false
        default_dangerous: true
        timeout_seconds: 30          # 可选，覆盖全局 default_timeout_seconds
        tools:                        # 可选，tool 级权限覆盖
          list_allowed_directories:
            read_only: true
            dangerous: false
      - name: remote-api
        transport: streamable_http
        url: https://mcp.example.com/mcp
        headers:
          Authorization: Bearer ${MCP_TOKEN}
```

审议确认：2026-06-25，grill-with-docs。

### Decision 4: MCP tool 命名 — `{server_name}__{tool_name}`

MCP tool 注册到 ToolRegistry 时使用 `{server_name}__{tool_name}` 格式（双下划线分隔），例如 `filesystem__read_file`。注册名必须满足 LLM provider 常见 function name 约束：

- `server_name` 配置值必须匹配 `^[A-Za-z0-9_-]+$`，否则配置解析 fail fast。
- MCP 原始 tool name 映射时只保留 ASCII 字母、数字、下划线和短横线；其他字符替换为 `_`，连续 `_` 压缩。
- 如果清洗后为空，使用 `tool` 作为 base name。
- 如果同一 server 内清洗后重名，追加稳定短 hash，例如 `filesystem__read_file_a1b2c3`。
- adapter 保存 original tool name，真实调用 MCP `tools/call` 时仍使用原始名称。

理由：避免与内置工具名称冲突，同时让 LLM 能识别工具归属；显式清洗和冲突处理可以避免外部 server 名称破坏 provider tool schema。

审议确认：2026-06-25，grill-with-docs。

### Decision 5: 权限模型 — server 级默认 + tool 级覆盖

每个 MCP server 配置 `default_read_only` 和 `default_dangerous` 两个 boolean；可通过 `tools.<tool_name>.read_only` / `.dangerous` 覆盖单个 tool。

- 未配置时默认：`read_only=False, dangerous=True`（对外部工具保守）
- MCP server 自身的权限 hints 仅供参考，不作为最终判定
- ModePolicy 的现有逻辑（`read_only and not dangerous`）直接复用，不改动

审议确认：2026-06-25，grill-with-docs。

### Decision 6: 连接生命周期 — run 开始前异步发现，失败跳过

AgentLoop 构造和 ToolRegistry 构造保持同步 API；MCP discovery 是异步工作，不放进构造函数。

入口层构造 `McpToolAdapter` 并传入 AgentLoop。每次 AgentLoop 第一次 `run()` 开始、首次 LLM 调用前，adapter 对配置的 MCP server 执行一次 `initialize` 握手和 `tools/list` 发现，把 MCP-backed tools 注册进当前 ToolRegistry。后续同一 AgentLoop run 复用已发现工具，不做后台重连；如果同一 session 多次 run，需要 adapter 避免重复注册同名工具。

连接失败的 server 记录 warning 并跳过，不阻止 agent 启动或 run 开始。失败 server 的工具不会暴露给 LLM。

理由：现有 CLI、Web、benchmark 和 subagent 都通过同步 factory 构造 registry；把异步 I/O 放入 AgentLoop run 边界可以复用现有入口结构，同时保证首次 LLM 调用前 schema 已包含可用 MCP tools。

审议确认：2026-06-25，grill-with-docs。

### Decision 7: Schema 映射 — 直通

MCP tool 的 `inputSchema` 原样赋值给 `Tool.parameters`，不做校验、裁剪或转换。没有 `inputSchema` 时用空对象 schema `{"type": "object", "properties": {}, "required": []}`。

理由：ToolRegistry 和 LLM 都能处理任意 JSON Schema，转换层只增加复杂度和出错可能。

审议确认：2026-06-25，grill-with-docs。

### Decision 8: 超时策略 — 全局默认 + server 覆盖，单次调用

`tools.mcp.default_timeout_seconds` 全局默认 30s，server 级可选覆盖。超时只影响当次 `tools/call` 调用，返回错误文本，server 连接保持可用。

理由：单次失败不应导致整个 server 被标记不可用；server 恢复后后续调用自动恢复。

审议确认：2026-06-25，grill-with-docs。

### Decision 9: 新增 `agent/mcp/` adapter 层

MCP 连接、工具发现、schema 映射和调用逻辑集中在 `agent/mcp/`，ToolRegistry 只看到包装后的 Tool。

理由：保持现有 ToolRegistry 简单，并隔离协议细节。

### Decision 10: 使用 fake MCP server 做测试

测试优先覆盖 fake server 的发现、调用、错误和超时，不依赖真实网络服务。

理由：MCP 集成必须可重复，不能让外部服务决定测试结果。

### Decision 11: 权限由 MyAgent 再判定，origin 只做来源元数据

MCP tool 可以声明权限提示，但最终是否可执行由 MyAgent 的 mode policy 和 workspace policy 决定。

MCP-backed Tool SHALL 携带来源元数据，例如 `origin="mcp"` 和 `server_name="<configured-server>"`，用于 trace、audit、display、默认权限推导和排查。`origin` 不直接参与当前 ModePolicy 判权。

`dangerous=True` 表示工具风险高或副作用不可控，不表示“外部来源”。MCP tool 默认 `dangerous=True`，是因为外部 server 默认能力未知；用户可以通过配置把已审阅的 MCP read-only tool 覆盖为 `read_only=True, dangerous=False`。

理由：外部 server 不应绕过本地安全模型；同时来源和风险是两条不同概念轴，不能把 “MCP 来源” 永久混同为 “dangerous”。

审议确认：2026-06-25，grill-with-docs。

### Decision 12: MCP tool result 转成字符串

MCP `tools/call` 结果可能包含多个 content block，不等同于本地 Tool 的单个字符串。MCP-backed Tool 的 `execute()` SHALL 始终返回字符串：

- text content block 按顺序拼接，中间用换行分隔。
- 非 text content block 返回简短占位和必要 metadata 摘要，不内联大体积二进制内容。
- `isError=true` 时返回以 `[MCP error: ...]` 开头的可读错误文本。
- SDK/transport 异常、未知 tool、无效参数和超时都返回可读错误文本，不向 AgentLoop 抛出可恢复异常。

理由：AgentLoop 和 ToolRegistry 当前协议以字符串 tool result 为边界；在 adapter 层收敛结果格式可以保持 tool-call 消息链合法。

审议确认：2026-06-25，design review。

### Decision 13: MCP 不新增 Tool 权限三态

MCP-backed Tool 复用现有 Tool 元数据：`read_only`、`dangerous` 和可选 `allowed_modes`。本 change 不新增独立 `read_write` 字段或三态权限 enum。

写入类 MCP tool 用 `read_only=False, dangerous=False` 表达；高风险或外部副作用不可控的 MCP tool 用 `dangerous=True` 表达。read-only / plan mode 继续只允许 `read_only=True and dangerous=False` 的工具。

理由：现有 ModePolicy 已以这两个 boolean 作为事实来源；新增三态模型会扩大本 change 范围，并要求同步重写内置工具权限语义。

审议确认：2026-06-25，design review。

### Decision 14: 完整 Tool 权限模型重构另开 change

本 change 只为 MCP adapter 明确现有权限模型的使用方式，不重构全局 Tool 权限模型。后续单独 OpenSpec change 将讨论并设计 `capabilities` / `risk_level` / `origin` / mode policy matrix 等更清晰的权限模型。

理由：权限模型重构会影响内置工具、agent modes、配置、测试、README 和后续 browser 能力；把它混入 MCP adapter 会扩大实现范围并降低可验证性。

审议确认：2026-06-25，grill-with-docs。

## Risks / Trade-offs

- [Risk] MCP schema 与本地 tool schema 不完全一致。Mitigation: 直通 inputSchema，LLM 自行理解复杂 schema。
- [Risk] 外部 server 卡住或不可用。Mitigation: discovery 和每次调用设置超时，返回可读错误文本。
- [Risk] 权限声明不可信。Mitigation: 默认 `dangerous=True`，必须用户显式配置才能放宽。
- [Risk] 来源和风险语义混淆。Mitigation: MCP tool 带 `origin=mcp` 来源元数据，但 mode policy 仍按 `read_only` / `dangerous` 判权；完整权限模型另开 change。
- [Risk] run 开始时 discovery 增加首轮延迟。Mitigation: 连接超时设置 + 失败跳过不阻塞，且同一 AgentLoop 后续 run 避免重复注册。
- [Risk] MCP SDK v2 API 变更。Mitigation: 依赖 `mcp>=1.27,<2`，后续升级作为单独 change。
- [Risk] MCP tool name 不满足 provider 约束或发生冲突。Mitigation: 配置名校验、tool name 清洗、冲突短 hash 和 original name 映射。

## Testing Strategy

- fake MCP server 覆盖 initialize、tools/list、tools/call。
- ToolRegistry 测试覆盖 MCP-backed tool 注册与 schema 暴露。
- 错误测试覆盖 server 不可用、超时、未知 tool、无效参数。
- 权限测试覆盖 mode policy 拒绝危险 MCP tool。
- 命名测试覆盖非法 server name、tool name 清洗和重名短 hash。
- result flattening 测试覆盖 text、非 text content 和 `isError=true`。
- stdio 和 Streamable HTTP fake server 各自覆盖 transport 特定场景。
