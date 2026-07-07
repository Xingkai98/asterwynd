# 测试指南

本文档记录 Asterwynd 的测试分层和回归测试要求。

## 基本原则

- 每个 bug fix 必须新增回归测试。
- 测试应该证明行为，而不是只覆盖实现细节。
- 涉及共享协议的变更必须覆盖协议不变量。
- real API 测试保持可选，不作为默认 CI 前置条件。
- CLI、Web 和未来 TUI 的入口 smoke 优先使用共享 `ScriptedLLM` fake harness，只替换 LLM provider，不替换真实 AgentLoop。

## 回归测试规则

当修复 bug 时：

1. 先定位根因。
2. 写出能复现问题的测试。
3. 修复实现。
4. 确认新测试和相关测试通过。

测试文件优先放在对应子系统下：

```text
tests/agent/<subsystem>/test_<component>.py
```

示例：

```text
agent/tools/builtin/edit.py
tests/agent/tools/test_edit_tool.py
```

## 测试分层

### 单元测试

覆盖确定性逻辑，不依赖真实 LLM 和网络。

重点模块：

- WorkspacePolicy
- ToolRegistry
- EditTool / BashTool / ListFiles / Find / RepoMap / SymbolSearch
- WebSearch / WebFetch 的 fake provider、fake transport、错误诊断和截断逻辑
- TraceRecorder
- Message / Result
- provider message serialization

### 集成测试

覆盖多个模块协作。

重点场景：

- EditTool + WorkspacePolicy + InspectGitDiff
- BashTool 执行本地测试并返回结构化输出
- AgentLoop 工具调用链
- Tool permission metadata、ModePolicy 三值判定和 require_approval fail-closed 行为
- Memory compact 后保持 tool-call 协议合法
- CLI slash command registry 的命令解析、未知命令拦截、上下文清理、手动 compact、`/skills` reload 和 skill command 触发 Agent run
- CLI 入口 smoke 应至少覆盖真实 `build_agent` + `ScriptedLLM` 的普通回复、streaming 去重和工具调用摘要；旧 `FakeAgent` 测试只能作为 adapter 层补充。
- Skill runtime 的多 root 加载、诊断、重复名称处理、index 注入、匹配注入和 `ActivateSkill` 工具激活
- Web session 消息历史
- Web session 的 session id / run id / session mode、Plan Document、planning state 事件、工具结果 display metadata、approval request/response 和 skill command 执行
- Benchmark runner artifact 写入

### Web 测试

Web 测试覆盖 server、session 和浏览器行为。

重点覆盖：

- server/session/browser 测试默认复用 `tests/support/llm_harness.py` 中的 `ScriptedLLM`，覆盖普通回复、streaming、tool call、错误和调用记录。
- Chat 页面 assistant Markdown 渲染，包括列表、代码块、链接，以及 raw HTML / unsafe link 的转义或阻断。
- 工具结果展示策略，包括长结果折叠、preview、字符/行数元数据，以及工具结果不走 Markdown/HTML 注入。
- session id、run id、session mode、Plan Document、planning state、approval request/response 和 Debug 开关的前端可见行为。

常用命令：

```bash
uv run pytest tests/web_tests/test_session.py tests/web_tests/test_server.py -q
```

浏览器测试需要 Playwright：

