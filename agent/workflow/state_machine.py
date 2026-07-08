from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.workflow.models import (
    DEFAULT_ROUTING,
    GATE_SUB_STATE,
    PHASE_ORDER,
    PHASE_SUB_STATES,
    PHASE_TO_ROLE,
    PHASES,
    Blocker,
    CurrentAgent,
    Decision,
    LastGate,
    NextHints,
    Phase,
    PhaseRouting,
    RoleAgentType,
    StateSnapshot,
    SubState,
    Transition,
    Trigger,
)


class StateMachineError(ValueError):
    pass


def _validate_phase(phase: str) -> Phase:
    if phase not in PHASES:
        raise StateMachineError(f"invalid phase: {phase!r}, expected one of {PHASES}")
    return phase


def _validate_sub_state(phase: Phase, sub_state: str | None) -> SubState | None:
    if phase in ("blocked", "done"):
        return None
    valid = PHASE_SUB_STATES.get(phase)
    if valid is None:
        raise StateMachineError(f"no sub_states defined for phase: {phase}")
    if sub_state not in valid:
        raise StateMachineError(
            f"invalid sub_state {sub_state!r} for phase {phase!r}, expected one of {valid}"
        )
    return sub_state


def _is_gate(state: StateSnapshot) -> bool:
    return state.sub_state == GATE_SUB_STATE and state.phase not in ("blocked", "done")


def _phase_index(phase: Phase) -> int:
    return PHASE_ORDER[phase]


# Legal cross-phase forward transitions: from_state -> to_state
CROSS_PHASE_FORWARD: dict[tuple[Phase, SubState], list[tuple[Phase, SubState]]] = {
    ("planning", "ready_for_review"): [
        ("reviewing", "reading_docs"),
        ("building", "writing_tests"),  # skip reviewing
    ],
    ("reviewing", "ready_for_review"): [
        ("building", "writing_tests"),
    ],
    ("building", "ready_for_review"): [
        ("code-review", "reading_diff"),
        ("closing", "syncing_specs"),  # skip code-review
    ],
    ("code-review", "ready_for_review"): [
        ("closing", "syncing_specs"),
    ],
    ("closing", "ready_for_review"): [
        ("done", None),
    ],
}

# Legal within-phase sub_state adjacency (sequential, with loops where noted)
WITHIN_PHASE_ADJACENT: dict[Phase, dict[SubState, list[SubState | None]]] = {
    "planning": {
        "exploring": ["writing_proposal"],
        "writing_proposal": ["writing_design"],
        "writing_design": ["grilling_design", "writing_specs"],
        "grilling_design": ["writing_design", "writing_specs"],  # loop back or advance
        "writing_specs": ["writing_tasks"],
        "writing_tasks": ["ready_for_review"],
        "ready_for_review": [],
    },
    "reviewing": {
        "reading_docs": ["reviewing_design"],
        "reviewing_design": ["ready_for_review"],
        "ready_for_review": [],
    },
    "building": {
        "writing_tests": ["test_failing", "implementing"],
        "test_failing": ["writing_tests", "implementing"],  # TDD loop
        "implementing": ["all_tests_passing", "writing_tests"],
        "all_tests_passing": ["implementing", "smoke_validating"],  # fix loop
        "smoke_validating": ["implementing", "ready_for_review"],  # fail -> back to implement
        "ready_for_review": [],
    },
    "code-review": {
        "reading_diff": ["analyzing_tests"],
        "analyzing_tests": ["reviewing_code"],
        "reviewing_code": ["requesting_changes", "ready_for_review"],
        "requesting_changes": ["reviewing_code", "ready_for_review"],
        "ready_for_review": [],
    },
    "closing": {
        "syncing_specs": ["archiving"],
        "archiving": ["updating_backlog"],
        "updating_backlog": ["validating"],
        "validating": ["pr_ready"],
        "pr_ready": ["ready_for_review"],
        "ready_for_review": [],
    },
}


