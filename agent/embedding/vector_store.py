"""Vector store abstraction and in-memory default.

``VectorStore`` is the retrieval seam for pluggable backends: an in-memory
list, a numpy matrix, FAISS/ChromaDB, or Postgres+pgvector all satisfy it.
Tool governance (#77) queries it for Top-K tool selection; long-term memory
(#75) reuses it for recall and write dedup.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from agent.embedding.provider import EmbeddingProvider, Vector


@runtime_checkable
class VectorStore(Protocol):
    """Store items by embedding and query for the most similar."""

    def add(self, item_id: str, text: str) -> None:
        """Index ``item_id`` by the embedding of ``text``."""
        ...

    def query(self, query_vector: Vector, top_k: int) -> list[tuple[str, float]]:
        """Return ``top_k`` ``(item_id, score)`` pairs ranked by similarity."""
        ...


class InMemoryVectorStore:
    """Simple in-memory vector store using cosine similarity.

    Zero external dependencies. Suitable for thousands of items; a vector
    database (FAISS/pgvector) can replace it behind the ``VectorStore``
    protocol for larger scales.
    """

    def __init__(self, embedder: EmbeddingProvider) -> None:
        self._embedder = embedder
        self._items: dict[str, str] = {}
        self._vectors: dict[str, Vector] = {}

    def add(self, item_id: str, text: str) -> None:
        self._items[item_id] = text
        self._vectors[item_id] = self._embedder.embed(text)

    def query(self, query_vector: Vector, top_k: int) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []
        for item_id, vec in self._vectors.items():
            score = self._embedder.cosine(query_vector, vec)
            scored.append((item_id, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def __len__(self) -> int:
        return len(self._items)
