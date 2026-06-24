## 1. 规格

- [x] 1.1 修改 `subagents` 规格，定义子 agent 为完整子 session runtime，而不是一次性委托。
- [x] 1.2 修改 `agent-runtime` 规格，定义父 run 与子 session / 子 run 的显式运行时接口边界。
- [x] 1.3 修改 `tool-system` 规格，定义子 session 的 mode / 工具权限继承与 inspect 边界。
- [x] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [x] 1.5 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认关键边界、依赖、风险、测试策略和文档影响已有最终方案。

## 2. 测试

- [x] 2.1 新增创建子 session、列出子 session、查询子 session 状态的测试。
- [x] 2.2 新增同一子 session 承载多次 run 的测试。
- [x] 2.3 新增多个子 session 并发存在，以及同一子 session 内拒绝并发 run 的测试。
- [x] 2.4 新增子 run 执行只读工具循环并产出独立 trace / usage 的测试。
- [x] 2.5 新增父 run 通过显式接口查询、等待和取消子 run 的测试。
- [x] 2.6 新增 transcript inspect 只返回受限范围内容的测试。
- [x] 2.7 新增子 session mode 继承、修改和“只影响后续 run”的测试。
- [x] 2.8 新增 CLI / Web 暴露子 session 状态与最近 run 摘要的测试。

## 3. 实现

- [x] 3.1 调整 `SubAgentManager` 为子 session runtime manager，维护 `subagent_id`、session metadata 和 run 历史。
- [x] 3.2 为子 session 配置独立 transcript、tools、memory、trace、mode 和 run identity。
- [x] 3.3 实现父 agent 使用的显式运行时接口：创建、启动 run、查询、等待、取消、inspect。
- [x] 3.4 将 `ParentChannel` 收敛为内部 runtime channel，移除“直接注入父 messages”的公共语义依赖。
- [x] 3.5 确保子 session 默认使用 `isolated` 上下文，且 mode / 工具权限不得高于父 session。
- [x] 3.6 为 CLI / Web 接入最小子 session 可见性：列表、状态、最近 run 摘要。

## 4. 验证

- [x] 4.1 运行 `tests/agent/subagent/` 和 `tests/agent/test_loop.py`。
- [x] 4.2 运行相关 CLI / Web 测试。
- [x] 4.3 运行全量测试。
- [x] 4.4 运行 OpenSpec strict validate。
- [x] 4.5 跑通至少一个 benchmark smoke。
- [x] 4.6 检查当前 change 文档、`docs/openspec-change-backlog.md` 和相关入口文档是否需要更新。
