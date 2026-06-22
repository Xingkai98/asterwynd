## 1. 规格

- [ ] 1.1 修改 agent-modes 规格，定义运行时 mode transition 语义。
- [ ] 1.2 修改 agent-runtime 规格，定义 session runtime state 和 mode_changed 事件。
- [ ] 1.3 修改 tool-system 规格，定义 schema / execute 读取最新 mode。
- [ ] 1.4 修改 CLI / Web / TUI 规格，定义用户触发 mode 切换的入口。

## 2. 测试

- [ ] 2.1 新增 runtime state `set_mode` 单元测试。
- [ ] 2.2 新增 mode 切换后 schema 立即变化测试。
- [ ] 2.3 新增 mode 切换后未执行 tool call 按新 mode 拒绝测试。
- [ ] 2.4 新增 CLI 交互 mode 切换测试。
- [ ] 2.5 新增 WebSocket mode 切换和事件转发测试。

## 3. 实现

- [ ] 3.1 增加 session runtime state 或等价状态对象。
- [ ] 3.2 增加统一 mode transition API。
- [ ] 3.3 让 ToolRegistry schema / execute 读取最新 mode。
- [ ] 3.4 接入 AgentLoop 事件和 trace 记录。
- [ ] 3.5 接入 CLI 交互命令。
- [ ] 3.6 接入 WebSocket mode 切换消息和前端状态。
- [ ] 3.7 为未来 TUI 暴露复用接口。

## 4. 验证

- [ ] 4.1 运行 agent runtime 和 tool-system 测试。
- [ ] 4.2 运行 CLI/Web 相关测试。
- [ ] 4.3 运行全量测试。
- [ ] 4.4 运行 OpenSpec strict validate 和项目 artifact checker。
- [ ] 4.5 跑通至少一个 benchmark smoke。
