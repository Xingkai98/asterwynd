from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from agent.workflow.models import (
    CurrentAgent,
    Decision,
    PHASE_SUB_STATES,
    PhaseRouting,
    StateSnapshot,
)
from agent.workflow.state_machine import (
    StateMachineError,
    _is_gate,
    _validate_phase,
    _validate_sub_state,
    apply_transition,
    compute_next_hints,
    create_transition,
    enter_blocked,
    get_legal_targets,
    get_recommended_role,
    init_handoff_json,
    load_handoff_json,
    resolve_blocked,
    save_handoff_json,
    validate_transition,
)


# ---------------------------------------------------------------------------
# validate_transition
# ---------------------------------------------------------------------------

class TestValidateTransitionWithinPhase:
    def test_exploring_to_writing_proposal(self):
        validate_transition(
            StateSnapshot(phase="planning", sub_state="exploring"),
            StateSnapshot(phase="planning", sub_state="writing_proposal"),
            "auto",
        )

    def test_design_grill_loop_forward(self):
        validate_transition(
            StateSnapshot(phase="planning", sub_state="writing_design"),
            StateSnapshot(phase="planning", sub_state="grilling_design"),
            "auto",
        )

    def test_design_grill_loop_back(self):
        validate_transition(
            StateSnapshot(phase="planning", sub_state="grilling_design"),
            StateSnapshot(phase="planning", sub_state="writing_design"),
            "auto",
        )

    def test_tdd_loop_test_to_impl(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="test_failing"),
            StateSnapshot(phase="building", sub_state="implementing"),
            "auto",
        )

    def test_tdd_loop_back_to_writing_tests(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="test_failing"),
            StateSnapshot(phase="building", sub_state="writing_tests"),
            "auto",
        )

    def test_impl_pass_loop(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="implementing"),
            StateSnapshot(phase="building", sub_state="all_tests_passing"),
            "auto",
        )

    def test_impl_fix_loop_back(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="all_tests_passing"),
            StateSnapshot(phase="building", sub_state="implementing"),
            "auto",
        )

    def test_smoke_fail_back_to_impl(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="smoke_validating"),
            StateSnapshot(phase="building", sub_state="implementing"),
            "auto",
        )

    def test_code_review_request_changes_loop(self):
        validate_transition(
            StateSnapshot(phase="code-review", sub_state="reviewing_code"),
            StateSnapshot(phase="code-review", sub_state="requesting_changes"),
            "auto",
        )

    def test_code_review_back_to_reviewing(self):
        validate_transition(
            StateSnapshot(phase="code-review", sub_state="requesting_changes"),
            StateSnapshot(phase="code-review", sub_state="reviewing_code"),
            "auto",
        )

    def test_rejects_invalid_within_phase_jump(self):
        with pytest.raises(StateMachineError, match="invalid within-phase transition"):
            validate_transition(
                StateSnapshot(phase="planning", sub_state="exploring"),
                StateSnapshot(phase="planning", sub_state="writing_tasks"),
                "auto",
            )


class TestValidateTransitionCrossPhase:
    def test_normal_planning_to_reviewing(self):
        validate_transition(
            StateSnapshot(phase="planning", sub_state="ready_for_review"),
            StateSnapshot(phase="reviewing", sub_state="reading_docs"),
            "human_review",
        )

    def test_skip_reviewing(self):
        validate_transition(
            StateSnapshot(phase="planning", sub_state="ready_for_review"),
            StateSnapshot(phase="building", sub_state="writing_tests"),
            "human_review",
        )

    def test_reviewing_to_building(self):
        validate_transition(
            StateSnapshot(phase="reviewing", sub_state="ready_for_review"),
            StateSnapshot(phase="building", sub_state="writing_tests"),
            "human_review",
        )

    def test_building_to_code_review(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="ready_for_review"),
            StateSnapshot(phase="code-review", sub_state="reading_diff"),
            "human_review",
        )

    def test_skip_code_review(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="ready_for_review"),
            StateSnapshot(phase="closing", sub_state="syncing_specs"),
            "human_review",
        )

    def test_code_review_to_closing(self):
        validate_transition(
            StateSnapshot(phase="code-review", sub_state="ready_for_review"),
            StateSnapshot(phase="closing", sub_state="syncing_specs"),
            "human_review",
        )

    def test_closing_to_done(self):
        validate_transition(
            StateSnapshot(phase="closing", sub_state="ready_for_review"),
            StateSnapshot(phase="done", sub_state=None),
            "human_review",
        )

    def test_rejects_cross_phase_from_non_gate(self):
        with pytest.raises(StateMachineError, match="only allowed from gate"):
            validate_transition(
                StateSnapshot(phase="planning", sub_state="exploring"),
                StateSnapshot(phase="reviewing", sub_state="reading_docs"),
                "auto",
            )

    def test_rejects_invalid_cross_phase_forward(self):
        with pytest.raises(StateMachineError, match="invalid cross-phase forward"):
            validate_transition(
                StateSnapshot(phase="planning", sub_state="ready_for_review"),
                StateSnapshot(phase="code-review", sub_state="reading_diff"),
                "human_review",
            )


