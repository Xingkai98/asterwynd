"""Tests for the evaluation-metrics (C2) `benchmark annotate` CLI.

Covers the minimal fault_owner annotation tool: it updates a result.json's
fault_owner field and rejects invalid owners.
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

import agent.main as cli


def _make_result(run_dir, task_id: str) -> dict:
    task_dir = run_dir / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "task_id": task_id,
        "agent": "fake",
        "model": "fake",
        "status": "failed",
        "reason": "test_failure",
        "fault_owner": None,
    }
    (task_dir / "result.json").write_text(json.dumps(data))
    return data


def test_annotate_sets_fault_owner(tmp_path) -> None:
    run_dir = tmp_path / "run-1"
    _make_result(run_dir, "task-1")

    result = CliRunner().invoke(
        cli.app,
        ["benchmark-annotate", str(run_dir), "task-1", "--owner", "agent"],
    )
    assert result.exit_code == 0, result.output
    saved = json.loads((run_dir / "tasks" / "task-1" / "result.json").read_text())
    assert saved["fault_owner"] == "agent"


def test_annotate_rejects_invalid_owner(tmp_path) -> None:
    run_dir = tmp_path / "run-1"
    _make_result(run_dir, "task-1")

    result = CliRunner().invoke(
        cli.app,
        ["benchmark-annotate", str(run_dir), "task-1", "--owner", "taskk"],
    )
    assert result.exit_code != 0
    saved = json.loads((run_dir / "tasks" / "task-1" / "result.json").read_text())
    assert saved["fault_owner"] is None  # unchanged


def test_annotate_missing_result_errors(tmp_path) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir(parents=True)

    result = CliRunner().invoke(
        cli.app,
        ["benchmark-annotate", str(run_dir), "task-1", "--owner", "agent"],
    )
    assert result.exit_code != 0
    assert "result.json" in result.output


def test_annotate_rejects_path_traversal(tmp_path) -> None:
    run_dir = tmp_path / "run-1"
    # create a result.json outside the tasks dir that must NOT be touched
    outside = tmp_path / "victim.json"
    outside.write_text(json.dumps({"status": "passed"}))

    result = CliRunner().invoke(
        cli.app,
        [
            "benchmark-annotate",
            str(run_dir),
            "../victim.json",
            "--owner",
            "agent",
        ],
    )
    assert result.exit_code != 0
    assert json.loads(outside.read_text()) == {"status": "passed"}
