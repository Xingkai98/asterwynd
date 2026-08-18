"""Tests for the evaluation-metrics (C2) pass^k / validity statistics.

Covers the invalid-round exclusion predicate (Q1), the pass@1 effective-pass
rate (Q2) and the task-level pass^k aggregate with small-N handling (Q3).
"""
from __future__ import annotations

import pytest

from benchmarks.statistics import (
    PassKSummary,
    effective_pass_rate,
    is_valid_round,
    pass_k_success_rate,
    valid_round_count,
)


# ---------------------------------------------------------------------------
# is_valid_round
# ---------------------------------------------------------------------------

def test_is_valid_round_excludes_unsupported_status() -> None:
    assert not is_valid_round("unsupported", "docker_unavailable")
    assert not is_valid_round("unsupported", "task_family_unsupported")
    assert not is_valid_round("unsupported", None)


def test_is_valid_round_excludes_approval_unavailable() -> None:
    assert not is_valid_round("failed", "approval_unavailable")
    assert not is_valid_round("error", "approval_unavailable")


def test_is_valid_round_keeps_real_failures() -> None:
    assert is_valid_round("passed", None)
    assert is_valid_round("passed_with_warnings", "max_iterations")
    assert is_valid_round("failed", "test_failure")
    assert is_valid_round("failed", "docker_runtime_error")
    assert is_valid_round("error", "setup_error")


# ---------------------------------------------------------------------------
# effective_pass_rate (pass@1 with invalid rounds already removed upstream)
# ---------------------------------------------------------------------------

def test_effective_pass_rate_basic() -> None:
    assert effective_pass_rate([True, True, False]) == pytest.approx(2 / 3)
    assert effective_pass_rate([True, True, True]) == pytest.approx(1.0)
    assert effective_pass_rate([False, False]) == pytest.approx(0.0)


def test_effective_pass_rate_empty() -> None:
    assert effective_pass_rate([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# pass_k_success_rate
# ---------------------------------------------------------------------------

def test_pass_k_success_rate_all_valid_all_pass() -> None:
    # 3 tasks, 3 valid rounds each, all pass
    summary = pass_k_success_rate(
        [[True, True, True], [True, True, True], [True, True, True]]
    )
    assert summary.rate == pytest.approx(1.0)
    assert summary.passed_tasks == 3
    assert summary.valid_tasks == 3
    assert summary.excluded_tasks == 0


def test_pass_k_success_rate_mixed() -> None:
    # task1 passes all rounds, task2 fails one round, task3 fails all rounds
    summary = pass_k_success_rate(
        [[True, True, True], [True, True, False], [False, False, False]]
    )
    assert summary.rate == pytest.approx(1 / 3)
    assert summary.passed_tasks == 1
    assert summary.valid_tasks == 3
    assert summary.excluded_tasks == 0


def test_pass_k_success_rate_small_n_excluded() -> None:
    # one valid round is below the min_valid_rounds threshold -> excluded
    summary = pass_k_success_rate([[True]])
    assert summary.rate is None
    assert summary.passed_tasks == 0
    assert summary.valid_tasks == 0
    assert summary.excluded_tasks == 1


def test_pass_k_success_rate_two_valid_rounds_excluded() -> None:
    summary = pass_k_success_rate([[True, True]])
    assert summary.rate is None
    assert summary.excluded_tasks == 1


def test_pass_k_success_rate_min_valid_rounds_customizable() -> None:
    summary = pass_k_success_rate([[True, True, True, True]], min_valid_rounds=4)
    assert summary.rate == pytest.approx(1.0)
    assert summary.valid_tasks == 1

    short = pass_k_success_rate([[True, True, True]], min_valid_rounds=4)
    assert short.rate is None
    assert short.excluded_tasks == 1


def test_pass_k_success_rate_all_invalid_rounds_removed() -> None:
    # task1 has no valid rounds (all unsupported) -> excluded from both
    # numerator and denominator; task2 passes 3 valid rounds
    summary = pass_k_success_rate([[], [True, True, True]])
    assert summary.rate == pytest.approx(1.0)
    assert summary.passed_tasks == 1
    assert summary.valid_tasks == 1
    assert summary.excluded_tasks == 1


def test_pass_k_success_rate_empty_input() -> None:
    summary = pass_k_success_rate([])
    assert summary.rate is None
    assert summary.valid_tasks == 0
    assert summary.excluded_tasks == 0


def test_pass_k_success_rate_mixed_validity() -> None:
    # task1: 3 valid, all pass; task2: only 2 valid (1 invalid), excluded
    summary = pass_k_success_rate(
        [[True, True, True], [True, True]]
    )
    assert summary.rate == pytest.approx(1.0)
    assert summary.valid_tasks == 1
    assert summary.excluded_tasks == 1


def test_pass_k_summary_dataclass_shape() -> None:
    summary = PassKSummary(
        rate=0.5, passed_tasks=1, valid_tasks=2, excluded_tasks=1, min_valid_rounds=3
    )
    assert summary.rate == 0.5
    assert summary.passed_tasks == 1
    assert summary.valid_tasks == 2
    assert summary.excluded_tasks == 1
    assert summary.min_valid_rounds == 3


# ---------------------------------------------------------------------------
# valid_round_count (small-N declaration support, Q10)
# ---------------------------------------------------------------------------

def test_valid_round_count_excludes_invalid_rounds() -> None:
    from benchmarks.models import TaskResult

    results = [
        TaskResult(task_id="t1", agent="a", status="passed"),
        TaskResult(task_id="t1", agent="a", status="failed", reason="test_failure"),
        TaskResult(
            task_id="t1",
            agent="a",
            status="unsupported",
            reason="docker_unavailable",
        ),
        TaskResult(
            task_id="t1",
            agent="a",
            status="failed",
            reason="approval_unavailable",
        ),
    ]
    assert valid_round_count(results) == 2


def test_valid_round_count_empty() -> None:
    assert valid_round_count([]) == 0
