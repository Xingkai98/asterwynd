## 1. 规格

- [x] 1.1 修改 agent-runtime 规格，定义 session/run id。
- [x] 1.2 修改 Web / CLI / TUI / benchmark 规格，定义展示和 artifact 记录要求。
- [x] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，逐项确认标识边界、日志关联、测试策略和文档影响。

## 2. 测试

- [x] 2.1 新增 Web session id 展示和事件测试。
- [x] 2.2 新增 CLI run id 输出测试。
- [x] 2.3 新增 trace / benchmark artifact 标识测试。

## 3. 实现

- [x] 3.1 增加统一运行标识生成和传递。
- [x] 3.2 Web UI 展示 session id。
- [x] 3.3 CLI 展示 run id。
- [x] 3.4 trace / benchmark 写入 session id / run id。

## 4. 验证

- [x] 4.1 运行 CLI/Web/trace/benchmark 相关测试。
- [x] 4.2 运行 OpenSpec strict validate。
- [x] 4.3 跑通至少一个 benchmark smoke。
