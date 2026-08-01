"""Tests for the evaluation-depth additions to benchmarks/models.py.

Covers the TaskResult.from_dict round-trip and the module-level LAYERS /
resolve_layer helpers used by the evaluation report pipeline.
"""
from __future__ import annotations

import json

from benchmarks.models import LAYERS, TaskResult, resolve_layer


# ---------------------------------------------------------------------------
# TaskResult.from_dict
# ---------------------------------------------------------------------------

def test_from_dict_round_trip() -> None:
    result = TaskResult(
        task_id="asterwynd-001-hello",
        agent="fake",
        model="fake-model",
        mode="build",
        status="passed",
        duration_seconds=3.5,
        iterations=2,
        input_tokens=100,
        output_tokens=50,
        category="tool-usage",
        task_family="local",
    )
    data = json.loads(json.dumps(result.to_dict()))
    parsed = TaskResult.from_dict(data)
    assert parsed == result


def test_from_dict_missing_optional_fields_use_defaults() -> None:
    parsed = TaskResult.from_dict(
        {"task_id": "t1", "agent": "fake", "status": "failed"}
    )
    assert parsed.task_id == "t1"
    assert parsed.agent == "fake"
    assert parsed.status == "failed"
    assert parsed.category is None
    assert parsed.task_family is None
    assert parsed.duration_seconds == 0.0
    assert parsed.reason is None


def test_from_dict_ignores_unknown_keys() -> None:
    parsed = TaskResult.from_dict(
        {
            "task_id": "t1",
            "agent": "fake",
            "status": "passed",
            "some_future_field": "x",
        }
    )
    assert parsed.task_id == "t1"
    assert not hasattr(parsed, "some_future_field")


def test_to_dict_omits_none_values() -> None:
    result = TaskResult(task_id="t1", agent="fake")
    data = result.to_dict()
    assert "category" not in data
    assert "reason" not in data
    assert "task_family" not in data


# ---------------------------------------------------------------------------
# resolve_layer
# ---------------------------------------------------------------------------

def test_resolve_layer_maps_known_layers() -> None:
    for layer in LAYERS:
        assert resolve_layer(layer) == layer


def test_resolve_layer_defaults_to_execution() -> None:
    assert resolve_layer(None) == "execution"
    assert resolve_layer("") == "execution"
    assert resolve_layer("unknown-layer") == "execution"


def test_layers_include_design_layers() -> None:
    assert LAYERS == (
        "execution",
        "tool-usage",
        "context-planning",
        "multi-step-solving",
    )
