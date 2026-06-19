import asyncio
import json
import subprocess
import time
from pathlib import Path

import pytest

from benchmarks.agent_runner import AgentRunner
from benchmarks.models import AgentRunResult
from benchmarks.runner import BenchmarkRunner, _now
from benchmarks.task_schema import LoadedTask, TaskSpec


class TimestampRecorder:
    """Records start timestamps to verify parallel vs serial execution."""
    def __init__(self):
        self.starts: list[float] = []

    def record(self):
        self.starts.append(time.time())


class DelayedRunner(AgentRunner):
    """Runner that sleeps then records its start time for concurrency checks."""
    def __init__(self, delay: float = 0.3, recorder: TimestampRecorder | None = None):
        self.delay = delay
        self.recorder = recorder

    async def run(self, task, problem_statement, workspace, output_dir, trace):
        if self.recorder:
            self.recorder.record()
        await asyncio.sleep(self.delay)
        return AgentRunResult(status="completed", iterations=1, tool_calls=1)


class FailingRunner(AgentRunner):
    """Runner that raises an exception."""
    def __init__(self, fail_on_task_ids: set[str] | None = None):
        self.fail_on_task_ids = fail_on_task_ids or set()

    async def run(self, task, problem_statement, workspace, output_dir, trace):
        if task.id in self.fail_on_task_ids:
            raise RuntimeError(f"Intentional failure for {task.id}")
        return AgentRunResult(status="completed", iterations=1, tool_calls=1)


# ---- Helpers ----

def _task_dir(tmp_path: Path, task_id: str, repo_path: Path) -> Path:
    base_commit = _git_out(repo_path, "rev-parse", "HEAD")
    root = tmp_path / "tasks" / task_id
    root.mkdir(parents=True)
    (root / "issue.md").write_text(f"Issue for {task_id}\n")
    task_data = {
        "id": task_id,
        "repo": "local",
        "base_commit": base_commit,
        "problem_statement_file": "issue.md",
        "test_command": "true",
        "timeout_seconds": 30,
    }
    (root / "task.json").write_text(json.dumps(task_data))
    return root


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init")
    _git(r, "config", "user.email", "bench@example.com")
    _git(r, "config", "user.name", "Bench")
    (r / "app.py").write_text("# Version 1\n")
    _git(r, "add", ".")
    _git(r, "commit", "-m", "init")
    return r


# ---- Tests ----

@pytest.mark.asyncio
async def test_serial_execution_default(repo, tmp_path):
    """With default MYAGENT_BENCHMARK_PARALLEL=1, tasks run sequentially."""
    recorder = TimestampRecorder()
    runner = BenchmarkRunner(
        agent_runner=DelayedRunner(delay=0.2, recorder=recorder),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )
    for i in range(3):
        _task_dir(tmp_path, f"task-{i}", repo)

    t0 = time.time()
    metadata = await runner.run_all(tmp_path / "tasks", run_id="serial")
    elapsed = time.time() - t0

    assert metadata.task_count == 3
    assert metadata.passed == 3
    # Sequential: each sleeps 0.2s, total >= 0.6s
    assert elapsed >= 0.55, f"Expected sequential (>=0.55s), got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_parallel_execution(repo, tmp_path, monkeypatch):
    """With MYAGENT_BENCHMARK_PARALLEL=3, tasks run concurrently."""
    monkeypatch.setenv("MYAGENT_BENCHMARK_PARALLEL", "3")
    recorder = TimestampRecorder()
    runner = BenchmarkRunner(
        agent_runner=DelayedRunner(delay=0.3, recorder=recorder),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )
    for i in range(3):
        _task_dir(tmp_path, f"task-{i}", repo)

    t0 = time.time()
    metadata = await runner.run_all(tmp_path / "tasks", run_id="parallel-3")
    elapsed = time.time() - t0

    assert metadata.task_count == 3
    assert metadata.passed == 3
    # Parallel: all sleep 0.3s concurrently, total < 0.8s
    assert elapsed < 0.8, f"Expected parallel (<0.8s), got {elapsed:.2f}s"
    # Start times should be clustered
    starts = recorder.starts
    assert max(starts) - min(starts) < 0.15, f"Starts not clustered: {starts}"


@pytest.mark.asyncio
async def test_semaphore_gating(repo, tmp_path, monkeypatch):
    """With semaphore=1, tasks execute sequentially even in async context."""
    monkeypatch.setenv("MYAGENT_BENCHMARK_PARALLEL", "1")
    recorder = TimestampRecorder()
    runner = BenchmarkRunner(
        agent_runner=DelayedRunner(delay=0.15, recorder=recorder),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )
    for i in range(3):
        _task_dir(tmp_path, f"task-{i}", repo)

    metadata = await runner.run_all(tmp_path / "tasks", run_id="gated")
    assert metadata.task_count == 3
    assert metadata.passed == 3
    # Sequential: total >= 0.45s
    if len(recorder.starts) >= 2:
        spread = max(recorder.starts) - min(recorder.starts)
        assert spread >= 0.25, f"Expected sequential spread, got {spread:.2f}s"


