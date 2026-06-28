import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.agent_runner import AgentRunner, FakeAgentRunner
from benchmarks.models import AgentRunResult
from benchmarks.runner import BenchmarkRunner, DockerPreflightResult


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
            reason="max_iterations",
        )


class PlanningTraceRunner(AgentRunner):
    async def run(self, task, problem_statement, workspace, output_dir, trace):
        trace.record_planning_state({
            "items": [
                {
                    "id": "item-1",
                    "content": "Update app.py",
                    "status": "completed",
                    "note": None,
                }
            ],
            "summary": {
                "total": 1,
                "pending": 0,
                "in_progress": 0,
                "completed": 1,
                "failed": 0,
                "skipped": 0,
                "current_item": None,
            },
        })
        target = workspace / "app.py"
        target.write_text(target.read_text().replace("Version 1", "Version 2"))
        return AgentRunResult(
            status="completed",
            iterations=1,
            tool_calls=0,
            edit_count=1,
        )


class CompleteEditRunner(AgentRunner):
    async def run(self, task, problem_statement, workspace, output_dir, trace):
        target = workspace / "app.py"
        target.write_text(target.read_text().replace("Version 1", "Version 2"))
        trace.record_edit("app.py", "ok", "Version 1 -> Version 2")
        return AgentRunResult(
            status="completed",
            iterations=1,
            tool_calls=1,
            edit_count=1,
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
    assert metadata.unsupported == 0
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
    assert result["mode"] == "build"
    assert result["agent_run_id"]
    assert "planning_summary" not in result

    trace = json.loads((task_output / "trace.json").read_text())
    assert trace["mode"] == "build"
    assert trace["run_id"] == result["agent_run_id"]
    step_types = [step["type"] for step in trace["steps"]]
    assert "tool_call" in step_types
    assert "edit" in step_types
    assert "diff" in step_types
    assert "test" in step_types

    final_diff = (task_output / "final.diff").read_text()
    assert "Version 2" in final_diff
    assert "benchmarks/tasks" not in final_diff

    run = json.loads((run_dir / "run.json").read_text())
    assert run["mode"] == "build"
    assert run["run_id"] == "run-1"


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
    assert metadata.unsupported == 0
    task_output = tmp_path / "runs" / "run-warning" / "tasks" / "task-1"
    result = json.loads((task_output / "result.json").read_text())
    assert result["status"] == "passed_with_warnings"
    assert result["reason"] == "max_iterations"

    summary = (tmp_path / "runs" / "run-warning" / "summary.md").read_text()
    assert "| task-1 | passed_with_warnings |" in summary


@pytest.mark.asyncio
async def test_benchmark_runner_writes_planning_summary_when_present(repo, tmp_path):
    base_commit = _git_out(repo, "rev-parse", "HEAD")
    task_dir = _task_dir(
        tmp_path,
        base_commit=base_commit,
        test_command="grep -q 'Version 2' app.py",
    )
    runner = BenchmarkRunner(
        agent_runner=PlanningTraceRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )

    await runner.run_task(task_dir, run_dir=tmp_path / "runs" / "run-planning")

    task_output = tmp_path / "runs" / "run-planning" / "tasks" / "task-1"
    result = json.loads((task_output / "result.json").read_text())
    trace = json.loads((task_output / "trace.json").read_text())

    assert result["planning_summary"]["completed"] == 1
    assert "planning_state_updated" in [
        step["type"] for step in trace["steps"]
    ]


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
    assert result.reason == "setup_error"
    assert (task_output / "result.json").exists()
    assert (task_output / "trace.json").exists()
    assert (task_output / "runner.log").exists()


@pytest.mark.asyncio
async def test_benchmark_runner_marks_docker_tasks_unsupported_when_preflight_fails(
    repo, tmp_path, monkeypatch
):
    base_commit = _git_out(repo, "rev-parse", "HEAD")
    task_dir = _task_dir(
        tmp_path,
        base_commit=base_commit,
        test_command="true",
        task_id="swebench-psf__requests-1142",
        repo_name="psf/requests",
        task_family="swebench",
        execution_environment="docker",
        external_repo="https://example.com/requests.git",
        instance_id="psf__requests-1142",
        dataset_name="princeton-nlp/SWE-bench_Verified",
        dataset_split="test",
    )
    runner = BenchmarkRunner(
        agent_runner=FakeAgentRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )

    monkeypatch.setattr(
        runner,
        "_get_docker_preflight_result",
        lambda: DockerPreflightResult(
            available=False,
            reason="docker_unavailable",
            detail="Cannot connect to the Docker daemon",
        ),
    )

    result = await runner.run_task(task_dir, run_dir=tmp_path / "runs" / "run-unsupported")

    task_output = tmp_path / "runs" / "run-unsupported" / "tasks" / "swebench-psf__requests-1142"
    assert result.status == "unsupported"
    assert result.reason == "docker_unavailable"
    assert (task_output / "result.json").exists()
    assert (task_output / "trace.json").exists()
    assert (task_output / "runner.log").exists()
    assert not (task_output / "final.diff").exists()
    assert not (task_output / "test_output.txt").exists()

    trace = json.loads((task_output / "trace.json").read_text())
    assert "benchmark_preflight" in [step["type"] for step in trace["steps"]]
    completion = [step for step in trace["steps"] if step["type"] == "completion"]
    assert completion[-1]["data"]["status"] == "unsupported"


@pytest.mark.asyncio
async def test_benchmark_runner_mixed_local_and_docker_tasks_keep_local_results(
    repo, tmp_path, monkeypatch
):
    base_commit = _git_out(repo, "rev-parse", "HEAD")
    _task_dir(
        tmp_path,
        base_commit=base_commit,
        test_command="grep -q 'Version 2' app.py",
        task_id="asterwynd-001-local",
    )
    _task_dir(
        tmp_path,
        base_commit=base_commit,
        test_command="pytest",
        task_id="swebench-psf__requests-1142",
        repo_name="psf/requests",
        task_family="swebench",
        execution_environment="docker",
        external_repo="https://example.com/requests.git",
        instance_id="psf__requests-1142",
        dataset_name="princeton-nlp/SWE-bench_Verified",
        dataset_split="test",
    )
    runner = BenchmarkRunner(
        agent_runner=AssertHiddenAndEditRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
        parallel=2,
    )

    monkeypatch.setattr(
        runner,
        "_get_docker_preflight_result",
        lambda: DockerPreflightResult(
            available=False,
            reason="docker_unavailable",
            detail="Cannot connect to the Docker daemon",
        ),
    )

    metadata = await runner.run_all(tmp_path / "tasks", run_id="run-mixed")

    assert metadata.passed == 1
    assert metadata.unsupported == 1
    assert metadata.failed == 0

    run_dir = tmp_path / "runs" / "run-mixed" / "tasks"
    local_result = json.loads((run_dir / "asterwynd-001-local" / "result.json").read_text())
    docker_result = json.loads(
        (run_dir / "swebench-psf__requests-1142" / "result.json").read_text()
    )
    assert local_result["status"] == "passed"
    assert docker_result["status"] == "unsupported"


def test_run_swebench_harness_reads_report_and_maps_pass(repo, tmp_path, monkeypatch):
    base_commit = _git_out(repo, "rev-parse", "HEAD")
    task_dir = _task_dir(
        tmp_path,
        base_commit=base_commit,
        test_command="pytest",
        task_id="swebench-psf__requests-1142",
        repo_name="psf/requests",
        task_family="swebench",
        execution_environment="docker",
        external_repo="https://example.com/requests.git",
        instance_id="psf__requests-1142",
        dataset_name="princeton-nlp/SWE-bench_Verified",
        dataset_split="test",
    )
    loaded = _load_task(task_dir)
    runner = BenchmarkRunner(
        agent_runner=FakeAgentRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
        agent_name="asterwynd",
        model="test-model",
    )
    task_output = tmp_path / "runs" / "task-output"
    task_output.mkdir(parents=True)

    calls: list[list[str]] = []

    def fake_run(command, cwd, capture_output, text, timeout):
        calls.append(command)
        run_id = "asterwynd-swebench-psf__requests-1142"
        report_path = (
            task_output
            / "logs"
            / "run_evaluation"
            / run_id
            / "asterwynd:test-model"
            / "psf__requests-1142"
            / "report.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({"psf__requests-1142": {"resolved": True}}))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("benchmarks.runner.subprocess.run", fake_run)

    verification = runner._run_swebench_harness(
        loaded,
        task_output,
        "diff --git a/app.py b/app.py\n",
    )

    assert calls, "expected harness subprocess to run"
    assert verification["status"] == "passed"
    assert verification["reason"] is None
    assert (task_output / "predictions.jsonl").exists()


@pytest.mark.asyncio
async def test_docker_task_persists_harness_output(repo, tmp_path, monkeypatch):
    base_commit = _git_out(repo, "rev-parse", "HEAD")
    task_dir = _task_dir(
        tmp_path,
        base_commit=base_commit,
        test_command="pytest",
        task_id="swebench-psf__requests-1142",
        repo_name="psf/requests",
        task_family="swebench",
        execution_environment="docker",
        external_repo=str(repo),
        instance_id="psf__requests-1142",
        dataset_name="princeton-nlp/SWE-bench_Verified",
        dataset_split="test",
    )
    runner = BenchmarkRunner(
        agent_runner=CompleteEditRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )

    monkeypatch.setattr(
        runner,
        "_get_docker_preflight_result",
        lambda: DockerPreflightResult(available=True, reason="ok", detail="docker info succeeded"),
    )
    monkeypatch.setattr(
        runner,
        "_run_swebench_harness",
        lambda loaded, task_output, patch_text: {
            "status": "error",
            "reason": "docker_runtime_error",
            "detail": "docker stderr: image pull failed",
        },
    )

    result = await runner.run_task(task_dir, run_dir=tmp_path / "runs" / "run-docker-error")

    task_output = tmp_path / "runs" / "run-docker-error" / "tasks" / "swebench-psf__requests-1142"
    assert result.status == "error"
    assert result.reason == "docker_runtime_error"
    assert (task_output / "test_output.txt").read_text() == "docker stderr: image pull failed"
    runner_log = (task_output / "runner.log").read_text()
    assert "SWE-bench verification detail saved to test_output.txt" in runner_log


def test_probe_docker_reports_available(repo, tmp_path, monkeypatch):
    runner = BenchmarkRunner(
        agent_runner=FakeAgentRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )

    monkeypatch.setattr(
        "benchmarks.runner.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )

    result = runner._probe_docker()

    assert result.available is True
    assert result.reason == "ok"


def test_get_docker_preflight_result_caches_probe(repo, tmp_path, monkeypatch):
    runner = BenchmarkRunner(
        agent_runner=FakeAgentRunner(),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )
    calls = {"count": 0}

    def fake_probe():
        calls["count"] += 1
        return DockerPreflightResult(available=True, reason="ok", detail="cached")

    monkeypatch.setattr(runner, "_probe_docker", fake_probe)

    first = runner._get_docker_preflight_result()
    second = runner._get_docker_preflight_result()

    assert first == second
    assert calls["count"] == 1


def _task_dir(
    tmp_path: Path,
    base_commit: str,
    test_command: str,
    test_patch: str | None = None,
    *,
    task_id: str = "task-1",
    repo_name: str = "local",
    execution_environment: str | None = None,
    task_family: str | None = None,
    external_repo: str | None = None,
    instance_id: str | None = None,
    dataset_name: str | None = None,
    dataset_split: str | None = None,
) -> Path:
    root = tmp_path / "tasks" / task_id
    root.mkdir(parents=True)
    (root / "issue.md").write_text("Update app.py to Version 2.\n")
    task = {
        "id": task_id,
        "repo": repo_name,
        "base_commit": base_commit,
        "problem_statement_file": "issue.md",
        "test_command": test_command,
        "timeout_seconds": 30,
        "gold_patch_file": "gold.patch",
        "test_patch_file": "test.patch" if test_patch is not None else None,
    }
    if execution_environment is not None:
        task["execution_environment"] = execution_environment
    if task_family is not None:
        task["task_family"] = task_family
    if external_repo is not None:
        task["external_repo"] = external_repo
    if instance_id is not None:
        task["instance_id"] = instance_id
    if dataset_name is not None:
        task["dataset_name"] = dataset_name
    if dataset_split is not None:
        task["dataset_split"] = dataset_split
    (root / "task.json").write_text(json.dumps(task))
    (root / "gold.patch").write_text("gold reference\n")
    if test_patch is not None:
        (root / "test.patch").write_text(test_patch)
    return root


def _load_task(task_dir: Path):
    from benchmarks.task_schema import load_task

    return load_task(task_dir)


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
