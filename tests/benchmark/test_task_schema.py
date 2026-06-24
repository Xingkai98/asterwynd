import json

import pytest

from benchmarks.task_schema import TaskSpec, load_task


def test_task_spec_requires_core_fields():
    with pytest.raises(ValueError, match="Missing required"):
        TaskSpec.from_dict({"id": "missing"})


def test_task_spec_rejects_invalid_timeout():
    with pytest.raises(ValueError, match="timeout_seconds"):
        TaskSpec.from_dict(
            {
                "id": "task",
                "repo": "local",
                "base_commit": "abc",
                "problem_statement_file": "issue.md",
                "test_command": "pytest",
                "timeout_seconds": 0,
            }
        )


def test_load_task_resolves_optional_patch_files(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "issue.md").write_text("Fix it\n")
    (task_dir / "gold.patch").write_text("gold\n")
    (task_dir / "test.patch").write_text("test\n")
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "task-1",
                "repo": "local",
                "base_commit": "abc",
                "problem_statement_file": "issue.md",
                "test_command": "pytest",
                "gold_patch_file": "gold.patch",
                "test_patch_file": "test.patch",
            }
        )
    )

    loaded = load_task(task_dir)

    assert loaded.problem_statement == "Fix it\n"
    assert loaded.gold_patch_path == task_dir / "gold.patch"
    assert loaded.test_patch_path == task_dir / "test.patch"


def test_load_task_rejects_escaping_task_file(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "task-1",
                "repo": "local",
                "base_commit": "abc",
                "problem_statement_file": "../issue.md",
                "test_command": "pytest",
            }
        )
    )

    with pytest.raises(ValueError, match="escapes"):
        load_task(task_dir)


def test_task_spec_defaults_execution_environment_to_local():
    task = TaskSpec.from_dict(
        {
            "id": "task-1",
            "repo": "local",
            "base_commit": "abc",
            "problem_statement_file": "issue.md",
            "test_command": "pytest",
        }
    )

    assert task.execution_environment == "local"
    assert task.task_family == "local"
    assert task.instance_id is None
    assert task.dataset_name is None
    assert task.dataset_split is None


def test_task_spec_accepts_swebench_docker_metadata():
    task = TaskSpec.from_dict(
        {
            "id": "swebench-psf__requests-1142",
            "repo": "psf/requests",
            "base_commit": "abc",
            "problem_statement_file": "issue.md",
            "test_command": "pytest",
            "task_family": "swebench",
            "execution_environment": "docker",
            "instance_id": "psf__requests-1142",
            "dataset_name": "princeton-nlp/SWE-bench_Verified",
            "dataset_split": "test",
        }
    )

    assert task.task_family == "swebench"
    assert task.execution_environment == "docker"
    assert task.instance_id == "psf__requests-1142"
    assert task.dataset_name == "princeton-nlp/SWE-bench_Verified"
    assert task.dataset_split == "test"


def test_task_spec_rejects_unknown_execution_environment():
    with pytest.raises(ValueError, match="execution_environment"):
        TaskSpec.from_dict(
            {
                "id": "task-1",
                "repo": "local",
                "base_commit": "abc",
                "problem_statement_file": "issue.md",
                "test_command": "pytest",
                "execution_environment": "vm",
            }
        )


def test_task_spec_requires_swebench_metadata_for_docker_tasks():
    with pytest.raises(ValueError, match="instance_id"):
        TaskSpec.from_dict(
            {
                "id": "swebench-psf__requests-1142",
                "repo": "psf/requests",
                "base_commit": "abc",
                "problem_statement_file": "issue.md",
                "test_command": "pytest",
                "task_family": "swebench",
                "execution_environment": "docker",
                "dataset_name": "princeton-nlp/SWE-bench_Verified",
                "dataset_split": "test",
            }
        )
