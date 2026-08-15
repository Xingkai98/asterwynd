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


def _append_ev(change_dir, event_type, seq, change_id="test-change", **extra):
    event = {
        "schema": "workflow-event/v1",
        "seq": seq,
        "event_type": event_type,
        "change_id": change_id,
        **extra,
    }
    with (change_dir / "workflow-events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _tr(from_state, to_state, trigger="auto"):
    return {"from": from_state, "to": to_state, "trigger": trigger}


def _seed_gen2_change(tmp_path, change_id="test-change"):
    change_dir = tmp_path / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True)
    _append_ev(change_dir, "change_created", 1, change_id)
    return change_dir


def _run_cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, str(WORKFLOW_STATE), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def test_flow_advance_rejects_invalid_sub_state_jump(tmp_path):
    change_dir = _seed_gen2_change(tmp_path)

    result = _run_cli(tmp_path, "flow", "advance", "--change", "test-change", "--to", "ready_for_review")

    assert result.returncode != 0
    assert "invalid within-phase transition" in (result.stderr + result.stdout)
    # 失败操作不写事件：从事件重新投影，状态不变
    assert not (change_dir / "workflow-state.json").exists()
    from agent.workflow.event_log import project_workflow_state

    assert project_workflow_state(change_dir)["state"] == {"phase": "planning", "sub_state": "exploring"}


def test_flow_approve_rejects_non_gate_state(tmp_path):
    change_dir = _seed_gen2_change(tmp_path)

    result = _run_cli(tmp_path, "flow", "approve", "--change", "test-change", "--phase", "planning")

    assert result.returncode != 0
    assert "期望 gate planning.ready_for_review" in (result.stderr + result.stdout)
    assert not (change_dir / "workflow-state.json").exists()
    from agent.workflow.event_log import project_workflow_state

    assert project_workflow_state(change_dir)["state"] == {"phase": "planning", "sub_state": "exploring"}


def test_flow_approve_rejects_gate_when_phase_check_fails(tmp_path):
    change_dir = _seed_gen2_change(tmp_path)
    subs = [
        "writing_proposal",
        "writing_design",
        "writing_spec",
        "writing_tickets",
        "reviewing_artifacts",
        "ready_for_review",
    ]
    current = {"phase": "planning", "sub_state": "exploring"}
    for seq, sub in enumerate(subs, start=2):
        _append_ev(
            change_dir,
            "transition_applied",
            seq,
            transition=_tr(current, {"phase": "planning", "sub_state": sub}),
        )
        current = {"phase": "planning", "sub_state": sub}

    result = _run_cli(tmp_path, "flow", "approve", "--change", "test-change", "--phase", "planning")

    assert result.returncode != 0
    assert "phase 机械检查未通过" in (result.stderr + result.stdout)
    assert not (change_dir / "workflow-state.json").exists()
    from agent.workflow.event_log import project_workflow_state

    assert project_workflow_state(change_dir)["state"] == {"phase": "planning", "sub_state": "ready_for_review"}


def test_flow_advance_ignores_workflow_disabled_flag(tmp_path):
    """flow 命令是新执法核心，不再受 workflow_methods.json enabled 旧旗标门控。"""
    change_dir = _seed_gen2_change(tmp_path)
    methods = tmp_path / "scripts" / "workflow_methods.json"
    methods.parent.mkdir(parents=True, exist_ok=True)
    methods.write_text('{"workflow": {"enabled": false}}', encoding="utf-8")

    result = _run_cli(tmp_path, "flow", "advance", "--change", "test-change", "--to", "writing_proposal")

    assert result.returncode == 0
    projection = json.loads((change_dir / "workflow-state.json").read_text(encoding="utf-8"))
    assert projection["state"] == {"phase": "planning", "sub_state": "writing_proposal"}


