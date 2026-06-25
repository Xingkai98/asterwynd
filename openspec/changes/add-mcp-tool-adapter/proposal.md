## Why

MCP 是扩展 agent 工具生态的重要协议。当前 MyAgent 只支持本地 Python Tool，不能发现或注册外部 MCP server 暴露的工具。

本 change 先实现最小可测试的 MCP adapter：配置 server、发现工具、映射 schema、执行调用、转换工具结果、应用权限边界。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 MCP server 配置和连接管理。
- MCP tools SHALL 映射为 ToolRegistry 可识别的工具 schema。
- MCP tool SHALL 复用现有 `read_only` / `dangerous` 权限元数据，并受 agent mode / workspace safety 策略约束。
- 错误、超时和 server 不可用 SHALL 返回可读工具错误。
- 首版支持 stdio 和 Streamable HTTP transport，不支持 legacy HTTP+SSE。

## Capabilities

### Modified Capabilities

- `mcp-integration`: 从预留能力域升级为 MCP tool adapter。
- `tool-system`: ToolRegistry 可注册 MCP-backed tools。
- `workspace-safety`: MCP tool 需要权限和审计边界。
- `configuration`: `myagent.yaml` 支持 `tools.mcp` 配置段。

## Impact

- 影响代码：
  - `agent/mcp/`
  - `agent/loop.py`
  - `agent/config.py`
  - `agent/tools/registry.py`
  - 配置加载路径
  - `pyproject.toml` / `uv.lock`
- 影响测试：
  - `tests/agent/mcp/`
  - `tests/agent/tools/`
- 优先使用 fake MCP server 做测试，不依赖真实外部服务。
