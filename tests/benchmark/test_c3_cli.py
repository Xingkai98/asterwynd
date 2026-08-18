"""C3 CLI budget-cap / no-cap / preflight tests.

Covers the confirmed budget semantics: per-round cap stops remaining rounds,
the overrunning round is marked ``truncated`` in run.json, ``--budget-cap 0``
and ``--no-cap`` cancel the cap, negatives are rejected, and ``--preflight``
exits 0/1/2 for ok / low-memory / docker-unavailable.
"""
from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

import agent.main as cli
from benchmarks.models import RunMetadata, TaskResult
from benchmarks.report import AggregateRun, render_report
from benchmarks.runner import BenchmarkRunner, DockerPreflightResult


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _git_out(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _setup_repo_and_task(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "bench@example.com")
    _git(repo, "config", "user.name", "Bench")
    (repo / "app.py").write_text("# Version 1\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "init")
    base_commit = _git_out(repo, "rev-parse", "HEAD")

    task_dir = tmp_path / "tasks" / "task-1"
    task_dir.mkdir(parents=True)
    (task_dir / "issue.md").write_text("Update app.py to Version 2.\n")
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "task-1",
                "repo": "local",
                "base_commit": base_commit,
                "problem_statement_file": "issue.md",
                "test_command": "grep -q 'Version 2' app.py",
                "timeout_seconds": 30,
            }
        )
    )
    runs_dir = tmp_path / "runs"
    return tmp_path / "tasks", repo, runs_dir


def _invoke(tasks_dir, repo, runs_dir, extra):
    return CliRunner().invoke(
        cli.app,
        [
            "benchmark",
            str(tasks_dir),
            "--agent",
            "fake",
            "--source-repo",
            str(repo),
            "--runs-dir",
            str(runs_dir),
            "--fake-edit-file",
            "app.py",
            "--fake-old-string",
            "Version 1",
            "--fake-new-string",
            "Version 2",
            *extra,
        ],
    )


# ---------------------------------------------------------------------------
# --budget-cap parsing
# ---------------------------------------------------------------------------

def test_budget_cap_negative_rejected(tmp_path):
    tasks, repo, runs = _setup_repo_and_task(tmp_path)
    result = _invoke(tasks, repo, runs, ["--budget-cap", "-1"])
    assert result.exit_code != 0
    assert "负数" in result.output


def test_no_cap_with_budget_cap_conflict_rejected(tmp_path):
    tasks, repo, runs = _setup_repo_and_task(tmp_path)
    result = _invoke(tasks, repo, runs, ["--no-cap", "--budget-cap", "50"])
    assert result.exit_code != 0
    assert "不能同时指定" in result.output


def test_budget_cap_zero_cancels_runs_all_rounds(tmp_path):
    tasks, repo, runs = _setup_repo_and_task(tmp_path)
    result = _invoke(tasks, repo, runs, ["--repeat", "3", "--budget-cap", "0"])
    assert result.exit_code == 0, result.output
    assert "Repeated 3 runs aggregated" in result.output
    round_dirs = [p for p in runs.iterdir() if p.is_dir()]
    assert len(round_dirs) == 3


def test_no_cap_cancels_runs_all_rounds(tmp_path):
    tasks, repo, runs = _setup_repo_and_task(tmp_path)
    result = _invoke(tasks, repo, runs, ["--repeat", "3", "--no-cap"])
    assert result.exit_code == 0, result.output
    assert "Repeated 3 runs aggregated" in result.output


# ---------------------------------------------------------------------------
# Budget overrun -> truncated
# ---------------------------------------------------------------------------

