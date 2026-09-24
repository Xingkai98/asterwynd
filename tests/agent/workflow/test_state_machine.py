from __future__ import annotations

import pytest

from agent.workflow.models import (
    GATE_SUB_STATE,
    PHASES as ALL_PHASES,
    StateSnapshot,
)
from agent.workflow.state_machine import (
    CROSS_PHASE_FORWARD,
    WITHIN_PHASE_ADJACENT,
    StateMachineError,
    compute_next_hints,
    get_legal_targets,
    get_recommended_role,
    validate_transition,
    _is_gate,
)

_ACTIVE_PHASES = ("wayfinding", "planning", "building", "closing")


class TestIsGate:
    def test_gate_sub_state_is_gate(self):
        for phase in _ACTIVE_PHASES:
            assert _is_gate(StateSnapshot(phase=phase, sub_state=GATE_SUB_STATE))

    def test_non_gate_is_not_gate(self):
        assert not _is_gate(StateSnapshot(phase="planning", sub_state="exploring"))
        assert not _is_gate(StateSnapshot(phase="building", sub_state="implementing"))

    def test_blocked_and_done_are_not_gate(self):
        assert not _is_gate(StateSnapshot(phase="blocked", sub_state=None))
        assert not _is_gate(StateSnapshot(phase="done", sub_state=None))


class TestValidateTransitionWithinPhase:
    def test_normal_planning_flow(self):
        validate_transition(
            StateSnapshot(phase="planning", sub_state="exploring"),
            StateSnapshot(phase="planning", sub_state="writing_proposal"),
            "auto",
        )

    def test_building_tdd_loop(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="test_failing"),
            StateSnapshot(phase="building", sub_state="writing_tests"),
            "auto",
        )
        validate_transition(
            StateSnapshot(phase="building", sub_state="test_failing"),
            StateSnapshot(phase="building", sub_state="implementing"),
            "auto",
        )

    def test_building_smoke_loop(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="smoke_validating"),
            StateSnapshot(phase="building", sub_state="implementing"),
            "auto",
        )

    def test_rejects_invalid_within_phase_jump(self):
        with pytest.raises(StateMachineError, match="invalid within-phase"):
            validate_transition(
                StateSnapshot(phase="building", sub_state="writing_tests"),
                StateSnapshot(phase="building", sub_state="ready_for_review"),
                "auto",
            )

    def test_handoff_self_loop(self):
        validate_transition(
            StateSnapshot(phase="planning", sub_state="exploring"),
            StateSnapshot(phase="planning", sub_state="exploring"),
            "handoff",
        )


class TestValidateTransitionCrossPhase:
    def test_planning_to_building(self):
        validate_transition(
            StateSnapshot(phase="planning", sub_state="ready_for_review"),
            StateSnapshot(phase="building", sub_state="writing_tests"),
            "auto",
        )

    def test_building_to_closing(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="ready_for_review"),
            StateSnapshot(phase="closing", sub_state="syncing_specs"),
            "auto",
        )

    def test_wayfinding_to_planning(self):
        validate_transition(
            StateSnapshot(phase="wayfinding", sub_state="ready_for_review"),
            StateSnapshot(phase="planning", sub_state="exploring"),
            "auto",
        )

    def test_rejects_cross_phase_from_non_gate(self):
        with pytest.raises(StateMachineError, match="cross-phase"):
            validate_transition(
                StateSnapshot(phase="planning", sub_state="writing_design"),
                StateSnapshot(phase="building", sub_state="writing_tests"),
                "auto",
            )

    def test_rejects_invalid_cross_phase_forward(self):
        with pytest.raises(StateMachineError, match="invalid cross-phase"):
            validate_transition(
                StateSnapshot(phase="planning", sub_state="ready_for_review"),
                StateSnapshot(phase="closing", sub_state="syncing_specs"),
                "auto",
            )

    def test_closing_to_done(self):
        validate_transition(
            StateSnapshot(phase="closing", sub_state="ready_for_review"),
            StateSnapshot(phase="done", sub_state=None),
            "auto",
        )


class TestValidateTransitionRollback:
    def test_rollback_within_phase(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="implementing"),
            StateSnapshot(phase="building", sub_state="writing_tests"),
            "human_rollback",
        )

    def test_rollback_cross_phase(self):
        validate_transition(
            StateSnapshot(phase="building", sub_state="implementing"),
            StateSnapshot(phase="planning", sub_state="writing_design"),
            "human_rollback",
        )

    def test_rollback_must_go_earlier(self):
        with pytest.raises(StateMachineError, match="must be earlier"):
            validate_transition(
                StateSnapshot(phase="building", sub_state="writing_tests"),
                StateSnapshot(phase="building", sub_state="implementing"),
                "human_rollback",
            )


class TestGetLegalTargets:
    def test_planning_exploring_targets(self):
        targets = get_legal_targets(StateSnapshot(phase="planning", sub_state="exploring"))
        target_ids = [(t.phase, t.sub_state) for t in targets if t.phase != "blocked"]
        assert ("planning", "writing_proposal") in target_ids

    def test_gate_has_cross_phase_targets(self):
        targets = get_legal_targets(StateSnapshot(phase="planning", sub_state="ready_for_review"))
        assert any(t.phase == "building" for t in targets)

    def test_done_has_no_targets(self):
        assert get_legal_targets(StateSnapshot(phase="done", sub_state=None)) == []

    def test_blocked_has_no_targets(self):
        assert get_legal_targets(StateSnapshot(phase="blocked", sub_state=None)) == []

    def test_blocked_is_always_an_option(self):
        targets = get_legal_targets(StateSnapshot(phase="closing", sub_state="pr_ready"))
        assert any(t.phase == "blocked" for t in targets)


class TestHelpers:
    def test_get_recommended_role(self):
        assert get_recommended_role(StateSnapshot(phase="wayfinding", sub_state="charting_map")) == "wayfinder"
        assert get_recommended_role(StateSnapshot(phase="planning", sub_state="exploring")) == "planner"
        assert get_recommended_role(StateSnapshot(phase="building", sub_state="implementing")) == "builder"
        assert get_recommended_role(StateSnapshot(phase="closing", sub_state="archiving")) == "closer"

    def test_blocked_and_done_return_none(self):
        assert get_recommended_role(StateSnapshot(phase="blocked", sub_state=None)) is None
        assert get_recommended_role(StateSnapshot(phase="done", sub_state=None)) is None

    def test_compute_next_hints(self):
        hints = compute_next_hints(StateSnapshot(phase="planning", sub_state="ready_for_review"))
        assert hints.recommended_agent == "planner"
        assert len(hints.priority_hints) >= 1


class TestCrossoverCoverage:
    def test_every_active_phase_has_within_phase_adjacent(self):
        for p in _ACTIVE_PHASES:
            assert p in WITHIN_PHASE_ADJACENT

    def test_every_active_phase_has_gate_transition(self):
        for p in _ACTIVE_PHASES:
            assert (p, GATE_SUB_STATE) in CROSS_PHASE_FORWARD
