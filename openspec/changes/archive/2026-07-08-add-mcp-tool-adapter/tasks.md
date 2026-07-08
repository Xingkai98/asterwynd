## 1. 规格

- [x] 1.1 修改 mcp-integration 规格，定义 stdio / Streamable HTTP server 配置、tools/prompts/resources 发现、执行/读取和错误语义。
- [x] 1.2 修改 tool-system 规格，定义 MCP-backed Tool 映射。
- [x] 1.3 修改 workspace-safety 规格，定义 MCP tools/prompts/resources 权限边界。
- [x] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [x] 1.5 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案。
- [x] 1.6 开发前补实 `## Reference Implementation Research`，基于 `.dev/reference-repos.txt` 中可用参考仓库调研 MCP adapter，并回写 findings / design impact。

## 2. 测试

- [x] 2.1 新增 fake MCP server tool/prompt/resource discovery 测试。
- [x] 2.2 新增 MCP schema 映射到 ToolRegistry schema 的测试。
- [x] 2.3 新增 MCP tool 执行成功、失败、超时测试。
- [x] 2.4 新增 mode policy 禁止 MCP dangerous tool 的测试。
- [x] 2.5 新增 MCP prompt/resource 读取成功、失败、超时测试。
- [x] 2.6 新增 Streamable HTTP MCP server 发现和调用测试。

## 3. 实现

- [x] 3.1 增加 MCP 配置模型。
- [x] 3.2 增加 MCP stdio client/adapter 层。
- [x] 3.3 增加 MCP Streamable HTTP client/adapter 层。
- [x] 3.4 将 MCP tools 注册到 ToolRegistry。
- [x] 3.5 暴露 MCP prompts/resources 发现和读取接口。
- [x] 3.6 接入权限元数据和 mode policy。

## 4. 验证

- [x] 4.1 运行 MCP 和 tool registry 测试。
- [x] 4.2 运行全量测试。
- [x] 4.3 运行 OpenSpec strict validate。
- [x] 4.4 跑通至少一个 benchmark smoke。
