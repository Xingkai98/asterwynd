"""Tests for benchmarks/statistics.py.

Covers the design decision of a pure-Python, seed-reproducible bootstrap
confidence interval plus Pass@k and per-layer pass-rate helpers.
"""
from __future__ import annotations

import pytest

from benchmarks.statistics import (
    DEFAULT_LAYER,
    LAYERS,
    bootstrap_ci,
    layer_pass_rate,
    mean_std,
    pass_at_k,
    resolve_layer,
)


# ---------------------------------------------------------------------------
# mean_std
# ---------------------------------------------------------------------------

def test_mean_std_basic_sample_std() -> None:
    mean, std = mean_std([2.0, 4.0, 6.0])
    assert mean == pytest.approx(4.0)
    # Sample standard deviation (n-1): sqrt((4 + 0 + 4) / 2) == 2.0
    assert std == pytest.approx(2.0)


def test_mean_std_empty() -> None:
    assert mean_std([]) == (0.0, 0.0)


def test_mean_std_single_value() -> None:
    assert mean_std([5.0]) == (5.0, 0.0)


def test_mean_std_constant_values() -> None:
    assert mean_std([3.0, 3.0, 3.0]) == (3.0, 0.0)


# ---------------------------------------------------------------------------
# bootstrap_ci
# ---------------------------------------------------------------------------

def test_bootstrap_ci_reproducible_for_same_seed() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 8.0, 13.0]
    assert bootstrap_ci(values, seed=42) == bootstrap_ci(values, seed=42)


def test_bootstrap_ci_empty() -> None:
    assert bootstrap_ci([]) == (0.0, 0.0)


def test_bootstrap_ci_single_value() -> None:
    assert bootstrap_ci([7.0]) == (7.0, 7.0)


def test_bootstrap_ci_constant_values() -> None:
    assert bootstrap_ci([3.0, 3.0, 3.0]) == (3.0, 3.0)


def test_bootstrap_ci_brackets_sample_mean() -> None:
    values = list(range(1, 31))
    sample_mean = sum(values) / len(values)
    lo, hi = bootstrap_ci(values, seed=7)
    assert lo <= sample_mean <= hi


def test_bootstrap_ci_stays_within_data_range() -> None:
    values = [1.0, 2.0, 3.0, 100.0]
    lo, hi = bootstrap_ci(values, seed=3)
    # A resampled mean can never fall outside [min, max] of the data.
    assert lo >= min(values) - 1e-9
    assert hi <= max(values) + 1e-9


def test_bootstrap_ci_higher_confidence_is_wider() -> None:
    values = list(range(1, 31))
    # Same seed => identical resample stream; only the percentile indices
    # change, so the 95% interval must contain the 90% interval.
    lo95, hi95 = bootstrap_ci(values, seed=11, ci=0.95)
    lo90, hi90 = bootstrap_ci(values, seed=11, ci=0.90)
    assert lo95 <= lo90 <= hi90 <= hi95


# ---------------------------------------------------------------------------
# pass_at_k
# ---------------------------------------------------------------------------

def test_pass_at_k_combinatorial_default_k_equals_n() -> None:
    # pass@k with k=n: 1 - C(n-c, n)/C(n, n); any pass makes it 1.
    assert pass_at_k(3, 4) == pytest.approx(1.0)
    assert pass_at_k(0, 5) == 0.0
    assert pass_at_k(5, 5) == 1.0


def test_pass_at_k_with_explicit_smaller_k() -> None:
    # pass@1 over n=2 with c=1: 1 - C(1,1)/C(2,1) = 1 - 1/2 = 0.5.
    assert pass_at_k(1, 2, k=1) == pytest.approx(0.5)
    # pass@2 over n=3 with c=2: 1 - C(1,2)/C(3,2) = 1 - 0/3 = 1.0.
    assert pass_at_k(2, 3, k=2) == pytest.approx(1.0)


def test_pass_at_k_guards_division_by_zero() -> None:
    assert pass_at_k(3, 0) == 0.0
    assert pass_at_k(0, 0) == 0.0


# ---------------------------------------------------------------------------
# layer_pass_rate
# ---------------------------------------------------------------------------

def test_layer_pass_rate_mean() -> None:
    assert layer_pass_rate([True, True, False]) == pytest.approx(2.0 / 3.0)
    assert layer_pass_rate([True, True, True]) == 1.0
    assert layer_pass_rate([False, False]) == 0.0


def test_layer_pass_rate_empty() -> None:
    assert layer_pass_rate([]) == 0.0


# ---------------------------------------------------------------------------
# layer resolution (used by statistics consumers)
# ---------------------------------------------------------------------------

def test_resolve_layer_known_and_default() -> None:
    for layer in LAYERS:
        assert resolve_layer(layer) == layer
    assert resolve_layer("unknown-layer") == DEFAULT_LAYER
    assert resolve_layer(None) == DEFAULT_LAYER
    assert resolve_layer("") == DEFAULT_LAYER
