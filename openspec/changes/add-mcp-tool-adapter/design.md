## Context

MyAgent 当前工具系统只支持本地 Python `Tool`。MCP 是外部工具生态的通用协议，但直接接入 MCP server 会引入 schema 映射、连接生命周期、超时、错误格式和权限边界问题。

本 change 目标是最小可测试 MCP adapter，不追求完整 MCP client 平台。

## Goals / Non-Goals

**Goals:**

- 配置一个或多个 MCP server（stdio 和 HTTP/SSE transport）。
- 发现 MCP tools 并映射为 ToolRegistry 可注册工具。
- 执行 MCP tool call 并返回可读错误。
- MCP tools 带权限元数据，受 mode policy 和 workspace safety 约束。

**Non-Goals:**

- 不实现 MCP server 管理 UI。
- 不把 MCP 权限视为可信输入。
- 不引入真实外部 MCP server 作为单元测试依赖。

## Decisions

### Decision 1: 使用官方 `mcp` Python SDK 做协议层

使用 `mcp` 包（PyPI）处理 transport、initialize 握手、capability 协商、ping 和 error 编码。`agent/mcp/` 层只做发现、schema 映射和权限包装。

理由：避免自己实现 JSON-RPC 协议细节，减少维护成本。SDK 已支持 stdio 和 HTTP/SSE client。

审议确认：2026-06-25，grill-with-docs。

### Decision 2: 支持 stdio + HTTP/SSE 两种 transport

stdio server 通过 `command` + `args` + `env` 启动子进程；HTTP server 通过 `url` + `headers` 连接。

理由：stdio 覆盖本地 MCP server，HTTP 覆盖远程场景。两者都是 MCP 规范的核心 transport。

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
        transport: http
        url: https://mcp.example.com/mcp
        headers:
          Authorization: Bearer ${MCP_TOKEN}
```

审议确认：2026-06-25，grill-with-docs。

### Decision 4: MCP tool 命名 — `{server_name}__{tool_name}`

MCP tool 注册到 ToolRegistry 时使用 `{server_name}__{tool_name}` 格式（双下划线分隔），例如 `filesystem__read_file`。

理由：避免与内置工具名称冲突，同时让 LLM 能识别工具归属。

审议确认：2026-06-25，grill-with-docs。

### Decision 5: 权限模型 — server 级默认 + tool 级覆盖

每个 MCP server 配置 `default_read_only` 和 `default_dangerous` 两个 boolean；可通过 `tools.<tool_name>.read_only` / `.dangerous` 覆盖单个 tool。

- 未配置时默认：`read_only=False, dangerous=True`（对外部工具保守）
- MCP server 自身的权限 hints 仅供参考，不作为最终判定
- ModePolicy 的现有逻辑（`read_only and not dangerous`）直接复用，不改动

审议确认：2026-06-25，grill-with-docs。

### Decision 6: 连接生命周期 — 启动时全量连接，失败跳过

AgentLoop 初始化时连接所有配置的 MCP server，完成 `initialize` 握手和 `tools/list` 发现。连接失败的 server 记录警告并跳过，不阻止 agent 启动。不实现惰性连接或后台重连。

理由：实现简单可测，失败不阻塞主流程。

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

### Decision 11: 权限由 MyAgent 再判定

MCP tool 可以声明权限提示，但最终是否可执行由 MyAgent 的 mode policy 和 workspace policy 决定。

理由：外部 server 不应绕过本地安全模型。

## Risks / Trade-offs

- [Risk] MCP schema 与本地 tool schema 不完全一致。Mitigation: 直通 inputSchema，LLM 自行理解复杂 schema。
- [Risk] 外部 server 卡住或不可用。Mitigation: 每次调用设置超时，返回结构化错误文本。
- [Risk] 权限声明不可信。Mitigation: 默认 `dangerous=True`，必须用户显式配置才能放宽。
- [Risk] 启动时全量连接可能因 server 不可用而增加启动时间。Mitigation: 连接超时设置 + 失败跳过不阻塞。

## Testing Strategy

- fake MCP server 覆盖 initialize、tools/list、tools/call。
- ToolRegistry 测试覆盖 MCP-backed tool 注册与 schema 暴露。
- 错误测试覆盖 server 不可用、超时、未知 tool、无效参数。
- 权限测试覆盖 mode policy 拒绝危险 MCP tool。
- stdio 和 HTTP fake server 各自覆盖 transport 特定场景。