```bash
playwright install chromium
uv run pytest tests/web_tests/test_browser.py -q
ASTERWYND_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

默认浏览器 smoke 使用 fake LLM 测试专用 Web server，不要求 API key；真实 API 浏览器 E2E 仍然必须显式传入 `--run-real-api`。

### 共享 LLM 测试 Harness

共享 fake LLM 位于 `tests/support/llm_harness.py`。新增 CLI、Web、未来 TUI 或 benchmark 入口回归时，优先复用 `ScriptedLLM`：

- 使用顺序脚本响应表达普通文本、streaming delta、tool call 和 provider-like error。
- 使用 `call_count`、`calls`、`last_messages` 和 `messages_seen` 断言入口层传给 LLM 的消息、工具和 model。
- 首版 harness 不做 prompt hash 匹配、record/replay 或真实响应录制；这些能力可作为后续扩展单独设计。
- fake 入口 smoke 不应 monkeypatch 整个 AgentLoop；只有 adapter 层测试才保留私有 fake agent。

未来 TUI 实现时，至少新增一个基于 `ScriptedLLM` 的入口 smoke，证明 TUI 输入、runtime event 消费和屏幕状态展示接入真实 AgentLoop。

### Benchmark 测试

Benchmark 测试要和模型质量解耦，优先使用 fake agent 和临时 git 仓库。

常用命令：

```bash
uv run pytest tests/benchmark -q
uv run python cli.py benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke
```

涉及 AgentLoop、coding tools、workspace safety、benchmark runner 或其他 coding-agent 核心路径的变更，除了相关单元/集成测试外，至少跑通一个 benchmark smoke。优先选择能验证真实 runner 闭环的任务；如果改动影响外部 SWE-bench 风格任务，至少单独跑一个 `swebench-*` 任务。

外部 SWE-bench 风格任务依赖 Docker daemon 和 `swebench` 包；默认 `uv sync --extra dev` 会一并安装。Docker 不可用时，这类任务应返回 `unsupported`，而不是误记为 agent 失败。

单任务 SWE smoke 示例：

```bash
rm -rf /tmp/asterwynd-one-swe-task /tmp/asterwynd-swe-smoke
mkdir -p /tmp/asterwynd-one-swe-task
ln -s "$PWD/benchmarks/tasks/swebench-psf__requests-5414" \
  /tmp/asterwynd-one-swe-task/swebench-psf__requests-5414
uv run python cli.py benchmark /tmp/asterwynd-one-swe-task \
  --agent shell \
  --shell-command "git apply $PWD/benchmarks/tasks/swebench-psf__requests-5414/gold.patch" \
  --source-repo . \
  --runs-dir /tmp/asterwynd-swe-smoke \
  --clone-cache-dir /tmp/asterwynd-swe-cache
```

如果当前开发环境是没有 `systemd` 的容器，可先用辅助脚本启动 Docker daemon：

```bash
sudo ./scripts/start-docker-daemon.sh
```

Claw-SWE-Bench 集成使用独立 harness，不通过 `cli.py benchmark`。如果改动影响 `claw-swe-bench/` 或 `agent/claw_solve.py`，在环境具备 Docker 镜像和 API key 时至少跑一个单实例 smoke：

```bash
cd claw-swe-bench
uv run python run_infer.py \
  --claw asterwynd \
  --dataset verified \
  --instance_ids psf__requests-1142 \
  --run_id asterwynd-claw-smoke \
  --model deepseek-v4-pro \
  --timeout 600
```

## 必须守住的协议

- assistant message 如果包含 `tool_calls`，必须保留匹配的 tool result。
- `max_iterations` 不能把最后一个 tool result 包装成 assistant 最终回复。
- 最终 assistant 回复需要进入消息历史，避免多轮对话复读。
- Memory compact 不能破坏 tool-call / tool-result 相邻链。
- CLI/Web 独立 slash command 属于命令输入；未知 slash command、`/clear`、`/compact` 和 `/skills` 不能作为普通用户消息发送给 AgentLoop/LLM。`kind=prompt` 的 skill command 必须只把命令参数作为用户消息启动 Agent run，并在 run 前激活对应 skill。
- `passed_with_warnings` 是测试通过但过程不干净，不能算 clean pass。
- benchmark 结果分类读 `status`，具体细节读 `reason`；`unsupported` 不能并入 `failed`。
- Web Chat 的 assistant streaming 必须通过 AgentLoop `assistant_delta` / `assistant_stream_complete` 事件进入 WebSocket 和 CLI；回归测试必须覆盖流式展示不重复最终 `llm_response`，不能只改前端展示。

## 覆盖率目标

后续需要建立明确覆盖率门槛。初始建议：

- 核心 agent、工具、workspace policy、benchmark runner 保持高覆盖。
- CLI 和 Web 需要覆盖主要用户路径。
- 新增功能必须有单元测试；涉及跨模块行为时补集成测试。
