## 1. 规格

- [ ] 1.1 修改 tui 规格，定义最小 runtime view。
- [ ] 1.2 修改 CLI 规格，定义 TUI 命令入口。
- [ ] 1.3 修改 planning 规格，定义 TUI 展示 planning state 的要求。
- [ ] 1.4 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案。

## 2. 测试

- [ ] 2.1 新增 TUI 命令构造 AgentLoop 的测试。
- [ ] 2.2 新增 TUI 消费工具事件和 planning 事件的测试。
- [ ] 2.3 新增非交互环境下 TUI graceful failure 或降级测试。

## 3. 实现

- [ ] 3.1 选择 TUI 框架或最小终端渲染方案。
- [ ] 3.2 增加 TUI 命令入口。
- [ ] 3.3 接入 AgentLoop 事件流、planning state 和工具调用展示。
- [ ] 3.4 展示最终回复、diff/test 摘要和 trace 路径。

## 4. 验证

- [ ] 4.1 运行 TUI/CLI 相关测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 手动启动 TUI smoke。
- [ ] 4.4 运行 OpenSpec strict validate。
- [ ] 4.5 跑通至少一个 benchmark smoke。
