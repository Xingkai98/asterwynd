import json

import pytest

from benchmarks.task_set import CAPABILITIES, Manifest
from benchmarks.task_schema import load_task


def _write_task(root, task_id, scenario, track, difficulty="easy", family="local"):
    task_dir = root / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "issue.md").write_text("Do the thing\n")
    data = {
        "id": task_id,
        "repo": "local",
        "base_commit": "abc",
        "problem_statement_file": "issue.md",
        "test_command": "pytest -q",
        "difficulty": difficulty,
        "task_family": family,
        "track": track,
        "scenario": scenario,
    }
    if family == "swebench":
        data.update(
            {
                "execution_environment": "docker",
                "instance_id": task_id,
                "dataset_name": "princeton-nlp/SWE-bench_Verified",
                "dataset_split": "test",
            }
        )
    (task_dir / "task.json").write_text(json.dumps(data))
    return task_id


def _load_all(root):
    return [load_task(d) for d in root.iterdir() if (d / "task.json").exists()]


def _write_manifest(root, coverage, capabilities=None):
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "capabilities": capabilities or list(CAPABILITIES),
                "coverage": coverage,
            }
        )
    )
    return Manifest.load(manifest_path)


def test_manifest_coverage_complete_when_every_column_has_task(tmp_path):
    # 5 场景 × 每能力列至少一条；构造任务覆盖所有能力列
    tasks = {
        "t-bug": "bug-fix",
        "t-feat": "feature-dev",
        "t-ref": "refactor",
        "t-debug": "debug",
        "t-int": "integration",
    }
    for tid, scenario in tasks.items():
        _write_task(tmp_path, tid, scenario, track="A")
    # Q6: 声明的缺口能力列需有 B 轨任务登记——把覆盖这三列的任务标为 B
    for tid, track in (("t-feat", "B"), ("t-debug", "B"), ("t-int", "B")):
        _write_task(tmp_path, tid, tasks[tid], track=track)
    coverage = {tid: ["tool-usage"] for tid in tasks}
    # 补齐其余能力列到不同任务
    coverage["t-bug"].extend(["multi-step-solving", "error-recovery"])
    coverage["t-feat"].append("context-planning")
    coverage["t-ref"].append("safety-boundary")
    coverage["t-debug"].append("long-term-memory")
    coverage["t-int"].append("long-context")

    manifest = _write_manifest(tmp_path, coverage)
    report = manifest.validate_coverage(_load_all(tmp_path))

    assert report.missing_capabilities == []
    assert report.missing_scenarios == []
    assert report.unknown_task_ids == []
    assert report.missing_track_coverage == []
    assert report.is_complete()


def test_manifest_reports_missing_track_coverage(tmp_path):
    """Q6: 能力列只有 A 轨任务时，per-track B 缺口须被报告。"""
    _write_task(tmp_path, "t-feat", "feature-dev", track="A")
    coverage = {"t-feat": ["context-planning", "long-term-memory", "long-context"]}

    manifest = _write_manifest(tmp_path, coverage)
    report = manifest.validate_coverage(_load_all(tmp_path))

    assert report.missing_track_coverage == [
        "context-planning@B",
        "long-context@B",
        "long-term-memory@B",
    ]
    assert not report.is_complete()


def test_manifest_track_coverage_ok_when_b_task_registered(tmp_path):
    """Q6: 补一条 B 轨任务后对应缺口消失，其它缺口仍报告。"""
    _write_task(tmp_path, "t-feat-a", "feature-dev", track="A")
    _write_task(tmp_path, "t-feat-b", "feature-dev", track="B")
    coverage = {
        "t-feat-a": ["context-planning", "long-term-memory", "long-context"],
        "t-feat-b": ["context-planning"],
    }

    manifest = _write_manifest(tmp_path, coverage)
    report = manifest.validate_coverage(_load_all(tmp_path))

    assert report.missing_track_coverage == [
        "long-context@B",
        "long-term-memory@B",
    ]
    # 场景列 feature-dev 已覆盖，无场景缺口
    assert "feature-dev" not in report.missing_scenarios


def test_manifest_reports_missing_capability_column(tmp_path):
    _write_task(tmp_path, "t-bug", "bug-fix", track="A")
    coverage = {"t-bug": ["tool-usage"]}

    manifest = _write_manifest(tmp_path, coverage)
    report = manifest.validate_coverage(_load_all(tmp_path))

    assert report.missing_capabilities == [
        "context-planning",
        "multi-step-solving",
        "error-recovery",
        "safety-boundary",
        "long-term-memory",
        "long-context",
    ]
    assert not report.is_complete()


def test_manifest_reports_missing_scenario_column(tmp_path):
    _write_task(tmp_path, "t-bug", "bug-fix", track="A")
    coverage = {"t-bug": list(CAPABILITIES)}

    manifest = _write_manifest(tmp_path, coverage)
    report = manifest.validate_coverage(_load_all(tmp_path))

    assert report.missing_scenarios == [
        "feature-dev",
        "refactor",
        "debug",
        "integration",
    ]


def test_manifest_ignores_verified_tasks_for_scenario_coverage(tmp_path):
    """OQ-2：Verified 子集全 bug-fix，不得撑满场景列。"""
    _write_task(tmp_path, "v-1", "bug-fix", track="verified", family="swebench")
    # 唯一本地任务也是 bug-fix
    _write_task(tmp_path, "t-bug", "bug-fix", track="A")
    coverage = {"t-bug": list(CAPABILITIES)}

    manifest = _write_manifest(tmp_path, coverage)
    report = manifest.validate_coverage(_load_all(tmp_path))

    # verified 任务不算，本地只有 bug-fix，其余场景列仍缺失
    assert report.missing_scenarios == [
        "feature-dev",
        "refactor",
        "debug",
        "integration",
    ]


def test_manifest_reports_unknown_task_ids(tmp_path):
    _write_task(tmp_path, "t-bug", "bug-fix", track="A")
    coverage = {"t-bug": ["tool-usage"], "ghost-task": ["long-context"]}

    manifest = _write_manifest(tmp_path, coverage)
    report = manifest.validate_coverage(_load_all(tmp_path))

    assert "ghost-task" in report.unknown_task_ids
    # ghost-task 的覆盖不计入能力列（long-context 仍缺失）
    assert "long-context" in report.missing_capabilities


def test_manifest_coverage_from_real_tasks_dir_is_loadable():
    """真实 tasks 目录的 manifest 必须能被加载（结构合法）。"""
    manifest = Manifest.load("benchmarks/tasks/manifest.json")
    assert manifest.version == 1
    assert set(manifest.capabilities) == set(CAPABILITIES)
