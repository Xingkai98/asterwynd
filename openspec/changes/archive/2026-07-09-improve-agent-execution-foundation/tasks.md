## 1. 规格

- [ ] 1.1 更新 `tool-system` spec delta：定义 TodoWrite 工具行为。
- [ ] 1.2 更新 `agent-runtime` spec delta：定义工具错误重试行为和可重试错误分类。
- [ ] 1.3 更新 `planning` spec delta：定义 build mode 下的执行期 todo 状态展示。
- [ ] 1.4 开发前使用 `grill-with-docs` 审视 `design.md`。
- [ ] 1.5 维护 `## Impact Analysis`。
- [ ] 1.6
- [ ] 1.7 同步 spec delta 到 `openspec/specs/<capability>/spec.md`（当前规格）。
 维护 `## Reference Implementation Research`。

## 2. 测试

- [ ] 2.1 TodoWrite 工具单元测试：create/update/list、无效 status、重复 id。
- [ ] 2.2 RetryHook 策略测试：可重试错误重试 3 次后失败、不可重试错误直接失败、退避间隔。
- [ ] 2.3 AgentLoop 集成测试：工具失败后自动重试、重试成功继续执行、达到最大次数后上报 error。
- [ ] 2.4 AgentLoop 集成测试：build mode 下注入 todo 上下文、todo 列表空时不注入。
- [ ] 2.5 Loop 集成测试：retry 不重复触发 approval。
- [ ] 2.6 TUI test：todo 面板展示 pending/in_progress/completed 项。
- [ ] 2.7 AgentLoop 集成测试：`tool_retry` trace step 记录断言（包括重试中 `final=false` 和耗尽后 `final=true` 两场景）。
- [ ] 2.8 AgentLoop 集成测试：read_only mode 下 TodoWrite 权限/执行/注入全链路。
- [ ] 2.9 TodoWrite 工具单元测试：排序规则（in_progress > pending > completed，同组按创建顺序）和最多 10 条截断。
- [ ] 2.10 WebSocket/session 层测试：`todo_updated` 事件到 Web UI 面板渲染。
- [ ] 2.11 AgentLoop 集成测试：Plan items 与 execution todos 隔离——mode 切换后展示互不污染。

## 3. 实现

- [ ] 3.1 实现 `agent/tools/builtin/todo.py` —— TodoWrite 工具。
- [ ] 3.2 在 `factory.py` 将 TodoWrite 加入 `KNOWN_BUILTIN_TOOL_NAMES`；实例由 AgentLoop `_ensure_todo_tool_registered()` 注册，通过回调绑定 loop 内部 `_execution_todos`。
- [ ] 3.3 在 AgentLoop `_execute_tool_calls` 中接入重试逻辑（含 `tool_retry` trace step 记录）。
- [ ] 3.4 在 `_messages_with_run_context` 中注入 todo 状态。
- [ ] 3.5 在 TUI 中新增可选 todo 面板。
- [ ] 3.6 Web UI 展示 todo 状态（后续 PR 或本 PR 内，视复杂度）。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [ ] 4.4 运行 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 4.5 跑通至少一个 benchmark smoke。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-improve-agent-execution-foundation/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除本 change。
- [ ] 5.3 确认 Impact Analysis 无残留 `unknown`/`TBD`/`待确认`。
- [ ] 5.4 运行全量校验。
