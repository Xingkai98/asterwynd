import json
import subprocess

from typer.testing import CliRunner

import cli
from benchmarks.runner import DockerPreflightResult


def test_benchmark_cli_runs_fake_agent(tmp_path):
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

    result = CliRunner().invoke(
        cli.app,
        [
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
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Benchmark run:" in result.output
    run_dirs = list(runs_dir.iterdir())
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "run.json").exists()
    assert (run_dirs[0] / "tasks" / "task-1" / "trace.json").exists()


def test_benchmark_cli_uses_yaml_default_mode(tmp_path):
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
    (task_dir / "issue.md").write_text("Read app.py.\n")
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "task-1",
                "repo": "local",
                "base_commit": base_commit,
                "problem_statement_file": "issue.md",
                "test_command": "true",
                "timeout_seconds": 30,
            }
        )
    )
    config_path = tmp_path / "asterwynd.yaml"
    config_path.write_text("agent:\n  default_mode: plan\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"

    result = CliRunner().invoke(
        cli.app,
        [
            "benchmark",
            str(tmp_path / "tasks"),
            "--agent",
            "fake",
            "--source-repo",
            str(repo),
            "--runs-dir",
            str(runs_dir),
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0, result.output
    run_dirs = list(runs_dir.iterdir())
    run = json.loads((run_dirs[0] / "run.json").read_text())
    trace = json.loads((run_dirs[0] / "tasks" / "task-1" / "trace.json").read_text())
    assert run["mode"] == "plan"
    assert trace["mode"] == "plan"


def test_benchmark_cli_reports_unsupported_docker_tasks(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "bench@example.com")
    _git(repo, "config", "user.name", "Bench")
    (repo / "app.py").write_text("# Version 1\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "init")
    base_commit = _git_out(repo, "rev-parse", "HEAD")

    task_dir = tmp_path / "tasks" / "swebench-psf__requests-1142"
    task_dir.mkdir(parents=True)
    (task_dir / "issue.md").write_text("Fix requests issue.\n")
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "swebench-psf__requests-1142",
                "repo": "psf/requests",
                "base_commit": base_commit,
                "problem_statement_file": "issue.md",
                "test_command": "pytest",
                "timeout_seconds": 30,
                "task_family": "swebench",
                "execution_environment": "docker",
                "external_repo": "https://example.com/requests.git",
                "instance_id": "psf__requests-1142",
                "dataset_name": "princeton-nlp/SWE-bench_Verified",
                "dataset_split": "test",
            }
        )
    )
    runs_dir = tmp_path / "runs"

    def fake_preflight(self):
        return DockerPreflightResult(
            available=False,
            reason="docker_unavailable",
            detail="Cannot connect to the Docker daemon",
        )

    monkeypatch.setattr(
        "benchmarks.runner.BenchmarkRunner._get_docker_preflight_result",
        fake_preflight,
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "benchmark",
            str(tmp_path / "tasks"),
            "--agent",
            "fake",
            "--source-repo",
            str(repo),
            "--runs-dir",
            str(runs_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "unsupported: 1" in result.output
    run_dirs = list(runs_dir.iterdir())
    task_result = json.loads(
        (run_dirs[0] / "tasks" / "swebench-psf__requests-1142" / "result.json").read_text()
    )
    assert task_result["status"] == "unsupported"
    assert task_result["reason"] == "docker_unavailable"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _git_out(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
