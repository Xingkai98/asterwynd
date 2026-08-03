"""Long-term memory data model shared by persistent storage, dedup, and summary.

The entry is backed by one Markdown file with YAML frontmatter; the dataclass
is the in-memory representation that keeps storage parsing, write dedup, decay
scoring and summary generation decoupled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MemoryEntry:
    """A single long-term memory entry.

    ``importance`` is a 1..5 score (higher = more important); ``scope`` is the
    project root path that owns this entry. ``conflict_with`` lists the names of
    entries that were judged to contradict this one by the write-time dedup pass.
    """

    name: str
    description: str
    body: str
    type: str = "project"
    importance: int = 3
    created_at: datetime | None = None
    last_accessed_at: datetime | None = None
    scope: str = ""
    archived: bool = False
    conflict_with: list[str] = field(default_factory=list)

    @property
    def searchable_text(self) -> str:
        """Text embedded for semantic recall and write dedup."""
        return f"{self.name}: {self.description}\n{self.body}"


@dataclass
class MemoryHit:
    """A search result: an entry plus its similarity score."""

    entry: MemoryEntry
    score: float
