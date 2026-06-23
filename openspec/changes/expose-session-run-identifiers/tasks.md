## 1. 规格

- [ ] 1.1 修改 agent-runtime 规格，定义 session/run/correlation id。
- [ ] 1.2 修改 Web / CLI / TUI / benchmark 规格，定义展示和 artifact 记录要求。

## 2. 测试

- [ ] 2.1 新增 Web session id 展示和事件测试。
- [ ] 2.2 新增 CLI run id 输出测试。
- [ ] 2.3 新增 trace / benchmark artifact 标识测试。

## 3. 实现

- [ ] 3.1 增加统一运行标识生成和传递。
- [ ] 3.2 Web UI 展示 session id。
- [ ] 3.3 CLI 展示 run id。
- [ ] 3.4 trace / benchmark 写入 correlation id。

## 4. 验证

- [ ] 4.1 运行 CLI/Web/trace/benchmark 相关测试。
- [ ] 4.2 运行 OpenSpec strict validate。
- [ ] 4.3 跑通至少一个 benchmark smoke。
