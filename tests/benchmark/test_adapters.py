"""Contract tests for the VerifierAdapter abstraction and SwebenchAdapter.

Covers the A0/7b design decisions: task_family-keyed registry, unknown
families returning None, and the migration of ``_run_swebench_harness`` into
the first adapter with unchanged status/reason mapping.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.adapters import SwebenchAdapter, Verdict, get_verifier
from benchmarks.models import BenchmarkReason
from benchmarks.task_schema import LoadedTask, TaskSpec


def _make_loaded(task_id: str = "swebench-inst-1", **overrides) -> LoadedTask:
    data = {
        "id": task_id,
        "repo": "psf/requests",
        "base_commit": "0" * 40,
        "problem_statement_file": "problem.md",
        "test_command": "pytest",
        "timeout_seconds": 300,
        "task_family": "swebench",
        "execution_environment": "docker",
        "instance_id": "psf__requests-1142",
        "dataset_name": "princeton-nlp/SWE-bench_Verified",
        "dataset_split": "test",
    }
    data.update(overrides)
    return LoadedTask(
        task=TaskSpec.from_dict(data),
        task_dir=Path("/nonexistent/task-dir"),
        problem_statement="Fix the reported bug.",
    )


def _report_path(task_output: Path, loaded: LoadedTask, model_name: str) -> Path:
    run_id = f"asterwynd-{loaded.task.id}"
    return (
        task_output
        / "logs"
        / "run_evaluation"
        / run_id
        / model_name.replace("/", "__")
        / loaded.task.instance_id
        / "report.json"
    )


def _write_report(task_output: Path, loaded: LoadedTask, model_name: str, resolved: bool) -> Path:
    report_path = _report_path(task_output, loaded, model_name)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({loaded.task.instance_id: {"resolved": resolved}})
    )
    return report_path


# --- Registry ------------------------------------------------------------


def test_get_verifier_returns_swebench_adapter() -> None:
    adapter = get_verifier("swebench")
    assert adapter is not None
    assert isinstance(adapter, SwebenchAdapter)
    assert callable(adapter.verify)


def test_get_verifier_passes_constructor_kwargs() -> None:
    adapter = get_verifier("swebench", agent_name="runner-agent", model="runner-model")
    assert isinstance(adapter, SwebenchAdapter)
    assert adapter._prediction_model_name() == "runner-agent:runner-model"


@pytest.mark.parametrize("task_family", ["harbor", "local", "unknown-family"])
def test_get_verifier_unknown_family_returns_none(task_family: str) -> None:
    assert get_verifier(task_family) is None


# --- SwebenchAdapter status/reason mapping -------------------------------


def test_swebench_verify_maps_passed(tmp_path, monkeypatch) -> None:
    loaded = _make_loaded()
    task_output = tmp_path / "task-output"
    task_output.mkdir(parents=True)

    def fake_run(command, cwd, capture_output, text, timeout):
        _write_report(task_output, loaded, "asterwynd:test-model", resolved=True)
        return SimpleNamespace(returncode=0, stdout="harness stdout", stderr="")

    monkeypatch.setattr("benchmarks.adapters.subprocess.run", fake_run)

    adapter = SwebenchAdapter(agent_name="asterwynd", model="test-model")
    verdict = adapter.verify(loaded, task_output, "diff --git a/app.py b/app.py\n")

    assert verdict.status == "passed"
    assert verdict.reason is None
    assert "harness stdout" in verdict.detail

    predictions = json.loads((task_output / "predictions.jsonl").read_text())
    assert predictions["instance_id"] == loaded.task.instance_id
    assert predictions["model_name_or_path"] == "asterwynd:test-model"
    assert predictions["model_patch"] == "diff --git a/app.py b/app.py\n"


def test_swebench_verify_maps_failed(tmp_path, monkeypatch) -> None:
    loaded = _make_loaded()
    task_output = tmp_path / "task-output"
    task_output.mkdir(parents=True)

    def fake_run(command, cwd, capture_output, text, timeout):
        _write_report(task_output, loaded, "asterwynd", resolved=False)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("benchmarks.adapters.subprocess.run", fake_run)

    verdict = SwebenchAdapter().verify(loaded, task_output, "patch")

    assert verdict.status == "failed"
    assert verdict.reason == BenchmarkReason.TEST_FAILURE.value


def test_swebench_verify_error_on_nonzero_exit(tmp_path, monkeypatch) -> None:
    loaded = _make_loaded()
    task_output = tmp_path / "task-output"
    task_output.mkdir(parents=True)

    def fake_run(command, cwd, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stdout="", stderr="image pull failed")

    monkeypatch.setattr("benchmarks.adapters.subprocess.run", fake_run)

    verdict = SwebenchAdapter().verify(loaded, task_output, "patch")

    assert verdict.status == "error"
    assert verdict.reason == BenchmarkReason.DOCKER_RUNTIME_ERROR.value
    assert "image pull failed" in verdict.detail


def test_swebench_verify_error_on_missing_report(tmp_path, monkeypatch) -> None:
    loaded = _make_loaded()
    task_output = tmp_path / "task-output"
    task_output.mkdir(parents=True)

    def fake_run(command, cwd, capture_output, text, timeout):
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("benchmarks.adapters.subprocess.run", fake_run)

    verdict = SwebenchAdapter().verify(loaded, task_output, "patch")

    assert verdict.status == "error"
    assert verdict.reason == BenchmarkReason.DOCKER_RUNTIME_ERROR.value
    assert "Missing SWE-bench report" in verdict.detail


# --- Migration fidelity: harness command and prediction model name -------


def test_swebench_harness_command_shape(tmp_path, monkeypatch) -> None:
    loaded = _make_loaded()
    task_output = tmp_path / "task-output"
    task_output.mkdir(parents=True)
    calls: list[tuple] = []

    def fake_run(command, cwd, capture_output, text, timeout):
        calls.append((command, cwd))
        _write_report(task_output, loaded, "asterwynd", resolved=True)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("benchmarks.adapters.subprocess.run", fake_run)

    SwebenchAdapter().verify(loaded, task_output, "patch")

    assert calls
    command, cwd = calls[0]
    assert Path(cwd) == task_output
    assert "swebench.harness.run_evaluation" in command

    def flag_value(name: str) -> str:
        assert name in command
        return command[command.index(name) + 1]

    assert flag_value("--dataset_name") == loaded.task.dataset_name
    assert flag_value("--split") == loaded.task.dataset_split
    assert flag_value("--instance_ids") == loaded.task.instance_id
    assert Path(flag_value("--predictions_path")) == task_output / "predictions.jsonl"
    assert flag_value("--max_workers") == "1"
    assert flag_value("--run_id") == f"asterwynd-{loaded.task.id}"
    assert flag_value("--timeout") == str(loaded.task.timeout_seconds)


def test_prediction_model_name_matches_legacy_build() -> None:
    # SwebenchAdapter._prediction_model_name is the migrated
    # _build_prediction_model_name from the runner.
    assert SwebenchAdapter()._prediction_model_name() == "asterwynd"
    assert SwebenchAdapter(agent_name="custom", model="gpt-5")._prediction_model_name() == "custom:gpt-5"


# --- Verdict contract ----------------------------------------------------


def test_verdict_defaults() -> None:
    verdict = Verdict(status="passed")
    assert verdict.status == "passed"
    assert verdict.reason is None
    assert verdict.detail == ""
    assert verdict.score is None


def test_any_adapter_verdict_carries_contract_fields(tmp_path, monkeypatch) -> None:
    adapter = get_verifier("swebench")
    assert adapter is not None

    loaded = _make_loaded()
    task_output = tmp_path / "task-output"
    task_output.mkdir(parents=True)

    def fake_run(command, cwd, capture_output, text, timeout):
        _write_report(task_output, loaded, "asterwynd", resolved=True)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("benchmarks.adapters.subprocess.run", fake_run)

    verdict = adapter.verify(loaded, task_output, "patch")
    for field in ("status", "reason", "detail", "score"):
        assert hasattr(verdict, field), f"Verdict missing field {field!r}"
    assert verdict.status in {
        "passed",
        "passed_with_warnings",
        "failed",
        "error",
        "unsupported",
    }
    # Deterministic verifiers do not set a score yet; the field stays None.
    assert verdict.score is None
