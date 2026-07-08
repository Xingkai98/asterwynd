from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.workflow.models import (
    DEFAULT_ROUTING,
    GATE_SUB_STATE,
    PHASE_ORDER,
    PHASE_TO_ROLE,
    ActorType,
    CurrentAgent,
    Decision,
    NextHints,
    Phase,
    PhaseRouting,
    RoleAgentType,
    StateSnapshot,
    SubState,
    Transition,
    Trigger,
)
from agent.workflow.routing import (
    get_routing_for_phase,
    load_global_defaults,
    merge_routing,
    routing_to_dict,
)
from agent.workflow.state_machine import (
    StateMachineError,
    _is_gate,
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


class WorkflowManager:
    """Orchestrates the multi-agent development workflow for a single change."""

    def __init__(
        self,
        change_dir: str | Path,
        repo_root: str | Path = ".",
    ) -> None:
        self._change_dir = Path(change_dir)
        self._repo_root = Path(repo_root)
        self._data: dict[str, Any] | None = None

    # -- lifecycle -----------------------------------------------------------

    def init(self, change_id: str) -> dict[str, Any]:
        """Initialize a new handoff.json for the change."""
        self._change_dir.mkdir(parents=True, exist_ok=True)
        global_defaults = load_global_defaults(self._repo_root)
        self._data = init_handoff_json(change_id, routing=global_defaults)
        save_handoff_json(self._change_dir, self._data)
        return self.snapshot()

    def load(self) -> dict[str, Any]:
        """Load existing handoff.json from the change directory."""
        self._data = load_handoff_json(self._change_dir)
        return self.snapshot()

    def ensure_loaded(self) -> dict[str, Any]:
        if self._data is None:
            return self.load()
        return self.snapshot()

    # -- read-only queries ---------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        if self._data is None:
            raise StateMachineError("not initialized or loaded")
        return {
            "change_id": self._data["change_id"],
            "state": dict(self._data["state"]),
            "current_agent": dict(self._data["current_agent"]) if self._data.get("current_agent") else None,
            "last_gate": dict(self._data["last_gate"]) if self._data.get("last_gate") else None,
            "blockers": list(self._data.get("blockers", [])),
            "transition_count": len(self._data.get("transitions", [])),
        }

    @property
    def current_state(self) -> StateSnapshot:
        self.ensure_loaded()
        s = self._data["state"]
        return StateSnapshot(phase=s["phase"], sub_state=s.get("sub_state"))

    @property
    def current_phase(self) -> Phase:
        return self.current_state.phase

    @property
    def current_sub_state(self) -> SubState | None:
        return self.current_state.sub_state

    @property
    def is_at_gate(self) -> bool:
        return _is_gate(self.current_state)

    @property
    def is_blocked(self) -> bool:
        return self.current_phase == "blocked"

    @property
    def is_done(self) -> bool:
        return self.current_phase == "done"

    @property
    def transitions(self) -> list[dict]:
        self.ensure_loaded()
        return list(self._data.get("transitions", []))

    @property
    def recommended_role(self) -> RoleAgentType | None:
        return get_recommended_role(self.current_state)

    def legal_targets(self) -> list[StateSnapshot]:
        return get_legal_targets(self.current_state)

    def routing(self) -> dict[Phase, PhaseRouting]:
        self.ensure_loaded()
        global_defaults = load_global_defaults(self._repo_root)
        per_change = self._data.get("routing", {})
        return merge_routing(global_defaults, per_change)

    def routing_for_phase(self, phase: Phase | None = None) -> PhaseRouting:
        target = phase or self.current_phase
        return get_routing_for_phase(self.routing(), target)

    # -- mutations -----------------------------------------------------------

    def transition(
        self,
        to_phase: Phase,
        to_sub_state: SubState | None,
        trigger: Trigger,
        actor_type: ActorType,
        actor_id: str,
        handoff_note: str | None = None,
        decision: Decision | None = None,
        reason: str | None = None,
        rollback_reason: str | None = None,
        skip_reason: str | None = None,
        current_agent: CurrentAgent | None = None,
    ) -> dict[str, Any]:
        self.ensure_loaded()
        from_state = self.current_state
        to_state = StateSnapshot(phase=to_phase, sub_state=to_sub_state)

        transition = create_transition(
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            actor_type=actor_type,
            actor_id=actor_id,
            handoff_note=handoff_note,
            decision=decision,
            reason=reason,
            rollback_reason=rollback_reason,
            skip_reason=skip_reason,
        )

        self._data = apply_transition(self._data, transition, current_agent)

        next_hints = compute_next_hints(to_state, handoff_note)
        self._data["next_hints"] = next_hints.to_dict()

        save_handoff_json(self._change_dir, self._data)
        return self.snapshot()

    def advance_sub_state(
        self,
        next_sub_state: SubState,
        actor_type: ActorType = "agent",
        actor_id: str = "system",
    ) -> dict[str, Any]:
        return self.transition(
            to_phase=self.current_phase,
            to_sub_state=next_sub_state,
            trigger="auto",
            actor_type=actor_type,
            actor_id=actor_id,
        )

    def handoff(
        self,
        next_phase: Phase,
        handoff_note_path: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Record a handoff trigger at gate (does not change phase)."""
        if not self.is_at_gate:
            raise StateMachineError("handoff only allowed at gate (ready_for_review)")
        # handoff stays in same gate, records note path
        return self.transition(
            to_phase=self.current_phase,
            to_sub_state=GATE_SUB_STATE,
            trigger="handoff",
            actor_type="agent",
            actor_id=actor_id,
            handoff_note=handoff_note_path,
        )

    def human_approve(
        self,
        actor_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Human approves at gate, advancing to next phase."""
        if not self.is_at_gate:
            raise StateMachineError("approval only allowed at gate (ready_for_review)")
        targets = get_legal_targets(self.current_state)
        # find the forward targets (not blocked, not rollback)
        forward = [
            t for t in targets
            if t.phase not in ("blocked", "done")
            and _phase_earlier(t.phase, self.current_phase) is False
        ]
        done_targets = [t for t in targets if t.phase == "done"]
        if done_targets:
            forward = done_targets
        if not forward:
            raise StateMachineError("no forward target found from gate")
        # prefer non-skip path (next sequential phase)
        target = forward[0]
        return self.transition(
            to_phase=target.phase,
            to_sub_state=target.sub_state,
            trigger="human_review",
            actor_type="human",
            actor_id=actor_id,
            decision="approved",
            reason=reason,
        )

    def human_skip(
        self,
        actor_id: str,
        skip_reason: str,
    ) -> dict[str, Any]:
        """Human skips the next phase at gate."""
        if not self.is_at_gate:
            raise StateMachineError("skip only allowed at gate (ready_for_review)")
        targets = get_legal_targets(self.current_state)
        forward = [
            t for t in targets
            if t.phase not in ("blocked", "done", self.current_phase)
            and _phase_earlier(t.phase, self.current_phase) is False
        ]
        if len(forward) < 2:
            raise StateMachineError("no skip target available (only one forward path)")
        target = forward[-1]  # the skip target is the later one
        return self.transition(
            to_phase=target.phase,
            to_sub_state=target.sub_state,
            trigger="human_review",
            actor_type="human",
            actor_id=actor_id,
            decision="skip",
            skip_reason=skip_reason,
        )

    def human_rollback(
        self,
        target_phase: Phase,
        target_sub_state: SubState,
        actor_id: str,
        rollback_reason: str,
    ) -> dict[str, Any]:
        """Human rolls back to an earlier phase."""
        if self.current_phase in ("blocked", "done"):
            raise StateMachineError("cannot rollback from blocked or done")
        return self.transition(
            to_phase=target_phase,
            to_sub_state=target_sub_state,
            trigger="human_rollback",
            actor_type="human",
            actor_id=actor_id,
            decision="rollback",
            rollback_reason=rollback_reason,
        )

    def block(
        self,
        reason: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Enter blocked state."""
        self.ensure_loaded()
        self._data = enter_blocked(self._data, reason, actor_id)
        save_handoff_json(self._change_dir, self._data)
        return self.snapshot()

    def unblock(self, blocker_index: int = 0) -> dict[str, Any]:
        self.ensure_loaded()
        self._data = resolve_blocked(self._data, blocker_index)
        save_handoff_json(self._change_dir, self._data)
        return self.snapshot()

    def update_routing(
        self,
        phase: Phase,
        executor: str | None = None,
        session_mode: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_loaded()
        current = dict(self._data.get("routing", {}))
        entry = dict(current.get(phase, {}))
        if executor is not None:
            entry["executor"] = executor
        if session_mode is not None:
            entry["session_mode"] = session_mode
        current[phase] = entry
        self._data["routing"] = current
        save_handoff_json(self._change_dir, self._data)
        return self.snapshot()


def _phase_earlier(a: Phase, b: Phase) -> bool | None:
    """Return True if a is earlier than b, False if later, None if non-comparable."""
    ai = PHASE_ORDER.get(a)
    bi = PHASE_ORDER.get(b)
    if ai is None or bi is None:
        return None
    if ai < bi:
        return True
    if ai > bi:
        return False
    return None
