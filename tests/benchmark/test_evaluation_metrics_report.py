"""Tests for the evaluation-metrics (C2) report integration.

Covers the spec-mandated pass-rate semantics: invalid rounds never count into
pass@1 / pass@k denominators, pass^k layer aggregation is rendered, and the
metric-semantics note is present.
"""
from __future__ import annotations

from benchmarks.models import TaskResult
from benchmarks.report import aggregate_results, render_html, render_report


def _result(
    task_id: str,
    status: str,
    *,
    reason: str | None = None,
    category: str | None = None,
    run_round: int = 0,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        agent="fake",
        model="fake",
        status=status,
        reason=reason,
        category=category,
        run_round=run_round,
    )


def test_render_report_includes_metric_semantics_note() -> None:
    aggregates = aggregate_results(
        [[_result("t1", "passed"), _result("t2", "failed", reason="test_failure")]]
    )
    md = render_report(aggregates)
    assert "pass@1" in md
    assert "pass@k" in md
    assert "pass^k" in md
    assert "无效轮次" in md


def test_layer_pass_rate_excludes_invalid_rounds() -> None:
    # task A: 3 valid rounds all passed; task B: 1 valid round passed,
    # 2 unsupported rounds. Spec pass@1 over valid rounds = (3/3 + 1/1)/2 == 1.0
    # at task level; the layer table shows the valid-round rate.
    aggregates = aggregate_results(
        [
            [
                _result("a", "passed", category="execution", run_round=0),
                _result("b", "passed", category="execution", run_round=0),
            ],
            [
                _result("a", "passed", category="execution", run_round=1),
                _result(
                    "b", "unsupported",
                    reason="docker_unavailable", category="execution", run_round=1,
                ),
            ],
            [
                _result("a", "passed", category="execution", run_round=2),
                _result(
                    "b", "unsupported",
                    reason="docker_unavailable", category="execution", run_round=2,
                ),
            ],
        ]
    )
    md = render_report(aggregates)
    # layer row: Rounds = 4 valid rounds (a×3 + b×1), Pass Rate = 1.00
    assert "| execution | 2 | 4 | 1.00 |" in md
    # layer Pass^k: both tasks have >=3 valid rounds? b has only 1 valid -> excluded
    # a passes all 3 -> passed_tasks=1, valid_tasks=1 -> rate 1.00
    assert "| execution | 2 | 4 | 1.00 | [1.00, 1.00] | 1.00 |" in md


def test_task_row_pass_at_k_counts_only_valid_rounds() -> None:
    aggregates = aggregate_results(
        [
            [_result("t1", "passed", run_round=0)],
            [_result("t1", "passed", run_round=1)],
            [
                _result(
                    "t1", "unsupported", reason="docker_unavailable", run_round=2
                )
            ],
        ]
    )
    md = render_report(aggregates)
    # 2 valid rounds, both passed -> Pass@k 1.00, Passes 2/2,
    # Pass^k shows em-dash (below the 3-valid-round threshold)
    assert "| t1 | local | execution | 1.00 | 2/2 | — |" in md


def test_task_row_pass_k_marked_no_when_any_valid_round_fails() -> None:
    aggregates = aggregate_results(
        [
            [_result("t1", "passed", run_round=0)],
            [_result("t1", "failed", reason="test_failure", run_round=1)],
        ]
    )
    md = render_report(aggregates)
    # pass@2 = "at least one success in 2 rounds" -> 1.00; pass^k (all rounds)
    # shows em-dash because only 2 valid rounds (below threshold).
    assert "| t1 | local | execution | 1.00 | 1/2 | — |" in md


def test_render_html_includes_pass_k_columns() -> None:
    aggregates = aggregate_results(
        [[_result("t1", "passed", category="execution")]]
    )
    html = render_html(aggregates)
    assert "Pass^k" in html
    assert ">—<" in html


def test_layer_pass_k_n_a_when_no_task_has_enough_rounds() -> None:
    aggregates = aggregate_results(
        [[_result("t1", "passed", category="execution", run_round=0)]]
    )
    md = render_report(aggregates)
    # single round: no task has >=3 valid rounds -> Pass^k n/a
    assert "| execution | 1 | 1 | 1.00 | [1.00, 1.00] | n/a |" in md


def test_task_row_pass_k_yes_when_three_valid_rounds_pass() -> None:
    aggregates = aggregate_results(
        [
            [_result("t1", "passed", run_round=0)],
            [_result("t1", "passed", run_round=1)],
            [_result("t1", "passed", run_round=2)],
        ]
    )
    md = render_report(aggregates)
    assert "| t1 | local | execution | 1.00 | 3/3 | yes |" in md
