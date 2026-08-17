"""Tests for the evaluation-metrics (C2) adapter extensions.

Covers Verdict.resolved (strict SWE-bench resolved pass-through, Q6) and
Verdict.partial (f2p_rate / p2p_rate / reward retention, Q9).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from benchmarks.adapters import SwebenchAdapter, Verdict, get_verifier
from tests.benchmark.test_adapters import _make_loaded, _report_path


def test_verdict_defaults_new_fields_none() -> None:
    verdict = Verdict(status="passed")
    assert verdict.resolved is None
    assert verdict.partial is None


def _write_report_with_partial(
    task_output: Path,
    loaded,
    model_name: str,
    *,
    resolved: bool,
    partial: dict | None,
) -> Path:
    report_path = _report_path(task_output, loaded, model_name)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"resolved": resolved}
    if partial is not None:
        entry.update(partial)
    report_path.write_text(json.dumps({loaded.task.instance_id: entry}))
    return report_path


def test_swebench_adapter_passes_resolved_and_partial(tmp_path, monkeypatch) -> None:
    adapter = SwebenchAdapter()
    loaded = _make_loaded()
    task_output = tmp_path / "task-output"
    task_output.mkdir(parents=True)

    partial = {"f2p_rate": 0.8, "p2p_rate": 0.5, "reward": 0.3}

    def fake_run(command, cwd, capture_output, text, timeout):
        _write_report_with_partial(
            task_output, loaded, "asterwynd", resolved=True, partial=partial
        )
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("benchmarks.adapters.subprocess.run", fake_run)

    verdict = adapter.verify(loaded, task_output, "patch")
    assert verdict.status == "passed"
    assert verdict.resolved is True
    assert verdict.partial == partial


def test_swebench_adapter_partial_on_failure(tmp_path, monkeypatch) -> None:
    adapter = SwebenchAdapter()
    loaded = _make_loaded()
    task_output = tmp_path / "task-output"
    task_output.mkdir(parents=True)

    partial = {"f2p_rate": 0.4, "p2p_rate": 0.2, "reward": 0.1}

    def fake_run(command, cwd, capture_output, text, timeout):
        _write_report_with_partial(
            task_output, loaded, "asterwynd", resolved=False, partial=partial
        )
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("benchmarks.adapters.subprocess.run", fake_run)

    verdict = adapter.verify(loaded, task_output, "patch")
    assert verdict.status == "failed"
    assert verdict.resolved is False
    assert verdict.partial == partial


def test_swebench_adapter_resolved_none_when_report_missing_fields(tmp_path, monkeypatch) -> None:
    adapter = SwebenchAdapter()
    loaded = _make_loaded()
    task_output = tmp_path / "task-output"
    task_output.mkdir(parents=True)

    def fake_run(command, cwd, capture_output, text, timeout):
        _write_report_with_partial(
            task_output, loaded, "asterwynd", resolved=True, partial=None
        )
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("benchmarks.adapters.subprocess.run", fake_run)

    verdict = adapter.verify(loaded, task_output, "patch")
    assert verdict.resolved is True
    assert verdict.partial is None


def test_contract_verdict_has_new_fields(tmp_path, monkeypatch) -> None:
    adapter = get_verifier("swebench")
    assert adapter is not None
    for field in ("status", "reason", "detail", "score", "resolved", "partial"):
        assert hasattr(Verdict(status="passed"), field), f"missing {field}"
