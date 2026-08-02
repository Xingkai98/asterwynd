"""Integration tests for the ``benchmark-gate`` CLI command.

Runs the real CLI (Typer CliRunner) with a fake agent against a small local
task set and a synthetic baseline, exercising the pass/block/update-baseline/
require-baseline branches. The fake agent's wall-clock duration is machine
dependent, so latency assertions use thresholds far from the gate's boundaries.
"""
from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

import agent.main as cli


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _git_out(repo, *args) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def gate_env(tmp_path):
    """A local git repo + a 2-task gate-smoke set + a runs dir."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "gate@example.com")
    _git(repo, "config", "user.name", "Gate")
    (repo / "app.py").write_text("# Version 1\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "init")
    base_commit = _git_out(repo, "rev-parse", "HEAD")

    tasks_dir = tmp_path / "tasks" / "gate-smoke"
    for i, (cmd, expect) in enumerate(
        [("python -c \"import sys; sys.exit(0)\"", "ok-a"),
         ("python -c \"import sys; sys.exit(0)\"", "ok-b")]
    ):
        task_dir = tasks_dir / f"gate-{i}"
        task_dir.mkdir(parents=True)
        (task_dir / "issue.md").write_text(f"Task {i}: verify exit 0.\n")
        (task_dir / "task.json").write_text(
            json.dumps({
                "id": f"gate-{i}",
                "repo": "local",
                "base_commit": base_commit,
                "problem_statement_file": "issue.md",
                "test_command": cmd,
                "timeout_seconds": 30,
            })
        )
    runs_dir = tmp_path / "runs"
    return repo, tasks_dir, runs_dir, base_commit


def _invoke(args):
    return CliRunner().invoke(cli.app, args)


def _baseline_json(task_set: str, success_rate: float, p95: float) -> dict:
    return {
        "schema_version": 1,
        "agent": "fake",
        "model": "",
        "task_set": task_set,
        "created_at": "2026-08-03T00:00:00Z",
        "git_sha": None,
        "metrics": {"success_rate": success_rate, "p95_latency_s": p95},
        "per_task": {},
    }


def test_gate_pass_when_matches_baseline(gate_env, tmp_path):
    repo, tasks_dir, runs_dir, _ = gate_env
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(_baseline_json("gate-smoke", 1.0, 0.001)),
        encoding="utf-8",
    )
    result = _invoke([
        "benchmark-gate",
        str(tasks_dir),
        "--source-repo", str(repo),
        "--runs-dir", str(runs_dir),
        "--baseline", str(baseline),
        "--require-baseline",
    ])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output


def test_gate_blocks_on_success_rate_regression(gate_env, tmp_path):
    repo, tasks_dir, runs_dir, _ = gate_env
    baseline = tmp_path / "baseline.json"
    # Impossible baseline: success_rate 1.0 while one task is configured to fail.
    baseline.write_text(
        json.dumps(_baseline_json("gate-smoke", 1.0, 0.001)),
        encoding="utf-8",
    )
    # Make the second task fail by pointing its test_command at a failing check.
    failing = tasks_dir / "gate-1" / "task.json"
    data = json.loads(failing.read_text())
    data["test_command"] = "python -c \"import sys; sys.exit(1)\""
    failing.write_text(json.dumps(data), encoding="utf-8")
    result = _invoke([
        "benchmark-gate",
        str(tasks_dir),
        "--source-repo", str(repo),
        "--runs-dir", str(runs_dir),
        "--baseline", str(baseline),
        "--require-baseline",
    ])
    assert result.exit_code != 0, result.output
    assert "FAIL" in result.output
    assert "success_rate" in result.output


def test_gate_skips_without_baseline_and_require(gate_env):
    repo, tasks_dir, runs_dir, _ = gate_env
    result = _invoke([
        "benchmark-gate",
        str(tasks_dir),
        "--source-repo", str(repo),
        "--runs-dir", str(runs_dir),
        "--baseline", str(tmp_path_nonexistent()),
    ])
    assert result.exit_code == 0
    assert "SKIPPED" in result.output


def test_gate_require_baseline_fails_without_baseline(gate_env, tmp_path):
    repo, tasks_dir, runs_dir, _ = gate_env
    result = _invoke([
        "benchmark-gate",
        str(tasks_dir),
        "--source-repo", str(repo),
        "--runs-dir", str(runs_dir),
        "--baseline", str(tmp_path / "missing.json"),
        "--require-baseline",
    ])
    assert result.exit_code != 0
    assert "baseline not found" in result.output


def test_gate_update_baseline_writes_file(gate_env, tmp_path):
    repo, tasks_dir, runs_dir, _ = gate_env
    baseline = tmp_path / "baseline.json"
    result = _invoke([
        "benchmark-gate",
        str(tasks_dir),
        "--source-repo", str(repo),
        "--runs-dir", str(runs_dir),
        "--baseline", str(baseline),
        "--update-baseline",
    ])
    assert result.exit_code == 0, result.output
    assert "Baseline updated" in result.output
    data = json.loads(baseline.read_text())
    assert data["task_set"] == "gate-smoke"
    assert data["metrics"]["success_rate"] == 1.0
    assert data["metrics"]["p95_latency_s"] >= 0.0
    assert "per_task" in data
    assert len(data["per_task"]) == 2


def test_gate_skip_p95_reports_skipped(gate_env, tmp_path):
    repo, tasks_dir, runs_dir, _ = gate_env
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(_baseline_json("gate-smoke", 1.0, 0.001)),
        encoding="utf-8",
    )
    result = _invoke([
        "benchmark-gate",
        str(tasks_dir),
        "--source-repo", str(repo),
        "--runs-dir", str(runs_dir),
        "--baseline", str(baseline),
        "--require-baseline",
        "--skip-p95",
    ])
    assert result.exit_code == 0, result.output
    assert "SKIPPED (deterministic task set)" in result.output


def test_gate_update_baseline_refuses_empty_run(gate_env, tmp_path):
    repo, tasks_dir, runs_dir, _ = gate_env
    empty_tasks = tmp_path / "tasks" / "empty"
    empty_tasks.mkdir(parents=True)
    baseline = tmp_path / "baseline.json"
    result = _invoke([
        "benchmark-gate",
        str(empty_tasks),
        "--source-repo", str(repo),
        "--runs-dir", str(runs_dir),
        "--baseline", str(baseline),
        "--update-baseline",
    ])
    assert result.exit_code != 0
    assert not baseline.exists()


def tmp_path_nonexistent():
    from pathlib import Path
    return Path("/nonexistent/baseline.json")
