## 1. 规格

- [ ] 1.1 修改 agent-modes 规格，定义 `read_only`、`build`、`plan`、`bypass` 的边界。
- [ ] 1.2 修改 tool-system 规格，定义 mode 对工具 schema 暴露和执行的约束。
- [ ] 1.3 修改 CLI/Web/benchmark 规格，定义 mode 参数和记录语义。

## 2. 测试

- [ ] 2.1 新增 read-only mode 不暴露 Write/Edit/Bash 等写入或 dangerous 工具的测试。
- [ ] 2.2 新增 build mode 保持当前 coding tools 可用的测试。
- [ ] 2.3 新增 mode 传入 CLI/Web/benchmark 构造路径的测试。
- [ ] 2.4 新增直接执行被 mode 禁止工具时返回可读错误的测试。

## 3. 实现

- [ ] 3.1 增加 AgentMode 数据结构或枚举。
- [ ] 3.2 在工具集合构造或 ToolRegistry 层应用 mode policy。
- [ ] 3.3 为 CLI 增加 mode 参数并传入 AgentLoop 构造路径。
- [ ] 3.4 为 Web session 增加 mode 配置入口。
- [ ] 3.5 为 benchmark runner 记录并传入 mode。

## 4. 验证

- [ ] 4.1 运行 agent/tool 相关测试。
- [ ] 4.2 运行 CLI/Web/benchmark 相关测试。
- [ ] 4.3 运行全量测试。
- [ ] 4.4 运行 OpenSpec strict validate。
