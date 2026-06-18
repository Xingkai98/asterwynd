from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.trace_recorder import TraceRecorder
from benchmarks.agent_runner import AgentRunner
from benchmarks.models import (
    FailureCategory,
    RunMetadata,
    TaskResult,
    render_summary,
)
from benchmarks.task_schema import LoadedTask, load_task


@dataclass
class TaskArtifacts:
    result_json: Path
    trace_json: Path
    final_diff: Path
    test_output: Path
    runner_log: Path


class BenchmarkRunner:
    def __init__(
        self,
        agent_runner: AgentRunner,
        source_repo: str | Path,
        runs_dir: str | Path,
        agent_name: str = "myagent",
        model: str = "",
        keep_worktrees: bool = False,
        clone_cache_dir: str | Path | None = None,
    ):
        self.agent_runner = agent_runner
        self.source_repo = Path(source_repo).resolve()
        self.runs_dir = Path(runs_dir).resolve()
        self.agent_name = agent_name
        self.model = model
        self.keep_worktrees = keep_worktrees
        self.clone_cache_dir = (
            Path(clone_cache_dir).resolve() if clone_cache_dir else None
        )

    def run_all(self, tasks_dir: str | Path, run_id: str | None = None) -> RunMetadata:
        task_dirs = sorted(
            path for path in Path(tasks_dir).iterdir()
            if path.is_dir() and (path / "task.json").exists()
        )
        run_id = run_id or _new_run_id()
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        started_at = _now()
        results = [self.run_task(task_dir, run_dir=run_dir) for task_dir in task_dirs]
        ended_at = _now()

        metadata = RunMetadata(
            run_id=run_id,
            agent=self.agent_name,
            model=self.model,
            started_at=started_at,
            ended_at=ended_at,
            task_count=len(results),
            passed=sum(result.status == "passed" for result in results),
            warnings=sum(result.status == "passed_with_warnings" for result in results),
            failed=sum(
                result.status not in {"passed", "passed_with_warnings"}
                for result in results
            ),
        )
        metadata.write_json(run_dir / "run.json")
        (run_dir / "summary.md").write_text(render_summary(results), errors="replace")
        return metadata

    def run_task(
        self,
        task_dir: str | Path,
        run_dir: str | Path | None = None,
    ) -> TaskResult:
        loaded = load_task(task_dir)
        run_dir = Path(run_dir).resolve() if run_dir else self.runs_dir / _new_run_id()
        task_output = run_dir / "tasks" / loaded.task.id
        task_output.mkdir(parents=True, exist_ok=True)
        artifacts = TaskArtifacts(
            result_json=task_output / "result.json",
            trace_json=task_output / "trace.json",
            final_diff=task_output / "final.diff",
            test_output=task_output / "test_output.txt",
            runner_log=task_output / "runner.log",
        )

        log_lines: list[str] = []
        trace = TraceRecorder(task_id=loaded.task.id)
        start = time.time()
        workspace: Path | None = None
        hidden_backup: Path | None = None

        def log(message: str) -> None:
            log_lines.append(f"[{_now()}] {message}")

        result = TaskResult(
            task_id=loaded.task.id,
            agent=self.agent_name,
            model=self.model,
        )

        try:
            log(f"Starting task {loaded.task.id}")
            if loaded.task.external_repo:
                workspace = self._clone_external_repo(loaded, task_output)
                log(f"Cloned external repo to: {workspace}")
                self._install_repo_deps(workspace, log)
            else:
                workspace = self._create_worktree(loaded, task_output)
                log(f"Created worktree: {workspace}")
                hidden_backup = self._hide_agent_invisible_task_files(workspace, task_output)
                if hidden_backup:
                    log("Temporarily hid benchmarks/tasks from agent workspace")

            agent_result = self._run_agent(loaded, workspace, task_output, trace)
            log(f"Agent finished with status={agent_result.status}")

            if hidden_backup:
                self._restore_agent_invisible_task_files(workspace, hidden_backup)
                log("Restored hidden benchmark task files before diff capture")

            self._write_final_diff(workspace, artifacts.final_diff)
            trace.record_diff(
                str(artifacts.final_diff),
                self._git_diff_stat(workspace),
            )
            log(f"Captured final diff: {artifacts.final_diff}")

            if loaded.test_patch_path:
                self._apply_test_patch(workspace, loaded.test_patch_path, task_output)
                log(f"Applied test.patch: {loaded.test_patch_path}")

            test_exit_code, test_output, test_duration_ms = self._run_test_command(
                loaded.task.test_command,
                workspace,
                loaded.task.timeout_seconds,
                is_external=bool(loaded.task.external_repo),
            )
            artifacts.test_output.write_text(test_output, errors="replace")
            trace.record_test(
                loaded.task.test_command,
                test_exit_code,
                test_duration_ms,
                test_output,
            )
            log(f"Test command exit code: {test_exit_code}")

            failure_category = None
            if test_exit_code == 0:
                if agent_result.status != "completed" or agent_result.failure_category:
                    status = "passed_with_warnings"
                    failure_category = (
                        agent_result.failure_category
                        or FailureCategory.MODEL_FAILURE.value
                    )
                else:
                    status = "passed"
            else:
                status = "failed"
                failure_category = (
                    FailureCategory.TEST_TIMEOUT.value
                    if test_exit_code == -1 and "Timeout" in test_output
                    else FailureCategory.TEST_FAILURE.value
                )

            result = TaskResult(
                task_id=loaded.task.id,
                agent=self.agent_name,
                model=self.model,
                status=status,
                test_exit_code=test_exit_code,
                duration_seconds=round(time.time() - start, 1),
                iterations=agent_result.iterations,
                tool_calls=agent_result.tool_calls,
                edit_count=agent_result.edit_count,
                test_runs=1,
                failure_category=failure_category or agent_result.failure_category,
            )
            trace.record_completion(status)
            log(f"Task result: {status}")
        except Exception as exc:
            result.status = "error"
            result.duration_seconds = round(time.time() - start, 1)
            result.failure_category = FailureCategory.SETUP_ERROR.value
            log(f"Error: {type(exc).__name__}: {exc}")
            trace.record_completion("error", f"{type(exc).__name__}: {exc}")
        finally:
            if workspace and hidden_backup and hidden_backup.exists():
                self._restore_agent_invisible_task_files(workspace, hidden_backup)
            if workspace and not self.keep_worktrees:
                if loaded.task.external_repo:
                    self._cleanup_external_repo(workspace)
                else:
                    self._cleanup_worktree(workspace)
                log("Cleaned up workspace")

            result.write_json(artifacts.result_json)
            trace.write_to_file(artifacts.trace_json)
            artifacts.runner_log.write_text("\n".join(log_lines) + "\n", errors="replace")

        return result

    def _create_worktree(self, loaded: LoadedTask, task_output: Path) -> Path:
        worktree = task_output / ".worktree"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), loaded.task.base_commit],
            cwd=self.source_repo,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return worktree

    def _clone_external_repo(self, loaded: LoadedTask, task_output: Path) -> Path:
        """Clone an external repo at the task's base_commit into a temp workspace."""
        repo_dir = task_output / ".external_repo"
        repo_url = loaded.task.external_repo
        commit = loaded.task.base_commit
        repo_key = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

        # Use cached bare clone if available to speed up repeated runs
        if self.clone_cache_dir:
            cache_dir = self.clone_cache_dir / f"{repo_key}_bare"
            if not cache_dir.exists():
                cache_dir.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "clone", "--bare", repo_url, str(cache_dir)],
                    capture_output=True, text=True, timeout=300, check=True,
                )
            subprocess.run(
                ["git", "clone", "--shared", str(cache_dir), str(repo_dir)],
                capture_output=True, text=True, timeout=60, check=True,
            )
        else:
            subprocess.run(
                ["git", "clone", repo_url, str(repo_dir)],
                capture_output=True, text=True, timeout=300, check=True,
            )

        subprocess.run(
            ["git", "checkout", commit],
            cwd=repo_dir, capture_output=True, text=True, timeout=30, check=True,
        )
        return repo_dir

    def _install_repo_deps(self, workspace: Path, log, python_version: str = "3.9") -> None:
        """Install repo dependencies into a local venv with the correct Python version."""
        log(f"Creating Python {python_version} venv and installing repo dependencies...")
        subprocess.run(
            ["uv", "venv", "--python", python_version],
            cwd=workspace, capture_output=True, text=True, timeout=120,
        )
        venv_python = str(workspace / ".venv" / "bin" / "python")
        for install_args in [
            ["uv", "pip", "install", "--python", venv_python,
             "-e", ".[socks]", "pytest", "pytest-httpbin",
             "setuptools", "werkzeug<3.0"],
            ["uv", "pip", "install", "--python", venv_python,
             "-e", ".", "pytest", "pytest-httpbin",
             "setuptools", "werkzeug<3.0"],
        ]:
            proc = subprocess.run(
                install_args,
                cwd=workspace, capture_output=True, text=True, timeout=300,
            )
            if proc.returncode == 0:
                log("Dependencies installed successfully")
                return
            log(f"Install attempt failed: {proc.stderr[:200]}")
        log(f"WARNING: all install attempts failed")

    def _cleanup_external_repo(self, workspace: Path) -> None:
        """Remove the cloned external repo."""
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)

    def _run_agent(
        self,
        loaded: LoadedTask,
        workspace: Path,
        task_output: Path,
        trace: TraceRecorder,
    ):
        import asyncio

        return asyncio.run(
            self.agent_runner.run(
                loaded.task,
                loaded.problem_statement,
                workspace,
                task_output,
                trace,
            )
        )

    def _hide_agent_invisible_task_files(self, worktree: Path, task_output: Path) -> Path | None:
        task_inputs = worktree / "benchmarks" / "tasks"
        if not task_inputs.exists():
            return None
        hidden_parent = task_output / ".hidden"
        hidden_parent.mkdir(exist_ok=True)
        backup = hidden_parent / "benchmarks_tasks"
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(task_inputs), str(backup))
        return backup

    def _restore_agent_invisible_task_files(self, worktree: Path, backup: Path) -> None:
        target = worktree / "benchmarks" / "tasks"
        if target.exists() or not backup.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(backup), str(target))

    def _write_final_diff(self, workspace: Path, output_path: Path) -> None:
        diff = _run_git(["diff"], workspace)
        output_path.write_text((diff or "(no changes)") + "\n", errors="replace")

    def _git_diff_stat(self, workspace: Path) -> str:
        return _run_git(["diff", "--stat"], workspace) or "(no changes)"

    def _apply_test_patch(self, workspace: Path, patch_path: Path, task_output: Path) -> None:
        # SWE-bench pattern: isolate test files from agent modifications.
        # Write the source patch OUTSIDE the workspace so git clean doesn't remove it.
        source_patch = task_output / ".agent_source.patch"
        subprocess.run(
            ["git", "add", "-A"],
            cwd=workspace, timeout=10,
        )
        source_result = subprocess.run(
            ["git", "diff", "--cached", "--", ":!tests/", ":!testing/"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if source_result.stdout.strip():
            source_patch.write_text(source_result.stdout)
            subprocess.run(
                ["git", "reset", "--hard", "HEAD"],
                cwd=workspace, timeout=10,
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=workspace, timeout=10,
            )
            apply_result = subprocess.run(
                ["git", "apply", str(source_patch)],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if apply_result.returncode != 0:
                raise RuntimeError(
                    f"Failed to re-apply agent source patch: "
                    f"{apply_result.stderr.strip() or apply_result.stdout.strip()}"
                )
        else:
            subprocess.run(
                ["git", "checkout", "HEAD", "--", "tests/", "testing/"],
                cwd=workspace, timeout=10,
            )
            subprocess.run(
                ["git", "clean", "-fd", "--", "tests/", "testing/"],
                cwd=workspace, timeout=10,
            )

        try:
            source_patch.unlink(missing_ok=True)
        except Exception:
            pass

        patch = subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if patch.returncode != 0:
            raise RuntimeError(
                f"Failed to apply test patch {patch_path}: "
                f"{patch.stderr.strip() or patch.stdout.strip()}"
            )

    def _run_test_command(
        self,
        command: str,
        workspace: Path,
        timeout_seconds: int,
        is_external: bool = False,
    ) -> tuple[int, str, float]:
        if is_external:
            venv_python = workspace / ".venv" / "bin" / "python"
            if venv_python.exists():
                command = command.replace(
                    "python -m pytest", f"{venv_python} -m pytest"
                )
        start = time.time()
        try:
            proc = subprocess.run(
                command,
                cwd=workspace,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            output = f"$ {command}\n\n{proc.stdout}{proc.stderr}\n[Exit code: {proc.returncode}]"
            return proc.returncode, output, (time.time() - start) * 1000
        except subprocess.TimeoutExpired as exc:
            output = f"$ {command}\n\n{exc.stdout or ''}{exc.stderr or ''}\n[Timeout after {timeout_seconds}s]"
            return -1, output, (time.time() - start) * 1000

    def _cleanup_worktree(self, worktree: Path) -> None:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            cwd=self.source_repo,
            capture_output=True,
            timeout=30,
        )
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)


def _run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return proc.stdout.strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
