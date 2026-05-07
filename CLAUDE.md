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
python cli.py --model gpt-4o-mini "用 Read 工具读 /tmp"

# Interactive mode
python cli.py --interactive
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

## File Naming Conventions

- Test files: `tests/agent/<subsystem>/test_<component>.py` (e.g., `test_registry.py`)
- Implementation: `agent/<subsystem>/<component>.py`
- Builtin subcomponents: `agent/<subsystem>/builtin/<name>.py`

## Design Documents

Architecture decisions are documented in `docs/superpowers/specs/`. These were created during brainstorming and should be updated if architecture changes.
