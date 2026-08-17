"""Tests for the evaluation-metrics (C2) cost-per-resolved and fault_owner stats.

Covers cost_per_resolved ($/resolved-task, Q6), the reason x fault_owner
cross-tab (Q7) and the Cohen's kappa annotator-agreement helper (Q7).
"""
from __future__ import annotations

import pytest

from benchmarks.models import TaskResult
from benchmarks.statistics import (
    cohen_kappa,
    cost_per_resolved,
    fault_owner_cross,
)


def _result(
    status: str,
    *,
    reason: str | None = None,
    model: str = "claude-sonnet-5",
    input_tokens: int = 1_000_000,
    output_tokens: int = 1_000_000,
    cache_read_tokens: int | None = None,
    fault_owner: str | None = None,
) -> TaskResult:
    return TaskResult(
        task_id="t1",
        agent="fake",
        model=model,
        status=status,
        reason=reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        fault_owner=fault_owner,
    )


# ---------------------------------------------------------------------------
# cost_per_resolved
# ---------------------------------------------------------------------------

def test_cost_per_resolved_counts_passed_and_warnings() -> None:
    # 2 resolved (passed + passed_with_warnings) + 1 failed; all token usage
    # counts into the numerator, including the failed run.
    results = [
        _result("passed", input_tokens=1_000_000, output_tokens=1_000_000),
        _result(
            "passed_with_warnings",
            reason="max_iterations",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        ),
        _result(
            "failed",
            reason="test_failure",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        ),
    ]
    per, total, resolved = cost_per_resolved(results)
    # claude-sonnet-5 $3/$15; 3M in + 3M out = 9 + 45 = $54 total, 2 resolved
    assert total == pytest.approx(54.0)
    assert resolved == 2
    assert per == pytest.approx(27.0)


def test_cost_per_resolved_cache_aware() -> None:
    results = [
        _result(
            "passed",
            input_tokens=20_000,
            output_tokens=2_000,
            cache_read_tokens=80_000,
        )
    ]
    per, total, resolved = cost_per_resolved(results)
    # claude-sonnet-5: fresh 20K*$3/1M + read 80K*$0.30/1M + out 2K*$15/1M
    assert total == pytest.approx(0.06 + 0.024 + 0.03)
    assert resolved == 1


def test_cost_per_resolved_zero_resolved_returns_none() -> None:
    results = [_result("failed", reason="test_failure")]
    per, total, resolved = cost_per_resolved(results)
    assert per is None
    assert resolved == 0
    assert total > 0


def test_cost_per_resolved_self_hosted_zero_cost() -> None:
    results = [
        _result(
            "passed",
            model="deepseek-v4-flash",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
    ]
    per, total, resolved = cost_per_resolved(results)
    assert total == pytest.approx(0.0)
    assert per == pytest.approx(0.0)
    assert resolved == 1


def test_cost_per_resolved_empty() -> None:
    per, total, resolved = cost_per_resolved([])
    assert per is None
    assert total == pytest.approx(0.0)
    assert resolved == 0


# ---------------------------------------------------------------------------
# fault_owner_cross
# ---------------------------------------------------------------------------

def test_fault_owner_cross_counts_failures_by_reason_and_owner() -> None:
    results = [
        _result("failed", reason="test_failure", fault_owner="agent"),
        _result("failed", reason="test_failure", fault_owner="task"),
        _result("failed", reason="tool_error", fault_owner="agent"),
        _result("error", reason="setup_error", fault_owner="environment"),
        # unsupported and passed are not failure attribution samples
        _result("unsupported", reason="docker_unavailable"),
        _result("passed"),
    ]
    cross = fault_owner_cross(results)
    assert cross["test_failure"]["agent"] == 1
    assert cross["test_failure"]["task"] == 1
    assert cross["tool_error"]["agent"] == 1
    assert cross["setup_error"]["environment"] == 1


def test_fault_owner_cross_unlabelled_falls_back_to_unknown() -> None:
    results = [
        _result("failed", reason="test_failure"),  # fault_owner is None
    ]
    cross = fault_owner_cross(results)
    assert cross["test_failure"]["unknown"] == 1


def test_fault_owner_cross_invalid_value_falls_back_to_unknown() -> None:
    results = [
        _result("failed", reason="test_failure", fault_owner="taskk"),
    ]
    cross = fault_owner_cross(results)
    assert cross["test_failure"]["unknown"] == 1


def test_fault_owner_cross_empty() -> None:
    assert fault_owner_cross([]) == {}


def test_fault_owner_cross_known_owners_constant() -> None:
    from benchmarks.statistics import FAULT_OWNERS

    assert set(FAULT_OWNERS) == {"agent", "task", "environment", "unknown"}


# ---------------------------------------------------------------------------
# cohen_kappa
# ---------------------------------------------------------------------------

def test_cohen_kappa_perfect_agreement() -> None:
    a = ["agent", "task", "environment", "agent"]
    b = ["agent", "task", "environment", "agent"]
    assert cohen_kappa(a, b) == pytest.approx(1.0)


def test_cohen_kappa_random_agreement_is_zero() -> None:
    # balanced labels, no agreement beyond chance
    a = ["agent", "agent", "task", "task"]
    b = ["task", "task", "agent", "agent"]
    # Po = 0, Pe = 0.5 -> kappa = -1.0... with 4 items Po=0 gives (0-0.5)/(1-0.5) = -1
    assert cohen_kappa(a, b) == pytest.approx(-1.0)


def test_cohen_kappa_partial_agreement() -> None:
    # 3 of 4 agree
    a = ["agent", "task", "environment", "agent"]
    b = ["agent", "task", "agent", "agent"]
    kappa = cohen_kappa(a, b)
    assert -1.0 <= kappa <= 1.0
    assert kappa > 0


def test_cohen_kappa_unequal_lengths_raises() -> None:
    with pytest.raises(ValueError):
        cohen_kappa(["agent"], ["agent", "task"])


def test_cohen_kappa_empty() -> None:
    assert cohen_kappa([], []) == pytest.approx(0.0)
