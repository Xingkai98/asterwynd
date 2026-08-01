"""Embedding provider abstraction and zero-dependency default.

The protocol is the seam for pluggable backends: a local sentence-transformers
model, a remote OpenAI/Anthropic/Cohere embedding API, or a hash-based
n-gram implementation all satisfy ``EmbeddingProvider``. Tool governance (#77)
and long-term memory (#75) depend on this protocol, not on any concrete backend.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

# A vector is a fixed-length sequence of floats.
Vector = Sequence[float]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Embed text into a fixed-length numeric vector."""

    def embed(self, text: str) -> Vector:
        """Embed a single text into a vector."""
        ...

    def embed_many(self, texts: Sequence[str]) -> list[Vector]:
        """Embed multiple texts into vectors."""
        ...

    def cosine(self, a: Vector, b: Vector) -> float:
        """Cosine similarity between two vectors in [-1, 1]."""
        ...


class NGramEmbedding:
    """Zero-dependency embedding via character n-gram hashing.

    Maps character n-grams of the input text into a fixed-dimension
    bag-of-hashed-grams vector. Deterministic and dependency-free, it is the
    default backend; a higher-quality backend can replace it behind the
    ``EmbeddingProvider`` protocol.
    """

    def __init__(self, dim: int = 256, n: int = 3) -> None:
        self._dim = dim
        self._n = n

    def embed(self, text: str) -> Vector:
        vec = [0.0] * self._dim
        normalized = text.lower()
        padded = f" {normalized} "
        for i in range(max(0, len(padded) - self._n + 1)):
            gram = padded[i : i + self._n]
            h = int(hashlib.md5(gram.encode("utf-8"), usedforsecurity=False).hexdigest(), 16)
            vec[h % self._dim] += 1.0
        return vec

    def embed_many(self, texts: Sequence[str]) -> list[Vector]:
        return [self.embed(text) for text in texts]

    @staticmethod
    def cosine(a: Vector, b: Vector) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
