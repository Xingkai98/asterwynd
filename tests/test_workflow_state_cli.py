from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from agent.workflow.manager import WorkflowManager
from agent.workflow.event_log import event_log_path, verify_handoff_projection, write_init_event
from agent.workflow.review_manifest import verify_review_manifest
from agent.workflow.state_machine import init_handoff_json
from scripts.workflow_state import _method_hint, _ticket_tracker_label

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_STATE = REPO_ROOT / "scripts" / "workflow_state.py"


def test_advance_rejects_invalid_sub_state_jump(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    WorkflowManager(change_dir, repo_root=REPO_ROOT).init("test-change")

    result = subprocess.run(
        [
            sys.executable,
            str(WORKFLOW_STATE),
            "advance",
            "--change",
            "test-change",
            "--to",
            "ready_for_review",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    handoff = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))

    assert result.returncode != 0
    assert "invalid within-phase transition" in (result.stderr + result.stdout)
    assert handoff["state"] == {"phase": "planning", "sub_state": "exploring"}


def test_approve_rejects_non_gate_state_without_writing_approval(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    WorkflowManager(change_dir, repo_root=REPO_ROOT).init("test-change")

    result = subprocess.run(
        [
            sys.executable,
            str(WORKFLOW_STATE),
            "approve",
            "--change",
            "test-change",
            "--phase",
            "planning",
            "--who",
            "human-1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    handoff = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))

    assert result.returncode != 0
    assert "approval only allowed at gate" in (result.stderr + result.stdout)
    assert handoff["state"] == {"phase": "planning", "sub_state": "exploring"}
    assert not (tmp_path / ".handoff" / "test-change" / "gate-approvals.json").exists()


def test_approve_rejects_gate_when_phase_check_fails(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    mgr = WorkflowManager(change_dir, repo_root=REPO_ROOT)
    mgr.init("test-change")
    for sub_state in [
        "writing_proposal",
        "writing_design",
        "writing_spec",
        "writing_tickets",
        "reviewing_artifacts",
        "ready_for_review",
    ]:
        mgr.advance_sub_state(sub_state, actor_id="planner-1")

    result = subprocess.run(
        [
            sys.executable,
            str(WORKFLOW_STATE),
            "approve",
            "--change",
            "test-change",
            "--phase",
            "planning",
            "--who",
            "human-1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    handoff = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))

    assert result.returncode != 0
    assert "phase 机械检查未通过" in (result.stderr + result.stdout)
    assert handoff["state"] == {"phase": "planning", "sub_state": "ready_for_review"}
    assert not (tmp_path / ".handoff" / "test-change" / "gate-approvals.json").exists()


def test_spawn_rejects_wayfinding_before_ready_for_review(tmp_path):
    parent_dir = tmp_path / "openspec" / "changes" / "parent-map"
    parent_dir.mkdir(parents=True)
    handoff = init_handoff_json("parent-map")
    handoff["state"] = {"phase": "wayfinding", "sub_state": "charting_map"}
    (parent_dir / "handoff.json").write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(WORKFLOW_STATE),
            "spawn",
            "--from",
            "parent-map",
            "--changes",
            "child-a",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "ready_for_review" in (result.stderr + result.stdout)
    assert not (tmp_path / "openspec" / "changes" / "child-a").exists()


def test_spawn_created_child_has_replayable_event_log(tmp_path):
    parent_dir = tmp_path / "openspec" / "changes" / "parent-map"
    parent_dir.mkdir(parents=True)
    handoff = init_handoff_json("parent-map")
    handoff["state"] = {"phase": "wayfinding", "sub_state": "ready_for_review"}
    (parent_dir / "handoff.json").write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_init_event(parent_dir, handoff)

    result = subprocess.run(
        [
            sys.executable,
            str(WORKFLOW_STATE),
            "spawn",
            "--from",
            "parent-map",
            "--changes",
            "child-a",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    child_dir = tmp_path / "openspec" / "changes" / "child-a"
    parent_events = event_log_path(parent_dir).read_text(encoding="utf-8")

    assert result.returncode == 0
    assert '"event_type": "wayfinding_children_spawned"' in parent_events
    assert '"children": ["child-a"]' in parent_events
    assert json.loads((parent_dir / "handoff.json").read_text(encoding="utf-8"))["wayfinding_children"] == ["child-a"]
    assert verify_handoff_projection(parent_dir) == []
    assert verify_handoff_projection(child_dir) == []


def test_artifact_event_command_appends_event_without_touching_handoff(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    WorkflowManager(change_dir, repo_root=tmp_path).init("test-change")
    handoff_before = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))

    result = subprocess.run(
        [
            sys.executable,
            str(WORKFLOW_STATE),
            "artifact-event",
            "--change",
            "test-change",
            "--event-type",
            "protected_artifact_explained",
            "--artifact-path",
            "docs/known-debt.md",
            "--reason",
            "documented debt entry updated through the workflow gate",
            "--approved-by",
            "human-1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    event_log = event_log_path(change_dir).read_text(encoding="utf-8")
    handoff_after = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))

    assert result.returncode == 0
    assert '"event_type": "protected_artifact_explained"' in event_log
    assert '"artifact_path": "docs/known-debt.md"' in event_log
    assert handoff_after == handoff_before
    assert verify_handoff_projection(change_dir) == []


def test_review_manifest_command_writes_manifest(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    WorkflowManager(change_dir, repo_root=tmp_path).init("test-change")

    handoff_dir = tmp_path / ".handoff" / "test-change"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    (handoff_dir / "building-review.md").write_text("## Review\n\nPASS\n", encoding="utf-8")
    (change_dir / "tasks.md").write_text("- [x] cover the path\n", encoding="utf-8")
    (change_dir / "specs").mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            sys.executable,
            str(WORKFLOW_STATE),
            "review-manifest",
            "--change",
            "test-change",
            "--phase",
            "building",
            "--reviewer-run-id",
            "reviewer-1",
            "--base-sha",
            "base-sha",
            "--head-sha",
            "head-sha",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    manifest_path = handoff_dir / "building-review-manifest.json"

    assert result.returncode == 0
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["reviewer_run_id"] == "reviewer-1"
    assert manifest["phase"] == "building"
    assert verify_review_manifest(tmp_path, "test-change", "building") == []


def test_ticket_tracker_defaults_to_github_issues():
    assert _ticket_tracker_label() == "GitHub Issues (Xingkai98/asterwynd)"


def test_ticket_related_hints_include_backend_label():
    assert "GitHub Issues" in _method_hint("wayfinding", "working_tickets")
    assert "GitHub Issues" in _method_hint("planning", "writing_tickets")


def test_discover_treats_disabled_workflow_as_empty(capsys, monkeypatch):
    import scripts.workflow_state as mod

    monkeypatch.setattr(mod, "is_workflow_enabled", lambda *_: False)
    monkeypatch.setattr(
        mod,
        "_all_change_ids",
        lambda: (_ for _ in ()).throw(AssertionError("discover should short-circuit")),
    )

    result = mod.cmd_discover(Namespace(format="json"))
    output = capsys.readouterr().out

    assert result == 0
    assert '"workflow_enabled": false' in output
    assert '"active_count": 0' in output


def test_discover_includes_resume_audit_when_enabled(capsys, monkeypatch):
    import scripts.workflow_state as mod

    audit = SimpleNamespace(
        baseline_present=True,
        needs_reconciliation=True,
        errors=("resume required",),
        warnings=(),
        to_dict=lambda: {"needs_reconciliation": True, "errors": ["resume required"]},
    )
    monkeypatch.setattr(mod, "is_workflow_enabled", lambda *_: True)
    monkeypatch.setattr(mod, "_all_change_ids", lambda: [])
    monkeypatch.setattr(mod, "run_resume_audit", lambda *_: audit)

    result = mod.cmd_discover(Namespace(format="json"))
    output = capsys.readouterr().out

    assert result == 0
    assert '"resume_audit"' in output
    assert "resume required" in output


def test_advance_rejects_when_workflow_disabled(tmp_path, capsys, monkeypatch):
    import scripts.workflow_state as mod

    monkeypatch.setattr(mod, "is_workflow_enabled", lambda *_: False)

    result = mod.cmd_advance(Namespace(change="test-change", to="writing_proposal", to_phase=None))
    output = capsys.readouterr()

    assert result == 1
    assert "workflow 已在 workflow_methods.json 中禁用" in output.err
