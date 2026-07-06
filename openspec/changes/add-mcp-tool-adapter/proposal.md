## Why

MCP 是扩展 agent 工具生态的重要协议。当前 Asterwynd 只支持本地 Python Tool，不能发现或注册外部 MCP server 暴露的工具。

本 change 先实现最小可测试的 MCP adapter：配置 server、发现工具、映射 schema、执行调用、应用权限边界。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 MCP server 配置和连接管理。
- MCP tools SHALL 映射为 ToolRegistry 可识别的工具 schema。
- MCP tool SHALL 携带权限元数据，并受 agent mode / workspace safety 策略约束。
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
  - 本次仅为参考实现调研门禁的结构迁移，尚未完成本 change 的针对性横向调研。
  - 当前工作区 `.dev/reference-repos.txt` 存在，可用于开发前调研；真正开始实现前必须补充具体参考仓库发现。
- design impact:
  - 当前方案仍保留 fake MCP server、schema mapping、权限元数据和 workspace safety 作为实现前必须确认的设计点。
  - 如果调研发现应复用已有协议抽象或配置结构，应先回写 design/spec/tasks。
