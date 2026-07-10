## Context

当前测试分层已经覆盖 AgentLoop 单元/集成、CLI adapter、Web server/session 和可选真实 API 浏览器 E2E，但 fake LLM 逻辑散落在多个测试文件中。CLI 入口测试多数直接替换整个 agent，Web 入口测试有私有 `MockLLM`，浏览器测试默认依赖真实 LLM。

这导致一个风险：入口层看起来有测试，但它们证明的是各自局部 adapter 行为，不能稳定证明 CLI、Web 和未来 TUI 都通过同一套 AgentLoop、ToolRegistry、slash command、streaming、mode 和 tool display 语义。

## Goals / Non-Goals

Goals:

- 抽象共享测试 LLM harness，供 CLI、Web、未来 TUI 的入口 smoke 复用。
- 默认使用 deterministic fake LLM，覆盖真实 AgentLoop 路径。
- 保留 opt-in real LLM profile，便于人工或夜间验证。
- 支持普通回复、streaming、tool call、错误路径和调用记录。
- 让 Playwright browser smoke 不再依赖真实 API。

Non-Goals:

- 不把 fake LLM 做成生产 provider。
- 不替换所有已有小粒度 adapter 测试。
- 不在本 change 实现 TUI。
- 不把真实 API smoke 加入默认 CI。
- 不解决所有 UI 视觉回归，只先覆盖基本功能 smoke。

## Decisions

### Decision 1: 共享 harness 实现 LLM protocol

新增测试辅助模块，例如 `tests/support/llm_harness.py`。核心对象命名可为 `ScriptedLLM`，实现现有 `LLM` protocol，并暴露 `model` 字段，便于 CLI/Web `/status` 和调试输出复用。

理由：只替换 LLM，可以保留真实 AgentLoop、ToolRegistry、Memory、hooks、runtime event 和入口输出逻辑。

### Decision 2: 脚本化响应是默认 fake 模型

`ScriptedLLM` 首版接收一组顺序 response step，每次 `chat` 或 `stream_chat` 消费下一个 step。step 至少覆盖：

- 普通 `LLMResponse(content=...)`
- streaming delta 和最终 `streamed` 完成态
- tool call response
- provider-like error
- 调用记录和断言辅助

理由：入口回归需要可预测，而不是依赖模型自然语言质量。

首版不实现 prompt hash 匹配、record/replay 或真实响应录制。参考 Gemini CLI、Goose、SWE-agent 和 OpenCode 后，record/replay 确认有价值，但先作为未来扩展记录，避免首版 harness 变成另一套 provider/trajectory 系统。

### Decision 3: CLI smoke 不再 fake 整个 agent

新增 CLI runtime smoke 时，只在测试中 monkeypatch `cli.build_llm`，不新增生产级 LLM factory seam，也不 monkeypatch `build_agent` 为 `FakeAgent`。已有 `FakeAgent` adapter 测试可以保留，用于快速覆盖 CLI 命令解析和输出边界。

理由：`FakeAgent` 测不到 AgentLoop 与 CLI 之间的真实事件、工具和消息协议。

### Decision 4: Web browser smoke 使用 fake LLM app/server

新增 Playwright smoke 应通过 `create_app(ScriptedLLM)` 启动测试专用 uvicorn server，绑定随机空闲端口，再让 Playwright 打开该地址。测试覆盖页面加载、slash suggestions、命令执行、mode 切换、消息展示和基本响应。不要求 API key，也不依赖真实模型输出。

理由：浏览器回归应该默认稳定；真实 API 浏览器 E2E 继续作为可选验证。

### Decision 5: real LLM profile 复用 smoke 入口，不进入默认 CI

harness 可以提供 real provider adapter 或 fixture profile，让同一类 smoke 在显式 flag/env 下切换到真实 LLM。默认 CI 只运行 fake LLM。

理由：真实 API 适合发现 provider 集成问题，但不适合作为基础门禁。

### Decision 6: TUI 实现前必须接入同一 harness

未来 TUI change 进入实现时，应使用本 harness 做至少一个 fake LLM 入口 smoke，覆盖 TUI 输入事件、runtime event 消费和屏幕状态。

理由：TUI 不能另起一套 fake runtime，否则 CLI/Web/TUI 行为会漂移。

## Pre-Implementation Review

