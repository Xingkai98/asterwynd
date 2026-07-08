## 1. 规格

- [x] 1.1 修改 tui 规格，定义最小多轮 runtime view。
- [x] 1.2 修改 CLI 规格，定义 TUI 命令入口。
- [x] 1.3 修改 planning 规格，定义 TUI 展示 planning state 的要求。
- [ ] 1.4 closing 阶段同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [x] 1.5 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案。
- [x] 1.6 开发前补实 `## Reference Implementation Research`，基于 `.dev/reference-repos.txt` 中可用参考仓库调研 TUI runtime view，并回写 findings / design impact。
- [x] 1.7 按 PR #47 的 workflow 状态机补齐 `handoff.json`，并记录当前处于 `planning.grilling_design`。
- [x] 1.8 将 `building` phase 的 routing 设置为 `claude-code/new`，当前 Codex 负责 planning、handoff 和后续非实现工作。
- [x] 1.9 明确 `.handoff/` 默认不提交，只作为本地交接材料；长期结论写入 OpenSpec、`handoff.json` 或评审报告。

## 2. 测试

- [x] 2.1 新增 TUI 命令构造 AgentLoop 的测试。
- [x] 2.2 新增 TUI 消费工具事件和 planning 事件的测试。
- [x] 2.3 新增非交互环境下 TUI graceful failure 测试，确认首版清晰报错且不实现 `--plain` 降级。
- [x] 2.4 新增 TUI 多轮 session/controller 测试，覆盖同一 session 多个 run、message history 和退出路径。
- [x] 2.5 新增 Textual app 轻量 smoke 或等价组件测试，避免把主要行为绑定到脆弱渲染快照。
- [x] 2.6 新增 TUI slash command 提示测试，覆盖前缀过滤、alias、skill command、选择填充和命令执行路径。
- [x] 2.7 新增 TUI approval 测试，覆盖 approve、deny 和审批不可用路径。
- [x] 2.8 新增基于真实 AgentLoop + 共享 `ScriptedLLM` 的 TUI 入口 smoke，覆盖输入、运行事件消费和屏幕状态更新；不得使用只服务 TUI 的私有 fake AgentLoop 替代入口 smoke。

## 3. 实现

> Building phase 由 Claude Code 执行；当前 Codex 只负责在 planning gate 前补齐方案和 handoff。

- [x] 3.1 选择 TUI 框架：首版使用 `textual`，核心 runtime 不依赖 Textual。
- [x] 3.2 新增并锁定 `textual` 依赖。
- [x] 3.3 增加 TUI 命令入口。
- [x] 3.4 增加 TUI event reducer / state model，消费 AgentLoop 事件流、planning state 和工具调用展示。
- [x] 3.5 增加 Textual 多轮 app：transcript、输入区、状态栏、工具摘要、planning 区和退出路径。
- [x] 3.6 增加 TUI slash command 提示，复用现有 slash command registry/catalog。
- [x] 3.7 保留基础鼠标滚动 transcript 和点击聚焦输入区能力。
- [x] 3.8 增加 TUI approval approve/deny 交互，复用现有 approval handler 语义；实现为 TUI 独立异步等待型 handler，不得直接调用阻塞 Textual event loop 的 CLI stdin prompt。
- [x] 3.9 展示最终回复、diff/test 摘要、trace 路径、当前 session id 和最近 run id。

## 4. 验证

- [x] 4.1 运行 TUI/CLI 相关测试。
- [x] 4.2 运行全量测试。
- [ ] 4.3 手动启动 TUI smoke。
- [x] 4.4 运行 OpenSpec strict validate。
- [x] 4.5 跑通至少一个 benchmark smoke。
