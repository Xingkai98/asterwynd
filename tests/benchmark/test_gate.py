"""Tests for benchmarks/gate.py — benchmark regression gate.

Covers baseline load/save, run-metric computation (success rate, p95 over
passed tasks only), threshold comparison semantics (strict ``>``, p95 absolute
floor), and CLI-adjacent edge cases (missing baseline, zero tasks, update
baseline refusing empty runs).
"""
from __future__ import annotations

import json

import pytest

from benchmarks.gate import (
    ABS_P95_FLOOR_S,
    DEFAULT_BASELINE_PATH,
    GateVerdict,
    compute_run_metrics,
    compare,
    load_baseline,
    write_baseline,
)
from benchmarks.models import TaskResult


def _result(
    task_id: str,
    status: str,
    *,
    duration: float = 1.0,
    category: str | None = None,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        agent="fake",
        model="",
        status=status,
        duration_seconds=duration,
        category=category,
    )


def _run_dir(tmp_path, results: list[TaskResult]) -> "object":
    """Write result.json files under a fake run directory and return its path."""
    tasks_dir = tmp_path / "tasks"
    for r in results:
        task_dir = tasks_dir / r.task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        r.write_json(task_dir / "result.json")
    return tmp_path


# ---------------------------------------------------------------------------
# compute_run_metrics
# ---------------------------------------------------------------------------

def test_metrics_success_rate_uses_pass_statuses() -> None:
    results = [
        _result("t1", "passed"),
        _result("t2", "passed_with_warnings"),
        _result("t3", "failed"),
        _result("t4", "error"),
    ]
    metrics = compute_run_metrics(results)
    assert metrics["success_rate"] == 0.5  # 2 / 4
    assert metrics["total_tasks"] == 4
    assert metrics["passed_tasks"] == 2


def test_metrics_p95_excludes_non_pass_tasks() -> None:
    # Failed tasks carry duration=0.0 (runner crash / missing field). Including
    # them would drag the p95 down and hide latency regressions.
    results = [
        _result("fast-pass", "passed", duration=1.0),
        _result("slow-pass", "passed", duration=5.0),
        _result("crash", "error", duration=0.0),
    ]
    metrics = compute_run_metrics(results)
    # p95 over [1.0, 5.0] (passed only): nearest-rank idx = int(2*0.95)=1 -> 5.0
    assert metrics["p95_latency_s"] == 5.0


def test_metrics_all_failed_has_zero_p95() -> None:
    results = [_result("t1", "failed", duration=3.0)]
    metrics = compute_run_metrics(results)
    assert metrics["success_rate"] == 0.0
    assert metrics["passed_tasks"] == 0
    assert metrics["p95_latency_s"] == 0.0


def test_metrics_empty_run() -> None:
    metrics = compute_run_metrics([])
    assert metrics["success_rate"] == 0.0
    assert metrics["total_tasks"] == 0
    assert metrics["p95_latency_s"] == 0.0


# ---------------------------------------------------------------------------
# compare — threshold semantics
# ---------------------------------------------------------------------------

def _baseline(**overrides) -> dict:
    base = {
        "schema_version": 1,
        "agent": "fake",
        "model": "",
        "task_set": "gate-smoke",
        "created_at": "2026-08-03T00:00:00Z",
        "git_sha": None,
        "metrics": {"success_rate": 1.0, "p95_latency_s": 1.0},
        "per_task": {},
    }
    base.update(overrides)
    return base


def test_compare_pass_when_within_thresholds() -> None:
    baseline = _baseline()
    current = {"success_rate": 0.95, "p95_latency_s": 1.04}
    verdict = compare(baseline, current)
    assert verdict.ok is True
    assert verdict.success_rate_delta == pytest.approx(-0.05)
    assert verdict.p95_delta == pytest.approx(0.04)


def test_compare_success_rate_drop_exactly_5pp_not_blocked() -> None:
    # spec: "more than 5 percentage points" -> strict >, exactly 5pp is pass.
    baseline = _baseline()
    current = {"success_rate": 0.95, "p95_latency_s": 1.0}
    verdict = compare(baseline, current)
    assert verdict.ok is True
    assert verdict.blocked_reasons == []


def test_compare_success_rate_drop_just_over_5pp_blocked() -> None:
    baseline = _baseline()
    current = {"success_rate": 0.9499, "p95_latency_s": 1.0}
    verdict = compare(baseline, current)
    assert verdict.ok is False
    assert "success_rate" in verdict.blocked_reasons


def test_compare_p95_exactly_1_05_not_blocked() -> None:
    baseline = _baseline()
    current = {"success_rate": 1.0, "p95_latency_s": 1.05}
    verdict = compare(baseline, current)
    assert verdict.ok is True
    assert verdict.blocked_reasons == []


