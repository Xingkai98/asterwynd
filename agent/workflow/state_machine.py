from __future__ import annotations

from agent.workflow.models import (
    GATE_SUB_STATE,
    PHASE_ORDER,
    PHASE_SUB_STATES,
    PHASE_TO_ROLE,
    NextHints,
    Phase,
    RoleAgentType,
    StateSnapshot,
    SubState,
    Trigger,
)


class StateMachineError(ValueError):
    pass


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
    ("wayfinding", "ready_for_review"): [
        ("planning", "exploring"),
    ],
    ("planning", "ready_for_review"): [
        ("building", "writing_tests"),
    ],
    ("building", "ready_for_review"): [
        ("closing", "syncing_specs"),
    ],
    ("closing", "ready_for_review"): [
        ("done", None),
    ],
}

# Legal within-phase sub_state adjacency (sequential, with loops where noted)
WITHIN_PHASE_ADJACENT: dict[Phase, dict[SubState, list[SubState | None]]] = {
    "wayfinding": {
        "charting_map": ["working_tickets"],
        "working_tickets": ["map_cleared"],
        "map_cleared": ["reviewing_map"],
        "reviewing_map": ["ready_for_review"],
        "ready_for_review": [],
    },
    "planning": {
        "exploring": ["writing_proposal"],
        "writing_proposal": ["writing_design"],
        "writing_design": ["writing_spec"],
        "writing_spec": ["writing_tickets"],
        "writing_tickets": ["reviewing_artifacts"],
        "reviewing_artifacts": ["ready_for_review"],
        "ready_for_review": [],
    },
    "building": {
        "writing_tests": ["test_failing", "implementing"],
        "test_failing": ["writing_tests", "implementing"],  # TDD loop
        "implementing": ["all_tests_passing", "writing_tests"],
        "all_tests_passing": ["implementing", "smoke_validating"],  # fix loop
        "smoke_validating": ["implementing", "reviewing_impl"],  # fail -> back to implement
        "reviewing_impl": ["ready_for_review"],
        "ready_for_review": [],
    },
    "closing": {
        "syncing_specs": ["archiving"],
        "archiving": ["updating_backlog"],
        "updating_backlog": ["validating"],
        "validating": ["pr_ready"],
        "pr_ready": ["reviewing_archive"],
        "reviewing_archive": ["ready_for_review"],
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
