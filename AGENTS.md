# AGENTS.md

Guidance for coding agents working in this repository.

## Project

MyAgent is a lightweight Python agent framework with a Typer CLI and FastAPI/WebSocket UI.

Core areas:

- `agent/loop.py`: main agent loop and tool-call orchestration.
- `agent/llm.py`, `agent/openai_llm.py`, `agent/anthropic_llm.py`: LLM protocol and adapters.
- `agent/tools/`: tool base classes, registry, sandbox, and built-in tools.
- `agent/memory/`: message compaction.
- `agent/subagent/`: background subagent delegation and parent channel.
- `web/`: FastAPI app, session manager, debug hook, and static UI.
- `tests/`: pytest coverage for agent, tools, subagent, CLI, and web paths.

## Commands

Prefer `uv run` for reproducible dependency resolution:

```bash
uv sync --extra dev
uv run pytest -q
uv run python cli.py main "Hello"
MYAGENT_DEBUG=enabled uv run python cli.py web --host 127.0.0.1 --port 8000
```

Direct commands are also valid when the active Python environment already has dependencies installed:

```bash
pytest -q
python3 cli.py main "Hello"
MYAGENT_DEBUG=enabled python3 cli.py web --host 127.0.0.1 --port 8000
```

The CLI uses Typer subcommands. Single-prompt and interactive chat go through `main`; the web server goes through `web`.

## Testing

Run both default entry points before submitting broad changes:

```bash
pytest -q
python3 -m pytest -q
```

For web or debug UI changes, also run targeted web tests:

```bash
pytest -q tests/web_tests/test_session.py tests/web_tests/test_server.py
```

Browser/real API tests are optional and require explicit setup:

```bash
playwright install chromium
MYAGENT_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

## Development Rules

- Add or update regression tests for bug fixes.
- Keep tool-call protocol chains valid: an assistant message with `tool_calls` must keep its matching `tool` result messages.
- Do not make the `max_iterations` path fabricate a final assistant response from a tool result.
- Preserve debug UI behavior across multiple chat turns; AgentLoop iteration numbers restart per chat turn, so UI grouping must distinguish chat turns.
- Keep `.codegraph/`, `.understand-anything/`, local `.env*`, logs, and other generated/local files out of commits unless explicitly requested.

## Environment

Relevant environment variables:

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`
- `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`
- `MYAGENT_PROVIDER`: `openai` or `anthropic`
- `MYAGENT_MODEL`: default model override
- `MYAGENT_DEBUG=enabled`: enables the Debug tab and structured debug events
- `MYAGENT_LOG_LEVEL=DEBUG`: more verbose server/CLI logging