class TestValidateTransitionRollback:
    def test_rollback_from_building_to_planning(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="ready_for_review"),
            StateSnapshot(phase="planning", sub_state="writing_design"),
            "human_rollback",
        )

    def test_rollback_from_code_review_to_building(self):
        validate_transition(
            StateSnapshot(phase="code-review", sub_state="ready_for_review"),
            StateSnapshot(phase="building", sub_state="implementing"),
            "human_rollback",
        )

    def test_rejects_rollback_to_later_phase(self):
        with pytest.raises(StateMachineError, match="must be earlier"):
            validate_transition(
                StateSnapshot(phase="planning", sub_state="ready_for_review"),
                StateSnapshot(phase="building", sub_state="writing_tests"),
                "human_rollback",
            )

    def test_rejects_rollback_to_same_sub_state(self):
        with pytest.raises(StateMachineError, match="must be earlier"):
            validate_transition(
                StateSnapshot(phase="building", sub_state="ready_for_review"),
                StateSnapshot(phase="building", sub_state="ready_for_review"),
                "human_rollback",
            )


class TestValidateTransitionBlocked:
    def test_any_phase_to_blocked(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="implementing"),
            StateSnapshot(phase="blocked", sub_state=None),
            "auto",
        )

    def test_blocked_to_recovery(self):
        validate_transition(
            StateSnapshot(phase="blocked", sub_state=None),
            StateSnapshot(phase="building", sub_state="implementing"),
            "auto",
        )

    def test_rejects_blocked_from_blocked(self):
        with pytest.raises(StateMachineError, match="already blocked"):
            validate_transition(
                StateSnapshot(phase="blocked", sub_state=None),
                StateSnapshot(phase="blocked", sub_state=None),
                "auto",
            )

    def test_rejects_block_from_done(self):
        with pytest.raises(StateMachineError, match="cannot block from done"):
            validate_transition(
                StateSnapshot(phase="done", sub_state=None),
                StateSnapshot(phase="blocked", sub_state=None),
                "auto",
            )


class TestValidateTransitionHandoff:
    def test_handoff_self_loop_at_gate(self):
        validate_transition(
            StateSnapshot(phase="planning", sub_state="ready_for_review"),
            StateSnapshot(phase="planning", sub_state="ready_for_review"),
            "handoff",
        )

    def test_rejects_self_loop_with_auto(self):
        with pytest.raises(StateMachineError, match="self-loop only allowed with handoff"):
            validate_transition(
                StateSnapshot(phase="planning", sub_state="ready_for_review"),
                StateSnapshot(phase="planning", sub_state="ready_for_review"),
                "auto",
            )


# ---------------------------------------------------------------------------
# get_legal_targets
# ---------------------------------------------------------------------------

class TestGetLegalTargets:
    def test_from_exploring(self):
        targets = get_legal_targets(StateSnapshot(phase="planning", sub_state="exploring"))
        phases = [(t.phase, t.sub_state) for t in targets]
        assert ("planning", "writing_proposal") in phases
        assert ("blocked", None) in phases
        assert len(targets) == 2  # next sub_state + blocked

    def test_from_gate_includes_forward_targets(self):
        targets = get_legal_targets(StateSnapshot(phase="planning", sub_state="ready_for_review"))
        phases = [(t.phase, t.sub_state) for t in targets]
        assert ("reviewing", "reading_docs") in phases
        assert ("building", "writing_tests") in phases  # skip
        assert ("blocked", None) in phases

    def test_from_building_gate(self):
        targets = get_legal_targets(StateSnapshot(phase="building", sub_state="ready_for_review"))
        phases = [(t.phase, t.sub_state) for t in targets]
        assert ("code-review", "reading_diff") in phases
        assert ("closing", "syncing_specs") in phases  # skip
        assert ("blocked", None) in phases

    def test_from_done_is_empty(self):
        targets = get_legal_targets(StateSnapshot(phase="done", sub_state=None))
        assert targets == []

    def test_from_blocked_is_empty(self):
        targets = get_legal_targets(StateSnapshot(phase="blocked", sub_state=None))
        assert targets == []


# ---------------------------------------------------------------------------
# validate helpers
# ---------------------------------------------------------------------------

