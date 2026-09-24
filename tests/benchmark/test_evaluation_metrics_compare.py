"""Tests for the evaluation-metrics (C2) paired-comparison statistics.

Covers paired_comparison (per-task pass@1 delta + paired-bootstrap CI +
win-rate, Q8) and the exact-binomial McNemar test on pass^k booleans.
"""
from __future__ import annotations

import pytest

from benchmarks.models import TaskResult
from benchmarks.statistics import mcnemar_exact, paired_comparison


def _r(
    task_id: str,
    status: str,
    *,
    reason: str | None = None,
    run_round: int = 0,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        agent="fake",
        model="fake",
        status=status,
        reason=reason,
        run_round=run_round,
    )


# ---------------------------------------------------------------------------
# paired_comparison
# ---------------------------------------------------------------------------

def test_paired_comparison_per_task_delta_and_win_rate() -> None:
    run_a = [
        _r("t1", "passed", run_round=0),
        _r("t2", "failed", reason="test_failure", run_round=0),
        _r("t1", "passed", run_round=1),
        _r("t2", "failed", reason="test_failure", run_round=1),
        _r("t1", "passed", run_round=2),
        _r("t2", "failed", reason="test_failure", run_round=2),
    ]
    run_b = [
        _r("t1", "passed", run_round=0),
        _r("t2", "passed", run_round=0),
        _r("t1", "passed", run_round=1),
        _r("t2", "passed", run_round=1),
        _r("t1", "passed", run_round=2),
        _r("t2", "passed", run_round=2),
    ]
    comp = paired_comparison(run_a, run_b)
    # t1: 1.0 - 1.0 = 0.0 ; t2: 0.0 - 1.0 = -1.0
    assert comp.per_task_deltas["t1"] == pytest.approx(0.0)
    assert comp.per_task_deltas["t2"] == pytest.approx(-1.0)
    assert comp.win_rate["a_wins"] == 0
    assert comp.win_rate["b_wins"] == 1
    assert comp.win_rate["ties"] == 1
    assert comp.delta_ci is not None
    # mean delta = -0.5 must fall inside the CI
    lo, hi = comp.delta_ci
    assert lo <= -0.5 <= hi


def test_paired_comparison_reproducible_seed() -> None:
    run_a = [
        _r(f"t{i}", "passed" if i % 2 else "failed", reason="test_failure", run_round=0)
        for i in range(10)
    ]
    run_b = [
        _r(f"t{i}", "passed", run_round=0)
        for i in range(10)
    ]
    comp1 = paired_comparison(run_a, run_b, seed=42)
    comp2 = paired_comparison(run_a, run_b, seed=42)
    assert comp1.delta_ci == comp2.delta_ci
    assert comp1.per_task_deltas == comp2.per_task_deltas


def test_paired_comparison_excludes_invalid_rounds() -> None:
    run_a = [
        _r("t1", "passed", run_round=0),
        _r("t1", "passed", run_round=1),
        _r("t1", "unsupported", reason="docker_unavailable", run_round=2),
    ]
    run_b = [
        _r("t1", "failed", reason="test_failure", run_round=0),
        _r("t1", "failed", reason="test_failure", run_round=1),
    ]
    comp = paired_comparison(run_a, run_b)
    # t1: 2/2 - 0/2 = 1.0
    assert comp.per_task_deltas["t1"] == pytest.approx(1.0)


def test_paired_comparison_only_common_tasks() -> None:
    run_a = [_r("t1", "passed", run_round=0), _r("t2", "failed", reason="x", run_round=0)]
    run_b = [_r("t1", "failed", reason="x", run_round=0)]
    comp = paired_comparison(run_a, run_b)
    assert set(comp.per_task_deltas) == {"t1"}


def test_paired_comparison_empty_common() -> None:
    run_a = [_r("t1", "passed", run_round=0)]
    run_b = [_r("t2", "passed", run_round=0)]
    comp = paired_comparison(run_a, run_b)
    assert comp.per_task_deltas == {}
    assert comp.delta_ci is None
    assert comp.win_rate == {"a_wins": 0, "b_wins": 0, "ties": 0}


# ---------------------------------------------------------------------------
# mcnemar_exact
# ---------------------------------------------------------------------------

