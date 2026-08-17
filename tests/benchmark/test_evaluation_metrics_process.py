"""Tests for the evaluation-metrics (C2) process-efficiency and SWE-bench versions.

Covers process_efficiency (D10: time-to-first-successful-edit +
exploration fraction) and the SWE-bench pollution-disclosure data layer
(D11: dataset / package versions into run metadata).
"""
from __future__ import annotations

import pytest

from pathlib import Path

from benchmarks.statistics import process_efficiency, swebench_versions
from benchmarks.task_schema import LoadedTask, TaskSpec


def _event(event_type: str, ts: float, **data) -> dict:
    return {"type": event_type, "timestamp": ts, "data": data}


def _loaded_swebench_task(version: str | None = None) -> LoadedTask:
    task = TaskSpec(
        id="swebench-psf__requests-1142",
        repo="psf/requests",
        base_commit="abc",
        problem_statement_file="issue.md",
        test_command="pytest",
        timeout_seconds=600,
        task_family="swebench",
        execution_environment="docker",
        instance_id="psf__requests-1142",
        dataset_name="princeton-nlp/SWE-bench_Verified",
        dataset_split="test",
        version=version,
    )
    return LoadedTask(
        task=task,
        task_dir=Path("/nonexistent"),
        problem_statement="fix",
    )


# ---------------------------------------------------------------------------
# process_efficiency
# ---------------------------------------------------------------------------

def test_process_efficiency_successful_edit_and_exploration() -> None:
    events = [
        _event("run_started", 100.0),
        _event("tool_call", 101.0, tool_name="Grep"),
        _event("tool_result", 102.0, tool_name="Grep"),
        _event("tool_call", 103.0, tool_name="Edit"),
        _event("tool_result", 104.0, tool_name="Edit"),
        _event("edit", 104.5, tool_name="Edit", path="app.py", status="ok"),
    ]
    result = process_efficiency(events)
    # first successful edit at 104.5 - run start 100.0
    assert result["time_to_first_successful_edit"] == pytest.approx(4.5)
    # exploration: (Grep 1s + Edit 1s total, Edit excluded) -> 1/2
    assert result["exploration_fraction"] == pytest.approx(0.5)


def test_process_efficiency_no_successful_edit() -> None:
    events = [
        _event("run_started", 100.0),
        _event("edit", 105.0, tool_name="Edit", path="app.py", status="error"),
    ]
    result = process_efficiency(events)
    assert result["time_to_first_successful_edit"] is None
    assert result["exploration_fraction"] == pytest.approx(0.0)


def test_process_efficiency_no_tool_calls_exploration_zero() -> None:
    events = [_event("run_started", 100.0), _event("edit", 101.0, path="x", status="ok")]
    result = process_efficiency(events)
    assert result["time_to_first_successful_edit"] == pytest.approx(1.0)
    assert result["exploration_fraction"] == pytest.approx(0.0)


def test_process_efficiency_empty_trace() -> None:
    result = process_efficiency([])
    assert result["time_to_first_successful_edit"] is None
    assert result["exploration_fraction"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# swebench_versions
# ---------------------------------------------------------------------------

def test_swebench_versions_from_task_and_package(monkeypatch) -> None:
    loaded = [
        _loaded_swebench_task(version="v1.0"),
        _loaded_swebench_task(version="ignored"),
    ]
    monkeypatch.setattr(
        "importlib.metadata.version", lambda name: "1.0.10" if name == "swebench" else "?"
    )
    dataset_version, package_version = swebench_versions(loaded)
    assert dataset_version == "v1.0"
    assert package_version == "1.0.10"


def test_swebench_versions_no_swebench_tasks() -> None:
    local_task = TaskSpec(
        id="local-1",
        repo="local",
        base_commit="abc",
        problem_statement_file="issue.md",
        test_command="grep x",
        timeout_seconds=30,
        task_family="local",
        execution_environment="local",
    )
    loaded = [
        LoadedTask(task=local_task, task_dir=Path("/nonexistent"), problem_statement="fix")
    ]
    dataset_version, package_version = swebench_versions(loaded)
    assert dataset_version is None
    assert package_version is None


def test_swebench_versions_package_missing(monkeypatch) -> None:
    loaded = [_loaded_swebench_task(version="v2")]
    def _raise(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.metadata.version", _raise)
    dataset_version, package_version = swebench_versions(loaded)
    assert dataset_version == "v2"
    assert package_version is None