def test_budget_cap_overrun_stops_and_marks_truncated(tmp_path, monkeypatch):
    tasks, repo, runs = _setup_repo_and_task(tmp_path)
    monkeypatch.setattr("agent.main._round_cost", lambda run_dir, model: 999.0)
    result = _invoke(
        tasks, repo, runs,
        ["--repeat", "3", "--budget-cap", "1"],
    )
    assert result.exit_code == 0, result.output
    assert "预算超限" in result.output
    # Only the first round ran; remaining rounds stopped.
    round_dirs = [p for p in runs.iterdir() if p.is_dir()]
    assert len(round_dirs) == 1
    meta = json.loads((round_dirs[0] / "run.json").read_text())
    assert meta["truncated"] is True
    # The aggregate report still renders and discloses truncation.
    report = (runs / "evaluation-report.md").read_text()
    assert "truncated" in report


def test_budget_cap_overrun_single_run_marks_truncated(tmp_path, monkeypatch):
    """repeat=1 (default) also honors --budget-cap (regression for review r1)."""
    tasks, repo, runs = _setup_repo_and_task(tmp_path)
    monkeypatch.setattr("agent.main._round_cost", lambda run_dir, model: 999.0)
    result = _invoke(tasks, repo, runs, ["--budget-cap", "1"])
    assert result.exit_code == 0, result.output
    assert "预算超限" in result.output
    round_dirs = [p for p in runs.iterdir() if p.is_dir()]
    assert len(round_dirs) == 1
    meta = json.loads((round_dirs[0] / "run.json").read_text())
    assert meta["truncated"] is True


def test_report_excludes_truncated_round_from_pass_k():
    """Truncated rounds keep their pass@1 data but drop out of pass^k (Q4)."""
    results = [
        TaskResult(task_id="t1", agent="a", status="passed", run_round=0),
        TaskResult(task_id="t1", agent="a", status="passed", run_round=1),
        # round 2 truncated: the completed task failed, but it must not sink pass^k
        TaskResult(task_id="t1", agent="a", status="failed", reason="test_failure", run_round=2),
        TaskResult(task_id="t1", agent="a", status="passed", run_round=3),
    ]
    metas = [
        RunMetadata(run_id="r0", agent="a"),
        RunMetadata(run_id="r1", agent="a"),
        RunMetadata(run_id="r2", agent="a", truncated=True),
        RunMetadata(run_id="r3", agent="a"),
    ]
    agg = AggregateRun(agent="a", model="m", repeat=4, results=results, metadata=metas)
    md = render_report(agg)
    # pass@1 = 3/4, pass^k over non-truncated rounds 0,1,3 = 3/3 -> yes
    assert "| t1 | local | execution | 1.00 | 3/4 | yes |" in md


# ---------------------------------------------------------------------------
# --preflight
# ---------------------------------------------------------------------------

def test_preflight_memory_below_threshold_exits_1(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmarks.runner._available_memory_gib", lambda: 2.0)
    result = CliRunner().invoke(
        cli.app, ["benchmark", str(tmp_path / "tasks"), "--agent", "fake", "--preflight"]
    )
    assert result.exit_code == 1
    assert "L1" in result.output


def test_preflight_docker_unavailable_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmarks.runner._available_memory_gib", lambda: 16.0)
    monkeypatch.setattr(
        BenchmarkRunner,
        "_get_docker_preflight_result",
        lambda self: DockerPreflightResult(
            available=False, reason="docker_unavailable", detail="docker info failed"
        ),
    )
    result = CliRunner().invoke(
        cli.app, ["benchmark", str(tmp_path / "tasks"), "--agent", "fake", "--preflight"]
    )
    assert result.exit_code == 2
    assert "Docker" in result.output


def test_preflight_ok_exits_0(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmarks.runner._available_memory_gib", lambda: 16.0)
    monkeypatch.setattr(
        BenchmarkRunner,
        "_get_docker_preflight_result",
        lambda self: DockerPreflightResult(available=True, reason="ok"),
    )
    result = CliRunner().invoke(
        cli.app, ["benchmark", str(tmp_path / "tasks"), "--agent", "fake", "--preflight"]
    )
    assert result.exit_code == 0
    assert "可跑全量" in result.output
