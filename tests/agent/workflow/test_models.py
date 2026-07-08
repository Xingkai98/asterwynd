from __future__ import annotations

import pytest

from agent.workflow.models import (
    DEFAULT_ROUTING,
    GATE_SUB_STATE,
    PHASE_ORDER,
    PHASE_SUB_STATES,
    PHASE_TO_ROLE,
    PHASES,
    SESSION_MODES,
    TRIGGERS,
    Blocker,
    CurrentAgent,
    LastGate,
    NextHints,
    PhaseRouting,
    StateSnapshot,
    Transition,
)


class TestEnums:
    def test_phases_include_all_states(self):
        assert "planning" in PHASES
        assert "reviewing" in PHASES
        assert "building" in PHASES
        assert "code-review" in PHASES
        assert "closing" in PHASES
        assert "blocked" in PHASES
        assert "done" in PHASES
        assert len(PHASES) == 7

    def test_triggers_have_four_types(self):
        assert "auto" in TRIGGERS
        assert "handoff" in TRIGGERS
        assert "human_review" in TRIGGERS
        assert "human_rollback" in TRIGGERS
        assert len(TRIGGERS) == 4

    def test_session_modes(self):
        assert "same" in SESSION_MODES
        assert "new" in SESSION_MODES
        assert "ask" in SESSION_MODES

    def test_gate_sub_state_is_ready_for_review(self):
        assert GATE_SUB_STATE == "ready_for_review"

    def test_every_non_terminal_phase_has_gate(self):
        for phase in ("planning", "reviewing", "building", "code-review", "closing"):
            assert GATE_SUB_STATE in PHASE_SUB_STATES[phase]

    def test_phase_maps_to_role(self):
        assert PHASE_TO_ROLE["planning"] == "planner"
        assert PHASE_TO_ROLE["reviewing"] == "reviewer"
        assert PHASE_TO_ROLE["building"] == "builder"
        assert PHASE_TO_ROLE["code-review"] == "code-reviewer"
        assert PHASE_TO_ROLE["closing"] == "closer"

    def test_blocked_and_done_not_in_role_map(self):
        assert "blocked" not in PHASE_TO_ROLE
        assert "done" not in PHASE_TO_ROLE


class TestStateSnapshot:
    def test_to_dict(self):
        s = StateSnapshot(phase="planning", sub_state="exploring")
        assert s.to_dict() == {"phase": "planning", "sub_state": "exploring"}

    def test_default_sub_state_is_none(self):
        s = StateSnapshot(phase="blocked")
        assert s.sub_state is None


class TestTransition:
    def test_minimal_to_dict(self):
        t = Transition(
            from_state=StateSnapshot(phase="planning", sub_state="exploring"),
            to_state=StateSnapshot(phase="planning", sub_state="writing_proposal"),
            trigger="auto",
            actor_type="agent",
            actor_id="test-1",
            timestamp="2024-01-01T00:00:00Z",
        )
        d = t.to_dict()
        assert d["from"] == {"phase": "planning", "sub_state": "exploring"}
        assert d["to"] == {"phase": "planning", "sub_state": "writing_proposal"}
        assert d["trigger"] == "auto"
        assert d["actor_type"] == "agent"
        assert d["actor_id"] == "test-1"

    def test_full_to_dict(self):
        t = Transition(
            from_state=StateSnapshot(phase="planning", sub_state="ready_for_review"),
            to_state=StateSnapshot(phase="reviewing", sub_state="reading_docs"),
            trigger="human_review",
            actor_type="human",
            actor_id="human-1",
            timestamp="2024-01-01T00:00:00Z",
            decision="approved",
            reason="looks good",
        )
        d = t.to_dict()
        assert d["decision"] == "approved"
        assert d["reason"] == "looks good"

    def test_optional_fields_excluded_when_none(self):
        t = Transition(
            from_state=StateSnapshot(phase="planning", sub_state="exploring"),
            to_state=StateSnapshot(phase="planning", sub_state="writing_proposal"),
            trigger="auto",
            actor_type="agent",
            actor_id="test-1",
            timestamp="2024-01-01T00:00:00Z",
        )
        d = t.to_dict()
        assert "handoff_note" not in d
        assert "decision" not in d
        assert "rollback_reason" not in d
        assert "skip_reason" not in d


