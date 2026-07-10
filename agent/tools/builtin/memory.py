from __future__ import annotations

from pathlib import Path

from agent.memory.persistent import PersistentMemory
from agent.tool_permissions import AGENT_STATE_LOW_PERMISSION, AGENT_STATE_PERMISSION
from agent.tools.base import Tool, tool_parameters


@tool_parameters(
    name="SaveMemory",
    description=(
        "Save a persistent memory entry that persists across sessions. "
        "Four types: user (user role/preferences/knowledge), "
        "feedback (user corrections and confirmed approaches), "
        "project (non-code project information like deadlines, constraints), "
        "reference (pointers to external resources like bug trackers, dashboards)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "Memory type",
            },
            "name": {
                "type": "string",
                "description": "kebab-case slug used as filename (e.g. user-role)",
            },
            "description": {
                "type": "string",
                "description": "One-line summary written to MEMORY.md index",
            },
            "body": {
                "type": "string",
                "description": "Memory body in Markdown (frontmatter is auto-generated)",
            },
        },
        "required": ["type", "name", "description", "body"],
    },
)
class SaveMemoryTool(Tool):
    read_only = False
    permission = AGENT_STATE_PERMISSION

    def __init__(self, memory: PersistentMemory | None = None) -> None:
        self._memory = memory

    def _get_memory(self) -> PersistentMemory:
        if self._memory is None:
            return PersistentMemory(Path.cwd())
        return self._memory

    async def execute(self, type: str, name: str, description: str, body: str, **kwargs) -> str:
        return self._get_memory().save(type=type, name=name, description=description, body=body)


@tool_parameters(
    name="RecallMemory",
    description=(
        "Read persistent memories stored across sessions. "
        "Optionally filter by type. Returns full content of matching memories."
    ),
    parameters={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "Optional filter. Omit to return all memories.",
            },
        },
        "required": [],
    },
)
class RecallMemoryTool(Tool):
    read_only = True
    permission = AGENT_STATE_LOW_PERMISSION

    def __init__(self, memory: PersistentMemory | None = None) -> None:
        self._memory = memory

    def _get_memory(self) -> PersistentMemory:
        if self._memory is None:
            return PersistentMemory(Path.cwd())
        return self._memory

    async def execute(self, type: str | None = None, **kwargs) -> str:
        return self._get_memory().recall(type=type if type else None)
