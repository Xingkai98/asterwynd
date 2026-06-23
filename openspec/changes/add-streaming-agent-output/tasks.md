## 1. 规格

- [ ] 1.1 修改 agent-runtime 规格，定义 assistant text delta / streaming complete 事件。
- [ ] 1.2 修改 Web / CLI / TUI 规格，定义 streaming event 消费语义。
- [ ] 1.3 设计 tool call streaming 和最终 assistant message 的关系。
- [ ] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.5 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，逐项确认 provider streaming、AgentLoop 事件、消息链合法性、各端展示和测试策略。

## 2. 测试

- [ ] 2.1 新增 provider fake streaming 测试。
- [ ] 2.2 新增 AgentLoop streaming event 测试。
- [ ] 2.3 新增 WebSocket streaming 测试。
- [ ] 2.4 新增 CLI streaming 输出测试。

## 3. 实现

- [ ] 3.1 扩展 LLM streaming 协议或新增 stream 方法。
- [ ] 3.2 AgentLoop 发布 streaming 事件。
- [ ] 3.3 Web UI 消费 text delta。
- [ ] 3.4 CLI 实时打印 text delta。
- [ ] 3.5 为未来 TUI 暴露 streaming event。

## 4. 验证

- [ ] 4.1 运行 LLM / AgentLoop / Web / CLI 相关测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 跑通至少一个 benchmark smoke。
