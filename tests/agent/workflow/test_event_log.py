from __future__ import annotations

import json

from agent.workflow.event_log import (
    append_resume_audit_reconciled_event,
    append_wayfinding_children_event,
    event_log_path,
    replay_handoff_projection,
    verify_handoff_projection,
)
from agent.workflow.manager import WorkflowManager


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
