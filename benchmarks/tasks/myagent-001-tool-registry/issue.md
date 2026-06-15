# Implement ToolRegistry

The project has a `Tool` ABC (abstract base class) defined in `agent/tools/base.py` with `name`, `description`, `parameters`, and an abstract `execute()` method. However, there is no central registry to manage tool instances.

## Task

Implement `ToolRegistry` in `agent/tools/registry.py` that:

1. Maintains a dictionary of `Tool` instances keyed by name
2. Provides a `register(tool: Tool)` method to add tools
3. Provides a `get(name: str) -> Tool` method to look up tools by name
4. Provides a `list() -> list[str]` method that returns all registered tool names

The registry is the central lookup point for tool execution. All tools must be registered before use.

## Requirements

- Create `agent/tools/registry.py`
- Follow the existing `Tool` ABC interface in `agent/tools/base.py`
- Tests will be provided that verify registration, lookup, and listing behavior
