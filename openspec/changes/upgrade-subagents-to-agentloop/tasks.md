## 1. 规格

- [ ] 1.1 修改 subagents 规格，定义受限 AgentLoop 子 agent。
- [ ] 1.2 修改 agent-runtime 规格，定义父子 AgentLoop 事件边界。
- [ ] 1.3 修改 tool-system 规格，定义子 agent 工具权限继承和限制。

## 2. 测试

- [ ] 2.1 新增子 agent 使用独立 messages 的测试。
- [ ] 2.2 新增子 agent 可执行只读工具循环的测试。
- [ ] 2.3 新增 ParentChannel 回传完成/失败/取消结果的测试。
- [ ] 2.4 新增子 agent trace 记录测试。

## 3. 实现

- [ ] 3.1 调整 SubAgentManager 以创建受限 AgentLoop。
- [ ] 3.2 为子 agent 配置独立 tools、memory、trace 和 mode。
- [ ] 3.3 扩展 ParentChannel result 格式。
- [ ] 3.4 确保取消逻辑能停止子 AgentLoop。

## 4. 验证

- [ ] 4.1 运行 subagent 和 AgentLoop 测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 OpenSpec strict validate。
