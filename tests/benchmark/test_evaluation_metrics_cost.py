"""Tests for the evaluation-metrics (C2) cache-aware cost tracking.

Covers the four-tier MODEL_PRICES migration (Q4), compute_cost_cached /
cache_hit_rate (Q5) and the unknown-model / self-hosted fallbacks.
"""
from __future__ import annotations

import pytest

from agent.cost_tracker import (
    MODEL_PRICES,
    PRICING_TABLE_VERSION,
    CostEstimate,
    cache_hit_rate,
    compute_cost,
    compute_cost_cached,
)


# ---------------------------------------------------------------------------
# MODEL_PRICES four-tier structure
# ---------------------------------------------------------------------------

def test_model_prices_four_tier_shape() -> None:
    for prefix, prices in MODEL_PRICES.items():
        assert len(prices) == 4, f"{prefix} has {len(prices)} prices"
        in_price, cache_read, cache_write, out_price = prices
        assert in_price >= 0
        assert cache_read >= 0
        assert cache_write >= 0
        assert out_price >= 0
        # cache read is cheaper than fresh input; write is a premium
        assert cache_read <= in_price
        assert cache_write >= in_price


def test_model_prices_include_5_series() -> None:
    assert "claude-sonnet-5" in MODEL_PRICES
    assert "claude-opus-5" in MODEL_PRICES
    assert "claude-haiku-4-5" in MODEL_PRICES
    assert "deepseek-v4-flash" in MODEL_PRICES


def test_model_prices_self_hosted_zero_cost() -> None:
    # deepseek-v4-flash is a self-hosted near-zero-cost tier
    assert MODEL_PRICES["deepseek-v4-flash"] == (0.0, 0.0, 0.0, 0.0)


def test_pricing_table_version_present() -> None:
    assert PRICING_TABLE_VERSION
    assert "2026" in PRICING_TABLE_VERSION


# ---------------------------------------------------------------------------
# compute_cost backward compatibility
# ---------------------------------------------------------------------------

def test_compute_cost_keeps_two_arg_behavior() -> None:
    # claude-sonnet-5: $3 / $15 per 1M tokens -> 1M input + 2M output
    cost = compute_cost("claude-sonnet-5", 1_000_000, 2_000_000)
    assert cost == pytest.approx(3.0 + 30.0)


def test_compute_cost_unknown_model_returns_none() -> None:
    assert compute_cost("some-unknown-model", 1000, 1000) is None


def test_compute_cost_longest_prefix_wins() -> None:
    # claude-sonnet-4-6 must match its own entry, not claude-sonnet-4
    cost_46 = compute_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    cost_4 = compute_cost("claude-sonnet-4", 1_000_000, 1_000_000)
    assert cost_46 == pytest.approx(3.0 + 15.0)
    assert cost_4 == pytest.approx(3.0 + 15.0)


def test_compute_cost_prefix_not_swallowed_by_shorter() -> None:
    # "claude-sonnet-5" must NOT match "claude-sonnet-4"
    assert compute_cost("claude-sonnet-5", 1_000_000, 1_000_000) == pytest.approx(18.0)


# ---------------------------------------------------------------------------
# compute_cost_cached
# ---------------------------------------------------------------------------

def test_compute_cost_cached_four_tier_pricing() -> None:
    # claude-sonnet-5: fresh $3 / cache read $0.30 / cache write $3.75 / out $15
    estimate = compute_cost_cached(
        "claude-sonnet-5",
        input_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        cache_write_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert estimate.known
    assert estimate.cost == pytest.approx(3.0 + 0.30 + 3.75 + 15.0)


def test_compute_cost_cached_unknown_model_estimates_and_warns() -> None:
    estimate = compute_cost_cached(
        "brand-new-model-xyz",
        input_tokens=1_000_000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=1_000_000,
    )
    assert not estimate.known
    assert estimate.cost > 0  # must not silently return zero


def test_compute_cost_cached_self_hosted_zero_cost() -> None:
    estimate = compute_cost_cached(
        "deepseek-v4-flash",
        input_tokens=1_000_000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=1_000_000,
    )
    assert estimate.known
    assert estimate.cost == pytest.approx(0.0)


def test_compute_cost_cached_longest_prefix() -> None:
    estimate = compute_cost_cached(
        "claude-opus-5",
        input_tokens=1_000_000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=0,
    )
    assert estimate.known
    assert estimate.cost == pytest.approx(5.0)


def test_cost_estimate_repr() -> None:
    est = CostEstimate(cost=1.5, known=True)
    assert est.cost == 1.5
    assert est.known


# ---------------------------------------------------------------------------
# cache_hit_rate
# ---------------------------------------------------------------------------

def test_cache_hit_rate_basic() -> None:
    # 80K served from cache, 20K fresh -> 80%
    assert cache_hit_rate(cache_read_tokens=80_000, fresh_input_tokens=20_000) == pytest.approx(0.8)


def test_cache_hit_rate_zero_when_no_input() -> None:
    assert cache_hit_rate(cache_read_tokens=0, fresh_input_tokens=0) == pytest.approx(0.0)


def test_cache_hit_rate_all_fresh() -> None:
    assert cache_hit_rate(cache_read_tokens=0, fresh_input_tokens=100) == pytest.approx(0.0)


def test_cache_hit_rate_excludes_cache_write() -> None:
    # cache_write tokens are a one-time write cost, not a hit
    assert cache_hit_rate(
        cache_read_tokens=50, fresh_input_tokens=50
    ) == pytest.approx(0.5)
