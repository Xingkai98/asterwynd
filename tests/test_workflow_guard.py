from __future__ import annotations

import json
import os
import io
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.workflow.manager import WorkflowManager

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "workflow_guard.py"


def _run_guard(tmp_path: Path, payload: dict) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["_GUARD_TEST_CHANGES_DIR"] = str(tmp_path / "openspec" / "changes")
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )


def _seed_active_change(tmp_path: Path) -> None:
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    WorkflowManager(change_dir, repo_root=tmp_path).init("test-change")


def _seed_reviewing_change(tmp_path: Path) -> None:
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    handoff = {
        "schema_version": "1.0",
        "change_id": "test-change",
        "state": {"phase": "building", "sub_state": "reviewing_impl"},
        "transitions": [],
    }
    (change_dir / "handoff.json").write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def test_guard_blocks_direct_writes_to_protected_files(tmp_path):
    _seed_active_change(tmp_path)

    cases = [
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "openspec" / "changes" / "test-change" / "handoff.json")}},
        {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / ".handoff" / "test-change" / "building-review-manifest.json")}},
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "docs" / "known-debt.md")}},
    ]

    for payload in cases:
        result = _run_guard(tmp_path, payload)
        assert result.returncode == 2
        assert "⛔" in result.stderr


def test_guard_allows_workflow_state_cli_commands(tmp_path):
    _seed_active_change(tmp_path)

    result = _run_guard(
        tmp_path,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "python3 scripts/workflow_state.py artifact-event "
                    "--change test-change "
                    "--event-type protected_artifact_explained "
                    "--artifact-path docs/known-debt.md "
                    "--reason ok "
                    "--approved-by human"
                )
            },
        },
    )

    assert result.returncode == 0


def test_guard_agent_calls_are_not_tracked_when_workflow_disabled(tmp_path):
    """issue #90：状态机停用后，_agent-calls.json 审阅跟踪不再产生。

    独立审阅闭环由 /review-loop 命令驱动，产物是 building-review.md + manifest，
    不再依赖 handoff.json 驱动的 _agent-calls.json 跟踪。
    """
    _seed_reviewing_change(tmp_path)

    result = _run_guard(
        tmp_path,
        {
            "tool_name": "Agent",
            "tool_input": {"prompt": "review implementation"},
        },
    )

    log_path = tmp_path / ".handoff" / "test-change" / "_agent-calls.json"
    assert result.returncode == 0
    assert not log_path.exists(), "状态机停用后不应再记录 _agent-calls.json"


def test_guard_noops_when_workflow_disabled(tmp_path, monkeypatch):
    """issue #90：状态机停用后，普通写操作放行（exit 0）。"""
    import scripts.workflow_guard as mod

    monkeypatch.setattr(mod, "is_workflow_enabled", lambda *_: False)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(tmp_path / "agent" / "test.py")},
                }
            )
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    assert excinfo.value.code == 0


def test_guard_blocks_protected_files_even_when_workflow_disabled(tmp_path, monkeypatch):
    """issue #90：受保护文件（known-issues/known-debt/specs/archive）始终拦截，
    不随状态机停用而放行——这是安全边界，不依赖 workflow 状态。"""
    import scripts.workflow_guard as mod

    monkeypatch.setattr(mod, "is_workflow_enabled", lambda *_: False)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(tmp_path / "docs" / "known-debt.md")},
                }
            )
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    assert excinfo.value.code == 2


def test_guard_resume_audit_no_longer_blocks_writes(tmp_path, monkeypatch):
    """issue #90：resume audit 门禁已停用（状态机仪式），普通写操作放行。"""
    import scripts.workflow_guard as mod

    monkeypatch.setattr(mod, "is_workflow_enabled", lambda *_: True)
    monkeypatch.setattr(
        mod,
        "run_resume_audit",
        lambda *_: SimpleNamespace(
            needs_reconciliation=True,
            errors=("resume required",),
        ),
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")},
                }
            )
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    assert excinfo.value.code == 0
