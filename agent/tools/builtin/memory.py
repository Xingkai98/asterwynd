from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agent.memory.persistent import PersistentMemory
from agent.tool_permissions import AGENT_STATE_LOW_PERMISSION, AGENT_STATE_PERMISSION
from agent.tools.base import Tool, tool_parameters

if TYPE_CHECKING:
    from agent.memory.dedup import MemoryDedupJudge


@tool_parameters(
    name="SaveMemory",
    description=(
        "Save a persistent memory entry that persists across sessions. "
        "Four types: user (user role/preferences/knowledge), "
        "feedback (user corrections and confirmed approaches), "
        "project (non-code project information like deadlines, constraints), "
        "reference (pointers to external resources like bug trackers, dashboards). "
        "When a dedup judge is available, semantically similar existing memories "
        "are recalled and the write is classified as supplement/update/conflict/new."
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
            "importance": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Optional importance score 1-5 (default 3); drives decay",
            },
        },
        "required": ["type", "name", "description", "body"],
    },
)
class SaveMemoryTool(Tool):
    read_only = False
    permission = AGENT_STATE_PERMISSION

    def __init__(
        self,
        memory: PersistentMemory | None = None,
        judge: "MemoryDedupJudge | None" = None,
        recall_top_k: int = 5,
    ) -> None:
        self._memory = memory
        self._judge = judge
        self._recall_top_k = recall_top_k

    def _get_memory(self) -> PersistentMemory:
        if self._memory is None:
            return PersistentMemory(Path.cwd())
        return self._memory

    async def execute(
        self,
        type: str,
        name: str,
        description: str,
        body: str,
        importance: int | None = None,
        **kwargs,
    ) -> str:
        memory = self._get_memory()
        if self._judge is not None:
            incoming = f"{name}: {description}\n{body}"
            candidates = memory.recall_similar(incoming, top_k=self._recall_top_k)
            judgment = await self._judge.judge(incoming, candidates)
            return memory.apply_judgment(
                type=type,
                name=name,
                description=description,
                body=body,
                importance=importance,
                judgment=judgment,
            )
        return memory.save(
            type=type,
            name=name,
            description=description,
            body=body,
            importance=importance,
        )


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


@tool_parameters(
    name="SearchMemory",
    description=(
        "Semantically search persistent long-term memories by meaning, not just "
        "keywords. Returns top-k matching entries with similarity scores. "
        "Use when the global memory summary does not contain the detail you need."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Free-text semantic query describing the memory you need",
            },
            "top_k": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "Number of results to return (default 5)",
            },
            "type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "Optional filter by memory type",
            },
            "scope": {
                "type": "string",
                "description": "Optional project scope (git root path). A non-matching "
                "scope is rejected so cross-project memories never leak.",
            },
        },
        "required": ["query"],
    },
)
class SearchMemoryTool(Tool):
    read_only = True
    permission = AGENT_STATE_LOW_PERMISSION

    def __init__(self, memory: PersistentMemory | None = None) -> None:
        self._memory = memory

    def _get_memory(self) -> PersistentMemory:
        if self._memory is None:
            return PersistentMemory(Path.cwd())
        return self._memory

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        type: str | None = None,
        scope: str | None = None,
        **kwargs,
    ) -> str:
        memory = self._get_memory()
        hits = memory.search(query=query, top_k=top_k, type=type, scope=scope)
        if not hits:
            return "No memories found."
        parts: list[str] = []
        for hit in hits:
            entry = hit.entry
            parts.append(
                f"### {entry.name} ({entry.type}) [similarity={hit.score:.2f}]\n"
                f"{entry.body}"
            )
        return "\n\n---\n\n".join(parts)
