## Context

Asterwynd 当前工具系统只支持本地 Python `Tool`。MCP 是外部工具生态的通用协议，但直接接入 MCP server 会引入 schema 映射、连接生命周期、超时、错误格式和权限边界问题。

本 change 目标是最小可测试 MCP adapter，不追求完整 MCP client 平台。

## Goals / Non-Goals

**Goals:**

- 配置一个或多个 MCP server。
- 发现 MCP tools 并映射为 ToolRegistry 可注册工具。
- 执行 MCP tool call 并返回可读错误。
- MCP tools 带权限元数据，受 mode policy 和 workspace safety 约束。

**Non-Goals:**

- 不实现 MCP server 管理 UI。
- 不支持所有 transport 变体。
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
