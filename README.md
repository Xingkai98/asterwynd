# MyAgent

A lightweight general-purpose AI agent framework in Python.

## Features

- **Plugin Architecture**: ToolRegistry, HookManager, MemoryManager, SkillLoader, SubAgentManager
- **Sandbox Execution**: subprocess-based sandbox with resource limits
- **Hook Lifecycle**: before_iteration, before_tool_execute, after_tool_execute, etc.
- **AutoCompact**: Token budget-based context compression
- **SubAgent Delegation**: Background task spawning with mid-turn injection
- **Markdown Skills**: Dynamic skill loading from .md files

## Quick Start

```bash
pip install -e ".[dev]"
python cli.py --model gpt-4 "Hello, what can you do?"
```

## Architecture

See `docs/superpowers/specs/` for design documents.

## License

MIT
