from __future__ import annotations

import tempfile

import pytest

from agent.workflow.manager import WorkflowManager
from agent.workflow.state_machine import StateMachineError


class TestWorkflowManagerInit:
    def test_init_creates_handoff_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            snap = mgr.init("my-change")
            assert snap["state"] == {"phase": "planning", "sub_state": "exploring"}
            assert snap["change_id"] == "my-change"

    def test_load_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            mgr2 = WorkflowManager(tmp)
            snap = mgr2.load()
            assert snap["state"]["phase"] == "planning"

    def test_ensure_loaded_auto_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            mgr2 = WorkflowManager(tmp)
            snap = mgr2.ensure_loaded()
            assert snap["change_id"] == "test"

    def test_snapshot_before_init_raises(self):
        mgr = WorkflowManager("/tmp/nonexistent")
        with pytest.raises(StateMachineError, match="not initialized"):
            mgr.snapshot()


class TestWorkflowManagerFullFlow:
    def test_full_planning_through_reviewing(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")

            # Complete planning
            for sub in ["writing_proposal", "writing_design", "grilling_design",
                        "writing_specs", "writing_tasks", "ready_for_review"]:
                mgr.advance_sub_state(sub, actor_id="planner-1")

            assert mgr.is_at_gate
            assert mgr.current_phase == "planning"

            # Handoff
            mgr.handoff("reviewing", ".handoff/test/planning-to-reviewing.md", "planner-1")

            # Human approves
            snap = mgr.human_approve("human-1", "design approved")
            assert snap["state"]["phase"] == "reviewing"
            assert snap["state"]["sub_state"] == "reading_docs"

    def test_skip_reviewing(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")

            # Go to planning gate
            for sub in ["writing_proposal", "writing_design", "writing_specs",
                        "writing_tasks", "ready_for_review"]:
                mgr.advance_sub_state(sub)

            # Skip reviewing
            snap = mgr.human_skip("human-1", "trivial change, no design review needed")
            assert snap["state"]["phase"] == "building"
            assert snap["state"]["sub_state"] == "writing_tests"

    def test_skip_code_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")

            # planning gate -> approve to reviewing
            for sub in ["writing_proposal", "writing_design", "writing_specs",
                        "writing_tasks", "ready_for_review"]:
                mgr.advance_sub_state(sub)
            mgr.human_approve("human-1")

            # reviewing: already at reading_docs from approve
            for sub in ["reviewing_design", "ready_for_review"]:
                mgr.advance_sub_state(sub)
            mgr.human_approve("human-1")

            # building: already at writing_tests from approve
            for sub in ["implementing", "all_tests_passing",
                        "smoke_validating", "ready_for_review"]:
                mgr.advance_sub_state(sub)
            snap = mgr.human_skip("human-1", "small change, skip code review")
            assert snap["state"]["phase"] == "closing"
            assert snap["state"]["sub_state"] == "syncing_specs"

    def test_rollback_at_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")

            for sub in ["writing_proposal", "writing_design", "writing_specs",
                        "writing_tasks", "ready_for_review"]:
                mgr.advance_sub_state(sub)
            mgr.human_approve("human-1")

            # Now in reviewing.reading_docs
            for sub in ["reviewing_design", "ready_for_review"]:
                mgr.advance_sub_state(sub)

            # Reviewer finds design issues, human rolls back to planning
            snap = mgr.human_rollback(
                "planning", "writing_design",
                "human-1", "design has gaps in error handling"
            )
            assert snap["state"]["phase"] == "planning"
            assert snap["state"]["sub_state"] == "writing_design"

    def test_rollback_from_any_sub_state_not_just_gate(self):
        """Human can rollback from any state, not just gate."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            for sub in ["writing_proposal", "writing_design"]:
                mgr.advance_sub_state(sub)

            # Rollback from writing_design (not gate) to exploring
            snap = mgr.human_rollback(
                "planning", "exploring",
                "human-1", "wrong direction, restarting exploration"
            )
            assert snap["state"]["phase"] == "planning"
            assert snap["state"]["sub_state"] == "exploring"

    def test_tdd_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")

            # Get to building
            for sub in ["writing_proposal", "writing_design", "writing_specs",
                        "writing_tasks", "ready_for_review"]:
                mgr.advance_sub_state(sub)
            mgr.human_approve("human-1")
            for sub in ["reviewing_design", "ready_for_review"]:
                mgr.advance_sub_state(sub)
            mgr.human_approve("human-1")

            # TDD: write test -> fail -> implement -> pass (already at writing_tests)
            mgr.advance_sub_state("test_failing")
            mgr.advance_sub_state("implementing")
            mgr.advance_sub_state("all_tests_passing")
            assert mgr.current_sub_state == "all_tests_passing"

            # Test fix loop: back to implementing
            mgr.advance_sub_state("implementing")
            assert mgr.current_sub_state == "implementing"
            mgr.advance_sub_state("all_tests_passing")
            mgr.advance_sub_state("smoke_validating")

            # Smoke fails -> back to implementing
            mgr.advance_sub_state("implementing")
            assert mgr.current_sub_state == "implementing"


class TestWorkflowManagerBlocked:
    def test_block_and_unblock(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            mgr.advance_sub_state("writing_proposal")

            snap = mgr.block("need API clarification", "human-1")
            assert mgr.is_blocked
            assert snap["blockers"][0]["reason"] == "need API clarification"

            snap = mgr.unblock()
            assert not mgr.is_blocked
            assert mgr.current_phase == "planning"
            assert mgr.current_sub_state == "writing_proposal"

    def test_cannot_block_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            mgr.block("reason", "human-1")
            with pytest.raises(StateMachineError, match="already blocked"):
                mgr.block("another", "human-1")


class TestWorkflowManagerRouting:
    def test_update_routing_per_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            mgr.update_routing("reviewing", executor="codex")
            routing = mgr.routing()
            assert routing["reviewing"].executor == "codex"

    def test_routing_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            mgr.update_routing("code-review", executor="codex", session_mode="new")

            mgr2 = WorkflowManager(tmp)
            mgr2.load()
            routing = mgr2.routing()
            assert routing["code-review"].executor == "codex"


class TestWorkflowManagerProperties:
    def test_is_at_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            assert not mgr.is_at_gate
            for sub in ["writing_proposal", "writing_design", "writing_specs",
                        "writing_tasks", "ready_for_review"]:
                mgr.advance_sub_state(sub)
            assert mgr.is_at_gate

    def test_is_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            assert not mgr.is_done

    def test_transitions_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            mgr.advance_sub_state("writing_proposal")
            mgr.advance_sub_state("writing_design")
            assert len(mgr.transitions) == 2

    def test_recommended_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            assert mgr.recommended_role == "planner"

    def test_legal_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            targets = mgr.legal_targets()
            target_phases = [(t.phase, t.sub_state) for t in targets]
            assert ("blocked", None) in target_phases


class TestWorkflowManagerEdgeCases:
    def test_human_approve_not_at_gate_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            with pytest.raises(StateMachineError, match="only allowed at gate"):
                mgr.human_approve("human-1")

    def test_human_skip_not_at_gate_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            with pytest.raises(StateMachineError, match="only allowed at gate"):
                mgr.human_skip("human-1", "reason")

    def test_handoff_not_at_gate_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            with pytest.raises(StateMachineError, match="only allowed at gate"):
                mgr.handoff("reviewing", "path.md", "agent-1")

    def test_rejects_invalid_sub_state_advance(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test")
            with pytest.raises(StateMachineError, match="invalid within-phase transition"):
                mgr.advance_sub_state("ready_for_review")  # too far from exploring
