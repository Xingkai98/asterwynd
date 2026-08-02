"""Public embedding abstractions.

Provides the ``EmbeddingProvider`` protocol and the ``VectorStore`` protocol,
plus zero-dependency default implementations (``NGramEmbedding`` and
``InMemoryVectorStore``). This is a shared layer: tool-governance (#77) uses it
for semantic dedup and Top-K selection, and long-term-memory (#75) reuses it
for write dedup and recall. Backends are pluggable behind these two protocols.
"""
from __future__ import annotations

from agent.embedding.provider import EmbeddingProvider, NGramEmbedding, Vector
from agent.embedding.vector_store import InMemoryVectorStore, VectorStore

__all__ = [
    "EmbeddingProvider",
    "NGramEmbedding",
    "Vector",
    "VectorStore",
    "InMemoryVectorStore",
]
