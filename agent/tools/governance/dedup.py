"""Semantic dedup of tool descriptions (soft prompt, not hard constraint).

At registration time, each tool's description is embedded and compared with
already-registered tools. Descriptions whose cosine similarity exceeds a
configurable threshold are marked ``duplicate_of`` the first (primary) tool.
The mark is stored as Tool metadata (a side table), not injected into the
official schema — the model decides which to use. Selection-time injection of a
difference explanation happens only for tools that are actually selected.

Threshold is calibrated to the embedding backend: n-gram hashing measures
semantic-equivalent descriptions around 0.86-0.88 and completely different
ones around 0.11, so the n-gram default is 0.7 (0.9 is for real embeddings
such as sentence-transformers).
"""
from __future__ import annotations

from agent.embedding.provider import EmbeddingProvider


class SemanticDeduper:
    """Tracks semantic duplicates among tool descriptions."""

    def __init__(self, embedder: EmbeddingProvider, threshold: float = 0.7) -> None:
        self._embedder = embedder
        self._threshold = threshold
        self._descriptions: dict[str, str] = {}
        self._vectors: dict[str, object] = {}
        self._duplicate_of: dict[str, str] = {}

    def add(self, tool_name: str, description: str) -> None:
        """Index a tool description and mark it as a duplicate if it is one."""
        self._descriptions[tool_name] = description
        vector = self._embedder.embed(description)
        self._vectors[tool_name] = vector
        for other in self._descriptions:
            if other == tool_name:
                continue
            sim = self._embedder.cosine(vector, self._vectors[other])
            if sim > self._threshold:
                # first registered is the primary
                self._duplicate_of[tool_name] = other
                break

    def duplicate_of(self, tool_name: str) -> str | None:
        """Return the primary tool this one duplicates, or None."""
        return self._duplicate_of.get(tool_name)

    def difference_explanation(self, tool_name: str) -> str | None:
        """Return a soft-prompt difference explanation for a marked tool.

        For example: ``SymbolSearch is similar to Grep; Grep matches text by
        pattern, SymbolSearch searches by symbol index``.
        """
        primary = self.duplicate_of(tool_name)
        if primary is None:
            return None
        return (
            f"{tool_name} is semantically similar to {primary}; consider which "
            f"is appropriate — {primary}: {self._descriptions.get(primary, '')}, "
            f"{tool_name}: {self._descriptions.get(tool_name, '')}"
        )
