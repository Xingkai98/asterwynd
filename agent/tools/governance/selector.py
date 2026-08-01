"""ToolSelector — two-stage dynamic tool selection for the LLM injection seam.

Pipeline: BM25 coarse filter (all tools → top ``coarse_k``) → embedding
re-rank → top ``top_k``. Stable-layer core tools are always injected and sort
first (design Q3), so the stable prefix stays byte-identical for #74's prefix
cache. Selection latency is recorded (design Q4) and a configurable budget
degrades to a full-schema fallback on exceed.

The query is constructed by the caller from the recent user message plus recent
tool calls (design Q9); this module is query-agnostic.
"""
from __future__ import annotations

import math
import time
from collections import Counter
from collections.abc import Sequence

from agent.embedding.provider import EmbeddingProvider


class ToolSelector:
    """Rank tools by relevance to a query using BM25 + embedding re-rank."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        top_k: int = 5,
        coarse_k: int = 50,
        latency_budget_ms: float = 50.0,
    ) -> None:
        self._embedder = embedder
        self._top_k = top_k
        self._coarse_k = coarse_k
        self._latency_budget_ms = latency_budget_ms
        self._names: list[str] = []
        self._descriptions: dict[str, str] = {}
        self._vectors: dict[str, object] = {}
        self._stable: set[str] = set()
        # BM25 statistics
        self._doc_tokens: dict[str, list[str]] = {}
        self._doc_freq: Counter[str] = Counter()
        self._avg_len: float = 0.0
        self.last_selection_latency_ms: float | None = None
        self.last_timed_out: bool = False

    def index_tool(self, tool_name: str, description: str) -> None:
        self._names.append(tool_name)
        self._descriptions[tool_name] = description
        self._vectors[tool_name] = self._embedder.embed(description)
        toks = self._tokenize(description)
        self._doc_tokens[tool_name] = toks
        for tok in set(toks):
            self._doc_freq[tok] += 1
        total = sum(len(t) for t in self._doc_tokens.values())
        self._avg_len = total / len(self._doc_tokens) if self._doc_tokens else 0.0

    def set_stable_tools(self, tool_names: Sequence[str]) -> None:
        """Stable-layer tools: always injected and sorted first (Q3)."""
        self._stable = set(tool_names)

    def select(self, query: str) -> list[str]:
        """Return the top-K tool names for ``query``.

        Stable tools are always included first; the remaining slots are filled
        by BM25 coarse filter → embedding re-rank. Selection latency is
        recorded on ``last_selection_latency_ms``.
        """
        start = time.perf_counter()
        try:
            return self._select_impl(query)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.last_selection_latency_ms = elapsed_ms
            self.last_timed_out = elapsed_ms > self._latency_budget_ms

    def _select_impl(self, query: str) -> list[str]:
        if not self._names:
            return []

        # Stable layer always included, deterministic order (registration order).
        stable_names = [n for n in self._names if n in self._stable]
        # Coarse BM25 filter over non-stable tools.
        query_toks = self._tokenize(query)
        scored = [
            (name, self._bm25(query_toks, self._doc_tokens[name]))
            for name in self._names
            if name not in self._stable
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        candidates = scored[: self._coarse_k]

        # Embedding re-rank over candidates.
        q_vec = self._embedder.embed(query)
        ranked = sorted(
            candidates,
            key=lambda pair: self._embedder.cosine(q_vec, self._vectors[pair[0]]),
            reverse=True,
        )
        # Variable layer: the top-K most relevant non-stable tools. Stable layer
        # is always injected and does NOT consume the top-K budget (design Q3:
        # stable prefix stays cacheable, variable tail is what changes).
        tail = [name for name, _ in ranked[: self._top_k]]
        return stable_names + tail

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().replace(",", " ").replace(".", " ").split()

    def _bm25(self, query_toks: list[str], doc_toks: list[str]) -> float:
        if not self._avg_len:
            return 0.0
        tf = Counter(doc_toks)
        n = len(self._doc_tokens)
        score = 0.0
        for tok in query_toks:
            df = self._doc_freq.get(tok, 0)
            if df == 0:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            f = tf.get(tok, 0)
            k = 1.5
            b = 0.75
            denom = f + k * (1 - b + b * len(doc_toks) / self._avg_len)
            score += idf * (f * (k + 1)) / denom if denom else 0.0
        return score
