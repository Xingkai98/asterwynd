## 1. 规格

- [ ] 1.1 更新 `agent-runtime` spec delta，定义共享测试 LLM harness 的 fake/real smoke 语义。
- [ ] 1.2 更新 `cli` spec delta，定义 CLI fake LLM runtime smoke 约束。
- [ ] 1.3 更新 `web-ui` spec delta，定义 Web server/browser fake LLM smoke 约束。
- [ ] 1.4 更新 `tui` spec delta，定义未来 TUI 必须复用共享 harness。
- [x] 1.5 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [x] 1.6 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，逐项确认 harness API、fixture 注入方式、Playwright server 生命周期、real LLM flag、CI 策略和文档影响。
- [x] 1.7 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面；开发前把待确认项清理为明确结论或阻塞项。
- [x] 1.8 维护 `## Reference Implementation Research`；开发前基于 `.dev/reference-repos.txt` 中可用参考仓库补充具体实现发现和设计影响。
- [x] 1.9 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。

## 2. 测试

- [x] 2.1 新增共享 `ScriptedLLM` 或等价 harness 单元测试，覆盖普通回复、streaming、tool call、错误和调用记录。
- [x] 2.2 新增 CLI runtime smoke，覆盖真实 `build_agent` + fake LLM 的单轮输出。
- [x] 2.3 新增 CLI runtime smoke，覆盖 streaming 去重和 tool call 摘要。
- [x] 2.4 新增 Web server/session smoke 复用共享 harness，替换或收敛私有 `MockLLM`。
- [x] 2.5 新增 deterministic Playwright browser smoke，覆盖页面加载、slash suggestions、`/status`、`/clear`、mode 切换和普通回复展示。
- [x] 2.6 保留 real API smoke 为显式 opt-in，并覆盖 fake/real profile 切换配置或 pytest flag。
- [x] 2.7 为未来 TUI change 增加测试指南约束，说明 TUI 必须接入共享 harness。

## 3. 实现

- [x] 3.1 新增 `tests/support/llm_harness.py` 或等价测试辅助模块。
- [x] 3.2 实现 `ScriptedLLM` response script、调用记录和断言辅助。
- [x] 3.3 提供 CLI 测试注入 helper，优先只替换 LLM，不替换 AgentLoop。
- [x] 3.4 提供 Web app/server 测试 helper，复用同一 harness。
- [x] 3.5 将 Web 私有 `MockLLM` 逐步收敛到共享 harness，保留必要的局部轻量 fixture。
- [x] 3.6 新增或调整 Playwright fixture，使 browser smoke 默认不依赖真实 API。
- [x] 3.7 更新必要文档。

## 4. 验证

- [x] 4.1 运行 harness 单元测试。
- [x] 4.2 运行 CLI 相关测试。
- [x] 4.3 运行 Web session/server 测试。
- [x] 4.4 运行 Playwright fake LLM browser smoke；如当前环境缺少浏览器依赖，记录明确原因和替代验证。
- [x] 4.5 运行全量测试。
- [x] 4.6 运行 OpenSpec strict validate。
- [x] 4.7 运行项目 OpenSpec artifact checker。
- [x] 4.8 如实现触碰 AgentLoop、ToolRegistry 或工具协议，跑通至少一个 benchmark smoke。本 change 未修改 AgentLoop、ToolRegistry 或工具协议；全量测试已覆盖现有 benchmark 测试。

## 5. PR 收尾

- [x] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-add-shared-test-llm-harness/`。
- [x] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [x] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [x] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖。
- [x] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
