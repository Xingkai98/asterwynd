from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger("asterwynd.cost_tracker")

# USD per 1M tokens as (fresh input, cache read, cache write, output).
# Cache read = 0.1x fresh input, cache write = 1.25x fresh input (5-minute TTL),
# matching Anthropic prompt-caching economics. deepseek-v4-flash is a
# self-hosted near-zero-cost tier (all zeros -> reported as $0.00, not billed).
PRICING_TABLE_VERSION = "2026-08-17"

MODEL_PRICES: dict[str, tuple[float, float, float, float]] = {
    "gpt-4o": (2.50, 0.25, 3.125, 10.00),
    "gpt-4o-mini": (0.15, 0.015, 0.1875, 0.60),
    "gpt-5": (3.75, 0.375, 4.6875, 15.00),
    "claude-sonnet-4": (3.00, 0.30, 3.75, 15.00),
    "claude-sonnet-4-6": (3.00, 0.30, 3.75, 15.00),
    "claude-sonnet-5": (3.00, 0.30, 3.75, 15.00),
    "claude-opus-4": (15.00, 1.50, 18.75, 75.00),
    "claude-opus-4-6": (5.00, 0.50, 6.25, 25.00),
    "claude-opus-4-7": (5.00, 0.50, 6.25, 25.00),
    "claude-opus-4-8": (5.00, 0.50, 6.25, 25.00),
    "claude-opus-5": (5.00, 0.50, 6.25, 25.00),
    "claude-fable-5": (10.00, 1.00, 12.50, 50.00),
    "claude-haiku-3.5": (0.80, 0.08, 1.00, 4.00),
    "claude-haiku-4-5": (1.00, 0.10, 1.25, 5.00),
    "deepseek-chat": (0.27, 0.027, 0.3375, 1.10),
    "deepseek-reasoner": (0.55, 0.055, 0.6875, 2.19),
    "deepseek-v4-flash": (0.0, 0.0, 0.0, 0.0),
}

# Fallback estimate for unknown models: average fresh-input / output price
# across the known table, so an unknown model is never silently priced at zero.
_AVG_INPUT_PRICE = sum(p[0] for p in MODEL_PRICES.values()) / len(MODEL_PRICES)
_AVG_OUTPUT_PRICE = sum(p[3] for p in MODEL_PRICES.values()) / len(MODEL_PRICES)


@dataclass
class CostEstimate:
    """A computed cost with a flag for whether the model was in the table."""

    cost: float
    known: bool


def _lookup_prices(model: str) -> tuple[float, float, float, float] | None:
    # Sort by prefix length descending to avoid short-prefix collisions
    # (e.g. "gpt-4o" matching "gpt-4o-mini" before the longer prefix).
    for prefix in sorted(MODEL_PRICES, key=len, reverse=True):
        if model.startswith(prefix):
            return MODEL_PRICES[prefix]
    return None


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = _lookup_prices(model)
    if prices is None:
        return None
    in_price, _cache_read, _cache_write, out_price = prices
    return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price


def compute_cost_cached(
    model: str,
    input_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
) -> CostEstimate:
    """Cache-aware four-tier cost for ``model``.

    Returns a :class:`CostEstimate`; ``known`` is False when the model is not in
    the price table, in which case the cost is estimated from the table average
    (never silently zero). Self-hosted models priced at zero still count as
    known (reported as $0.00 with a self-hosted note upstream).
    """
    prices = _lookup_prices(model)
    if prices is None:
        _logger.warning(
            "Unknown model %r not in pricing table — estimating cost from table average",
            model,
        )
        cost = (
            (input_tokens / 1_000_000) * _AVG_INPUT_PRICE
            + (cache_read_tokens / 1_000_000) * _AVG_INPUT_PRICE * 0.1
            + (cache_write_tokens / 1_000_000) * _AVG_INPUT_PRICE * 1.25
            + (output_tokens / 1_000_000) * _AVG_OUTPUT_PRICE
        )
        return CostEstimate(cost=cost, known=False)
    in_price, cache_read_price, cache_write_price, out_price = prices
    cost = (
        (input_tokens / 1_000_000) * in_price
        + (cache_read_tokens / 1_000_000) * cache_read_price
        + (cache_write_tokens / 1_000_000) * cache_write_price
        + (output_tokens / 1_000_000) * out_price
    )
    return CostEstimate(cost=cost, known=True)


def cache_hit_rate(cache_read_tokens: int, fresh_input_tokens: int) -> float:
    """Share of prompt tokens served from cache.

    Cache-write tokens are a one-time write cost, not a hit, so they are
    excluded from the ratio. Returns 0.0 when there is no input to hit on.
    """
    denominator = cache_read_tokens + fresh_input_tokens
    if denominator <= 0:
        return 0.0
    return cache_read_tokens / denominator


def format_cost(cost: float | None) -> str:
    if cost is None:
        return "unknown"
    if cost < 0.01:
        return f"${cost:.6f}"
    return f"${cost:.4f}"


#: 四维分桶值的 round 位数（Q16：与 envelope ``total_cost`` 的 9 位对齐）。
BUCKET_ROUND = 9

#: 图距分桶的上界桶名（与 ``budget_for_distance`` 的 3+=root 同口径）。
_DEPTH_OVERFLOW_KEY = "3+"


def _depth_key(depth: Any) -> str:
    """图距 -> ``by_depth`` 桶名（0/1/2/3+）。非整数一律折进 leaf 桶。"""
    if isinstance(depth, bool) or not isinstance(depth, int):
        return "0"
    if depth <= 0:
        return "0"
    if depth >= 3:
        return _DEPTH_OVERFLOW_KEY
    return str(depth)


