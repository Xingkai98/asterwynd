from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# --- Enums ---

Phase = Literal["wayfinding", "planning", "building", "closing", "blocked", "done"]
PHASES: tuple[Phase, ...] = ("wayfinding", "planning", "building", "closing", "blocked", "done")

SubState = str

Trigger = Literal["auto", "handoff", "human_review", "human_rollback"]
TRIGGERS: tuple[Trigger, ...] = ("auto", "handoff", "human_review", "human_rollback")

ActorType = Literal["agent", "human"]

Executor = Literal["inline", "subagent", "claude-code", "codex"]
EXECUTORS: tuple[Executor, ...] = ("inline", "subagent", "claude-code", "codex")

SessionMode = Literal["same", "new", "ask"]
SESSION_MODES: tuple[SessionMode, ...] = ("same", "new", "ask")

Decision = Literal["approved", "skip", "rollback"]

RoleAgentType = Literal["wayfinder", "planner", "builder", "closer"]
ROLE_AGENT_TYPES: tuple[RoleAgentType, ...] = ("wayfinder", "planner", "builder", "closer")

PHASE_ORDER: dict[Phase, int] = {
    "wayfinding": 0,
    "planning": 1,
    "building": 2,
    "closing": 3,
    "blocked": -1,
    "done": 4,
}

PHASE_TO_ROLE: dict[Phase, RoleAgentType] = {
    "wayfinding": "wayfinder",
    "planning": "planner",
    "building": "builder",
    "closing": "closer",
}

# --- Sub-state sequences per phase ---

WAYFINDING_SUB_STATES: tuple[SubState, ...] = (
    "charting_map",
    "working_tickets",
    "map_cleared",
    "reviewing_map",
    "ready_for_review",
)

PLANNING_SUB_STATES: tuple[SubState, ...] = (
    "exploring",
    "writing_proposal",
    "writing_design",
    "writing_spec",
    "writing_tickets",
    "reviewing_artifacts",
    "ready_for_review",
)

BUILDING_SUB_STATES: tuple[SubState, ...] = (
    "writing_tests",
    "test_failing",
    "implementing",
    "all_tests_passing",
    "smoke_validating",
    "reviewing_impl",
    "ready_for_review",
)

CLOSING_SUB_STATES: tuple[SubState, ...] = (
    "syncing_specs",
    "archiving",
    "updating_backlog",
    "validating",
    "pr_ready",
    "reviewing_archive",
    "ready_for_review",
)

PHASE_SUB_STATES: dict[Phase, tuple[SubState, ...]] = {
    "wayfinding": WAYFINDING_SUB_STATES,
    "planning": PLANNING_SUB_STATES,
    "building": BUILDING_SUB_STATES,
    "closing": CLOSING_SUB_STATES,
}

GATE_SUB_STATE = "ready_for_review"

WORKTREE_REQUIRED_PHASES: set[Phase] = {"building"}

# --- Review sub-state names per phase ---
REVIEW_SUB_STATES: dict[Phase, SubState] = {
    "wayfinding": "reviewing_map",
    "planning": "reviewing_artifacts",
    "building": "reviewing_impl",
    "closing": "reviewing_archive",
}

# --- Dataclasses ---

@dataclass
class StateSnapshot:
    phase: Phase
    sub_state: SubState | None = None

    def to_dict(self) -> dict:
        return {"phase": self.phase, "sub_state": self.sub_state}


@dataclass
class Transition:
    from_state: StateSnapshot
    to_state: StateSnapshot
    trigger: Trigger
    actor_type: ActorType
    actor_id: str
    timestamp: str
    handoff_note: str | None = None
    decision: Decision | None = None
    reason: str | None = None
    rollback_reason: str | None = None
    skip_reason: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "from": self.from_state.to_dict(),
            "to": self.to_state.to_dict(),
            "trigger": self.trigger,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "timestamp": self.timestamp,
        }
        if self.handoff_note is not None:
            d["handoff_note"] = self.handoff_note
        if self.decision is not None:
            d["decision"] = self.decision
        if self.reason is not None:
            d["reason"] = self.reason
        if self.rollback_reason is not None:
            d["rollback_reason"] = self.rollback_reason
        if self.skip_reason is not None:
            d["skip_reason"] = self.skip_reason
        return d


@dataclass
class CurrentAgent:
    run_id: str
    type: RoleAgentType

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "type": self.type}


@dataclass
class LastGate:
    phase: Phase
    sub_state: SubState
    awaiting: str = "human_review"

    def to_dict(self) -> dict:
        return {"phase": self.phase, "sub_state": self.sub_state, "awaiting": self.awaiting}


@dataclass
class Blocker:
    blocked_from: StateSnapshot
    reason: str
    blocked_at: str
    resolved_at: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "blocked_from": self.blocked_from.to_dict(),
            "reason": self.reason,
            "blocked_at": self.blocked_at,
        }
        if self.resolved_at is not None:
            d["resolved_at"] = self.resolved_at
        return d


@dataclass
class PhaseRouting:
    executor: Executor
    session_mode: SessionMode

    def to_dict(self) -> dict:
        return {"executor": self.executor, "session_mode": self.session_mode}


@dataclass
class NextHints:
    recommended_agent: RoleAgentType | None = None
    entry_point: str | None = None
    priority_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {}
        if self.recommended_agent is not None:
            d["recommended_agent"] = self.recommended_agent
        if self.entry_point is not None:
            d["entry_point"] = self.entry_point
        if self.priority_hints:
            d["priority_hints"] = self.priority_hints
        return d


DEFAULT_ROUTING: dict[Phase, PhaseRouting] = {
    "wayfinding": PhaseRouting(executor="inline", session_mode="same"),
    "planning": PhaseRouting(executor="inline", session_mode="same"),
    "building": PhaseRouting(executor="inline", session_mode="same"),
    "closing": PhaseRouting(executor="inline", session_mode="same"),
}