def validate_transition(
    from_state: StateSnapshot,
    to_state: StateSnapshot,
    trigger: Trigger,
) -> None:
    """Validate a state transition, raising StateMachineError if invalid."""

    if from_state.phase not in ("blocked", "done"):
        _validate_sub_state(from_state.phase, from_state.sub_state)
    if to_state.phase not in ("blocked", "done"):
        _validate_sub_state(to_state.phase, to_state.sub_state)

    # blocked transitions
    if to_state.phase == "blocked":
        if from_state.phase == "blocked":
            raise StateMachineError("already blocked")
        if from_state.phase == "done":
            raise StateMachineError("cannot block from done")
        return  # any phase -> blocked is valid

    if from_state.phase == "blocked":
        return  # blocked -> recovery is valid (caller sets correct target)

    # done transitions
    if to_state.phase == "done":
        if from_state.phase != "closing" or from_state.sub_state != "ready_for_review":
            raise StateMachineError("only closing.ready_for_review can transition to done")
        if trigger == "human_rollback":
            raise StateMachineError("cannot rollback to done")
        return

    # same state self-loop: only allowed for handoff trigger (marks handoff moment)
    if from_state.phase == to_state.phase and from_state.sub_state == to_state.sub_state:
        if trigger == "handoff":
            return
        if trigger == "human_rollback":
            raise StateMachineError(
                f"rollback target sub_state {to_state.sub_state!r} must be earlier "
                f"than current sub_state {from_state.sub_state!r} "
                f"in phase {from_state.phase}"
            )
        raise StateMachineError(
            f"self-loop only allowed with handoff trigger, "
            f"got {trigger} for {from_state.phase}.{from_state.sub_state}"
        )

    # within-phase human_rollback: can jump backwards to any earlier sub_state
    if trigger == "human_rollback" and from_state.phase == to_state.phase:
        sub_states = list(PHASE_SUB_STATES.get(from_state.phase, ()))
        if from_state.sub_state not in sub_states or to_state.sub_state not in sub_states:
            raise StateMachineError(
                f"invalid sub_state for rollback in phase {from_state.phase}"
            )
        from_idx = sub_states.index(from_state.sub_state)
        to_idx = sub_states.index(to_state.sub_state)
        if to_idx >= from_idx:
            raise StateMachineError(
                f"rollback target sub_state {to_state.sub_state!r} must be earlier "
                f"than current sub_state {from_state.sub_state!r} "
                f"in phase {from_state.phase}"
            )
        return

    # same phase: within-phase adjacency check
    if from_state.phase == to_state.phase:
        adjacent = WITHIN_PHASE_ADJACENT.get(from_state.phase, {})
        valid_next = adjacent.get(from_state.sub_state, [])
        if to_state.sub_state not in valid_next:
            raise StateMachineError(
                f"invalid within-phase transition: "
                f"{from_state.phase}.{from_state.sub_state} -> "
                f"{to_state.phase}.{to_state.sub_state}. "
                f"Valid next sub_states: {valid_next}"
            )
        return

    # cross-phase transition
    if trigger == "human_rollback":
        # rollback: target phase must be earlier (allowed from any sub_state, not just gate)
        from_idx = _phase_index(from_state.phase)
        to_idx = _phase_index(to_state.phase)
        if to_idx < 0:
            raise StateMachineError(f"cannot rollback to {to_state.phase}")
        if to_idx >= from_idx:
            raise StateMachineError(
                f"rollback target phase {to_state.phase!r} must be earlier "
                f"than current phase {from_state.phase!r}"
            )
        _validate_sub_state(to_state.phase, to_state.sub_state)
        return

    # forward cross-phase — must be from a gate
    if not _is_gate(from_state):
        raise StateMachineError(
            f"cross-phase transition only allowed from gate sub_state, "
            f"got {from_state.phase}.{from_state.sub_state}"
        )
    key = (from_state.phase, from_state.sub_state)
    valid_targets = CROSS_PHASE_FORWARD.get(key, [])
    target = (to_state.phase, to_state.sub_state)
    if target not in valid_targets:
        raise StateMachineError(
            f"invalid cross-phase forward transition: "
            f"{from_state.phase}.{from_state.sub_state} -> "
            f"{to_state.phase}.{to_state.sub_state}. "
            f"Valid targets: {valid_targets}"
        )


def get_legal_targets(from_state: StateSnapshot) -> list[StateSnapshot]:
    """Return all legal next states from a given state."""
    targets: list[StateSnapshot] = []

    if from_state.phase == "done":
        return targets

    if from_state.phase == "blocked":
        return targets  # recovery target is determined by blocked_from

    # within-phase targets
    adjacent = WITHIN_PHASE_ADJACENT.get(from_state.phase, {})
    for next_sub in adjacent.get(from_state.sub_state, []):
        targets.append(StateSnapshot(phase=from_state.phase, sub_state=next_sub))

    # blocked is always an option (except from done, handled above)
    targets.append(StateSnapshot(phase="blocked", sub_state=None))

    # cross-phase forward from gate
    if _is_gate(from_state):
        key = (from_state.phase, from_state.sub_state)
        for t_phase, t_sub in CROSS_PHASE_FORWARD.get(key, []):
            targets.append(StateSnapshot(phase=t_phase, sub_state=t_sub))

    return targets


def create_transition(
    from_state: StateSnapshot,
    to_state: StateSnapshot,
    trigger: Trigger,
    actor_type: str,
    actor_id: str,
    handoff_note: str | None = None,
    decision: Decision | None = None,
    reason: str | None = None,
    rollback_reason: str | None = None,
    skip_reason: str | None = None,
) -> Transition:
    return Transition(
        from_state=from_state,
        to_state=to_state,
        trigger=trigger,
        actor_type=actor_type,
        actor_id=actor_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        handoff_note=handoff_note,
        decision=decision,
        reason=reason,
        rollback_reason=rollback_reason,
        skip_reason=skip_reason,
    )


