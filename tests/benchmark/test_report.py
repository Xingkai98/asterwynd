"""Tests for benchmarks/report.py evaluation aggregation and rendering.

Covers cross-round grouping, layer fallback, task-family inference, failure
attribution counting and golden fragments of the rendered markdown report.
"""
from __future__ import annotations

import json

import pytest

from benchmarks.models import TaskResult
from benchmarks.report import (
    AggregateRun,
    TaskAggregate,
    aggregate_results,
    collect_run_results,
    failure_attribution,
    render_report,
)


def _result(
    task_id: str,
    status: str,
    *,
    reason: str | None = None,
    category: str | None = None,
    task_family: str | None = None,
    run_round: int | None = None,
    duration: float = 1.0,
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        agent="fake",
        model="fake-model",
        status=status,
        reason=reason,
        category=category,
        task_family=task_family,
        run_round=run_round,
        duration_seconds=duration,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


# ---------------------------------------------------------------------------
# aggregate_results
# ---------------------------------------------------------------------------

def test_aggregate_results_groups_by_task_across_rounds() -> None:
    round0 = [
        _result("asterwynd-001", "passed", category="tool-usage"),
        _result("swebench-abc", "failed", reason="test_failure"),
    ]
    round1 = [
        _result("asterwynd-001", "passed_with_warnings", category="tool-usage"),
        _result("swebench-abc", "passed"),
    ]
    aggregates = aggregate_results([round0, round1])
    assert [a.task_id for a in aggregates] == ["asterwynd-001", "swebench-abc"]
    by_id = {a.task_id: a for a in aggregates}
    assert len(by_id["asterwynd-001"].results) == 2
    assert len(by_id["swebench-abc"].results) == 2
    # run_round is assigned from the round position when unset
    rounds = sorted(r.run_round for r in by_id["asterwynd-001"].results)
    assert rounds == [0, 1]


def test_aggregate_results_layer_default_fallback() -> None:
    aggregates = aggregate_results(
        [
            [_result("asterwynd-001", "passed", category=None)],
            [_result("asterwynd-001", "failed", category="")],
        ]
    )
    assert aggregates[0].category == "execution"


def test_aggregate_results_category_uses_resolve_layer() -> None:
    aggregates = aggregate_results(
        [[_result("t1", "passed", category="context-planning")]]
    )
    assert aggregates[0].category == "context-planning"


def test_aggregate_results_task_family_prefers_result_field() -> None:
    aggregates = aggregate_results(
        [
            [
                _result("swebench-abc", "passed", task_family="swebench"),
                _result("asterwynd-001", "passed", task_family="local"),
            ]
        ]
    )
    by_id = {a.task_id: a for a in aggregates}
    assert by_id["swebench-abc"].task_family == "swebench"
    assert by_id["asterwynd-001"].task_family == "local"


def test_aggregate_results_task_family_inferred_from_prefix() -> None:
    aggregates = aggregate_results(
        [
            [
                _result("swebench-abc", "passed", task_family=None),
                _result("asterwynd-001", "passed", task_family=None),
            ]
        ]
    )
    by_id = {a.task_id: a for a in aggregates}
    assert by_id["swebench-abc"].task_family == "swebench"
    assert by_id["asterwynd-001"].task_family == "local"


def test_aggregate_results_empty_rounds() -> None:
    assert aggregate_results([]) == []
    assert aggregate_results([[]]) == []


# ---------------------------------------------------------------------------
# collect_run_results
# ---------------------------------------------------------------------------

def test_collect_run_results_reads_result_jsons(tmp_path) -> None:
    task_dir = tmp_path / "tasks" / "asterwynd-001"
    task_dir.mkdir(parents=True)
    (task_dir / "result.json").write_text(
        json.dumps(
            {
                "task_id": "asterwynd-001",
                "agent": "fake",
                "status": "passed",
                "category": "tool-usage",
                "task_family": "local",
                "duration_seconds": 1.5,
            }
        )
    )
    results = collect_run_results(tmp_path)
    assert len(results) == 1
    assert results[0].task_id == "asterwynd-001"
    assert results[0].status == "passed"
    assert results[0].category == "tool-usage"
    assert results[0].task_family == "local"


def test_collect_run_results_missing_dir_returns_empty(tmp_path) -> None:
    assert collect_run_results(tmp_path / "nope") == []
    assert collect_run_results(tmp_path) == []


# ---------------------------------------------------------------------------
# failure_attribution
# ---------------------------------------------------------------------------

def test_failure_attribution_counts_reasons_and_rounds() -> None:
    aggregates = [
        TaskAggregate(
            task_id="t1",
            category="execution",
            task_family="local",
            results=[
                _result("t1", "failed", reason="test_failure", run_round=0),
                _result("t1", "failed", reason="test_failure", run_round=1),
                _result("t1", "passed", run_round=2),
            ],
        ),
        TaskAggregate(
            task_id="t2",
            category="execution",
            task_family="local",
            results=[
                _result("t2", "error", reason="tool_error", run_round=0),
                _result("t2", "unsupported", reason="docker_unavailable", run_round=1),
            ],
        ),
    ]
    attribution = failure_attribution(aggregates)
    # unsupported (docker_unavailable) is an invalid round, not a failure
    assert set(attribution) == {"test_failure", "tool_error"}
    assert attribution["test_failure"] == [("t1", 0), ("t1", 1)]
    assert attribution["tool_error"] == [("t2", 0)]


def test_failure_attribution_excludes_passed_and_none_reason() -> None:
    aggregates = [
        TaskAggregate(
            task_id="t1",
            category="execution",
            task_family="local",
            results=[
                _result("t1", "passed", run_round=0),
                _result("t1", "passed_with_warnings", run_round=1),
                _result("t1", "failed", reason=None, run_round=2),
            ],
        )
    ]
    assert failure_attribution(aggregates) == {}


def test_failure_attribution_empty_aggregates() -> None:
    assert failure_attribution([]) == {}


# ---------------------------------------------------------------------------
# render_report
# ---------------------------------------------------------------------------

def test_render_report_contains_golden_fragments() -> None:
    aggregates = aggregate_results(
        [
            [
                _result(
                    "asterwynd-001",
                    "passed",
                    category="tool-usage",
                    duration=1.5,
                    input_tokens=100,
                    output_tokens=50,
                ),
                _result("swebench-abc", "failed", reason="test_failure", duration=3.0),
            ],
            [
                _result(
                    "asterwynd-001",
                    "passed",
                    category="tool-usage",
                    duration=2.5,
                    input_tokens=120,
                    output_tokens=60,
                ),
                _result("swebench-abc", "failed", reason="test_failure", duration=4.0),
            ],
        ]
    )
    md = render_report(aggregates)
    assert md.startswith("# Benchmark Evaluation Report")
    assert "Pass@k" in md
    assert "95% CI" in md
    assert "p50" in md
    assert "p95" in md
    assert "Tokens" in md
    assert "execution" in md  # default-layer fallback from the second round
    assert "swebench" in md  # task_family value
    assert "tool-usage" in md
    assert "test_failure" in md
    assert "asterwynd-001" in md


def test_render_report_task_row_has_pass_at_k_and_tokens() -> None:
    aggregates = aggregate_results(
        [
            [
                _result(
                    "asterwynd-001",
                    "passed",
                    category="execution",
                    duration=2.0,
                    input_tokens=10,
                    output_tokens=5,
                ),
            ],
            [
                _result(
                    "asterwynd-001",
                    "passed",
                    category="execution",
                    duration=2.0,
                    input_tokens=10,
                    output_tokens=5,
                ),
            ],
        ]
    )
    md = render_report(aggregates)
    assert "| asterwynd-001 | local | execution | 1.00 | 2/2 |" in md
    assert "| 20 | 10 |" in md  # input/output tokens summed across both rounds


def test_render_report_deterministic_order() -> None:
    round_a = [
        _result("b-task", "passed", category="execution"),
        _result("a-task", "failed", reason="timeout"),
    ]
    round_b = [
        _result("a-task", "failed", reason="timeout"),
        _result("b-task", "passed", category="execution"),
    ]
    md1 = render_report(aggregate_results([round_a]))
    md2 = render_report(aggregate_results([round_b]))
    assert md1 == md2
    # task ids appear in sorted order
    assert md1.index("a-task") < md1.index("b-task")


def test_render_report_accepts_aggregate_run() -> None:
    aggregated = AggregateRun(
        agent="fake",
        model="fake-model",
        repeat=2,
        results=[
            _result("asterwynd-001", "passed", category="execution", run_round=0),
            _result("asterwynd-001", "failed", reason="test_failure", run_round=1),
        ],
        run_ids=["r1", "r2"],
    )
    md = render_report(aggregated)
    assert md.startswith("# Benchmark Evaluation Report")
    assert "**Agent**: fake" in md
    assert "Pass@k" in md
    assert "asterwynd-001" in md
    assert "test_failure" in md


def test_render_report_empty_aggregates() -> None:
    md = render_report([])
    assert md.startswith("# Benchmark Evaluation Report")
    assert "(no failures)" in md
