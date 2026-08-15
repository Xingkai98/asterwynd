from __future__ import annotations

import json

import pytest

from agent.workflow.event_log import (
    append_resume_audit_reconciled_event,
    append_wayfinding_children_event,
    event_log_path,
    is_awaiting_state,
    project_workflow_state,
    replay_handoff_projection,
    verify_handoff_projection,
    verify_projection,
    workflow_state_path,
)
from agent.workflow.manager import WorkflowManager
from agent.workflow.state_machine import StateMachineError


def _append_raw_event(change_dir, event_type, seq, change_id="test-change", **extra):
    event = {
        "schema": "workflow-event/v1",
        "seq": seq,
        "event_type": event_type,
        "change_id": change_id,
        **extra,
    }
    with event_log_path(change_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _seed_new_gen_change(tmp_path) -> "object":
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    _append_raw_event(change_dir, "change_created", 1)
    return change_dir


def _transition(from_state, to_state, trigger="auto"):
    return {"from": from_state, "to": to_state, "trigger": trigger}


def test_projection_verification_rejects_manual_state_edit(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    mgr = WorkflowManager(change_dir)
    mgr.init("test-change")
    mgr.advance_sub_state("writing_proposal", actor_id="planner-1")

    assert verify_handoff_projection(change_dir) == []

    handoff_path = change_dir / "handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["state"] = {"phase": "building", "sub_state": "writing_tests"}
    handoff_path.write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    errors = verify_handoff_projection(change_dir)

    assert any("handoff.json projection does not match workflow-events.jsonl" in e for e in errors)


def test_projection_verification_ignores_non_state_artifact_events(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    mgr = WorkflowManager(change_dir)
    mgr.init("test-change")
    with event_log_path(change_dir).open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "schema": "workflow-event/v1",
                    "seq": 2,
                    "event_type": "current_spec_synced",
                    "change_id": "test-change",
                    "artifact_path": "openspec/specs/dev-workflow-state-machine/spec.md",
                    "reason": "closing synced accepted workflow state machine spec",
                    "approved_by": "human",
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    assert verify_handoff_projection(change_dir) == []


def test_projection_verification_ignores_resume_reconciliation_event(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    mgr = WorkflowManager(change_dir)
    mgr.init("test-change")
    append_resume_audit_reconciled_event(
        change_dir,
        "test-change",
        artifact_path=".dev/workflow-resume-baseline.json",
        reason="disabled-period work reconciled",
        approved_by="human",
        baseline_sha="base",
        head_sha="head",
        changed_paths_hash="hash",
        changed_paths=["agent/feature.py"],
    )

    assert verify_handoff_projection(change_dir) == []


def test_projection_verification_replays_block_unblock_and_routing_updates(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    mgr = WorkflowManager(change_dir)
    mgr.init("test-change")
    mgr.advance_sub_state("writing_proposal")
    mgr.block("need API clarification", "human-1")
    mgr.unblock()
    mgr.update_routing("planning", executor="codex", session_mode="new")

    assert verify_handoff_projection(change_dir) == []


def test_projection_verification_replays_wayfinding_children(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    mgr = WorkflowManager(change_dir)
    mgr.init("test-change")
    append_wayfinding_children_event(change_dir, "test-change", ["child-a", "child-b"])

    projection = replay_handoff_projection(change_dir)
    (change_dir / "handoff.json").write_text(
        json.dumps(projection, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    assert verify_handoff_projection(change_dir) == []
    handoff = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))
    assert handoff["wayfinding_children"] == ["child-a", "child-b"]


# ── workflow-state.json 统一投影（flow-event-projection P1）──────────────


def test_project_new_gen_change_created_seed(tmp_path):
    change_dir = _seed_new_gen_change(tmp_path)
    _append_raw_event(change_dir, "backlog_updated", 2, artifact_path="docs/x.md")

    projection = project_workflow_state(change_dir)

    assert projection["schema"] == "workflow-state/v1"
    assert projection["change_id"] == "test-change"
    assert projection["state"] == {"phase": "planning", "sub_state": "exploring"}
    assert projection["milestones"] == []
    assert projection["source_event_seq"] == 2


def test_project_new_gen_milestones_pusher_does_not_change_state(tmp_path):
    change_dir = _seed_new_gen_change(tmp_path)
    _append_raw_event(change_dir, "backlog_updated", 2, artifact_path="docs/x.md")
    _append_raw_event(change_dir, "grill_completed", 3)
    _append_raw_event(change_dir, "design_reviewed", 4)
    _append_raw_event(change_dir, "known_debt_updated", 5, artifact_path="docs/known-debt.md")

    projection = project_workflow_state(change_dir)

    assert projection["state"] == {"phase": "planning", "sub_state": "exploring"}
    assert projection["milestones"] == ["grill_completed", "design_reviewed", "known_debt_updated"]
    assert projection["source_event_seq"] == 5


def test_project_new_gen_transition_applied_updates_state(tmp_path):
    change_dir = _seed_new_gen_change(tmp_path)
    _append_raw_event(
        change_dir,
        "transition_applied",
        2,
        transition=_transition(
            {"phase": "planning", "sub_state": "exploring"},
            {"phase": "planning", "sub_state": "writing_proposal"},
        ),
    )

    projection = project_workflow_state(change_dir)

    assert projection["state"] == {"phase": "planning", "sub_state": "writing_proposal"}


def test_project_new_gen_blocked_awaiting_state(tmp_path):
    change_dir = _seed_new_gen_change(tmp_path)
    _append_raw_event(
        change_dir,
        "blocked_entered",
        2,
        transition=_transition(
            {"phase": "planning", "sub_state": "writing_design"},
            {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"},
        ),
        blocker={"blocked_from": {"phase": "planning", "sub_state": "writing_design"}, "reason": "proposal done"},
    )

    projection = project_workflow_state(change_dir)

    assert projection["state"] == {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"}
    assert is_awaiting_state(projection["state"])
    assert is_awaiting_state({"phase": "blocked", "sub_state": None}) is False
    assert is_awaiting_state({"phase": "planning", "sub_state": "exploring"}) is False


def test_project_new_gen_unblock_without_blocker_record(tmp_path):
    """Q9/代码层修正 7：无 blockers 数组记录时 blocked_resolved 不抛 invalid blocker index。"""
    change_dir = _seed_new_gen_change(tmp_path)
    _append_raw_event(
        change_dir,
        "blocked_entered",
        2,
        transition=_transition(
            {"phase": "planning", "sub_state": "writing_design"},
            {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"},
        ),
        blocker={"blocked_from": {"phase": "planning", "sub_state": "writing_design"}, "reason": "proposal done"},
    )
    _append_raw_event(
        change_dir,
        "blocked_resolved",
        3,
        transition=_transition(
            {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"},
            {"phase": "planning", "sub_state": "writing_design"},
        ),
    )

    projection = project_workflow_state(change_dir)

    assert projection["state"] == {"phase": "planning", "sub_state": "writing_design"}
    assert is_awaiting_state(projection["state"]) is False


def test_project_no_seed_tolerated(tmp_path):
    """无 seed 事件（backlog_updated 开头的老归档）按默认 seed 投影，不抛错。"""
    change_dir = tmp_path / "openspec" / "changes" / "gen0-change"
    change_dir.mkdir(parents=True)
    _append_raw_event(change_dir, "backlog_updated", 1, change_id="gen0-change", artifact_path="docs/x.md")
    _append_raw_event(change_dir, "current_spec_synced", 2, change_id="gen0-change", artifact_path="openspec/specs/x.md")

    projection = project_workflow_state(change_dir)

    assert projection["state"] == {"phase": "planning", "sub_state": "exploring"}
    assert projection["source_event_seq"] == 2
    assert projection["change_id"] == "gen0-change"


def test_project_unknown_event_type_raises(tmp_path):
    change_dir = _seed_new_gen_change(tmp_path)
    _append_raw_event(change_dir, "mystery_event", 2)

    with pytest.raises(StateMachineError, match="unknown workflow event type"):
        project_workflow_state(change_dir)


def test_project_rejects_blocked_non_awaiting_sub_state(tmp_path):
    """building-review Issue 5：blocked.<任意非 awaiting> 事件在投影层被拒，防绕过 awaiting 集。"""
    change_dir = _seed_new_gen_change(tmp_path)
    _append_raw_event(
        change_dir,
        "blocked_entered",
        2,
        transition=_transition(
            {"phase": "planning", "sub_state": "writing_design"},
            {"phase": "blocked", "sub_state": "weird_blocked"},
        ),
        blocker={"blocked_from": {"phase": "planning", "sub_state": "writing_design"}, "reason": "x"},
    )

    with pytest.raises(StateMachineError, match="awaiting type or null"):
        project_workflow_state(change_dir)


def test_project_empty_log_raises(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "empty-change"
    change_dir.mkdir(parents=True)
    event_log_path(change_dir).write_text("", encoding="utf-8")

    with pytest.raises(StateMachineError, match="empty"):
        project_workflow_state(change_dir)


def test_project_gen1_maps_handoff_to_workflow_state(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    mgr = WorkflowManager(change_dir, repo_root=tmp_path)
    mgr.init("test-change")
    mgr.advance_sub_state("writing_proposal", actor_id="planner-1")

    projection = project_workflow_state(change_dir)

    assert projection["state"] == {"phase": "planning", "sub_state": "writing_proposal"}
    assert projection["source_event_seq"] == 2
    assert "planning" in projection["milestones"]
    assert projection["change_id"] == "test-change"


def test_gen1_replay_shape_unchanged_parity(tmp_path):
    """parity（task 2.2）：老世代 replay_handoff_projection 仍返回 handoff 形状，
    与修复前一致——统一投影只新增 workflow-state 映射，不改既有 replay 输出。"""
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    mgr = WorkflowManager(change_dir, repo_root=tmp_path)
    mgr.init("test-change")
    mgr.advance_sub_state("writing_proposal", actor_id="planner-1")
    mgr.block("need API clarification", "human-1")
    mgr.unblock()

    projection = replay_handoff_projection(change_dir)

    assert "state" in projection
    assert "transitions" in projection
    assert "blockers" in projection
    assert "last_gate" in projection
    assert projection["state"] == {"phase": "planning", "sub_state": "writing_proposal"}
    assert len(projection["blockers"]) == 1


def test_verify_projection_gen2_disk_matches_and_tamper_detected(tmp_path):
    change_dir = _seed_new_gen_change(tmp_path)
    _append_raw_event(change_dir, "backlog_updated", 2, artifact_path="docs/x.md")
    workflow_state_path(change_dir).write_text(
        json.dumps(project_workflow_state(change_dir), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    assert verify_projection(change_dir) == []

    disk = json.loads(workflow_state_path(change_dir).read_text(encoding="utf-8"))
    disk["state"] = {"phase": "building", "sub_state": "writing_tests"}
    workflow_state_path(change_dir).write_text(json.dumps(disk, indent=2, ensure_ascii=False), encoding="utf-8")

    errors = verify_projection(change_dir)
    assert any("does not match" in e for e in errors)


def test_verify_projection_gen2_no_disk_projection_passes(tmp_path):
    change_dir = _seed_new_gen_change(tmp_path)
    _append_raw_event(change_dir, "backlog_updated", 2, artifact_path="docs/x.md")

    assert verify_projection(change_dir) == []


def test_verify_projection_gen1_handoff_consistency(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    mgr = WorkflowManager(change_dir, repo_root=tmp_path)
    mgr.init("test-change")
    mgr.advance_sub_state("writing_proposal", actor_id="planner-1")

    assert verify_projection(change_dir) == []

    handoff = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))
    handoff["state"] = {"phase": "building", "sub_state": "writing_tests"}
    (change_dir / "handoff.json").write_text(json.dumps(handoff, indent=2, ensure_ascii=False), encoding="utf-8")

    assert any("does not match" in e for e in verify_projection(change_dir))
