"""C3 self_check five-gate tests.

Each gate is exercised for pass and fail, plus integration: all-pass exits 0,
a failing gate exits 1, ``--skip`` bypasses a gate, and missing run.json fails
the tuple-dependent gates.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from scripts.self_check import (  # noqa: E402
    DISCLOSURE_HEADINGS,
    gate1,
    gate2,
    gate3,
    gate4,
    gate5,
)


def _full_run_json(**overrides) -> dict:
    meta = {
        "model": "deepseek-v4-flash",
        "model_version": "v4-flash-20260817",
        "adapter_version": "1",
        "prompt_version": "default",
        "network": "on",
        "task_set_hash": "abc123def456",
        "pricing_table_version": "2026-08-17",
        "temperature": 0.2,
        "seed": 0,
    }
    meta.update(overrides)
    return meta


def _write_run_json(run_dir: Path, meta: dict) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "run.json"
    path.write_text(json.dumps(meta))
    return path


def _write_result(run_dir: Path, task_id: str, status: str, fault_owner: str | None) -> None:
    path = run_dir / "tasks" / task_id / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"task_id": task_id, "status": status}
    if fault_owner is not None:
        data["fault_owner"] = fault_owner
    path.write_text(json.dumps(data))


def _write_report(run_dir: Path, headings: list[str]) -> Path:
    report = run_dir / "evaluation-report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n\n".join(headings) + "\n")
    return report


# ---------------------------------------------------------------------------
# Gate 1: 同模型同 harness 复现
# ---------------------------------------------------------------------------

def test_gate1_pass_single_run():
    assert gate1([_full_run_json()]).ok


def test_gate1_fail_missing_harness():
    result = gate1([_full_run_json(adapter_version=None)])
    assert not result.ok
    assert "adapter_version" in result.issues[0]


def test_gate1_fail_inconsistent_rounds():
    result = gate1([_full_run_json(seed=0), _full_run_json(model="other", seed=1)])
    assert not result.ok
    assert "不一致" in result.issues[0]


def test_gate1_fail_no_run_json():
    assert not gate1([]).ok


# ---------------------------------------------------------------------------
# Gate 2: seed 复现
# ---------------------------------------------------------------------------

def test_gate2_pass_complete_sampling():
    assert gate2([_full_run_json()]).ok


def test_gate2_fail_missing_seed():
    result = gate2([_full_run_json(seed=None)])
    assert not result.ok
    assert "seed" in result.issues[0]


# ---------------------------------------------------------------------------
# Gate 3: 失败归因闭环
# ---------------------------------------------------------------------------

def test_gate3_pass_no_failures(tmp_path):
    run_dir = tmp_path / "r0"
    _write_run_json(run_dir, _full_run_json())
    _write_result(run_dir, "t1", "passed", None)
    assert gate3(run_dir).ok


def test_gate3_pass_all_failures_annotated(tmp_path):
    run_dir = tmp_path / "r0"
    _write_run_json(run_dir, _full_run_json())
    _write_result(run_dir, "t1", "failed", "task")
    _write_result(run_dir, "t2", "error", "agent")
    assert gate3(run_dir).ok


def test_gate3_fail_missing_fault_owner(tmp_path):
    run_dir = tmp_path / "r0"
    _write_run_json(run_dir, _full_run_json())
    _write_result(run_dir, "t1", "failed", None)
    result = gate3(run_dir)
    assert not result.ok
    assert "fault_owner" in result.issues[0]


# ---------------------------------------------------------------------------
# Gate 4: 披露段齐全
# ---------------------------------------------------------------------------

def test_gate4_pass_all_headings(tmp_path):
    run_dir = tmp_path / "runs"
    _write_report(run_dir, list(DISCLOSURE_HEADINGS))
    assert gate4(run_dir).ok


def test_gate4_fail_missing_heading(tmp_path):
    run_dir = tmp_path / "runs"
    _write_report(run_dir, [h for h in DISCLOSURE_HEADINGS if h != "## 过程效率"])
    result = gate4(run_dir)
    assert not result.ok
    assert "过程效率" in result.issues[0]


def test_gate4_fail_no_report(tmp_path):
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    result = gate4(run_dir)
    assert not result.ok
    assert "evaluation-report.md" in result.issues[0]


# ---------------------------------------------------------------------------
# Gate 5: 报告元组完整
# ---------------------------------------------------------------------------

def test_gate5_pass_complete_tuple():
    assert gate5([_full_run_json()]).ok


def test_gate5_fail_missing_task_set_hash():
    result = gate5([_full_run_json(task_set_hash=None)])
    assert not result.ok
    assert "task_set_hash" in result.issues[0]


# ---------------------------------------------------------------------------
# Integration via CLI
# ---------------------------------------------------------------------------

def _run_self_check(run_dir: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "self_check.py"), str(run_dir), *extra],
        capture_output=True,
        text=True,
    )


def test_integration_all_pass_exit_0(tmp_path):
    run_dir = tmp_path / "runs"
    _write_run_json(run_dir / "r0", _full_run_json(seed=0))
    _write_run_json(run_dir / "r1", _full_run_json(seed=1))
    _write_result(run_dir / "r0", "t1", "passed", None)
    _write_report(run_dir, list(DISCLOSURE_HEADINGS))
    proc = _run_self_check(run_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "self_check PASS" in proc.stdout


def test_integration_failing_gate_exits_1(tmp_path):
    run_dir = tmp_path / "runs"
    _write_run_json(run_dir / "r0", _full_run_json(seed=None))
    _write_report(run_dir, list(DISCLOSURE_HEADINGS))
    proc = _run_self_check(run_dir)
    assert proc.returncode == 1
    assert "GATE 2 FAIL" in proc.stdout


def test_integration_skip_gate(tmp_path):
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    # no report -> gate 4 would fail, but it is skipped
    proc = _run_self_check(run_dir, "--skip", "4")
    assert proc.returncode == 1  # gates 1/2/5 still fail (no run.json)
    assert "GATE 4 SKIPPED" in proc.stdout


def test_integration_missing_run_dir_exits_1(tmp_path):
    proc = _run_self_check(tmp_path / "nope")
    assert proc.returncode == 1
    assert "不存在" in proc.stderr
