"""Tests for runner edge cases discovered during SWE-bench integration."""

import json
import subprocess
from pathlib import Path

import pytest

from benchmarks.runner import BenchmarkRunner
from benchmarks.task_schema import LoadedTask, TaskSpec


class TestRunTestCommand:
    """Test the _run_test_command method's venv Python replacement."""

    def test_venv_python_replacement(self, tmp_path):
        workspace = tmp_path / "repo"
        workspace.mkdir()
        venv_bin = workspace / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").touch()

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        exit_code, output, _ = runner._run_test_command(
            "python -m pytest tests/test_x.py::test_foo --tb=short -p no:warnings",
            workspace,
            timeout_seconds=5,
            is_external=True,
        )
        assert str(venv_bin / "python") in output

    def test_no_venv_falls_back(self, tmp_path):
        workspace = tmp_path / "repo2"
        workspace.mkdir()
        # No .venv — should not crash
        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        exit_code, output, _ = runner._run_test_command(
            "echo hello",
            workspace,
            timeout_seconds=5,
            is_external=True,
        )
        assert exit_code == 0 or exit_code == 1  # uv may or may not be found


class TestApplyTestPatch:
    """Verify the apply_test_patch flow doesn't lose agent edits."""

    def test_existing_test_roots_skips_missing_testing_dir(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        (repo / "tests").mkdir()
        (repo / "tests" / "test_x.py").write_text("def test_ok():\n    pass\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True)

        runner = BenchmarkRunner.__new__(BenchmarkRunner)

        assert runner._existing_test_roots(repo) == ["tests"]

    def test_source_patch_survives_git_clean(self, tmp_path):
        # Setup: create a git repo with a file
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test"], cwd=repo, check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=repo, check=True
        )
        source_file = repo / "src.py"
        source_file.write_text("original\n")
        subprocess.run(["git", "add", "src.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True)

        test_file = repo / "tests" / "test_x.py"
        test_file.parent.mkdir()
        test_file.write_text("# original test\n")
        subprocess.run(["git", "add", "tests/test_x.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "add test"], cwd=repo, check=True)

        # Simulate agent edit
        source_file.write_text("modified by agent\n")
        # Create test.patch
        test_patch = repo / "test.patch"
        test_patch.write_text(
            "diff --git a/tests/test_x.py b/tests/test_x.py\n"
            "--- a/tests/test_x.py\n"
            "+++ b/tests/test_x.py\n"
            "@@ -1 +1,2 @@\n"
            " # original test\n"
            "+# new assertion\n"
        )

        task_output = tmp_path / "output"
        task_output.mkdir()

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._apply_test_patch(repo, test_patch, task_output)

        # After the flow, the agent edit should still be present
        assert source_file.read_text() == "modified by agent\n"
        # And the test.patch should be applied
        assert "# new assertion" in test_file.read_text()