@pytest.mark.asyncio
async def test_exception_isolation(repo, tmp_path):
    """One failing task does not prevent other tasks from completing."""
    runner = BenchmarkRunner(
        agent_runner=FailingRunner(fail_on_task_ids={"task-1"}),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )
    for i in range(3):
        _task_dir(tmp_path, f"task-{i}", repo)

    metadata = await runner.run_all(tmp_path / "tasks", run_id="isolation")
    assert metadata.task_count == 3
    assert metadata.passed == 2
    assert metadata.failed == 1

    # Verify all 3 task output dirs exist
    run_dir = tmp_path / "runs" / "isolation"
    for i in range(3):
        assert (run_dir / "tasks" / f"task-{i}" / "result.json").exists()


@pytest.mark.asyncio
async def test_run_artifacts_complete(repo, tmp_path):
    """All expected output files are written for each task."""
    runner = BenchmarkRunner(
        agent_runner=DelayedRunner(delay=0.05),
        source_repo=repo,
        runs_dir=tmp_path / "runs",
    )
    for i in range(3):
        _task_dir(tmp_path, f"task-{i}", repo)

    metadata = await runner.run_all(tmp_path / "tasks", run_id="artifacts")
    assert metadata.task_count == 3
    assert (tmp_path / "runs" / "artifacts" / "run.json").exists()
    assert (tmp_path / "runs" / "artifacts" / "summary.md").exists()

    for i in range(3):
        task_output = tmp_path / "runs" / "artifacts" / "tasks" / f"task-{i}"
        assert (task_output / "result.json").exists()
        assert (task_output / "trace.json").exists()
        assert (task_output / "runner.log").exists()


# ---- Clone cache prefill tests ----

class _FakeLoadedTask:
    def __init__(self, external_repo: str | None):
        self.task = _FakeTask(external_repo)


class _FakeTask:
    def __init__(self, external_repo: str | None):
        self.external_repo = external_repo


def test_prefill_clone_cache_noop_without_cache_dir(tmp_path):
    """_prefill_clone_cache is a no-op when clone_cache_dir is None."""
    runner = BenchmarkRunner(
        agent_runner=DelayedRunner(),
        source_repo=tmp_path,
        runs_dir=tmp_path / "runs",
        clone_cache_dir=None,
    )
    loaded = [_FakeLoadedTask("https://example.com/repo.git")]
    # Should not raise
    runner._prefill_clone_cache(loaded)


def test_prefill_clone_cache_skips_existing(tmp_path):
    """_prefill_clone_cache skips repos that already exist in cache."""
    cache_dir = tmp_path / "cache"
    repo_bare = cache_dir / "repo_bare"
    repo_bare.mkdir(parents=True)
    (repo_bare / "HEAD").write_text("ref: refs/heads/main\n")
    # Initialize as a valid bare repo so git clone --bare would fail if called
    subprocess.run(["git", "init", "--bare", str(repo_bare)], check=True, capture_output=True)

    runner = BenchmarkRunner(
        agent_runner=DelayedRunner(),
        source_repo=tmp_path,
        runs_dir=tmp_path / "runs",
        clone_cache_dir=cache_dir,
    )
    loaded = [_FakeLoadedTask("https://example.com/repo.git")]
    runner._prefill_clone_cache(loaded)

    # The file we wrote should still be there (no clone overwrote it)
    assert (repo_bare / "HEAD").exists()


def test_prefill_clone_cache_dedup_same_repo(tmp_path):
    """Multiple tasks referencing the same repo only trigger one clone."""
    cache_dir = tmp_path / "cache"
    repo_bare = cache_dir / "repo_bare"
    repo_bare.mkdir(parents=True)
    subprocess.run(["git", "init", "--bare", str(repo_bare)], check=True, capture_output=True)

    runner = BenchmarkRunner(
        agent_runner=DelayedRunner(),
        source_repo=tmp_path,
        runs_dir=tmp_path / "runs",
        clone_cache_dir=cache_dir,
    )
    loaded = [
        _FakeLoadedTask("https://example.com/repo.git"),
        _FakeLoadedTask("https://example.com/repo.git"),
    ]
    # Should not raise — duplicate is skipped
    runner._prefill_clone_cache(loaded)
