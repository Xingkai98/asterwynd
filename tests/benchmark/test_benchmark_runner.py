import json
import subprocess
from pathlib import Path

import pytest

from benchmarks.agent_runner import AgentRunner, FakeAgentRunner
from benchmarks.models import AgentRunResult
from benchmarks.runner import BenchmarkRunner


class AssertHiddenAndEditRunner(AgentRunner):
    async def run(self, task, problem_statement, workspace, output_dir, trace):
        assert "Version 2" in problem_statement
        assert not (workspace / "benchmarks" / "tasks").exists()
        target = workspace / "app.py"
        target.write_text(target.read_text().replace("Version 1", "Version 2"))
        trace.record_tool_call("AssertHiddenAndEdit", {"path": "app.py"})
        trace.record_edit("app.py", "ok", "Version 1 -> Version 2")
        return AgentRunResult(
            status="completed",
            iterations=1,
            tool_calls=1,
            edit_count=1,
        )


class WarningEditRunner(AgentRunner):
    async def run(self, task, problem_statement, workspace, output_dir, trace):
        target = workspace / "app.py"
        target.write_text(target.read_text().replace("Version 1", "Version 2"))
        trace.record_edit("app.py", "ok", "Version 1 -> Version 2")
        return AgentRunResult(
            status="error",
            iterations=20,
            tool_calls=3,
            edit_count=1,
            failure_category="max_iterations",
        )


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "bench@example.com")
    _git(repo, "config", "user.name", "Bench")
    (repo / "app.py").write_text("# Version 1\n")
    tracked_task_dir = repo / "benchmarks" / "tasks" / "tracked"
    tracked_task_dir.mkdir(parents=True)
    (tracked_task_dir / "test.patch").write_text("hidden")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return repo


@pytest.mark.asyncio
async def test_benchmark_runner_writes_closed_loop_artifacts(repo, tmp_path):
    base_commit = _git_out(repo, "rev-parse", "HEAD")
    task_dir = _task_dir(
        tmp_path,
        base_commit=base_commit,
        test_command="grep -q 'Version 2' app.py",
    )
    runner = BenchmarkRunner(
        agent_runner=AssertHiddenAndEditRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )

    metadata = await runner.run_all(tmp_path / "tasks", run_id="run-1")

    assert metadata.passed == 1
    run_dir = tmp_path / "runs" / "run-1"
    task_output = run_dir / "tasks" / "task-1"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "summary.md").exists()
    assert (task_output / "result.json").exists()
    assert (task_output / "trace.json").exists()
    assert (task_output / "final.diff").exists()
    assert (task_output / "test_output.txt").exists()
    assert (task_output / "runner.log").exists()

    result = json.loads((task_output / "result.json").read_text())
    assert result["status"] == "passed"
    assert result["edit_count"] == 1

    trace = json.loads((task_output / "trace.json").read_text())
    step_types = [step["type"] for step in trace["steps"]]
    assert "tool_call" in step_types
    assert "edit" in step_types
    assert "diff" in step_types
    assert "test" in step_types

    final_diff = (task_output / "final.diff").read_text()
    assert "Version 2" in final_diff
    assert "benchmarks/tasks" not in final_diff


@pytest.mark.asyncio
async def test_benchmark_runner_reports_passed_with_warnings(repo, tmp_path):
    base_commit = _git_out(repo, "rev-parse", "HEAD")
    task_dir = _task_dir(
        tmp_path,
        base_commit=base_commit,
        test_command="grep -q 'Version 2' app.py",
    )
    runner = BenchmarkRunner(
        agent_runner=WarningEditRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )

    metadata = await runner.run_all(tmp_path / "tasks", run_id="run-warning")

    assert metadata.passed == 0
    assert metadata.warnings == 1
    assert metadata.failed == 0
    task_output = tmp_path / "runs" / "run-warning" / "tasks" / "task-1"
    result = json.loads((task_output / "result.json").read_text())
    assert result["status"] == "passed_with_warnings"
    assert result["failure_category"] == "max_iterations"

    summary = (tmp_path / "runs" / "run-warning" / "summary.md").read_text()
    assert "| task-1 | passed_with_warnings |" in summary


@pytest.mark.asyncio
async def test_benchmark_runner_writes_failure_artifacts_on_bad_test_patch(repo, tmp_path):
    base_commit = _git_out(repo, "rev-parse", "HEAD")
    task_dir = _task_dir(
        tmp_path,
        base_commit=base_commit,
        test_command="true",
        test_patch="this is not a patch\n",
    )
    runner = BenchmarkRunner(
        agent_runner=FakeAgentRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )

    result = await runner.run_task(task_dir, run_dir=tmp_path / "runs" / "run-2")

    task_output = tmp_path / "runs" / "run-2" / "tasks" / "task-1"
    assert result.status == "error"
    assert result.failure_category == "setup_error"
    assert (task_output / "result.json").exists()
    assert (task_output / "trace.json").exists()
    assert (task_output / "runner.log").exists()


def _task_dir(
    tmp_path: Path,
    base_commit: str,
    test_command: str,
    test_patch: str | None = None,
) -> Path:
    root = tmp_path / "tasks" / "task-1"
    root.mkdir(parents=True)
    (root / "issue.md").write_text("Update app.py to Version 2.\n")
    task = {
        "id": "task-1",
        "repo": "local",
        "base_commit": base_commit,
        "problem_statement_file": "issue.md",
        "test_command": test_command,
        "timeout_seconds": 30,
        "gold_patch_file": "gold.patch",
        "test_patch_file": "test.patch" if test_patch is not None else None,
    }
    (root / "task.json").write_text(json.dumps(task))
    (root / "gold.patch").write_text("gold reference\n")
    if test_patch is not None:
        (root / "test.patch").write_text(test_patch)
    return root


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