class TestValidatePhase:
    def test_valid_phases(self):
        for p in ("planning", "reviewing", "building", "code-review", "closing", "blocked", "done"):
            assert _validate_phase(p) == p

    def test_invalid_phase(self):
        with pytest.raises(StateMachineError, match="invalid phase"):
            _validate_phase("invalid")


class TestValidateSubState:
    def test_valid_sub_state(self):
        assert _validate_sub_state("planning", "exploring") == "exploring"

    def test_invalid_sub_state(self):
        with pytest.raises(StateMachineError, match="invalid sub_state"):
            _validate_sub_state("planning", "nonexistent")

    def test_blocked_returns_none(self):
        assert _validate_sub_state("blocked", None) is None
        assert _validate_sub_state("blocked", "anything") is None

    def test_done_returns_none(self):
        assert _validate_sub_state("done", None) is None


class TestIsGate:
    def test_gate_state_is_gate(self):
        assert _is_gate(StateSnapshot(phase="planning", sub_state="ready_for_review"))

    def test_non_gate_is_not_gate(self):
        assert not _is_gate(StateSnapshot(phase="planning", sub_state="exploring"))

    def test_blocked_is_not_gate(self):
        assert not _is_gate(StateSnapshot(phase="blocked", sub_state=None))


# ---------------------------------------------------------------------------
# handoff.json lifecycle
# ---------------------------------------------------------------------------

class TestInitHandoffJson:
    def test_minimal_init(self):
        data = init_handoff_json("my-change")
        assert data["schema_version"] == "1.0"
        assert data["change_id"] == "my-change"
        assert data["state"] == {"phase": "planning", "sub_state": "exploring"}
        assert data["transitions"] == []
        assert data["current_agent"] is None
        assert data["last_gate"] is None
        assert data["blockers"] == []
        assert "routing" in data
        for phase in ("planning", "reviewing", "building", "code-review", "closing"):
            assert phase in data["routing"]

    def test_custom_routing(self):
        custom = {
            "planning": PhaseRouting(executor="inline", session_mode="same"),
            "reviewing": PhaseRouting(executor="codex", session_mode="new"),
        }
        data = init_handoff_json("test", routing=custom)
        assert data["routing"]["reviewing"]["executor"] == "codex"
        # unreferenced phases get defaults
        assert data["routing"]["building"]["executor"] == "inline"


class TestSaveAndLoad:
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = init_handoff_json("test-change")
            save_handoff_json(tmp, data)
            loaded = load_handoff_json(tmp)
            assert loaded["change_id"] == "test-change"
            assert loaded["state"]["phase"] == "planning"

    def test_load_missing_file(self):
        with pytest.raises(StateMachineError, match="not found"):
            load_handoff_json("/nonexistent/path")

    def test_load_invalid_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "handoff.json"
            path.write_text(json.dumps({"bad": "schema"}))
            with pytest.raises(StateMachineError, match="missing required field"):
                load_handoff_json(tmp)

    def test_load_invalid_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "handoff.json"
            path.write_text(json.dumps({
                "schema_version": "1.0",
                "change_id": "test",
                "state": {"phase": "invalid", "sub_state": "x"},
                "transitions": [],
            }))
            with pytest.raises(StateMachineError, match="invalid phase"):
                load_handoff_json(tmp)


# ---------------------------------------------------------------------------
# apply_transition
# ---------------------------------------------------------------------------