- Questions resolved:
  - 本 change 是测试基础设施能力，不只是 Web Playwright 测试。
  - fake LLM 应作为共享驱动层，而不是每个入口 fake agent。
  - CLI、Web 和未来 TUI 都应能接入同一 harness。
  - 真实 LLM smoke 需要保留，但必须是 opt-in。
  - `ScriptedLLM` 首版只做顺序脚本和调用记录，不做 prompt hash、record/replay 或真实响应录制；record/replay 记录为未来扩展。
  - CLI runtime smoke 只 monkeypatch `cli.build_llm`，不先扩生产 factory seam。
  - Playwright fake browser smoke 使用 `create_app(ScriptedLLM)` 启测试专用 uvicorn server 和随机端口；缺少 Playwright browser 时跳过并记录。
  - 默认 CI 只跑 fake LLM harness 覆盖；real API 继续使用显式 `--run-real-api`。
  - Web server/session 的通用私有 `MockLLM`、`StreamingLLM`、`FailingLLM` 尽量迁移到共享 harness；CLI 旧 `FakeAgent` adapter 测试保留。
- Options considered:
  - 每个入口继续维护自己的 mock。
  - 共享 fake AgentLoop。
  - 共享 fake LLM 并保留真实 AgentLoop。
  - 将真实 API 浏览器 E2E 作为默认回归。
  - 首版引入 record/replay。
  - 首版新增生产级 LLM factory seam。
- Rejected alternatives:
  - 每个入口私有 mock。原因：会继续产生测试语义漂移。
  - 共享 fake AgentLoop。原因：无法证明入口和真实 runtime 的集成。
  - 默认真实 API E2E。原因：慢、依赖外部网络/API key、模型输出不稳定。
  - 首版 record/replay。原因：参考实现证明它适合 provider/trajectory 长期演进，但当前首要目标是稳定入口 smoke。
  - 生产级 LLM factory seam。原因：当前测试可通过 monkeypatch `build_llm` 接入，先避免无用户可见收益的生产结构变化。
- Final confirmations:
  - 可以进入实现；实现范围按上面的顺序脚本 harness、CLI/Web/Browser fake smoke、real API opt-in 和 Web mock 收敛推进。
  - `CONTEXT.md` 不新增实现细节；测试 harness 语义记录在 OpenSpec、测试指南和相关 current specs。
- Remaining risks:
  - 如果 harness API 太宽，会变成另一套 provider 抽象。
  - 如果 Playwright 环境依赖处理不好，默认回归可能 flaky。
  - 如果 CLI 只能通过 monkeypatch `build_llm` 接入，后续可能需要更清晰的 factory seam。

## Risks / Trade-offs

- [Risk] 测试辅助模块被生产代码依赖。Mitigation: 放在 `tests/support/` 或等价测试目录，生产代码不 import。
- [Risk] fake LLM 过度模拟 provider 细节。Mitigation: 只实现 `LLM` protocol 和入口 smoke 所需行为，provider serialization 仍由 provider 单元测试覆盖。
- [Risk] Browser smoke 引入环境不稳定。Mitigation: fake LLM browser smoke 与 real API E2E 分离；CI 是否安装 browser 由后续实现阶段确认。
- [Risk] CLI 注入点不清晰。Mitigation: 优先 monkeypatch `build_llm`，如不够再小步引入可测试的 LLM factory，不改用户可见行为。

## Testing Strategy

- Harness 单元测试：
  - 普通文本 response。
  - streaming delta 和 complete。
  - tool call response。
  - error response。
  - 调用记录、messages/tools/model 断言。
- CLI runtime smoke：
  - `CliRunner -> cli.main -> build_agent -> AgentLoop -> ScriptedLLM -> CLI output`。
  - 覆盖普通回复、streaming 去重、tool call 摘要、slash command 不触发 LLM。
- Web runtime smoke：
  - `create_app(ScriptedLLM)` 通过 TestClient/WebSocket 覆盖 session、run id、mode、streaming、command result。
- Web browser smoke：
  - Playwright 打开 fake LLM Web UI。
  - 覆盖页面加载、slash suggestions 过滤、`/status`、`/clear`、mode 切换和普通回复展示。
- TUI 预留：
  - TUI change 实现时必须新增至少一个 fake LLM entrance smoke。
- 验证：
  - 运行相关 CLI/Web/harness 测试。
  - 如实现涉及 AgentLoop 或 tool path，运行至少一个 benchmark smoke。
  - 运行全量测试、OpenSpec strict validate 和 artifact checker。
