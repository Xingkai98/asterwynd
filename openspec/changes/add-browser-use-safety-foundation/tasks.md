## 1. 规格

- [ ] 1.1 修改 browser-computer-use 规格，定义 URL、凭据、截图、超时和审计策略。
- [ ] 1.2 修改 tool-system 规格，定义 browser tools 权限元数据。
- [ ] 1.3 修改 workspace-safety 规格，定义 browser artifact 存储边界。
- [ ] 1.4 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案。

## 2. 测试

- [ ] 2.1 新增 URL allowlist 拒绝未允许站点的测试。
- [ ] 2.2 新增 browser tool 超时和错误返回测试。
- [ ] 2.3 新增 screenshot artifact 存储路径受 WorkspacePolicy 约束的测试。
- [ ] 2.4 新增 browser tools 受 mode policy 控制的测试。

## 3. 实现

- [ ] 3.1 增加 browser policy 配置。
- [ ] 3.2 增加最小 Playwright browser session 管理。
- [ ] 3.3 增加打开页面、读取页面信息和截图工具。
- [ ] 3.4 接入 ToolRegistry、mode policy 和 trace。

## 4. 验证

- [ ] 4.1 运行 browser policy 和 tool 测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 手动运行 browser smoke。
- [ ] 4.4 运行 OpenSpec strict validate。
- [ ] 4.5 跑通至少一个 benchmark smoke。
