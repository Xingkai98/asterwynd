## 1. 规格

- [ ] 1.1 更新受影响 capability 的 spec delta。
- [ ] 1.2 明确本 change 的范围、非目标和验收标准。
- [ ] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案。

## 2. 测试

- [ ] 2.1 按 TDD 先新增或调整相关单元测试。
- [ ] 2.2 覆盖跨模块行为的集成测试。
- [ ] 2.3 覆盖入口层测试，例如 CLI、Web、benchmark 或未来 TUI。
- [ ] 2.4 覆盖负向路径和回归场景。

## 3. 实现

- [ ] 3.1 实现最小可验证路径。
- [ ] 3.2 接入相关入口和 artifact 记录。
- [ ] 3.3 更新必要文档。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行项目 OpenSpec artifact checker。
- [ ] 4.5 如果涉及 AgentLoop、工具协议、coding tools、workspace safety、benchmark runner 或其他 coding-agent 核心路径，跑通至少一个 benchmark smoke。
- [ ] 4.6 如果涉及 Web，运行 Web session/server 测试；必要时运行浏览器 smoke。
- [ ] 4.7 如果涉及 TUI、browser/computer use、外部服务或其他人工交互入口，运行对应 smoke。
