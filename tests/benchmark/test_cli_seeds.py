"""Tests for the evaluation-metrics (C2) sampling-explicitness CLI.

Covers --seeds / --temperature / --model-version recording (Q11), the
seeds-vs-repeat length check and the repeat bounds (Q12).
"""
from __future__ import annotations

import json
import subprocess

from typer.testing import CliRunner

import agent.main as cli


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _git_out(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _make_repo_and_task(tmp_path):
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
    return repo


def _invoke_benchmark(tmp_path, extra_args):
    repo = _make_repo_and_task(tmp_path)
    runs_dir = tmp_path / "runs"
    args = [
        "benchmark",
        str(tmp_path / "tasks"),
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
    ]
    return CliRunner().invoke(cli.app, args + extra_args), runs_dir


def test_seeds_repeat_records_sampling_params(tmp_path) -> None:
    result, runs_dir = _invoke_benchmark(
        tmp_path,
        [
            "--repeat",
            "3",
            "--seeds",
            "0",
            "--seeds",
            "1",
            "--seeds",
            "2",
            "--temperature",
            "0.2",
            "--model-version",
            "v-20260817",
        ],
    )
    assert result.exit_code == 0, result.output
    run_dirs = sorted(
        d for d in runs_dir.iterdir() if d.is_dir() and "-r" in d.name
    )
    assert len(run_dirs) == 3
    for i, seed in enumerate([0, 1, 2]):
        run = json.loads((run_dirs[i] / "run.json").read_text())
        assert run["seed"] == seed
        assert run["temperature"] == 0.2
        assert run["model_version"] == "v-20260817"


def test_result_json_records_temperature_and_seed(tmp_path) -> None:
    result, runs_dir = _invoke_benchmark(
        tmp_path,
        [
            "--repeat",
            "2",
            "--seeds",
            "0",
            "--seeds",
            "1",
            "--temperature",
            "0.2",
            "--model-version",
            "v1",
        ],
    )
    assert result.exit_code == 0, result.output
    run_dirs = sorted(
        d for d in runs_dir.iterdir() if d.is_dir() and "-r" in d.name
    )
    task_result = json.loads(
        (run_dirs[1] / "tasks" / "task-1" / "result.json").read_text()
    )
    assert task_result["seed"] == 1
    assert task_result["temperature"] == 0.2


def test_seeds_mismatch_with_repeat_errors(tmp_path) -> None:
    result, _ = _invoke_benchmark(
        tmp_path, ["--repeat", "3", "--seeds", "0", "--seeds", "1"]
    )
    assert result.exit_code != 0
    assert "seeds" in result.output.lower() or "repeat" in result.output.lower()


def test_repeat_above_five_errors(tmp_path) -> None:
    result, _ = _invoke_benchmark(tmp_path, ["--repeat", "6"])
    assert result.exit_code != 0
    assert "repeat" in result.output.lower()


def test_repeat_below_three_warns_but_runs(tmp_path) -> None:
    result, runs_dir = _invoke_benchmark(tmp_path, ["--repeat", "2"])
    assert result.exit_code == 0, result.output
    assert "repeat" in result.output.lower()
    assert "warning" in result.output.lower()
    run_dirs = sorted(
        d for d in runs_dir.iterdir() if d.is_dir() and "-r" in d.name
    )
    assert len(run_dirs) == 2


def test_seeds_default_derives_from_repeat(tmp_path) -> None:
    result, runs_dir = _invoke_benchmark(tmp_path, ["--repeat", "3"])
    assert result.exit_code == 0, result.output
    run_dirs = sorted(
        d for d in runs_dir.iterdir() if d.is_dir() and "-r" in d.name
    )
    assert len(run_dirs) == 3
    for i, run_dir in enumerate(run_dirs):
        run = json.loads((run_dir / "run.json").read_text())
        assert run["seed"] == i