def test_flow_status_outputs_json_and_self_heals_stale(tmp_path):
    change_dir = _seed_gen2_change(tmp_path)
    _append_ev(change_dir, "backlog_updated", 2, artifact_path="docs/x.md")
    # 先写一个 stale 投影
    (change_dir / "workflow-state.json").write_text(
        json.dumps(
            {
                "schema": "workflow-state/v1",
                "change_id": "test-change",
                "state": {"phase": "building", "sub_state": "writing_tests"},
                "milestones": [],
                "source_event_seq": 99,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run_cli(tmp_path, "flow", "status", "--change", "test-change")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["state"] == {"phase": "planning", "sub_state": "exploring"}
    assert output["source_event_seq"] == 2
    assert output["stale"] is True
    # 自愈重建：磁盘投影已刷新
    disk = json.loads((change_dir / "workflow-state.json").read_text(encoding="utf-8"))
    assert disk["source_event_seq"] == 2


def test_flow_status_all_lists_contemporary_changes(tmp_path):
    _seed_gen2_change(tmp_path, "modern-change")
    # 老世代 change（handoff.json 驱动）
    old_dir = tmp_path / "openspec" / "changes" / "legacy-change"
    WorkflowManager(old_dir, repo_root=tmp_path).init("legacy-change")

    result = _run_cli(tmp_path, "flow", "status", "--all")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "modern-change" in output
    assert "legacy-change" in output


def test_flow_status_archived_change_readonly(tmp_path):
    """归档 change 可查询（用户故事：老 change 也能 flow status），只读不落盘。"""
    archive_dir = tmp_path / "openspec" / "changes" / "archive" / "2026-08-09-old-change"
    archive_dir.mkdir(parents=True)
    _append_ev(archive_dir, "change_created", 1, "old-change")
    _append_ev(archive_dir, "grill_completed", 2, "old-change")

    result = _run_cli(tmp_path, "flow", "status", "--change", "2026-08-09-old-change")

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["change_id"] == "old-change"
    assert output["milestones"] == ["grill_completed"]
    assert not (archive_dir / "workflow-state.json").exists()


def test_flow_block_and_confirm_roundtrip(tmp_path):
    change_dir = _seed_gen2_change(tmp_path)
    _append_ev(
        change_dir,
        "transition_applied",
        2,
        transition=_tr(
            {"phase": "planning", "sub_state": "exploring"},
            {"phase": "planning", "sub_state": "writing_proposal"},
        ),
    )

    block_result = _run_cli(
        tmp_path,
        "flow",
        "block",
        "--change",
        "test-change",
        "--awaiting",
        "awaiting_proposal_confirmation",
    )
    assert block_result.returncode == 0, block_result.stderr

    block_projection = json.loads((change_dir / "workflow-state.json").read_text(encoding="utf-8"))
    assert block_projection["state"] == {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"}

    confirm_result = _run_cli(tmp_path, "flow", "confirm", "--change", "test-change")
    assert confirm_result.returncode == 0, confirm_result.stderr

    confirm_projection = json.loads((change_dir / "workflow-state.json").read_text(encoding="utf-8"))
    assert confirm_projection["state"] == {"phase": "planning", "sub_state": "writing_proposal"}


def test_flow_confirm_rejects_when_not_awaiting(tmp_path):
    _seed_gen2_change(tmp_path)

    result = _run_cli(tmp_path, "flow", "confirm", "--change", "test-change")

    assert result.returncode != 0
    assert "不在 awaiting 态" in (result.stderr + result.stdout)


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

    review_dir = change_dir / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "building-review.md").write_text("## Review\n\nPASS\n", encoding="utf-8")
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

    manifest_path = review_dir / "building-review-manifest.json"

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


def test_flow_status_requires_change_or_all(capsys):
    import scripts.workflow_state as mod

    result = mod.cmd_flow_status(Namespace(change=None, all=False))
    output = capsys.readouterr()

    assert result == 1
    assert "需要 --change" in output.err
