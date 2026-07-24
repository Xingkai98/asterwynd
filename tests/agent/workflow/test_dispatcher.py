from __future__ import annotations

import tempfile

import pytest

from agent.workflow.dispatcher import DispatchResult, WorkflowDispatcher
from agent.workflow.manager import WorkflowManager
from agent.workflow.models import Phase
from agent.workflow.state_machine import StateMachineError


class FakeSubAgentManager:
    """Fake SubAgentManager for testing dispatcher without real subagent runtime."""

    def __init__(self):
        self.created_subagents: list[dict] = []

    def create_subagent(self, *, name: str, description: str, mode=None) -> dict:
        summary = {
            "subagent_id": f"fake-{len(self.created_subagents)}",
            "name": name,
            "description": description,
            "mode": "build" if mode is None else str(mode),
        }
        self.created_subagents.append(summary)
        return summary

    def run_subagent(self, *, subagent_id: str, task: str, wait=False, timeout_s=None):
        return {"subagent_id": subagent_id, "status": "completed", "summary": "done"}

    def configure_runtime(self, **kwargs):
        pass


class TestWorkflowDispatcher:
    def test_dispatch_current_phase_planning_inline(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")

            dispatcher = WorkflowDispatcher(tmp, subagent_manager=FakeSubAgentManager())
            result = dispatcher.dispatch_current_phase()

            assert result.executor == "inline"
            assert result.phase == "planning"
            assert result.role_type == "planner"
            assert result.session_mode == "same"
            assert result.subagent_id is None
            assert result.inline_context is not None

    def test_dispatch_phase_uses_subagent_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")
            mgr.update_routing("building", executor="subagent", session_mode="new")

            fake = FakeSubAgentManager()
            dispatcher = WorkflowDispatcher(tmp, subagent_manager=fake)

            result = dispatcher.dispatch_phase("building")
            assert result.executor == "subagent"
            assert result.role_type == "builder"
            assert result.subagent_id is not None
            assert len(fake.created_subagents) == 1

    def test_dispatch_phase_claude_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")
            mgr.update_routing("building", executor="claude-code", session_mode="new")

            dispatcher = WorkflowDispatcher(tmp, subagent_manager=FakeSubAgentManager())
            result = dispatcher.dispatch_phase("building")

            assert result.executor == "claude-code"
            assert result.role_type == "builder"
            assert result.cli_command is not None
            assert "claude-code" in result.cli_command

    def test_dispatch_phase_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")
            mgr.update_routing("planning", executor="codex", session_mode="new")

            dispatcher = WorkflowDispatcher(tmp, subagent_manager=FakeSubAgentManager())
            result = dispatcher.dispatch_phase("planning")

            assert result.executor == "codex"
            assert "codex exec" in result.cli_command

    def test_dispatch_subagent_without_manager_falls_back_to_inline(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")
            mgr.update_routing("planning", executor="subagent", session_mode="new")

            dispatcher = WorkflowDispatcher(tmp)  # no subagent_manager
            result = dispatcher.dispatch_phase("planning")

            assert result.executor == "inline"
            assert result.inline_context is not None
            assert "subagent_manager not configured" in result.inline_context["fallback_reason"]

    def test_dispatch_blocked_phase_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")
            mgr.block("blocked for testing", "test")

            dispatcher = WorkflowDispatcher(tmp, subagent_manager=FakeSubAgentManager())
            with pytest.raises(ValueError, match="cannot dispatch from terminal phase"):
                dispatcher.dispatch_current_phase()

    def test_dispatch_done_phase_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")
            mgr._data["state"] = {"phase": "done", "sub_state": None}
            from agent.workflow.state_machine import save_handoff_json
            save_handoff_json(tmp, mgr._data)

            dispatcher = WorkflowDispatcher(tmp, subagent_manager=FakeSubAgentManager())
            with pytest.raises(ValueError, match="cannot dispatch from terminal phase"):
                dispatcher.dispatch_current_phase()

    def test_dispatch_result_to_dict(self):
        result = DispatchResult(
            executor="inline",
            session_mode="same",
            phase="planning",
            role_type="planner",
            task_prompt="do planning work",
            inline_context={"change_dir": "/tmp/test"},
        )
        d = result.to_dict()
        assert d["executor"] == "inline"
        assert d["phase"] == "planning"
        assert d["role_type"] == "planner"

    def test_dispatch_result_to_dict_with_subagent(self):
        result = DispatchResult(
            executor="subagent",
            session_mode="new",
            phase="building",
            role_type="builder",
            task_prompt="build the feature",
            subagent_id="sa-123",
            subagent_summary={"subagent_id": "sa-123", "name": "Builder"},
        )
        d = result.to_dict()
        assert d["subagent_id"] == "sa-123"
        assert d["subagent_summary"]["name"] == "Builder"


class TestApproveAndDispatch:
    def test_approve_at_gate_dispatches_building(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp, repo_root=tmp)
            mgr.init("test-change")
            for sub in ["writing_proposal", "writing_design", "writing_spec",
                        "writing_tickets", "reviewing_artifacts", "ready_for_review"]:
                mgr.advance_sub_state(sub)

            dispatcher = WorkflowDispatcher(tmp, repo_root=tmp, subagent_manager=FakeSubAgentManager())
            result = dispatcher.approve_and_dispatch("human-1", "approved")

            assert result.phase == "building"
            assert result.role_type == "builder"
            assert result.executor == "inline"

    def test_approve_to_done_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp, repo_root=tmp)
            mgr.init("test-change")
            for sub in ["writing_proposal", "writing_design", "writing_spec",
                        "writing_tickets", "reviewing_artifacts", "ready_for_review"]:
                mgr.advance_sub_state(sub)
            mgr.human_approve("human-1")
            # Already at building.writing_tests after approve
            for sub in ["implementing", "all_tests_passing",
                        "smoke_validating", "reviewing_impl", "ready_for_review"]:
                mgr.advance_sub_state(sub)
            mgr.human_approve("human-1")
            # Already at closing.syncing_specs after approve
            for sub in ["archiving", "updating_backlog",
                        "validating", "pr_ready", "reviewing_archive", "ready_for_review"]:
                mgr.advance_sub_state(sub)

            dispatcher = WorkflowDispatcher(tmp, repo_root=tmp, subagent_manager=FakeSubAgentManager())
            with pytest.raises(ValueError, match="workflow complete"):
                dispatcher.approve_and_dispatch("human-1", "done")

    def test_approve_not_at_gate_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp, repo_root=tmp)
            mgr.init("test-change")

            dispatcher = WorkflowDispatcher(tmp, repo_root=tmp, subagent_manager=FakeSubAgentManager())
            with pytest.raises(StateMachineError, match="only allowed at gate"):
                dispatcher.approve_and_dispatch("human-1", "premature")

    def test_approve_dispatches_inline_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp, repo_root=tmp)
            mgr.init("test-change")
            mgr.update_routing("building", executor="inline", session_mode="same")
            for sub in ["writing_proposal", "writing_design", "writing_spec",
                        "writing_tickets", "reviewing_artifacts", "ready_for_review"]:
                mgr.advance_sub_state(sub)

            dispatcher = WorkflowDispatcher(tmp, repo_root=tmp, subagent_manager=FakeSubAgentManager())
            result = dispatcher.approve_and_dispatch("human-1", "approved")

            assert result.executor == "inline"
            assert result.phase == "building"


class TestSkipAndDispatch:
    def test_skip_not_available_in_four_phase_model(self):
        """In 4-phase model each gate has one forward path — skip raises."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")
            for sub in ["writing_proposal", "writing_design", "writing_spec",
                        "writing_tickets", "reviewing_artifacts", "ready_for_review"]:
                mgr.advance_sub_state(sub)

            dispatcher = WorkflowDispatcher(tmp, subagent_manager=FakeSubAgentManager())
            with pytest.raises(StateMachineError, match="no skip target"):
                dispatcher.skip_and_dispatch("human-1", "cannot skip")

    def test_skip_not_at_gate_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = WorkflowManager(tmp)
            mgr.init("test-change")

            dispatcher = WorkflowDispatcher(tmp, subagent_manager=FakeSubAgentManager())
            with pytest.raises(StateMachineError, match="only allowed at gate"):
                dispatcher.skip_and_dispatch("human-1", "too early")