class CostLedger:
    """Cost attribution ledger — records per-call cost across session/phase/tool.

    Each ``record`` computes the call cost via ``compute_cost`` and accumulates
    into a three-dimensional bill (by session, by phase, by tool). ``flush``
    appends records to a JSONL file for cross-session historical stats; ``load``
    restores a previously flushed ledger.

    The ledger is the *financial* record, decoupled from the trace (which is
    the *process* record). Persistence is explicit: callers choose when to
    flush (e.g. at run end).

    ``record`` 另接受四个**可选**归因键（``workflow_id`` / ``node_id`` /
    ``depth`` / ``edge``）与 cache 两档；带键的记录进 ``bill()`` 的四维分桶，
    不带的记录对三维账单**逐字节无影响**（change ``workflow-budget-attribution``，
    D3/Q12/Q16）。
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []
        self._total_cost: float = 0.0
        self._flushed_count: int = 0

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        session_id: str,
        phase: str,
        tool_name: str | None = None,
        workflow_id: str | None = None,
        node_id: str | None = None,
        depth: int | None = None,
        edge: str | None = None,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        cost = compute_cost(model, input_tokens, output_tokens)
        # 四维归因的 cost 走 cache-aware 四档定价（Q12：否则 by_node/by_edge 与
        # workflow 账本对不上）。legacy 三维账单仍用上面的二档 ``cost``——既有断言
        # 与已 flush 的历史记录都锁定「未知模型记 0 成本」的语义，不能一起改。
        estimate = compute_cost_cached(
            model, input_tokens, cache_read_tokens, cache_write_tokens, output_tokens
        )
        entry = {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "cost_cached": estimate.cost,
            "cost_known": estimate.known,
            "cache_read_tokens": cache_read_tokens,
            "cache_write_tokens": cache_write_tokens,
            "session_id": session_id,
            "phase": phase,
            "tool_name": tool_name,
            "workflow_id": workflow_id,
            "node_id": node_id,
            "depth": depth,
            "edge": edge,
        }
        self._entries.append(entry)
        if cost is not None:
            self._total_cost += cost

    def total(self) -> float:
        return self._total_cost

    def bill(self, *, workflow_id: str | None = None) -> dict:
        """Return per-dimension aggregation.

        legacy 三维：``by_session`` / ``by_phase`` / ``by_tool``（与改造前逐字节一致，
        且始终是跨 workflow 的全局财务记录——Q12 的权威口径在 workflow 账本，ledger
        只是历史）。

        四维归因：``by_workflow`` / ``by_node`` / ``by_depth`` / ``by_edge``——只收
        带对应归因键的记录；桶值为 ``{tokens, cost, estimated}``，tokens 口径是
        input+output（不含 cache），cost 单位 USD 且 round 到 :data:`BUCKET_ROUND` 位。

        ``workflow_id`` 给定时，**四维归因**只统计该 workflow 的记录（``None`` = 不过
        滤）。这是必需的：ledger 被同一个 manager 跨 workflow 共享，而 by_node/by_edge
        的桶键（node id / edge 串）在不同 workflow 间会重名——不过滤就会把别的
        workflow 的成本串进本 workflow 的 attribution 快照（D7/Q15）。
        """
        by_session: dict[str, dict] = {}
        by_phase: dict[str, dict] = {}
        by_tool: dict[str, dict] = {}
        by_workflow: dict[str, dict] = {}
        by_node: dict[str, dict] = {}
        by_depth: dict[str, dict] = {}
        by_edge: dict[str, dict] = {}
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
            # 四维归因：键缺失（None）的记录不进桶——不带归因键 = 不进任何归因维度。
            # 指定 workflow_id 时先按它过滤，避免跨 workflow 的桶键重名串账。
            if workflow_id is not None and e.get("workflow_id") != workflow_id:
                continue
            attribution_keys = (
                (by_workflow, e.get("workflow_id")),
                (by_node, e.get("node_id")),
                (by_depth, _depth_key(e["depth"]) if e.get("depth") is not None else None),
                (by_edge, e.get("edge")),
            )
            for dim, key in attribution_keys:
                if key is None:
                    continue
                bucket = dim.setdefault(
                    key, {"tokens": 0, "cost": 0.0, "estimated": False}
                )
                bucket["tokens"] += e["input_tokens"] + e["output_tokens"]
                bucket["cost"] += e.get("cost_cached") or 0.0
                if not e.get("cost_known", True):
                    bucket["estimated"] = True
        for dim in (by_workflow, by_node, by_depth, by_edge):
            for bucket in dim.values():
                bucket["cost"] = round(bucket["cost"], BUCKET_ROUND)
        return {
            "by_session": by_session,
            "by_phase": by_phase,
            "by_tool": by_tool,
            "by_workflow": by_workflow,
            "by_node": by_node,
            "by_depth": by_depth,
            "by_edge": by_edge,
        }

    def flush(self, path: str | Path) -> None:
        """Append entries recorded since the last flush to ``path`` as JSONL.

        A ledger instance may be shared across loops (parent + subagent), each
        flushing the same JSONL at run end. Keeping a ``_flushed_count`` cursor
        ensures the same entry is never appended twice.
        """
        import json as _json

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        pending = self._entries[self._flushed_count:]
        if not pending:
            return
        with p.open("a", encoding="utf-8") as f:
            for e in pending:
                f.write(_json.dumps(e, ensure_ascii=False) + "\n")
        self._flushed_count = len(self._entries)

    def load(self, path: str | Path) -> None:
        """Restore entries previously flushed to ``path``.

        Loaded entries are already persisted, so ``_flushed_count`` advances
        past them — a later flush only writes entries recorded after the load.
        """
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
        self._flushed_count = len(self._entries)
