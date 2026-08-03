"""Global memory summary generation (#75, Decision 4).

The summary is the ~50-token always-injected context for long-term memory; full
entries are retrieved on demand via the SearchMemory tool. Generation is
deterministic (importance-ranked name: description lines) so tests are stable
and no extra LLM call is spent per save.
"""
from __future__ import annotations

from datetime import datetime

from agent.memory.model import MemoryEntry


def build_summary(entries: list[MemoryEntry], max_tokens: int = 50) -> str | None:
    """Build a deterministic ~max_tokens global summary of *entries*.

    Returns None when there are no entries. The summary is importance-ranked
    (tie-broken by last access, most recent first) and truncated to the token
    budget with an ellipsis hint to use SearchMemory.
    """
    if not entries:
        return None
    ranked = sorted(
        entries,
        key=lambda e: (-e.importance, e.last_accessed_at or e.created_at or datetime.min),
    )
    lines = [f"- {e.name}: {e.description}" for e in ranked]
    summary = "\n".join(lines)
    if _estimate_tokens(summary) <= max_tokens:
        return summary

    kept: list[str] = []
    total = 0
    for line in lines:
        line_tokens = _estimate_tokens(line)
        if total + line_tokens > max_tokens:
            break
        kept.append(line)
        total += line_tokens
    if kept:
        return "\n".join(kept) + "\n- ... (use SearchMemory for details)"
    # Even the first line exceeds the budget — hard-truncate it.
    first = lines[0]
    return first[: max_tokens * 4]


def _estimate_tokens(text: str) -> int:
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)
