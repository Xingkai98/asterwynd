from __future__ import annotations

from pathlib import Path

MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5": (3.75, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-haiku-3.5": (0.80, 4.00),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
}
# USD per 1M tokens (input, output)


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    # Sort by prefix length descending to avoid short-prefix collisions
    # (e.g. "gpt-4o" matching "gpt-4o-mini" before the longer prefix).
    for prefix in sorted(MODEL_PRICES, key=len, reverse=True):
        in_price, out_price = MODEL_PRICES[prefix]
        if model.startswith(prefix):
            return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
    return None


def format_cost(cost: float | None) -> str:
    if cost is None:
        return "unknown"
    if cost < 0.01:
        return f"${cost:.6f}"
    return f"${cost:.4f}"


class CostLedger:
    """Cost attribution ledger — records per-call cost across session/phase/tool.

    Each ``record`` computes the call cost via ``compute_cost`` and accumulates
    into a three-dimensional bill (by session, by phase, by tool). ``flush``
    appends records to a JSONL file for cross-session historical stats; ``load``
    restores a previously flushed ledger.

    The ledger is the *financial* record, decoupled from the trace (which is
    the *process* record). Persistence is explicit: callers choose when to
    flush (e.g. at run end).
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []
        self._total_cost: float = 0.0

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        session_id: str,
        phase: str,
        tool_name: str | None = None,
    ) -> None:
        cost = compute_cost(model, input_tokens, output_tokens)
        entry = {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "session_id": session_id,
            "phase": phase,
            "tool_name": tool_name,
        }
        self._entries.append(entry)
        if cost is not None:
            self._total_cost += cost

    def total(self) -> float:
        return self._total_cost

    def bill(self) -> dict:
        """Return per-dimension aggregation: by_session / by_phase / by_tool."""
        by_session: dict[str, dict] = {}
        by_phase: dict[str, dict] = {}
        by_tool: dict[str, dict] = {}
        for e in self._entries:
            for dim, key in (
                (by_session, e["session_id"]),
                (by_phase, e["phase"]),
                (by_tool, e["tool_name"] or "no_tool"),
            ):
                bucket = dim.setdefault(key, {"tokens": 0, "cost": 0.0})
                bucket["tokens"] += e["input_tokens"] + e["output_tokens"]
                if e["cost"] is not None:
                    bucket["cost"] += e["cost"]
        return {
            "by_session": by_session,
            "by_phase": by_phase,
            "by_tool": by_tool,
        }

    def flush(self, path: str | Path) -> None:
        """Append all recorded entries to ``path`` as JSONL."""
        import json as _json

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            for e in self._entries:
                f.write(_json.dumps(e, ensure_ascii=False) + "\n")

    def load(self, path: str | Path) -> None:
        """Restore entries previously flushed to ``path``."""
        import json as _json

        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = _json.loads(line)
            self._entries.append(e)
            if e.get("cost") is not None:
                self._total_cost += e["cost"]
