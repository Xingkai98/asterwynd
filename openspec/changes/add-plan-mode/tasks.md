## 1. 规格

- [ ] 1.1 修改 agent-modes 规格，定义 plan mode 的实际行为。
- [ ] 1.2 修改 planning 规格，定义 plan mode 计划产物要求。
- [ ] 1.3 修改 CLI/Web 规格，定义 plan mode 入口。

## 2. 测试

- [ ] 2.1 新增 plan mode 工具 schema 只包含只读工具的测试。
- [ ] 2.2 新增 plan mode 拒绝写入或 dangerous 工具调用的测试。
- [ ] 2.3 新增 plan mode 生成 planning state 的 AgentLoop 测试。
- [ ] 2.4 新增 CLI/Web 入口传入 plan mode 的测试。

## 3. 实现

- [ ] 3.1 将 plan mode 接入 mode policy。
- [ ] 3.2 调整 system prompt 或运行策略，要求 plan mode 输出计划而非改代码。
- [ ] 3.3 接入 CLI 参数。
- [ ] 3.4 接入 Web session 配置。

## 4. 验证

- [ ] 4.1 运行 agent mode/planning 相关测试。
- [ ] 4.2 运行 Web/CLI 相关测试。
- [ ] 4.3 运行全量测试。
- [ ] 4.4 运行 OpenSpec strict validate。
