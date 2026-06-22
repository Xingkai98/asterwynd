## 1. 规格

- [ ] 1.1 修改 mcp-integration 规格，定义 server 配置、发现、执行和错误语义。
- [ ] 1.2 修改 tool-system 规格，定义 MCP-backed Tool 映射。
- [ ] 1.3 修改 workspace-safety 规格，定义 MCP tool 权限边界。

## 2. 测试

- [ ] 2.1 新增 fake MCP server tool discovery 测试。
- [ ] 2.2 新增 MCP schema 映射到 ToolRegistry schema 的测试。
- [ ] 2.3 新增 MCP tool 执行成功、失败、超时测试。
- [ ] 2.4 新增 mode policy 禁止 MCP dangerous tool 的测试。

## 3. 实现

- [ ] 3.1 增加 MCP 配置模型。
- [ ] 3.2 增加 MCP client/adapter 层。
- [ ] 3.3 将 MCP tools 注册到 ToolRegistry。
- [ ] 3.4 接入权限元数据和 mode policy。

## 4. 验证

- [ ] 4.1 运行 MCP 和 tool registry 测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 跑通至少一个 benchmark smoke。
