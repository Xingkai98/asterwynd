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
        # Static-source render cache.  A source marked ``static=True`` renders
        # from immutable inputs (cwd/mode/user_system_prompt); its output is
        # byte-identical across iterations, so we cache it keyed by
        # (source.name, cwd, mode, user_system_prompt).  Dynamic sources
        # (skills/plan/todo, memory index) are never cached.
        self._static_cache: dict[tuple, str] = {}

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

    @staticmethod
    def _static_cache_key(source: ContextSource, context: BuildContext) -> tuple | None:
        """Cache key for a static source, or ``None`` if the source is dynamic."""
        if not getattr(source, "static", False):
            return None
        return (source.name, context.cwd, context.mode, context.user_system_prompt)

    async def render_layers(
        self, context: BuildContext
    ) -> list[tuple[ContextSource, str]]:
        """Render all sources (static-cached) and apply the budget.

        Returns the surviving layers as ``(source, content)`` pairs in
        priority order.  ``cacheable`` sources (P0/P1/P2, the stable prefix)
        are frozen outside the budget pass — the token budget trims the
        variable P4/P5 layers first and may continue into non-cacheable
        lower-priority layers (e.g. Todo at P2) only after P4/P5 are fully
        removed, so the stable prefix stays byte-identical across iterations.
        """
        sorted_sources = sorted(self._sources, key=lambda s: s.priority)

        # Phase 1: render each source (skip failures); static sources reuse cache.
        rendered: list[tuple[ContextSource, str]] = []
        for source in sorted_sources:
            key = self._static_cache_key(source, context)
            if key is not None and key in self._static_cache:
                content = self._static_cache[key]
            else:
                try:
                    content = await source.render(context)
                except Exception:
                    logger.warning(
                        "ContextSource %r (priority=%d) failed to render — skipped",
                        source.name, source.priority, exc_info=True,
                    )
                    continue
                if key is not None:
                    self._static_cache[key] = content
            if content:
                rendered.append((source, content))

        if not rendered:
            return []

        # Phase 2: apply budget — truncate from lowest priority first
        return self._apply_budget(rendered)

    async def build(self, context: BuildContext) -> str:
        """Render all registered sources, apply truncation, return joined result."""
        layers = await self.render_layers(context)
        return self._join_layers(layers)

    async def build_blocks(self, context: BuildContext) -> list:
        """Render context as a list of ``TextBlock`` system blocks (P0-P5).

        Each surviving layer becomes one block; ``cacheable`` layers are
        flagged ``cache=True`` so the LLM layer can place a ``cache_control``
        breakpoint on the last stable block.
        """
        from agent.message import TextBlock

        layers = await self.render_layers(context)
        return [
            TextBlock(text=content, cache=bool(getattr(source, "cacheable", False)))
            for source, content in layers
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_budget(
        self, rendered: list[tuple[ContextSource, str]]
    ) -> list[tuple[ContextSource, str]]:
        """Truncate layers to fit within total_budget; return surviving layers.

        Strategy:
        1. Never truncate critical (P0) or cacheable (P0/P1/P2 stable prefix) sources.
        2. Truncate from the lowest-priority trimmable layer's tail first.
        3. If a layer is fully removed, move up to the next-lowest priority.
        """
        # Build list in priority order (already sorted by caller).
        # We work from the end (lowest priority) toward the front.
        layers: list[tuple[ContextSource, str]] = list(rendered)

        total_tokens = sum(_estimate_tokens(content) for _, content in layers)
        while total_tokens > self._total_budget and layers:
            # Find the lowest-priority trimmable layer (non-critical, non-cacheable)
            trim_idx = self._find_trimmable_index(layers)
            if trim_idx is None:
                # All remaining layers are protected — can't trim further
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

        return layers

    @staticmethod
    def _find_trimmable_index(layers: list[tuple[ContextSource, str]]
                              ) -> int | None:
        """Return the index of the lowest-priority trimmable layer.

        Critical sources (never truncated) and cacheable sources (the stable
        prefix, which must stay byte-identical across iterations) are skipped.
        """
        for i in range(len(layers) - 1, -1, -1):
            source = layers[i][0]
            if not source.critical and not getattr(source, "cacheable", False):
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
