"""Tests for the evaluation-metrics (C2) data model extensions.

Covers the optional new fields on TaskResult / RunMetadata and the
backward-compatibility guarantees: old artifacts keep parsing, unknown keys are
ignored, None values are omitted from serialized output.
"""
from __future__ import annotations

import json

from benchmarks.models import RunMetadata, TaskResult


# ---------------------------------------------------------------------------
# TaskResult new optional fields
# ---------------------------------------------------------------------------

def test_task_result_new_fields_default_to_none() -> None:
    result = TaskResult(task_id="t1", agent="fake")
    assert result.cache_read_tokens is None
    assert result.cache_write_tokens is None
    assert result.temperature is None
    assert result.seed is None
    assert result.fault_owner is None
    assert result.partial is None


def test_task_result_to_dict_omits_none_new_fields() -> None:
    result = TaskResult(
        task_id="t1",
        agent="fake",
        cache_read_tokens=80_000,
        cache_write_tokens=10_000,
        temperature=0.2,
        seed=1,
        fault_owner="task",
        partial={"f2p_rate": 0.8, "p2p_rate": 0.5, "reward": 0.3},
    )
    data = result.to_dict()
    assert data["cache_read_tokens"] == 80_000
    assert data["cache_write_tokens"] == 10_000
    assert data["temperature"] == 0.2
    assert data["seed"] == 1
    assert data["fault_owner"] == "task"
    assert data["partial"] == {"f2p_rate": 0.8, "p2p_rate": 0.5, "reward": 0.3}

    result_none = TaskResult(task_id="t1", agent="fake")
    for key in (
        "cache_read_tokens",
        "cache_write_tokens",
        "temperature",
        "seed",
        "fault_owner",
        "partial",
    ):
        assert key not in result_none.to_dict()


def test_task_result_from_dict_reads_new_fields() -> None:
    parsed = TaskResult.from_dict(
        {
            "task_id": "t1",
            "agent": "fake",
            "cache_read_tokens": 50,
            "cache_write_tokens": 20,
            "temperature": 0.1,
            "seed": 2,
            "fault_owner": "environment",
            "partial": {"f2p_rate": 0.1},
        }
    )
    assert parsed.cache_read_tokens == 50
    assert parsed.cache_write_tokens == 20
    assert parsed.temperature == 0.1
    assert parsed.seed == 2
    assert parsed.fault_owner == "environment"
    assert parsed.partial == {"f2p_rate": 0.1}


def test_task_result_from_dict_old_artifact_still_parses() -> None:
    """An old result.json without any new field must parse without error."""
    old_artifact = {
        "task_id": "asterwynd-001",
        "agent": "fake",
        "model": "fake-model",
        "mode": "build",
        "status": "failed",
        "reason": "test_failure",
        "input_tokens": 100,
        "output_tokens": 50,
        "category": "tool-usage",
        "task_family": "local",
        "run_round": 0,
    }
    parsed = TaskResult.from_dict(old_artifact)
    assert parsed.task_id == "asterwynd-001"
    assert parsed.status == "failed"
    assert parsed.cache_read_tokens is None
    assert parsed.fault_owner is None


def test_task_result_new_fields_round_trip() -> None:
    result = TaskResult(
        task_id="t1",
        agent="fake",
        status="passed",
        temperature=0.2,
        seed=0,
        cache_read_tokens=1,
        cache_write_tokens=2,
    )
    data = json.loads(json.dumps(result.to_dict()))
    assert TaskResult.from_dict(data) == result


# ---------------------------------------------------------------------------
# RunMetadata new optional fields
# ---------------------------------------------------------------------------

def test_run_metadata_new_fields_default_to_none() -> None:
    meta = RunMetadata(run_id="r1", agent="fake")
    for field in (
        "task_set_hash",
        "max_iterations",
        "timeout_seconds",
        "network",
        "adapter_version",
        "prompt_version",
        "pricing_table_version",
        "temperature",
        "seed",
        "model_version",
        "swebench_dataset_version",
        "swebench_package_version",
    ):
        assert getattr(meta, field) is None


def test_run_metadata_to_dict_omits_none_new_fields_keeps_existing() -> None:
    meta = RunMetadata(
        run_id="r1",
        agent="fake",
        model="claude-sonnet-5",
        mode="build",
        task_count=3,
        temperature=0.2,
        seed=1,
        model_version="v-20260817",
    )
    data = meta.to_dict()
    # existing fields keep their values
    assert data["run_id"] == "r1"
    assert data["mode"] == "build"
    assert data["task_count"] == 3
    # new fields with values are present
    assert data["temperature"] == 0.2
    assert data["seed"] == 1
    assert data["model_version"] == "v-20260817"
    # None new fields omitted
    for key in ("task_set_hash", "network", "adapter_version", "prompt_version"):
        assert key not in data


def test_run_metadata_to_dict_old_shape_unchanged() -> None:
    """A run.json written with only the legacy fields keeps its exact shape."""
    meta = RunMetadata(
        run_id="r1",
        agent="fake",
        model="fake",
        mode="build",
        started_at="2026-01-01",
        ended_at="2026-01-01",
        task_count=2,
        passed=1,
        warnings=0,
        failed=1,
        unsupported=0,
    )
    assert meta.to_dict() == {
        "run_id": "r1",
        "agent": "fake",
        "model": "fake",
        "mode": "build",
        "started_at": "2026-01-01",
        "ended_at": "2026-01-01",
        "task_count": 2,
        "passed": 1,
        "warnings": 0,
        "failed": 1,
        "unsupported": 0,
    }


def test_run_metadata_from_dict_round_trip_and_old_artifact() -> None:
    meta = RunMetadata(
        run_id="r1",
        agent="fake",
        model="claude-sonnet-5",
        task_count=2,
        temperature=0.2,
        seed=1,
        model_version="v1",
        swebench_dataset_version="SWE-bench_Verified@test",
    )
    data = json.loads(json.dumps(meta.to_dict()))
    assert RunMetadata.from_dict(data) == meta

    # old run.json without new fields parses without error
    old = {
        "run_id": "old",
        "agent": "fake",
        "model": "fake",
        "mode": "build",
        "task_count": 1,
        "passed": 1,
        "failed": 0,
        "some_future_key": "ignored",
    }
    parsed = RunMetadata.from_dict(old)
    assert parsed.run_id == "old"
    assert parsed.temperature is None
    assert parsed.seed is None
    assert not hasattr(parsed, "some_future_key")
