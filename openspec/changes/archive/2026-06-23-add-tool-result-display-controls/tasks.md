## 1. 规格

- [x] 1.1 修改 Web / CLI / TUI 规格，定义工具结果 display policy。
- [x] 1.2 明确 WebFetch 默认折叠和 YAML 可配置长结果阈值。
- [x] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，逐项确认展示边界、trace 保真、各端行为和测试策略。

## 2. 测试

- [x] 2.1 新增 WebFetch 结果默认折叠测试。
- [x] 2.2 新增 CLI 长工具结果摘要测试。
- [x] 2.3 新增 trace 完整内容不变的回归测试。
- [x] 2.4 新增 `tools.display` 配置默认值、YAML 读取和非法值测试。

## 3. 实现

- [x] 3.1 Web UI 接入折叠/展开控件。
- [x] 3.2 CLI 输出长工具结果摘要。
- [x] 3.3 为未来 TUI 暴露 display policy。
- [x] 3.4 将 display policy 阈值接入 `myagent.yaml` 配置。

## 4. 验证

- [x] 4.1 运行 Web / CLI / trace 相关测试。
- [x] 4.2 运行 OpenSpec strict validate。
