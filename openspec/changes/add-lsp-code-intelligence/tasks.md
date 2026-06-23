## 1. 规格

- [ ] 1.1 修改 code-intelligence 规格，定义 LSP provider 和语义能力。
- [ ] 1.2 修改 coding-tools 规格，定义 LSP 只读工具和编辑后 diagnostics 反馈。
- [ ] 1.3 修改 workspace-safety 规格，定义 LSP server 进程、路径和权限边界。
- [ ] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.5 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认 server 配置、生命周期、权限、诊断反馈和测试策略。

## 2. 测试

- [ ] 2.1 新增 fake LSP server 协议测试。
- [ ] 2.2 新增 LSP 工具 schema、权限、超时和错误测试。
- [ ] 2.3 新增 definition、references、hover、documentSymbol、workspaceSymbol 和 diagnostics 测试。
- [ ] 2.4 新增 workspace 外路径和 denied path 安全测试。
- [ ] 2.5 新增编辑后 diagnostics 反馈测试。

## 3. 实现

- [ ] 3.1 增加 `agent/lsp/` 配置、server registry 和生命周期管理。
- [ ] 3.2 增加 document open/sync 和请求调度。
- [ ] 3.3 增加 LSP provider 或只读工具。
- [ ] 3.4 将 diagnostics 反馈接入 Write/Edit/patch 类修改工具。
- [ ] 3.5 增加状态观测、超时、错误和输出截断。

## 4. 验证

- [ ] 4.1 运行 LSP、tool 和 workspace safety 测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 跑通一个需要 diagnostics 反馈的 benchmark smoke。
- [ ] 4.4 运行 OpenSpec strict validate。