class TestApplyTransition:
    def test_basic_transition(self):
        data = init_handoff_json("test")
        t = create_transition(
            from_state=StateSnapshot(phase="planning", sub_state="exploring"),
            to_state=StateSnapshot(phase="planning", sub_state="writing_proposal"),
            trigger="auto",
            actor_type="agent",
            actor_id="agent-1",
        )
        data = apply_transition(data, t)
        assert data["state"] == {"phase": "planning", "sub_state": "writing_proposal"}
        assert len(data["transitions"]) == 1

    def test_sets_last_gate_when_entering_gate(self):
        data = init_handoff_json("test")
        for sub in ["writing_proposal", "writing_design", "writing_specs", "writing_tasks", "ready_for_review"]:
            t = create_transition(
                from_state=StateSnapshot(phase=data["state"]["phase"], sub_state=data["state"]["sub_state"]),
                to_state=StateSnapshot(phase="planning", sub_state=sub),
                trigger="auto",
                actor_type="agent",
                actor_id="agent-1",
            )
            data = apply_transition(data, t)
        assert data["last_gate"] is not None
        assert data["last_gate"]["phase"] == "planning"

    def test_clears_last_gate_when_leaving_gate(self):
        data = init_handoff_json("test")
        for sub in ["writing_proposal", "writing_design", "writing_specs", "writing_tasks", "ready_for_review"]:
            t = create_transition(
                from_state=StateSnapshot(phase=data["state"]["phase"], sub_state=data["state"]["sub_state"]),
                to_state=StateSnapshot(phase="planning", sub_state=sub),
                trigger="auto",
                actor_type="agent",
                actor_id="agent-1",
            )
            data = apply_transition(data, t)
        assert data["last_gate"] is not None
        t = create_transition(
            from_state=StateSnapshot(phase="planning", sub_state="ready_for_review"),
            to_state=StateSnapshot(phase="reviewing", sub_state="reading_docs"),
            trigger="human_review",
            actor_type="human",
            actor_id="human-1",
            decision="approved",
        )
        data = apply_transition(data, t)
        assert data["last_gate"] is None
        assert data["state"]["phase"] == "reviewing"

    def test_sets_current_agent(self):
        data = init_handoff_json("test")
        t = create_transition(
            from_state=StateSnapshot(phase="planning", sub_state="exploring"),
            to_state=StateSnapshot(phase="planning", sub_state="writing_proposal"),
            trigger="auto",
            actor_type="agent",
            actor_id="agent-1",
        )
        agent = CurrentAgent(run_id="run-123", type="planner")
        data = apply_transition(data, t, current_agent=agent)
        assert data["current_agent"]["run_id"] == "run-123"
        assert data["current_agent"]["type"] == "planner"

    def test_rejects_invalid_transition(self):
        data = init_handoff_json("test")
        t = create_transition(
            from_state=StateSnapshot(phase="planning", sub_state="exploring"),
            to_state=StateSnapshot(phase="reviewing", sub_state="reading_docs"),
            trigger="auto",
            actor_type="agent",
            actor_id="agent-1",
        )
        with pytest.raises(StateMachineError, match="only allowed from gate"):
            apply_transition(data, t)


# ---------------------------------------------------------------------------
# enter_blocked / resolve_blocked
# ---------------------------------------------------------------------------

class TestBlockedFlow:
    def test_enter_and_resolve(self):
        data = init_handoff_json("test")
        data["state"] = {"phase": "building", "sub_state": "implementing"}

        data = enter_blocked(data, "waiting for dependency", "human-1")
        assert data["state"]["phase"] == "blocked"
        assert data["state"]["sub_state"] is None
        assert len(data["blockers"]) == 1
        assert data["blockers"][0]["blocked_from"] == {"phase": "building", "sub_state": "implementing"}

        data = resolve_blocked(data)
        assert data["state"]["phase"] == "building"
        assert data["state"]["sub_state"] == "implementing"
        assert data["blockers"][0]["resolved_at"] is not None

    def test_rejects_double_block(self):
        data = init_handoff_json("test")
        data = enter_blocked(data, "reason 1", "human-1")
        with pytest.raises(StateMachineError, match="already blocked"):
            enter_blocked(data, "reason 2", "human-1")

    def test_rejects_block_from_done(self):
        data = init_handoff_json("test")
        data["state"] = {"phase": "done", "sub_state": None}
        with pytest.raises(StateMachineError, match="cannot block from done"):
            enter_blocked(data, "reason", "human-1")

    def test_rejects_unblock_when_not_blocked(self):
        data = init_handoff_json("test")
        with pytest.raises(StateMachineError, match="not currently blocked"):
            resolve_blocked(data)


# ---------------------------------------------------------------------------
# get_recommended_role / compute_next_hints
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_get_recommended_role(self):
        assert get_recommended_role(StateSnapshot(phase="planning", sub_state="exploring")) == "planner"
        assert get_recommended_role(StateSnapshot(phase="reviewing", sub_state="reading_docs")) == "reviewer"
        assert get_recommended_role(StateSnapshot(phase="building", sub_state="writing_tests")) == "builder"
        assert get_recommended_role(StateSnapshot(phase="code-review", sub_state="reading_diff")) == "code-reviewer"
        assert get_recommended_role(StateSnapshot(phase="closing", sub_state="syncing_specs")) == "closer"
        assert get_recommended_role(StateSnapshot(phase="blocked")) is None
        assert get_recommended_role(StateSnapshot(phase="done")) is None

    def test_compute_next_hints_at_gate(self):
        hints = compute_next_hints(
            StateSnapshot(phase="planning", sub_state="ready_for_review"),
            ".handoff/test/note.md",
        )
        assert hints.recommended_agent == "planner"
        assert hints.entry_point == ".handoff/test/note.md"
        assert len(hints.priority_hints) > 0
        assert "gate at planning.ready_for_review" in hints.priority_hints[0]
