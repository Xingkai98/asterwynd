"""Tests for agent/embedding/ — EmbeddingProvider protocol + NGramEmbedding + InMemoryVectorStore.

Covers design.md 第三轮：agent/embedding/ 公共模块（provider + vector_store），
默认零依赖纯 Python 实现，供 #75 记忆复用。
"""
from __future__ import annotations

import math
import pytest

from agent.embedding import NGramEmbedding, InMemoryVectorStore
from agent.embedding.provider import EmbeddingProvider
from agent.embedding.vector_store import VectorStore


# --- NGramEmbedding ---


class TestNGramEmbedding:
    def test_embed_returns_fixed_dim_vector(self) -> None:
        emb = NGramEmbedding(dim=256)
        vec = emb.embed("search python files")
        assert len(vec) == 256

    def test_embed_batch(self) -> None:
        emb = NGramEmbedding(dim=64)
        vecs = emb.embed_many(["a", "bb", "ccc"])
        assert len(vecs) == 3
        assert all(len(v) == 64 for v in vecs)

    def test_similar_texts_high_cosine(self) -> None:
        emb = NGramEmbedding(dim=512)
        a = emb.embed("search files in repository")
        b = emb.embed("search files in repository with glob")
        sim = emb.cosine(a, b)
        assert sim > 0.7

    def test_dissimilar_texts_lower_cosine(self) -> None:
        emb = NGramEmbedding(dim=512)
        a = emb.embed("search files in repository")
        b = emb.embed("send a web request to an API")
        sim = emb.cosine(a, b)
        assert sim < 0.5

    def test_identical_texts_cosine_one(self) -> None:
        emb = NGramEmbedding(dim=256)
        a = emb.embed("the same text")
        b = emb.embed("the same text")
        assert math.isclose(emb.cosine(a, b), 1.0, abs_tol=1e-6)

    def test_similarity_threshold_positive(self) -> None:
        """去重阈值（n-gram 校准为 0.7）：等价描述应超阈值触发去重"""
        emb = NGramEmbedding(dim=2048)
        a = emb.embed("search files for text matching a regex pattern")
        b = emb.embed("search files for text matching a regex pattern with options")
        # 实测：等价+附加词 cosine≈0.88，完全重复=1.0，完全不同=0.11
        assert emb.cosine(a, b) > 0.7

    def test_similarity_threshold_negative(self) -> None:
        """去重阈值（n-gram 校准为 0.7）：不同能力的描述不应误触发"""
        emb = NGramEmbedding(dim=2048)
        a = emb.embed("search files for text matching a regex pattern")
        b = emb.embed("fetch a web page over http and extract content")
        assert emb.cosine(a, b) < 0.7

    def test_implements_protocol(self) -> None:
        assert isinstance(NGramEmbedding(), EmbeddingProvider)


# --- InMemoryVectorStore ---


class TestInMemoryVectorStore:
    def test_add_and_query_returns_ranked(self) -> None:
        emb = NGramEmbedding(dim=512)
        store: VectorStore = InMemoryVectorStore(embedder=emb)
        store.add("grep", "search files with regex")
        store.add("web", "fetch a URL over http")
        store.add("edit", "modify file contents")

        results = store.query(emb.embed("find text in files"), top_k=2)
        assert len(results) == 2
        assert results[0][0] == "grep"  # most relevant first

    def test_top_k_respected(self) -> None:
        emb = NGramEmbedding(dim=256)
        store: VectorStore = InMemoryVectorStore(embedder=emb)
        for i in range(10):
            store.add(f"tool{i}", f"tool number {i} does things")
        results = store.query(emb.embed("tool number five"), top_k=3)
        assert len(results) == 3

    def test_query_empty_store_returns_empty(self) -> None:
        emb = NGramEmbedding(dim=64)
        store: VectorStore = InMemoryVectorStore(embedder=emb)
        assert store.query(emb.embed("anything"), top_k=5) == []

    def test_implements_protocol(self) -> None:
        emb = NGramEmbedding(dim=64)
        assert isinstance(InMemoryVectorStore(embedder=emb), VectorStore)
