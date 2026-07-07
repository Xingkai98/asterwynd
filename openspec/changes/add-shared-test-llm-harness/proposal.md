## Why

当前仓库已经有多层 fake/mock 测试，但入口形态之间还没有统一的测试 LLM 驱动层：

- CLI 测试主要 monkeypatch `build_agent` 为 `FakeAgent`，能覆盖 CLI 参数、输出和 slash command 路由，但没有完整经过 `CLI -> AgentLoop -> fake LLM -> 工具/事件 -> CLI 输出`。
- Web server/session 测试已有 `MockLLM`，能通过 FastAPI/WebSocket 和 AgentLoop 跑 fake LLM，但这个 mock 是 Web 测试私有实现。
- Playwright 浏览器测试当前偏真实 API E2E，依赖 API key 和模型行为，不适合作为默认基础回归。
- 未来 TUI 也需要同样的入口 smoke；如果没有共享 harness，TUI 很容易重新发明一套 fake runtime。

本 change 目标是抽象共享的 fake/real LLM test harness，让 CLI、Web、未来 TUI 都能接入真实入口和 AgentLoop 逻辑做稳定回归，同时保留可选真实 LLM smoke。

## Change Type

- primary: feature
- secondary: [process]

## What Changes

- 新增共享测试 LLM harness，提供 `ScriptedLLM` 或等价实现，兼容现有 `LLM` protocol。
- harness SHALL 支持脚本化普通回复、streaming delta、tool call、错误返回和调用记录。
- CLI smoke SHALL 能只替换 LLM，不替换整个 AgentLoop，从而覆盖真实 `build_agent`、ToolRegistry、runtime event 和 CLI 输出路径。
- Web server/browser smoke SHALL 复用同一 harness，避免 Web 私有 `MockLLM` 继续扩散。
- 未来 TUI 实现时 SHALL 使用同一 harness 做入口 smoke。
- harness SHALL 允许切换到真实 provider 作为 opt-in smoke；真实 LLM 不进入默认 CI 门禁。

## Capabilities

### Modified Capabilities

- `agent-runtime`: 增加共享测试 LLM harness 对 AgentLoop fake/real smoke 的约束。
- `cli`: 要求 CLI 入口回归能通过真实 AgentLoop 和共享 fake LLM 运行。
- `web-ui`: 要求 Web server/browser 回归能通过共享 fake LLM 运行，不依赖真实 API。
- `tui`: 为未来 TUI 入口 smoke 预留同一 harness 约束。

## Impact Analysis

- 影响代码：
  - 可能新增 `tests/support/llm_harness.py` 或等价测试辅助模块。
  - 可能调整 `tests/test_cli.py`，新增 CLI runtime smoke。
  - 可能调整 `tests/web_tests/`，复用共享 harness，并新增 deterministic Playwright smoke。
  - 未来 `tui/` 或 TUI 测试应复用该 harness。
- 影响测试：
  - CLI fake LLM runtime smoke。
  - Web FastAPI/WebSocket fake LLM smoke。
  - Web Playwright fake LLM browser smoke。
  - harness 自身单元测试，覆盖文本、streaming、tool call、错误和调用记录。
  - 可选 real API smoke 继续通过显式 flag 或环境变量开启。
- 影响文档：
  - `docs/testing-guide.md`
  - 相关 OpenSpec current specs：`agent-runtime`、`cli`、`web-ui`、`tui`
  - 必要时更新 `docs/development-guide.md`
- 依赖：
  - 依赖现有 `LLM` protocol、AgentLoop、CLI build path、Web SessionManager。
  - Web browser smoke 依赖 Playwright 运行环境；不要求真实 API key。
- 不影响：
  - 不改变生产 LLM provider 行为。
  - 不把 fake LLM 暴露为用户可选 provider。
  - 不改变 benchmark fake runner 语义。
  - 不实现 TUI 本体。

## Reference Implementation Research

- status: enabled
- reason: 入口形态回归测试是 coding agent 质量门禁的一部分，应参考其他 coding agent 如何组织 fake provider、入口 smoke、browser/TUI 回归和真实模型可选验证。
- research questions:
  - 参考项目如何把 fake LLM/provider 接入 CLI、Web、TUI 或 app-server 测试？
  - fake provider 是否使用脚本化响应、fixture server、record/replay，还是直接 fake agent runtime？
  - streaming、tool call 和错误路径在入口 smoke 中如何建模？
  - 真实 LLM smoke 如何与默认 CI 隔离？
  - browser/TUI 回归如何避免模型输出不确定性导致 flaky？
- findings:
  - 当前仓库已有足够内部证据说明需要共享 harness：CLI 使用 `FakeAgent`，Web 使用私有 `MockLLM`，浏览器测试依赖 `--run-real-api`。
  - 本 PR 只创建 change，不进入实现；开发前必须基于 `.dev/reference-repos.txt` 中可用参考仓库补充具体参考实现发现。
  - 如果本地参考仓库不可用，开发前需要记录不可用原因，并以当前仓库测试结构和公开文档作为替代依据。
- design impact:
  - 初始方案坚持 fake LLM 层复用，而不是每个入口 fake 整个 AgentLoop。
  - 真实 LLM smoke 保持 opt-in，避免默认 CI 被外部 API、网络和模型随机性污染。
  - Playwright browser smoke 应走 fake LLM app/server，真实 API 浏览器 E2E 保留为人工或夜间验证。
