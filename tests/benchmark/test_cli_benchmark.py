import json
import subprocess

from typer.testing import CliRunner

import agent.main as cli
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


class _FakeRunMetadata:
    def __init__(
        self,
        run_id,
        task_count=1,
        passed=1,
        warnings=0,
        unsupported=0,
        failed=0,
    ):
        self.run_id = run_id
        self.task_count = task_count
        self.passed = passed
        self.warnings = warnings
        self.unsupported = unsupported
        self.failed = failed


class _FakeBenchmarkRunner:
    """Stand-in for BenchmarkRunner that records construction and run_all calls."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.run_all_calls: list[tuple[str, str | None]] = []

    async def run_all(self, tasks_dir, run_id=None, seed=None):
        self.run_all_calls.append((str(tasks_dir), run_id))
        return _FakeRunMetadata(run_id=run_id or "auto-run")


def _minimal_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "bench@example.com")
    _git(repo, "config", "user.name", "Bench")
    (repo / "app.py").write_text("# Version 1\n")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "init")
    return repo


def _minimal_task(tmp_path, repo):
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
                "test_command": "true",
                "timeout_seconds": 30,
            }
        )
    )
    return task_dir


def _patch_runner(monkeypatch, fake_runner) -> None:
    """Replace BenchmarkRunner with a factory returning ``fake_runner``.

    Constructor kwargs (e.g. ``parallel``) are recorded on the fake instance
    so tests can assert what the CLI actually passed.
    """

    def factory(**kwargs):
        fake_runner.kwargs = kwargs
        return fake_runner

    monkeypatch.setattr("benchmarks.runner.BenchmarkRunner", factory)


def test_benchmark_cli_repeat_calls_run_all_repeat_times(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path)
    _minimal_task(tmp_path, repo)
    fake_runner = _FakeBenchmarkRunner()
    _patch_runner(monkeypatch, fake_runner)
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
            "--repeat",
            "2",
            "--parallel",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(fake_runner.run_all_calls) == 2
    run_ids = [rid for _, rid in fake_runner.run_all_calls]
    assert all(rid is not None for rid in run_ids)
    assert run_ids[0] != run_ids[1], "each round must get its own run_id"
    # explicit --parallel takes precedence over the dynamic guardrail
    assert fake_runner.kwargs["parallel"] == 1
    assert "Repeated 2 runs aggregated" in result.output
    assert (runs_dir / "evaluation-report.md").exists()


def test_benchmark_cli_repeat_one_preserves_legacy_behavior(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path)
    _minimal_task(tmp_path, repo)
    fake_runner = _FakeBenchmarkRunner()
    _patch_runner(monkeypatch, fake_runner)
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
            "--parallel",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(fake_runner.run_all_calls) == 1
    assert fake_runner.run_all_calls[0][1] is None
    assert "Benchmark run:" in result.output
    assert "Tasks:" in result.output
    assert "Repeated" not in result.output


def test_benchmark_cli_parallel_default_uses_suggest_parallel(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path)
    _minimal_task(tmp_path, repo)
    fake_runner = _FakeBenchmarkRunner()
    _patch_runner(monkeypatch, fake_runner)
    monkeypatch.setattr(
        "benchmarks.resources.suggest_parallel_default",
        lambda: 7,
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
        ],
    )

    assert result.exit_code == 0, result.output
    assert fake_runner.kwargs["parallel"] == 7


def test_benchmark_cli_explicit_parallel_beats_suggest_parallel(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path)
    _minimal_task(tmp_path, repo)
    fake_runner = _FakeBenchmarkRunner()
    _patch_runner(monkeypatch, fake_runner)
    monkeypatch.setattr(
        "benchmarks.resources.suggest_parallel_default",
        lambda: 7,
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
            "--parallel",
            "3",
        ],
    )

    assert result.exit_code == 0, result.output
    assert fake_runner.kwargs["parallel"] == 3


def test_benchmark_cli_config_parallel_explicit_wins_over_dynamic(tmp_path, monkeypatch):
    """A configured benchmark.parallel (even 1) must beat the dynamic guardrail."""
    repo = _minimal_repo(tmp_path)
    _minimal_task(tmp_path, repo)
    fake_runner = _FakeBenchmarkRunner()
    _patch_runner(monkeypatch, fake_runner)
    # If the guardrail ran it would produce 7; config parallel: 1 must win.
    monkeypatch.setattr(
        "benchmarks.resources.suggest_parallel_default",
        lambda: 7,
    )
    config_path = tmp_path / "asterwynd.yaml"
    config_path.write_text("benchmark:\n  parallel: 1\n")
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
    assert fake_runner.kwargs["parallel"] == 1


def test_benchmark_cli_repeat_aggregates_real_results(tmp_path, monkeypatch):
    """Repeat >1 must collect per-round result.json and render them in the report.

    Unlike the mock-only repeat test, this fake runner writes actual
    ``tasks/<task>/result.json`` files so ``collect_run_results`` /
    ``aggregate_results`` / ``render_report`` are exercised end to end.
    """
    repo = _minimal_repo(tmp_path)
    _minimal_task(tmp_path, repo)
    runs_dir = tmp_path / "runs"

    class _WritingRunner(_FakeBenchmarkRunner):
        async def run_all(self, tasks_dir, run_id=None, seed=None):
            self.run_all_calls.append((str(tasks_dir), run_id))
            rid = run_id or "auto-run"
            task_out = runs_dir / rid / "tasks" / "task-1"
            task_out.mkdir(parents=True)
            (task_out / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": "task-1",
                        "agent": "fake",
                        "status": "passed",
                        "category": "tool-usage",
                        "task_family": "local",
                        "duration_seconds": 12.0,
                        "input_tokens": 100,
                        "output_tokens": 50,
                    }
                )
            )
            return _FakeRunMetadata(run_id=rid)

    fake_runner = _WritingRunner()
    _patch_runner(monkeypatch, fake_runner)

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
            "--repeat",
            "2",
            "--parallel",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    report_path = runs_dir / "evaluation-report.md"
    assert report_path.exists()
    report_text = report_path.read_text()
    # Real per-round data flows into the report: layer table, task row, tokens.
    assert "## By Capability Layer" in report_text
    assert "| tool-usage" in report_text
    assert "| task-1 | local | tool-usage |" in report_text
    assert "100" in report_text
    assert "50" in report_text


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