class TestCurrentAgent:
    def test_to_dict(self):
        a = CurrentAgent(run_id="run-123", type="planner")
        assert a.to_dict() == {"run_id": "run-123", "type": "planner"}


class TestLastGate:
    def test_to_dict(self):
        g = LastGate(phase="planning", sub_state="ready_for_review")
        d = g.to_dict()
        assert d["phase"] == "planning"
        assert d["sub_state"] == "ready_for_review"
        assert d["awaiting"] == "human_review"


class TestBlocker:
    def test_minimal_to_dict(self):
        b = Blocker(
            blocked_from=StateSnapshot(phase="building", sub_state="implementing"),
            reason="waiting for API key",
            blocked_at="2024-01-01T00:00:00Z",
        )
        d = b.to_dict()
        assert d["blocked_from"] == {"phase": "building", "sub_state": "implementing"}
        assert d["reason"] == "waiting for API key"
        assert "resolved_at" not in d

    def test_with_resolved_at(self):
        b = Blocker(
            blocked_from=StateSnapshot(phase="building", sub_state="implementing"),
            reason="waiting",
            blocked_at="2024-01-01T00:00:00Z",
            resolved_at="2024-01-02T00:00:00Z",
        )
        d = b.to_dict()
        assert d["resolved_at"] == "2024-01-02T00:00:00Z"


class TestPhaseRouting:
    def test_to_dict(self):
        r = PhaseRouting(executor="subagent", session_mode="new")
        assert r.to_dict() == {"executor": "subagent", "session_mode": "new"}


class TestNextHints:
    def test_empty(self):
        h = NextHints()
        assert h.to_dict() == {}

    def test_full(self):
        h = NextHints(
            recommended_agent="builder",
            entry_point=".handoff/test/planning-to-building.md",
            priority_hints=["run tests first", "check design.md"],
        )
        d = h.to_dict()
        assert d["recommended_agent"] == "builder"
        assert d["entry_point"] == ".handoff/test/planning-to-building.md"
        assert len(d["priority_hints"]) == 2


class TestPhaseOrder:
    def test_all_phases_have_order(self):
        for phase in PHASES:
            assert phase in PHASE_ORDER, f"{phase} missing from PHASE_ORDER"

    def test_order_values_are_correct(self):
        assert PHASE_ORDER["planning"] == 0
        assert PHASE_ORDER["reviewing"] == 1
        assert PHASE_ORDER["building"] == 2
        assert PHASE_ORDER["code-review"] == 3
        assert PHASE_ORDER["closing"] == 4
        assert PHASE_ORDER["blocked"] == -1
        assert PHASE_ORDER["done"] == 5

    def test_active_phases_are_monotonically_increasing(self):
        active_order = [
            PHASE_ORDER[p]
            for p in ("planning", "reviewing", "building", "code-review", "closing")
        ]
        assert active_order == sorted(active_order)

    def test_blocked_is_less_than_all_active_phases(self):
        for phase in ("planning", "reviewing", "building", "code-review", "closing"):
            assert PHASE_ORDER["blocked"] < PHASE_ORDER[phase]

    def test_done_is_greater_than_all_active_phases(self):
        for phase in ("planning", "reviewing", "building", "code-review", "closing"):
            assert PHASE_ORDER["done"] > PHASE_ORDER[phase]


class TestDefaultRouting:
    def test_all_phases_have_defaults(self):
        for phase in ("planning", "reviewing", "building", "code-review", "closing"):
            assert phase in DEFAULT_ROUTING
            assert DEFAULT_ROUTING[phase].executor in ("inline", "subagent", "claude-code", "codex")
            assert DEFAULT_ROUTING[phase].session_mode in ("same", "new", "ask")

    def test_reviewing_defaults_to_subagent_new(self):
        assert DEFAULT_ROUTING["reviewing"].executor == "subagent"
        assert DEFAULT_ROUTING["reviewing"].session_mode == "new"

    def test_code_review_defaults_to_subagent_new(self):
        assert DEFAULT_ROUTING["code-review"].executor == "subagent"
        assert DEFAULT_ROUTING["code-review"].session_mode == "new"
