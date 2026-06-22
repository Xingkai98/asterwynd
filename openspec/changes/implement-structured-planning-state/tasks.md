## 1. 规格

- [ ] 1.1 修改 planning 规格，定义 plan item 数据模型和状态集合。
- [ ] 1.2 修改 agent-runtime 规格，定义 planning state 事件语义。
- [ ] 1.3 修改 web-ui 和 benchmark 规格，定义展示与 trace 记录要求。
- [ ] 1.4 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案。

## 2. 测试

- [ ] 2.1 新增 PlanningManager 添加、更新、完成、失败状态的单元测试。
- [ ] 2.2 新增 AgentLoop 发出 planning state 事件的测试。
- [ ] 2.3 新增 TraceRecorder 记录 planning 事件的测试。
- [ ] 2.4 新增 Web session 转发 planning 事件的测试。

## 3. 实现

- [ ] 3.1 增加 `agent/planning/` 数据模型和管理器。
- [ ] 3.2 将 PlanningManager 接入 AgentLoop。
- [ ] 3.3 将 planning 事件写入 TraceRecorder。
- [ ] 3.4 将 planning 事件接入 Web session 和 Debug 视图。
- [ ] 3.5 将 planning 摘要写入 benchmark artifacts。

## 4. 验证

- [ ] 4.1 运行 planning/loop/trace 相关测试。
- [ ] 4.2 运行 Web 和 benchmark 相关测试。
- [ ] 4.3 运行全量测试。
- [ ] 4.4 运行 OpenSpec strict validate。
- [ ] 4.5 跑通至少一个 benchmark smoke。
