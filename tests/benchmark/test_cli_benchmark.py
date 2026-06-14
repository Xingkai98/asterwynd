import json
import subprocess

from typer.testing import CliRunner

import cli


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