def test_mcnemar_no_discordant_pairs() -> None:
    result = mcnemar_exact(b=0, c=0)
    assert result["p_value"] == pytest.approx(1.0)
    assert not result["significant"]


def test_mcnemar_one_discordant_pair_not_significant() -> None:
    result = mcnemar_exact(b=1, c=0)
    assert result["p_value"] == pytest.approx(1.0)
    assert not result["significant"]


def test_mcnemar_strong_imbalance_significant() -> None:
    result = mcnemar_exact(b=8, c=0)
    assert result["p_value"] < 0.05
    assert result["significant"]


def test_mcnemar_two_sided() -> None:
    # b=7, c=1: two-sided p = 2 * P(X >= 7 | n=8, p=0.5)
    result = mcnemar_exact(b=7, c=1)
    assert 0 < result["p_value"] < 1
    assert result["n_discordant"] == 8


def test_mcnemar_symmetric() -> None:
    assert mcnemar_exact(b=8, c=0)["p_value"] == mcnemar_exact(b=0, c=8)["p_value"]


# ---------------------------------------------------------------------------
# paired_comparison integrates McNemar on pass^k booleans
# ---------------------------------------------------------------------------

def test_paired_comparison_mcnemar_section() -> None:
    run_a = [
        _r("t1", "passed", run_round=i) for i in range(3)
    ] + [_r("t2", "failed", reason="x", run_round=i) for i in range(3)]
    run_b = [
        _r("t1", "passed", run_round=i) for i in range(3)
    ] + [_r("t2", "passed", run_round=i) for i in range(3)]
    comp = paired_comparison(run_a, run_b)
    assert comp.mcnemar is not None
    # t1: both pass^k; t2: A no, B yes -> b=0, c=1
    assert comp.mcnemar["b"] == 0
    assert comp.mcnemar["c"] == 1


# ---------------------------------------------------------------------------
# compare.py build_paired_report
# ---------------------------------------------------------------------------

def test_build_paired_report_markdown() -> None:
    from benchmarks.compare import build_paired_report

    runs = [
        (
            "agent-a",
            {
                "t1": {
                    "task_id": "t1",
                    "status": "passed",
                    "agent": "a",
                    "run_round": 0,
                },
                "t2": {
                    "task_id": "t2",
                    "status": "failed",
                    "reason": "test_failure",
                    "agent": "a",
                    "run_round": 0,
                },
            },
        ),
        (
            "agent-b",
            {
                "t1": {
                    "task_id": "t1",
                    "status": "passed",
                    "agent": "b",
                    "run_round": 0,
                },
                "t2": {
                    "task_id": "t2",
                    "status": "passed",
                    "agent": "b",
                    "run_round": 0,
                },
            },
        ),
    ]
    md = build_paired_report(runs)
    assert "## Paired Comparison" in md
    assert "Mean per-task delta" in md
    assert "Difference 95% CI" in md
    assert "Win-rate" in md
    assert "| t1 | 0.000 |" in md
    assert "| t2 | -1.000 |" in md


def test_build_paired_report_requires_two_runs() -> None:
    from benchmarks.compare import build_paired_report

    assert build_paired_report([("a", {})]) == ""
    assert build_paired_report([("a", {}), ("b", {}), ("c", {})]) == ""


def test_paired_comparison_ci_is_zero_when_runs_identical() -> None:
    """Paired bootstrap must preserve pairing: identical per-task pass rates
    yield a delta CI of exactly [0.0, 0.0] (regression for H1)."""
    results_a = []
    results_b = []
    for i in range(20):
        # both runs pass exactly the same tasks
        status = "passed" if i % 2 == 0 else "failed"
        reason = None if status == "passed" else "test_failure"
        results_a.append(_r(f"t{i}", status, reason=reason, run_round=0))
        results_b.append(_r(f"t{i}", status, reason=reason, run_round=0))
    comp = paired_comparison(results_a, results_b, seed=7)
    lo, hi = comp.delta_ci
    assert lo == pytest.approx(0.0)
    assert hi == pytest.approx(0.0)
    assert all(abs(d) == pytest.approx(0.0) for d in comp.per_task_deltas.values())
