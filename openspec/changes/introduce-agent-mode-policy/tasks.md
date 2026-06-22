## 1. 规格

- [ ] 1.1 修改 agent-modes 规格，定义 `read_only`、`build`、`plan`、`bypass` 的边界。
- [ ] 1.2 修改 tool-system 规格，定义 mode 对工具 schema 暴露和执行的约束。
- [ ] 1.3 修改 CLI/Web/benchmark 规格，定义 mode 参数和记录语义。

## 2. 测试

- [ ] 2.1 按 TDD 先新增 mode 字符串解析测试，覆盖 `read_only`、`read-only`、`build`、`plan` 和拒绝 `bypass` 用户入口。
- [ ] 2.2 新增 read-only mode 不暴露 Write/Edit/Bash 等写入或 dangerous 工具的测试。
- [ ] 2.3 新增 build mode 下 CLI/Web 默认工具集合一致、benchmark 保持 coding tools 的测试。
- [ ] 2.4 新增 mode 传入 CLI/Web/benchmark 构造路径的测试。
- [ ] 2.5 新增直接执行被 mode 禁止工具时返回可读错误且不调用真实 execute 的测试。
- [ ] 2.6 新增 run_started、日志、trace 和 benchmark artifact 记录 mode 的测试。

## 3. 实现

- [ ] 3.1 增加 `agent/run_config.py`，实现 AgentMode、AgentRunConfig、parse_agent_mode 和 ModePolicy。
- [ ] 3.2 增加 `agent/tools/factory.py`，实现 CLI/Web 共享默认工具构造路径，并保留 benchmark-specific coding tools。
- [ ] 3.3 在 ToolRegistry 层接入 ModePolicy。
- [ ] 3.4 为 CLI 增加 mode 参数并传入 AgentLoop 构造路径。
- [ ] 3.5 为 Web session 增加 mode 配置入口。
- [ ] 3.6 为 benchmark runner 记录并传入 mode。

## 4. 验证

- [ ] 4.1 运行 agent/tool 相关测试。
- [ ] 4.2 运行 CLI/Web/benchmark 相关测试。
- [ ] 4.3 运行全量测试。
- [ ] 4.4 运行 OpenSpec strict validate。
