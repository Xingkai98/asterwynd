# agent/context/builder.py
"""ContextBuilder: priority-based context assembly with token-budget management."""

import logging
from agent.context.protocol import BuildContext, ContextSource

logger = logging.getLogger("asterwynd.context")


# Rough char-to-token ratio for budget estimation.  Exact tokenization varies
# by model; we use the same fallback as MemoryManager (chars / 4).
_CHARS_PER_TOKEN_ESTIMATE = 4


def _estimate_tokens(text: str) -> int:
    """Rough token-count estimate.  Falls back to character-based heuristic."""
    if not text:
        return 0
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)


class ContextBuilder:
    """Assembles context from registered ContextSources.

    Flow:
    1. Sort sources by priority (0 = highest).
    2. Render each source.
    3. If total exceeds budget, truncate from lowest-priority layer tail-first.
    4. Insert ``---`` separators between layers.
    """

    def __init__(self, total_budget: int):
        self._total_budget = total_budget
        self._sources: list[ContextSource] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, source: ContextSource) -> None:
        """Register a context source.  Sources are sorted by priority on build.

        Sources registered at the same priority retain registration order.
        """
        self._sources.append(source)

    def set_budget(self, total_budget: int) -> None:
        """Update the injection-layer budget (e.g. when the context window changes)."""
        self._total_budget = total_budget

    async def build(self, context: BuildContext) -> str:
        """Render all registered sources, apply truncation, return joined result."""
        sorted_sources = sorted(self._sources, key=lambda s: s.priority)

        # Phase 1: render each source (skip failures)
        rendered: list[tuple[ContextSource, str]] = []
        for source in sorted_sources:
            try:
                content = await source.render(context)
            except Exception:
                logger.warning(
                    "ContextSource %r (priority=%d) failed to render — skipped",
                    source.name, source.priority, exc_info=True,
                )
                continue
            if content:
                rendered.append((source, content))

        if not rendered:
            return ""

        # Phase 2: apply budget — truncate from lowest priority first
        result = self._apply_budget(rendered)
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_budget(
        self, rendered: list[tuple[ContextSource, str]]
    ) -> str:
        """Truncate layers to fit within total_budget, then join with separators.

        Strategy:
        1. Never truncate critical (P0) sources.
        2. Truncate from the lowest-priority layer's tail first.
        3. If a layer is fully removed, move up to the next-lowest priority.
        4. Join remaining layers with ``---`` separators.
        """
        # Build list in priority order (already sorted by caller).
        # We work from the end (lowest priority) toward the front.
        layers: list[tuple[ContextSource, str]] = list(rendered)

        total_tokens = sum(_estimate_tokens(content) for _, content in layers)
        while total_tokens > self._total_budget and layers:
            # Find the lowest-priority non-critical layer to trim
            trim_idx = self._find_trimmable_index(layers)
            if trim_idx is None:
                # All remaining layers are critical — can't trim further
                break

            source, content = layers[trim_idx]
            excess = total_tokens - self._total_budget
            trimmed = self._truncate_tail(content, excess)
            if trimmed:
                layers[trim_idx] = (source, trimmed)
            else:
                # Layer was completely removed
                layers.pop(trim_idx)

            total_tokens = sum(_estimate_tokens(c) for _, c in layers)

        return self._join_layers(layers)

    @staticmethod
    def _find_trimmable_index(layers: list[tuple[ContextSource, str]]
                              ) -> int | None:
        """Return the index of the lowest-priority non-critical layer."""
        for i in range(len(layers) - 1, -1, -1):
            if not layers[i][0].critical:
                return i
        return None

    @staticmethod
    def _truncate_tail(text: str, excess_tokens: int) -> str:
        """Remove approximately *excess_tokens* worth of content from the tail.

        Returns empty string if the entire layer should be removed.
        """
        if excess_tokens <= 0:
            return text
        # Convert excess tokens to an estimated char count
        excess_chars = excess_tokens * _CHARS_PER_TOKEN_ESTIMATE
        if excess_chars >= len(text):
            return ""
        return text[:len(text) - excess_chars]

    @staticmethod
    def _join_layers(layers: list[tuple[ContextSource, str]]) -> str:
        """Join rendered layers with ``---`` separators."""
        if not layers:
            return ""
        parts: list[str] = []
        for _, content in layers:
            parts.append(content)
        return "\n\n---\n\n".join(parts)
