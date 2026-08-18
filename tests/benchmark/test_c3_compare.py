"""C3 compare enhancements: HTML paired-comparison section + run metadata.

The markdown paired section already shipped with C2 (``build_paired_report``);
C3 reuses the same paired data for the HTML path and adds a run-metadata
disclosure (model version / date / pricing-table version) to both formats.
"""
from __future__ import annotations

import pytest

from benchmarks.compare import build_html, build_summary


def _run(name: str, task_results: dict) -> tuple[str, dict[str, dict]]:
    return (name, task_results)


def _pair() -> list[tuple[str, dict[str, dict]]]:
    return [
        _run(
            "agent-a",
            {
                "t1": {"task_id": "t1", "status": "passed", "agent": "a", "run_round": 0},
                "t2": {
                    "task_id": "t2",
                    "status": "failed",
                    "reason": "test_failure",
                    "agent": "a",
                    "run_round": 0,
                },
            },
        ),
        _run(
            "agent-b",
            {
                "t1": {"task_id": "t1", "status": "passed", "agent": "b", "run_round": 0},
                "t2": {"task_id": "t2", "status": "passed", "agent": "b", "run_round": 0},
            },
        ),
    ]


def test_build_html_includes_paired_comparison() -> None:
    html = build_html(_pair())
    assert "<h2>Paired Comparison</h2>" in html
    assert "Mean per-task delta" in html
    assert "Difference 95% CI" in html
    assert "Win-rate" in html
    assert "<td>t1</td><td>0.000</td>" in html
    assert "<td>t2</td><td>-1.000</td>" in html


def test_build_html_no_paired_for_wrong_run_count() -> None:
    assert "Paired Comparison" not in build_html([_pair()[0]])
    assert "Paired Comparison" not in build_html(_pair() + [("c", {})])


def test_run_metadata_section_in_markdown() -> None:
    metas = [
        {
            "agent": "a",
            "model": "deepseek-v4-flash",
            "model_version": "v4-flash-20260817",
            "started_at": "2026-08-18T00:00:00+00:00",
            "pricing_table_version": "2026-08-17",
        }
    ]
    md = build_summary([("a", {})], metas=metas)
    assert "## Run Metadata" in md
    assert "v4-flash-20260817" in md
    assert "pricing_table_version" not in md  # rendered as value, not key


def test_run_metadata_section_absent_without_metas() -> None:
    assert "## Run Metadata" not in build_summary([("a", {})])
    assert "## Run Metadata" not in build_html([("a", {})])


def test_run_metadata_section_in_html() -> None:
    metas = [{"agent": "a", "model": "m", "model_version": "v1", "started_at": "d", "pricing_table_version": "p"}]
    html = build_html([("a", {})], metas=metas)
    assert "Run Metadata" in html
    assert "v1" in html


def test_build_html_paired_data_consistent_with_markdown() -> None:
    """HTML and markdown paired sections must agree on per-task deltas (Q1)."""
    from benchmarks.compare import build_paired_report

    md = build_paired_report(_pair())
    html = build_html(_pair())
    assert "| t2 | -1.000 |" in md
    assert "<td>t2</td><td>-1.000</td>" in html
