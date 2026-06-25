## 1. 规格

- [ ] 1.1 修改 mcp-integration 规格，定义 server 配置、发现、执行和错误语义。
- [ ] 1.2 修改 tool-system 规格，定义 MCP-backed Tool 映射。
- [ ] 1.3 修改 workspace-safety 规格，定义 MCP tool 权限边界。
- [ ] 1.4 修改 configuration 规格，定义 `tools.mcp` 配置段、transport 枚举、server name 校验和 fail-fast 规则。
- [ ] 1.5 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.6 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案。

## 2. 测试

- [ ] 2.1 新增 fake MCP server tool discovery 测试。
- [ ] 2.2 新增 MCP schema 映射到 ToolRegistry schema 的测试。
- [ ] 2.3 新增 MCP tool 执行成功、失败、超时测试。
- [ ] 2.4 新增 mode policy 禁止 MCP dangerous tool 的测试。
- [ ] 2.5 新增 MCP 配置解析测试，覆盖 stdio、streamable_http、非法 transport、非法 server name、缺失 command/url 和权限覆盖。
- [ ] 2.6 新增 MCP tool name 清洗与重名短 hash 测试。
- [ ] 2.7 新增 MCP tool result flattening 测试，覆盖 text、非 text content 和 `isError=true`。
- [ ] 2.8 新增 MCP-backed tool 来源元数据测试，覆盖 `origin=mcp`、server name 和来源不直接替代 mode policy 判权。

## 3. 实现

- [ ] 3.1 增加 MCP 配置模型。
- [ ] 3.2 增加 `mcp>=1.27,<2` 依赖。
- [ ] 3.3 增加 MCP client/adapter 层，支持 stdio 和 Streamable HTTP，不支持 legacy HTTP+SSE。
- [ ] 3.4 在 AgentLoop run 开始、首次 LLM 调用前执行一次 MCP discovery，并将 MCP-backed tools 注册到 ToolRegistry。
- [ ] 3.5 接入权限元数据和 mode policy，复用现有 `read_only` / `dangerous` / `allowed_modes`。
- [ ] 3.6 实现 provider-safe tool name 映射和 original tool name 调用映射。
- [ ] 3.7 实现 MCP content blocks 到字符串 tool result 的转换。
- [ ] 3.8 为 MCP-backed tools 增加来源元数据，用于 trace、audit、display 和后续权限模型演进。

## 4. 验证

- [ ] 4.1 运行 MCP 和 tool registry 测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 跑通至少一个 benchmark smoke。
