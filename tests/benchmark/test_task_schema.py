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


def _base_task_dict(**overrides):
    data = {
        "id": "task-1",
        "repo": "local",
        "base_commit": "abc",
        "problem_statement_file": "issue.md",
        "test_command": "pytest",
    }
    data.update(overrides)
    return data


def test_task_spec_accepts_all_scenario_enum_values():
    for scenario in ("bug-fix", "feature-dev", "refactor", "debug", "integration"):
        task = TaskSpec.from_dict(_base_task_dict(scenario=scenario))
        assert task.scenario == scenario


def test_task_spec_rejects_invalid_scenario_value():
    with pytest.raises(ValueError, match="scenario"):
        TaskSpec.from_dict(_base_task_dict(scenario="bugfix"))


def test_task_spec_defaults_scenario_to_none_for_backward_compat():
    task = TaskSpec.from_dict(_base_task_dict())
    assert task.scenario is None
    # 未标注场景的任务不得因缺少标签而加载失败
    assert task.difficulty is None


def test_task_spec_accepts_normalized_difficulty_values():
    for difficulty in ("easy", "medium", "hard"):
        task = TaskSpec.from_dict(_base_task_dict(difficulty=difficulty))
        assert task.difficulty == difficulty


def test_task_spec_rejects_unnormalized_difficulty():
    with pytest.raises(ValueError, match="difficulty"):
        TaskSpec.from_dict(_base_task_dict(difficulty="<15 min fix"))
    with pytest.raises(ValueError, match="difficulty"):
        TaskSpec.from_dict(_base_task_dict(difficulty="trivial"))


def test_task_spec_accepts_track_enum_values():
    for track in ("A", "B", "verified"):
        task = TaskSpec.from_dict(_base_task_dict(track=track))
        assert task.track == track


def test_task_spec_rejects_invalid_track_value():
    with pytest.raises(ValueError, match="track"):
        TaskSpec.from_dict(_base_task_dict(track="C"))


def test_task_spec_defaults_track_to_none_for_backward_compat():
    task = TaskSpec.from_dict(_base_task_dict())
    assert task.track is None


def test_legacy_task_json_without_new_fields_loads():
    """旧任务 JSON 不携带 scenario/difficulty/track 时应保持向后兼容加载。"""
    task = TaskSpec.from_dict(_base_task_dict())
    assert task.scenario is None
    assert task.difficulty is None
    assert task.track is None


def test_swebench_task_allows_local_verification_without_instance_metadata():
    """D6 L1 分级：swebench 任务可走本地 test_command 验证（免 Docker），
    不需要 instance_id/dataset 元数据。"""
    task = TaskSpec.from_dict(
        _base_task_dict(
            id="swebench-psf__requests-1142",
            task_family="swebench",
            execution_environment="local",
            external_repo="https://github.com/psf/requests.git",
            track="verified",
            scenario="bug-fix",
            difficulty="easy",
        )
    )
    assert task.execution_environment == "local"
    assert task.instance_id is None


def test_swebench_task_rejects_invalid_execution_environment():
    with pytest.raises(ValueError, match="execution_environment"):
        TaskSpec.from_dict(
            _base_task_dict(
                id="swebench-x",
                task_family="swebench",
                execution_environment="vm",
            )
        )
