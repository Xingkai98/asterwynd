# CLAUDE.md / AGENTS.md

Guidance for coding agents and Claude Code working in this repository.

> **Maintenance**: These two files are identical copies. When you edit
> `CLAUDE.md`, run `cp CLAUDE.md AGENTS.md`. When you edit `AGENTS.md`,
> run `cp AGENTS.md CLAUDE.md`. Commit both together.

## Language

- **README.md**: Chinese (中文) — see [README_EN.md](./README_EN.md) for English
- **docs/**: Chinese (中文)
- **CLAUDE.md, AGENTS.md**: English
- **Code + comments**: English
- **Commit messages**: Chinese

## Project Overview

MyAgent is a lightweight general-purpose AI agent framework in Python, with a
Typer CLI and FastAPI/WebSocket UI. Designed for clean architecture with every
plugin subsystem independently explainable, testable, and benchmarkable.

## Commands

Prefer `uv run` for reproducible dependency resolution. Direct commands are
also valid when the active Python environment already has dependencies installed.

```bash
# Install dependencies
uv sync --extra dev

# Run all tests
uv run pytest -q

# Run a specific test file
uv run pytest tests/agent/tools/test_registry.py -v

# Run CLI (requires .env with API key)
uv run python cli.py main "用 Read 工具读 /tmp"

# Interactive mode
uv run python cli.py main --interactive

# Web UI (provider/model from .env, CLI flags override)
uv run python cli.py web                          # start on port 8000
uv run python cli.py web --port 3000              # custom port
MYAGENT_DEBUG=enabled uv run python cli.py web     # debug mode

# Benchmark smoke (fake agent)
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake --source-repo . --runs-dir /tmp/smoke \
  --fake-edit-file README.md \
  --fake-old-string '# MyAgent' \
  --fake-new-string '# MyAgent Coding Agent'

# Real agent benchmark (serial, default)
uv run python cli.py benchmark benchmarks/tasks \
  --agent myagent --source-repo . --runs-dir /tmp/bench

# Real agent benchmark (parallel, with external repo cache)
MYAGENT_BENCHMARK_PARALLEL=4 uv run python cli.py benchmark benchmarks/tasks \
  --agent myagent --provider anthropic --runs-dir /tmp/bench \
  --clone-cache-dir /tmp/swebench-cache

# Browser tests (requires playwright)
playwright install chromium
MYAGENT_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

## Architecture

### Core: AgentLoop (`agent/loop.py`)

The `AgentLoop` is the single orchestrator:

```
messages → LLM → tool_calls → execute → append results → repeat
```

The only state it maintains is `messages: list[Message]`. All other concerns
are delegated to plugins.

### Seven Plugin Systems

| Plugin | File | Responsibility |
|--------|------|----------------|
| ToolRegistry | `agent/tools/registry.py` | Dynamic tool registration + sandbox execution |
| WorkspacePolicy | `agent/workspace_policy.py` | Workspace safety boundary (paths, files, commands) |
| HookManager | `agent/hooks/manager.py` | Lifecycle extension points (before_iteration, before_tool_execute, etc.) |
| MemoryManager | `agent/memory/manager.py` | Session message history + AutoCompact token compression |
| SkillLoader | `agent/skills/loader.py` | Markdown skill file loading (YAML frontmatter + prompt body) |
| SubAgentManager | `agent/subagent/manager.py` | Background task delegation + ParentChannel mid-turn injection |
| TraceRecorder | `agent/trace_recorder.py` | Full trace: iterations, tool calls, edits, tests (no truncation) |

### Coding Tools (10 built-in)

| Tool | File | Permission |
|------|------|------------|
| Read | `agent/tools/builtin/read.py` | read_only |
| Write | `agent/tools/builtin/write.py` | read_write |
| Edit | `agent/tools/builtin/edit.py` | read_write |
| Bash | `agent/tools/builtin/bash.py` | dangerous |
| Grep | `agent/tools/builtin/grep.py` | read_only |
| InspectGitDiff | `agent/tools/builtin/inspect_git_diff.py` | read_only |
| ListFiles | `agent/tools/builtin/list_files.py` | read_only |
| Find | `agent/tools/builtin/find.py` | read_only |
| WebSearch | `agent/tools/builtin/web_search.py` | read_only |
| WebFetch | `agent/tools/builtin/web_fetch.py` | read_only |

BashTool returns structured JSON (`exit_code`, `stdout`, `stderr`, `duration_ms`,
`timed_out`). WorkspacePolicy enforces a prefix allowlist and regex denylist
(42 patterns) for command safety. See `agent/workspace_policy.py`.

### Web UI (`web/`)

FastAPI + WebSocket server with vanilla JS frontend. Two views:

- **Chat**: conversational interface with streaming text and tool call display
- **Debug**: configurable via `MYAGENT_DEBUG=enabled`, shows per-iteration:
  full message list sent to LLM, LLM raw response, tool execution details,
  memory compaction events
- `web/server.py` — FastAPI app, WebSocket endpoint, session management
- `web/session.py` — SessionManager: one AgentLoop + messages per session
- `web/debug_hook.py` — DebugHook: captures iteration state via Hook protocol
- `web/static/` — Vanilla HTML/CSS/JS frontend

### Local Benchmark (`benchmarks/`)

31 coding-agent tasks: 21 myagent internal tasks (extracted from git history) +
10 SWE-bench Verified external tasks (flask, requests, pytest). SWE-bench style
evaluation in isolated git worktrees or external repo clones:

1. For internal tasks: create detached worktree at task `base_commit`
2. For external tasks: clone repo from `external_repo` URL, install deps in venv
3. Hide `benchmarks/tasks/` from agent workspace (internal tasks only)
4. Run agent with coding prompt + tools (30 min timeout per task)
5. Save agent source diff (`:!tests/`), reset worktree, reapply sources
6. Apply hidden `test.patch`, run validation command
7. Write `result.json`, `trace.json`, `final.diff`, `test_output.txt`, `runner.log`

**Parallel execution**: Set `MYAGENT_BENCHMARK_PARALLEL=N` to run N tasks
concurrently via `asyncio.Semaphore`. Default is 1 (serial, backward compatible).
External repos are cloned into a shared bare cache (`--clone-cache-dir`) with
serial pre-fill to eliminate TOCTOU races during parallel runs.

### Anthropic / DeepSeek Compatibility

When using Anthropic-compatible APIs (including DeepSeek), two requirements:

1. **Tool results must be batched**: consecutive `tool` messages are merged into
   a single `user` message with multiple `tool_result` blocks.
2. **Text before tool_use**: assistant messages must place `text` blocks before
   `tool_use` blocks.

Both are handled in `agent/anthropic_llm.py`. These do not affect the OpenAI
code path.

### Adding New Capabilities

- **New tool**: Subclass `Tool` (ABC), use `@tool_parameters` decorator, register with `ToolRegistry`
- **New hook**: Implement the `Hook` Protocol, add to `HookManager([...])`
- **New skill**: Create a `.md` file in `skills/` with YAML frontmatter
- **New LLM provider**: Implement the `LLM` Protocol (see `agent/llm.py`)

### Key Design Patterns

- **Protocol + runtime_checkable**: Used for `LLM` and `Hook` — structural typing without inheritance
- **`@tool_parameters` decorator**: Attaches name/description/JSONSchema to `Tool` subclasses
- **AutoCompact**: Triggered after each tool-call round; preserves system + recent messages, compresses middle via LLM
- **ParentChannel**: `asyncio.Queue` between parent and subagent; `ParentChannelHook` injects subagent results mid-turn

### LLM Interface (`agent/llm.py` + `agent/openai_llm.py`)

The `LLM` Protocol defines `chat(messages, tools, model) -> LLMResponse`.
`OpenAILLM` is the default implementation via httpx + OpenAI Chat Completions
API. To add another provider: implement `LLM` Protocol.

## Testing

```bash
# Full suite
pytest -q

# Benchmark tests
pytest -q tests/benchmark

# Web/server tests
pytest -q tests/web_tests/test_session.py tests/web_tests/test_server.py

# Single test file
uv run pytest tests/agent/tools/test_registry.py -v
```

For benchmark changes, also run a fake-runner smoke:

```bash
pytest -q tests/benchmark
uv run python cli.py benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke
```

Browser/real API tests are optional:

```bash
playwright install chromium
MYAGENT_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

## Development Rules

- Add or update regression tests for bug fixes.
- Keep tool-call protocol chains valid: an assistant message with `tool_calls` must keep its matching `tool` result messages.
- Do not make the `max_iterations` path fabricate a final assistant response from a tool result.
- Treat benchmark `passed_with_warnings` as a test-passing result with agent-side issues such as `max_iterations`; do not count it as a clean pass.
- Preserve debug UI behavior across multiple chat turns; AgentLoop iteration numbers restart per chat turn, so UI grouping must distinguish chat turns.
- Keep `.codegraph/`, `.understand-anything/`, `.dev/`, local `.env*`, logs, and other generated/local files out of commits unless explicitly requested.

## Regression Testing Rule

**Every bug fix requires a new regression test.** When an error occurs:

1. Analyze the error and identify the root cause
2. Fix the bug
3. **Immediately write a regression test** that reproduces the bug
   - The test must be in `tests/agent/<subsystem>/test_<component>.py`
   - Name it `test_<specific behavior>`, e.g. `test_anthropic_llm_sync_json_response`
   - The test must fail before the fix and pass after
4. Run `uv run pytest tests/ -v` to verify all tests pass before committing

Test files: `tests/agent/<subsystem>/test_<component>.py`. Implementation:
`agent/<subsystem>/<component>.py`. Builtins: `agent/<subsystem>/builtin/<name>.py`.

## Design Documents

- `docs/coding-agent-roadmap.md` — coding agent roadmap (live, updated as features ship)
- `docs/benchmark-plan.md` — benchmark system design and task structure
- `docs/discussions/` — design review meeting notes (write one per significant decision session)

## Environment

Relevant environment variables:

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`
- `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`
- `MYAGENT_PROVIDER`: `openai` or `anthropic`
- `MYAGENT_MODEL`: default model override
- `MYAGENT_DEBUG=enabled`: enables the Debug tab and structured debug events
- `MYAGENT_LOG_LEVEL=DEBUG`: more verbose server/CLI logging
- `MYAGENT_BENCHMARK_PARALLEL`: number of concurrent benchmark tasks (default 1, serial)
- `MYAGENT_COMMAND_DENYLIST`: comma-separated extra deny patterns for BashTool
- `MYAGENT_IGNORE_PATTERNS`: comma-separated extra ignore dirs for ListFiles/Find

## 问题定位

当需要定位问题时，首先定位清楚根因，给出解决方案，待确认后才能实际修改代码。

## Lessons Learned

### Pitfall 1: uv run 隔离 venv 缺少依赖
`uv run` 创建隔离虚拟环境，只装 `pyproject.toml` 中声明的依赖。`websockets` 在系统已安装但不在依赖列表 → WebSocket 连接 404。
**教训**: 新增 WebSocket/FastAPI 功能时，`pyproject.toml` 必须声明 `websockets`。

### Pitfall 2: Mock 行为与真实 API 不一致
`httpx.Response.json()` 是同步方法（返回 dict），测试用 `AsyncMock` 模拟 → `await response.json()` 通过了测试但运行时炸。
**教训**: Mock 第三方库方法前，先确认它是否真的是 async。用 `MagicMock` 而非 `AsyncMock` 模拟同步方法。

### Pitfall 3: LLM provider 专有字段透传
DeepSeek 思考模式返回 `reasoning_content`，必须在后续请求的 assistant message 中原样传回。Message 序列化时丢掉了这个字段 → 400。
**教训**: 对接新 provider 时，检查其响应是否有"需要回传"的非标准字段（如 reasoning_content）。Message 和 LLMResponse 需保守地保留未知字段。

### Pitfall 4: 0.0.0.0 是监听地址不是访问地址
服务器 bind `0.0.0.0` 表示监听所有网卡，但浏览器不能连接这个地址。
**教训**: 启动日志应显示实际可访问的 URL（`127.0.0.1` 或 `localhost`）。

### Pitfall 5: 默认模型名不匹配实际 provider
`OpenAILLM` 默认 `model="gpt-4"`，但用户可能配了 DeepSeek 等其他 provider。
**教训**: 无 `--model` 时应从环境变量读取默认值，或启动时警告 model 名与 base_url 不匹配。

### Pitfall 6: 日志只输出 stderr 不留痕
`logging.basicConfig()` 默认输出到 stderr，进程退出就没了。
**教训**: 服务器模式必须加文件日志（`RotatingFileHandler`），每次启动用不同文件名（带时间戳）。

### Pitfall 7: AgentLoop 返回前未将最终回复写入 messages（2026-05-28）
`AgentLoop.run()` 在正常返回路径直接 return，没有把 assistant 最终回复 append 到 messages。下一轮对话时 agent 看不到自己上一条回复，只能看到 tool call + tool result，于是根据同样的 tool result 重新生成相似回答，变成"复读机"。
**教训**: AgentLoop 返回前必须将最终回复写入 messages。CLI 模式的 `messages.append()` 和 loop 内部的 append 只能有一处，否则重复。

### Pitfall 8: MemoryManager.compact_if_needed 操作空列表（2026-05-28）
MemoryManager 的 `compact_if_needed()` 统计的是自己的 `self.messages`，但 AgentLoop 用的是独立的 `messages` 列表。没有任何代码调用 `memory.add()`，导致 self.messages 永远为空，token compaction 从不触发。
**教训**: 插件管理自己的内部状态时，确保 AgentLoop 实际使用的数据源与插件操作的数据源是同一个。