def init_handoff_json(
    change_id: str,
    routing: dict[Phase, PhaseRouting] | None = None,
) -> dict[str, Any]:
    """Generate the initial handoff.json content for a new change."""
    resolved_routing: dict[str, dict] = {}
    defaults = routing or DEFAULT_ROUTING
    for phase in ("planning", "reviewing", "building", "code-review", "closing"):
        r = defaults.get(phase, DEFAULT_ROUTING.get(phase))
        if r is None:
            r = PhaseRouting(executor="inline", session_mode="same")
        resolved_routing[phase] = r.to_dict()

    return {
        "schema_version": "1.0",
        "change_id": change_id,
        "state": {"phase": "planning", "sub_state": "exploring"},
        "transitions": [],
        "current_agent": None,
        "last_gate": None,
        "blockers": [],
        "routing": resolved_routing,
        "next_hints": {},
    }


def load_handoff_json(change_dir: str | Path) -> dict[str, Any]:
    path = Path(change_dir) / "handoff.json"
    if not path.exists():
        raise StateMachineError(f"handoff.json not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _validate_handoff_json_structure(data)
    return data


def save_handoff_json(change_dir: str | Path, data: dict[str, Any]) -> None:
    path = Path(change_dir) / "handoff.json"
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))


def _validate_handoff_json_structure(data: dict[str, Any]) -> None:
    required = ["schema_version", "change_id", "state", "transitions"]
    for key in required:
        if key not in data:
            raise StateMachineError(f"handoff.json missing required field: {key}")

    state = data["state"]
    if "phase" not in state:
        raise StateMachineError("handoff.json state missing phase")
    phase = state["phase"]
    _validate_phase(phase)
    if "sub_state" not in state:
        raise StateMachineError("handoff.json state missing sub_state")
    _validate_sub_state(phase, state["sub_state"])

    if not isinstance(data["transitions"], list):
        raise StateMachineError("handoff.json transitions must be an array")


def apply_transition(
    data: dict[str, Any],
    transition: Transition,
    current_agent: CurrentAgent | None = None,
) -> dict[str, Any]:
    """Apply a validated transition to the handoff.json data, returning updated data."""
    validate_transition(transition.from_state, transition.to_state, transition.trigger)

    data["state"] = transition.to_state.to_dict()
    data["transitions"].append(transition.to_dict())

    if current_agent is not None:
        data["current_agent"] = current_agent.to_dict()

    # update last_gate
    if _is_gate(transition.to_state):
        data["last_gate"] = LastGate(
            phase=transition.to_state.phase,
            sub_state=transition.to_state.sub_state,
        ).to_dict()
    else:
        data["last_gate"] = None

    return data


def enter_blocked(
    data: dict[str, Any],
    reason: str,
    actor_id: str,
) -> dict[str, Any]:
    """Transition into blocked state."""
    current = StateSnapshot(
        phase=data["state"]["phase"],
        sub_state=data["state"]["sub_state"],
    )
    if current.phase == "blocked":
        raise StateMachineError("already blocked")
    if current.phase == "done":
        raise StateMachineError("cannot block from done")

    now = datetime.now(timezone.utc).isoformat()
    blocker = Blocker(blocked_from=current, reason=reason, blocked_at=now)

    transition = create_transition(
        from_state=current,
        to_state=StateSnapshot(phase="blocked", sub_state=None),
        trigger="auto",
        actor_type="human",
        actor_id=actor_id,
        reason=reason,
    )

    data["state"] = {"phase": "blocked", "sub_state": None}
    data["transitions"].append(transition.to_dict())
    data["last_gate"] = None
    data["blockers"].append(blocker.to_dict())
    return data


def resolve_blocked(
    data: dict[str, Any],
    blocker_index: int = 0,
) -> dict[str, Any]:
    """Resolve the last blocker and restore state from blocked_from."""
    if data["state"]["phase"] != "blocked":
        raise StateMachineError("not currently blocked")
    if not data["blockers"]:
        raise StateMachineError("no blockers to resolve")

    blocker = data["blockers"][blocker_index]
    blocked_from = StateSnapshot(
        phase=blocker["blocked_from"]["phase"],
        sub_state=blocker["blocked_from"]["sub_state"],
    )
    now = datetime.now(timezone.utc).isoformat()
    blocker["resolved_at"] = now

    transition = create_transition(
        from_state=StateSnapshot(phase="blocked", sub_state=None),
        to_state=blocked_from,
        trigger="auto",
        actor_type="human",
        actor_id="system",
        reason=f"blocker resolved: {blocker.get('reason', '')}",
    )

    data["state"] = blocked_from.to_dict()
    data["transitions"].append(transition.to_dict())
    return data


def get_recommended_role(state: StateSnapshot) -> RoleAgentType | None:
    """Return the recommended role agent type for a given state."""
    if state.phase in ("blocked", "done"):
        return None
    return PHASE_TO_ROLE.get(state.phase)


def compute_next_hints(
    state: StateSnapshot,
    handoff_note_path: str | None = None,
) -> NextHints:
    """Compute hints for the next agent based on current state."""
    role = get_recommended_role(state)
    hints = NextHints(recommended_agent=role, entry_point=handoff_note_path)

    if _is_gate(state):
        targets = get_legal_targets(state)
        hints.priority_hints = [
            f"gate at {state.phase}.{state.sub_state}: "
            f"next phases: {[f'{t.phase}.{t.sub_state}' for t in targets if t.phase not in ('blocked', 'done')]}"
        ]

    return hints
