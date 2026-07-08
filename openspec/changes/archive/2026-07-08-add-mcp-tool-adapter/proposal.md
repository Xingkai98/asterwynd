## Why

MCP 是扩展 agent 工具生态的重要协议。当前 Asterwynd 只支持本地 Python Tool，不能发现或注册外部 MCP server 暴露的工具。

本 change 实现基础 MCP client adapter：配置 server、连接 stdio 与 Streamable HTTP server、发现 tools/prompts/resources、执行 tool call、读取 prompts/resources，并应用本地权限边界。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 MCP server 配置和连接管理，支持 stdio 与 Streamable HTTP。
- MCP tools SHALL 映射为 ToolRegistry 可识别的工具 schema。
- MCP prompts SHALL 可被发现和读取，为后续 slash command / skill-like workflow 集成提供基础。
- MCP resources SHALL 可被发现和读取，为后续外部上下文注入提供基础。
- MCP tool / prompt / resource 访问 SHALL 携带权限元数据，并受 agent mode / workspace safety 策略约束。
- 错误、超时和 server 不可用 SHALL 返回可读工具错误。

## Capabilities

### Modified Capabilities

- `mcp-integration`: 从预留能力域升级为 MCP tool adapter。
- `tool-system`: ToolRegistry 可注册 MCP-backed tools。
- `workspace-safety`: MCP tool 需要权限和审计边界。

## Impact Analysis

- 影响代码：
  - `agent/mcp/`
  - `agent/tools/registry.py`
  - 配置加载路径
- 影响测试：
  - `tests/agent/mcp/`
  - `tests/agent/tools/`
- 优先使用 fake MCP server 做测试，不依赖真实外部服务。

## Reference Implementation Research

- status: enabled
- reason: MCP adapter 属于外部工具协议接入，应参考其他 coding-agent 对 server 配置、工具发现、schema 映射、错误处理和权限隔离的实现。
- research questions:
  - Codex、Claude Code、opencode 等项目如何管理 MCP server 生命周期和工具 discovery？
  - MCP schema 如何映射到本地 ToolRegistry schema？
  - 外部 MCP tool 的权限 metadata、错误、超时和审计记录如何进入 runtime？
- findings:
  - 当前环境未找到 `codegraph` 命令，因此本次调研按仓库规则降级为读取 `.dev/reference-repos.txt` 后用 `rg` 和关键文件阅读完成。
  - Codex 将 MCP server 配置、连接管理、工具元数据和工具调用拆成独立模块：配置包含 server enablement、stdio/http transport、startup timeout、tool timeout、server/tool allow/deny 与 approval mode；连接管理层持有 server client，统一发现 tools，并按 `(server, tool)` 路由调用。
  - Codex 的 MCP tool 暴露会保留原始 server/tool 身份，同时生成模型可见名称；还会修补缺失 `properties` 的 MCP input schema，避免模型工具 schema 不合法。
  - opencode v2 配置设计把 MCP 放在独立 `mcp.servers` 子树，并建议将协议级默认 timeout 与 server 级 timeout 放在同一配置域；server entry 用显式 local/remote 类型，而不是把 MCP 混入通用 tool 配置。
  - Gemini CLI 和 Goose 测试都使用 fake MCP server 覆盖 discovery/call，不依赖真实外部 MCP server；Gemini 还展示了可用最小 JSON-RPC stdio server 直接覆盖 initialize、`tools/list`、`tools/call`。
  - Qwen/Craft 相关实现采用 `mcp__<server>__<tool>` 形式识别 MCP tool，并在运行时可按 server/tool 配置 enable/disable、timeout 和来源。
- design impact:
  - 用户确认本 change 应一次性支持 stdio 与 Streamable HTTP，并覆盖 tools、prompts、resources 三类基础 MCP 能力。
  - MCP 配置建议独立为 `mcp.servers`，而不是塞进 `tools`，因为它描述的是外部协议 server 生命周期；ToolRegistry 只接收已包装好的 MCP-backed Tool。
  - 模型可见工具名建议采用 `mcp__<server>__<tool>`，同时 MCP adapter 内部保留原始 server/tool 名用于实际 `tools/call`。
  - 权限默认值必须保守：未显式配置的 MCP action 默认 `origin=mcp`、`external_side_effect`、`high` risk，由 mode policy 决定是否可见或需审批；只允许通过本地配置降低到 read-only/low。
  - fake MCP server 应覆盖最小 JSON-RPC stdio 与 Streamable HTTP 协议，避免新增真实外部 server 依赖。
