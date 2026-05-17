# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MyAgent is a lightweight general-purpose AI agent framework in Python. It is designed for interview preparation — clean architecture with every plugin subsystem independently explainable.

## Commands

```bash
# Install dependencies (uv is fast)
uv sync
uv pip install pytest pytest-asyncio pytest-mock  # dev deps

# Run all tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/agent/tools/test_registry.py -v

# Run CLI (requires OPENAI_API_KEY env var)
uv run python cli.py --model gpt-4o-mini "用 Read 工具读 /tmp"

# Interactive mode
uv run python cli.py --interactive

# Web UI
uv run python cli.py web                          # start web server on port 8000
uv run python cli.py web --port 3000              # custom port
MYAGENT_DEBUG=enabled uv run python cli.py web     # start with debug mode

# Browser tests (requires playwright)
playwright install chromium
MYAGENT_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

## Architecture

### Core: AgentLoop (`agent/loop.py`)

The `AgentLoop` is the single orchestrator. It holds references to all plugins and runs the agent cycle:

```
messages → LLM → tool_calls → execute → append results → repeat
```

The only state it maintains is `messages: list[Message]`. All other concerns are delegated to plugins.

### Five Plugin Systems

Each plugin is a standalone subsystem with a clear interface:

| Plugin | File | Responsibility |
|--------|------|----------------|
| ToolRegistry | `agent/tools/registry.py` | Dynamic tool registration + sandbox execution |
| HookManager | `agent/hooks/manager.py` | Lifecycle extension points (before_iteration, before_tool_execute, etc.) |
| MemoryManager | `agent/memory/manager.py` | Session message history + AutoCompact token compression |
| SkillLoader | `agent/skills/loader.py` | Markdown skill file loading (YAML frontmatter + prompt body) |
| SubAgentManager | `agent/subagent/manager.py` | Background task delegation + ParentChannel for mid-turn injection |

### Web UI (`web/`)

FastAPI + WebSocket server with vanilla JS frontend. Two views:

- **Chat**: normal conversational interface with streaming text and tool call display
- **Debug**: configurable via `MYAGENT_DEBUG=enabled`, shows per-iteration message assembly:
  - Full message list sent to LLM (system prompt, user messages, tool results)
  - LLM raw response (content, stop_reason, tool_calls)
  - Tool execution details (name, arguments, result)
  - Memory compaction events
- `web/server.py` — FastAPI app, WebSocket endpoint, session management
- `web/session.py` — SessionManager: one AgentLoop + messages per session
- `web/debug_hook.py` — DebugHook: captures iteration state, emitted via Hook protocol
- `web/static/` — Vanilla HTML/CSS/JS frontend

### Adding New Capabilities

- **New tool**: Subclass `Tool` (ABC), use `@tool_parameters` decorator, register with `ToolRegistry`
- **New hook**: Implement the `Hook` Protocol, add to `HookManager([...])`
- **New skill**: Create a `.md` file in `skills/` with YAML frontmatter
- **New LLM provider**: Implement the `LLM` Protocol (see `agent/llm.py`)

### Key Design Patterns

- **Protocol + runtime_checkable**: Used for `LLM` and `Hook` — allows structural typing without inheritance
- **`@tool_parameters` decorator**: Attaches name/description/JSONSchema to `Tool` subclasses
- **AutoCompact**: Triggered after each tool-call round; preserves system + recent messages, compresses middle via LLM
- **ParentChannel**: `asyncio.Queue` between parent and subagent; `ParentChannelHook` injects subagent results mid-turn

### LLM Interface (`agent/llm.py` + `agent/openai_llm.py`)

The `LLM` Protocol defines `chat(messages, tools, model) -> LLMResponse`. `OpenAILLM` is the default implementation via httpx + OpenAI Chat Completions API. To add Anthropic/Gemini: implement `LLM` Protocol.

## Regression Testing Rule

**Every bug fix requires a new regression test.** When an error occurs:

1. Analyze the error and identify the root cause
2. Fix the bug
3. **Immediately write a regression test** that reproduces the bug
   - The test must be in `tests/agent/<subsystem>/test_<component>.py`
   - Name it `test_<specific behavior>`, e.g. `test_anthropic_llm_sync_json_response`
   - The test must fail before the fix and pass after — this is the proof the bug is fixed
4. Run `uv run pytest tests/ -v` to verify all tests pass before committing

This ensures every bug that was ever fixed stays fixed.

- Test files: `tests/agent/<subsystem>/test_<component>.py` (e.g., `test_registry.py`)
- Implementation: `agent/<subsystem>/<component>.py`
- Builtin subcomponents: `agent/<subsystem>/builtin/<name>.py`

## Design Documents

Architecture decisions are documented in `docs/superpowers/specs/`. These were created during brainstorming and should be updated if architecture changes.