def test_compare_p95_just_over_blocked() -> None:
    # With baseline p95 = 30s the absolute floor (30+1=31) no longer dominates
    # the relative term (30*1.05=31.5), so 31.51 is a genuine >5% regression.
    baseline = _baseline(metrics={"success_rate": 1.0, "p95_latency_s": 30.0})
    current = {"success_rate": 1.0, "p95_latency_s": 31.51}
    verdict = compare(baseline, current)
    assert verdict.ok is False
    assert "p95_latency" in verdict.blocked_reasons


def test_compare_p95_absolute_floor_for_subsecond_baseline() -> None:
    # Baseline p95 = 0.05s. Relative +5% is ±2.5ms — meaningless jitter noise.
    # The absolute floor (baseline + ABS_P95_FLOOR_S) governs instead.
    baseline = _baseline(metrics={"success_rate": 1.0, "p95_latency_s": 0.05})
    current = {"success_rate": 1.0, "p95_latency_s": 0.06}
    verdict = compare(baseline, current)
    assert verdict.ok is True  # 0.06 < 0.05 + 1.0


def test_compare_p95_absolute_floor_blocks_big_jump() -> None:
    baseline = _baseline(metrics={"success_rate": 1.0, "p95_latency_s": 0.05})
    current = {"success_rate": 1.0, "p95_latency_s": 1.2}
    verdict = compare(baseline, current)
    assert verdict.ok is False
    assert "p95_latency" in verdict.blocked_reasons


def test_compare_custom_thresholds() -> None:
    baseline = _baseline()
    current = {"success_rate": 0.90, "p95_latency_s": 1.0}
    # default drop=0.05 -> 1.0 - 0.90 = 0.10 > 0.05 blocked
    assert compare(baseline, current).ok is False
    # custom drop=0.15 -> allowed
    verdict = compare(baseline, current, success_rate_drop=0.15)
    assert verdict.ok is True


def test_compare_custom_p95_regression_frac() -> None:
    baseline = _baseline(metrics={"success_rate": 1.0, "p95_latency_s": 30.0})
    current = {"success_rate": 1.0, "p95_latency_s": 31.5}
    # default 5%: ceiling = max(31.5, 31.0) = 31.5, strictly > not exceeded.
    assert compare(baseline, current).ok is True
    # tighter 3%: ceiling = max(30.9, 31.0) = 31.0, 31.5 exceeds.
    verdict = compare(baseline, current, p95_regression_frac=0.03)
    assert verdict.ok is False


def test_compare_both_metrics_delayed_lists_both() -> None:
    baseline = _baseline()
    current = {"success_rate": 0.80, "p95_latency_s": 2.1}
    verdict = compare(baseline, current)
    assert verdict.ok is False
    assert set(verdict.blocked_reasons) == {"success_rate", "p95_latency"}


def test_compare_improvements_not_blocked() -> None:
    baseline = _baseline()
    current = {"success_rate": 1.0, "p95_latency_s": 0.5}
    verdict = compare(baseline, current)
    assert verdict.ok is True
    assert verdict.success_rate_delta == pytest.approx(0.0)
    assert verdict.p95_delta == pytest.approx(-0.5)


def test_compare_check_p95_false_ignores_p95_regression() -> None:
    baseline = _baseline()
    current = {"success_rate": 1.0, "p95_latency_s": 99.0}
    verdict = compare(baseline, current, check_p95=False)
    assert verdict.ok is True
    assert verdict.p95_skipped is True
    assert verdict.blocked_reasons == []


def test_compare_check_p95_false_still_blocks_success_rate() -> None:
    baseline = _baseline()
    current = {"success_rate": 0.5, "p95_latency_s": 99.0}
    verdict = compare(baseline, current, check_p95=False)
    assert verdict.ok is False
    assert "success_rate" in verdict.blocked_reasons
    assert "p95_latency" not in verdict.blocked_reasons


# ---------------------------------------------------------------------------
# load_baseline / write_baseline
# ---------------------------------------------------------------------------

def test_load_baseline_roundtrip(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    data = _baseline()
    write_baseline(data, path)
    loaded = load_baseline(path)
    assert loaded == data
    assert loaded["task_set"] == "gate-smoke"
    assert "git_sha" in loaded


def test_load_baseline_missing_returns_none(tmp_path) -> None:
    assert load_baseline(tmp_path / "nope.json") is None


def test_load_baseline_malformed_metrics_raises_clean_error(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": 1, "metrics": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="metrics"):
        load_baseline(path)


def test_write_baseline_default_path() -> None:
    assert DEFAULT_BASELINE_PATH.name == "baseline.json"


def test_compare_verdict_reports_text(tmp_path) -> None:
    baseline = _baseline()
    current = {"success_rate": 0.80, "p95_latency_s": 2.0}
    verdict = compare(baseline, current)
    text = verdict.report()
    assert "success_rate" in text
    assert "p95_latency" in text
    assert "FAIL" in text
