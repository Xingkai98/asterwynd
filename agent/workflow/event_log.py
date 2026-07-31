from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent.workflow.models import GATE_SUB_STATE, LastGate, StateSnapshot
from agent.workflow.state_machine import (
    StateMachineError,
    compute_next_hints,
    validate_transition,
)

EVENT_LOG_FILENAME = "workflow-events.jsonl"
EVENT_SCHEMA = "workflow-event/v1"
NON_STATE_EVENT_TYPES = {
    "protected_artifact_explained",
    "current_spec_synced",
    "backlog_updated",
    "change_archived",
}
BLOCKED_EVENT_TYPE = "blocked_entered"
UNBLOCKED_EVENT_TYPE = "blocked_resolved"
ROUTING_UPDATED_EVENT_TYPE = "routing_updated"
ALLOWED_PROTECTED_ARTIFACT_EVENT_TYPES = {
    "protected_artifact_explained",
    "current_spec_synced",
    "backlog_updated",
    "change_archived",
}
WAYFINDING_CHILDREN_EVENT_TYPE = "wayfinding_children_spawned"


def event_log_path(change_dir: str | Path) -> Path:
    return Path(change_dir) / EVENT_LOG_FILENAME


def write_init_event(change_dir: str | Path, handoff: dict[str, Any]) -> None:
    """Start a workflow event log from the initial handoff projection."""
    _append_event(
        change_dir,
        {
            "event_type": "initialized",
            "change_id": handoff["change_id"],
            "handoff": deepcopy(handoff),
        },
    )


def append_transition_event(
    change_dir: str | Path,
    change_id: str,
    transition: dict[str, Any],
    current_agent: dict[str, Any] | None = None,
) -> None:
    _append_event(
        change_dir,
        {
            "event_type": "transition_applied",
            "change_id": change_id,
            "transition": deepcopy(transition),
            **({"current_agent": deepcopy(current_agent)} if current_agent is not None else {}),
        },
    )


def append_blocked_event(
    change_dir: str | Path,
    change_id: str,
    transition: dict[str, Any],
    blocker: dict[str, Any],
    current_agent: dict[str, Any] | None = None,
) -> None:
    _append_event(
        change_dir,
        {
            "event_type": BLOCKED_EVENT_TYPE,
            "change_id": change_id,
            "transition": deepcopy(transition),
            "blocker": deepcopy(blocker),
            **({"current_agent": deepcopy(current_agent)} if current_agent is not None else {}),
        },
    )


def append_unblocked_event(
    change_dir: str | Path,
    change_id: str,
    transition: dict[str, Any],
    blocker_index: int,
    blocker: dict[str, Any],
    current_agent: dict[str, Any] | None = None,
) -> None:
    _append_event(
        change_dir,
        {
            "event_type": UNBLOCKED_EVENT_TYPE,
            "change_id": change_id,
            "transition": deepcopy(transition),
            "blocker_index": blocker_index,
            "blocker": deepcopy(blocker),
            **({"current_agent": deepcopy(current_agent)} if current_agent is not None else {}),
        },
    )


def append_routing_update_event(
    change_dir: str | Path,
    change_id: str,
    phase: str,
    routing: dict[str, Any],
) -> None:
    _append_event(
        change_dir,
        {
            "event_type": ROUTING_UPDATED_EVENT_TYPE,
            "change_id": change_id,
            "phase": phase,
            "routing": deepcopy(routing),
        },
    )


def append_wayfinding_children_event(
    change_dir: str | Path,
    change_id: str,
    children: list[str],
) -> None:
    _append_event(
        change_dir,
        {
            "event_type": WAYFINDING_CHILDREN_EVENT_TYPE,
            "change_id": change_id,
            "children": list(children),
        },
    )


def append_protected_artifact_event(
    change_dir: str | Path,
    change_id: str,
    event_type: str,
    artifact_path: str,
    reason: str,
    approved_by: str,
) -> None:
    if event_type not in ALLOWED_PROTECTED_ARTIFACT_EVENT_TYPES:
        raise ValueError(f"unsupported protected artifact event type: {event_type}")
    _append_event(
        change_dir,
        {
            "event_type": event_type,
            "change_id": change_id,
            "artifact_path": artifact_path,
            "reason": reason,
            "approved_by": approved_by,
        },
    )


def _append_event(change_dir: str | Path, event: dict[str, Any]) -> None:
    path = event_log_path(change_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    events = _read_events(path) if path.exists() else []
    record = {
        "schema": EVENT_SCHEMA,
        "seq": len(events) + 1,
        **deepcopy(event),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def replay_handoff_projection(change_dir: str | Path) -> dict[str, Any]:
    events = _read_events(event_log_path(change_dir))
    if not events:
        raise StateMachineError("workflow-events.jsonl is empty")

    first = events[0]
    if first.get("event_type") != "initialized":
        raise StateMachineError("workflow-events.jsonl must start with initialized event")

    projection = deepcopy(first["handoff"])
    projection["transitions"] = list(projection.get("transitions", []))

    for event in events[1:]:
        event_type = event.get("event_type")
        if event_type in NON_STATE_EVENT_TYPES:
            continue
        if event_type == "transition_applied":
            _apply_transition_event(projection, event)
        elif event_type == BLOCKED_EVENT_TYPE:
            _apply_blocked_event(projection, event)
        elif event_type == UNBLOCKED_EVENT_TYPE:
            _apply_unblocked_event(projection, event)
        elif event_type == ROUTING_UPDATED_EVENT_TYPE:
            _apply_routing_update_event(projection, event)
        elif event_type == WAYFINDING_CHILDREN_EVENT_TYPE:
            _apply_wayfinding_children_event(projection, event)
        else:
            raise StateMachineError(f"unknown workflow event type: {event_type}")

    return projection


def _apply_transition_event(projection: dict[str, Any], event: dict[str, Any]) -> None:
    transition = deepcopy(event["transition"])
    _validate_transition_dict(transition)
    projection["state"] = deepcopy(transition["to"])
    projection["transitions"].append(transition)

    current_agent = event.get("current_agent")
    if current_agent is not None:
        projection["current_agent"] = deepcopy(current_agent)

    to_state = StateSnapshot(
        phase=transition["to"]["phase"],
        sub_state=transition["to"].get("sub_state"),
    )
    if to_state.sub_state == GATE_SUB_STATE and to_state.phase not in ("blocked", "done"):
        projection["last_gate"] = LastGate(
            phase=to_state.phase,
            sub_state=GATE_SUB_STATE,
        ).to_dict()
    else:
        projection["last_gate"] = None
    projection["next_hints"] = compute_next_hints(
        to_state,
        transition.get("handoff_note"),
    ).to_dict()


def _apply_blocked_event(projection: dict[str, Any], event: dict[str, Any]) -> None:
    transition = deepcopy(event["transition"])
    blocker = deepcopy(event["blocker"])
    _validate_transition_dict(transition)
    if transition["to"]["phase"] != "blocked":
        raise StateMachineError("blocked event must transition to blocked")
    projection["state"] = deepcopy(transition["to"])
    projection["transitions"].append(transition)
    blockers = projection.setdefault("blockers", [])
    if not isinstance(blockers, list):
        raise StateMachineError("handoff.json blockers must be an array")
    blockers.append(blocker)
    current_agent = event.get("current_agent")
    if current_agent is not None:
        projection["current_agent"] = deepcopy(current_agent)
    projection["last_gate"] = None


def _apply_unblocked_event(projection: dict[str, Any], event: dict[str, Any]) -> None:
    transition = deepcopy(event["transition"])
    blocker = deepcopy(event["blocker"])
    blocker_index = event.get("blocker_index")
    _validate_transition_dict(transition)
    if transition["from"]["phase"] != "blocked":
        raise StateMachineError("unblocked event must transition from blocked")
    projection["state"] = deepcopy(transition["to"])
    projection["transitions"].append(transition)
    blockers = projection.setdefault("blockers", [])
    if not isinstance(blockers, list):
        raise StateMachineError("handoff.json blockers must be an array")
    if not isinstance(blocker_index, int) or blocker_index < 0 or blocker_index >= len(blockers):
        raise StateMachineError("unblocked event references invalid blocker index")
    blockers[blocker_index] = blocker
    current_agent = event.get("current_agent")
    if current_agent is not None:
        projection["current_agent"] = deepcopy(current_agent)


def _apply_routing_update_event(projection: dict[str, Any], event: dict[str, Any]) -> None:
    phase = event.get("phase")
    routing = event.get("routing")
    if not isinstance(phase, str) or not isinstance(routing, dict):
        raise StateMachineError("routing_updated event missing phase/routing")
    current = dict(projection.get("routing", {}))
    current[phase] = deepcopy(routing)
    projection["routing"] = current


def _apply_wayfinding_children_event(projection: dict[str, Any], event: dict[str, Any]) -> None:
    children = event.get("children")
    if not isinstance(children, list) or not all(isinstance(item, str) for item in children):
        raise StateMachineError("wayfinding_children_spawned event missing children list")
    projection["wayfinding_children"] = list(children)


def verify_handoff_projection(change_dir: str | Path) -> list[str]:
    handoff_path = Path(change_dir) / "handoff.json"
    if not handoff_path.exists():
        return [f"handoff.json missing: {handoff_path}"]
    try:
        actual = json.loads(handoff_path.read_text(encoding="utf-8"))
        expected = replay_handoff_projection(change_dir)
    except Exception as exc:
        return [f"workflow event log replay failed: {exc}"]

    if actual != expected:
        return ["handoff.json projection does not match workflow-events.jsonl"]
    return []


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise StateMachineError(f"workflow event log missing: {path}")
    events: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise StateMachineError(f"invalid workflow event JSON at line {lineno}: {exc}") from exc
        if event.get("schema") != EVENT_SCHEMA:
            raise StateMachineError(f"invalid workflow event schema at line {lineno}")
        if event.get("seq") != len(events) + 1:
            raise StateMachineError(f"invalid workflow event seq at line {lineno}")
        events.append(event)
    return events


def _validate_transition_dict(transition: dict[str, Any]) -> None:
    from_state = StateSnapshot(
        phase=transition["from"]["phase"],
        sub_state=transition["from"].get("sub_state"),
    )
    to_state = StateSnapshot(
        phase=transition["to"]["phase"],
        sub_state=transition["to"].get("sub_state"),
    )
    validate_transition(from_state, to_state, transition["trigger"])
