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
    "resume_audit_reconciled",
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
RESUME_AUDIT_RECONCILED_EVENT_TYPE = "resume_audit_reconciled"

# ── workflow-state.json projection（flow-event-projection P1）────────────
WORKFLOW_STATE_FILENAME = "workflow-state.json"
WORKFLOW_STATE_SCHEMA = "workflow-state/v1"
CHANGE_CREATED_EVENT_TYPE = "change_created"

# milestones 推进器：只追加 milestones 数组、不改 projection state（Q8 确认）。
MILESTONE_EVENT_TYPES = {
    "grill_completed",
    "design_reviewed",
    "design_review_completed",
    "building_review_completed",
    "known_debt_updated",
}

# awaiting 态集合（建模为 blocked phase 的 sub_state，代码层修正 1）。
AWAITING_SUB_STATES = (
    "awaiting_proposal_confirmation",
    "awaiting_human_review",
    "awaiting_user_confirmation",
)

# 默认 seed：首事件 change_created 或缺失 seed 时的初始投影（等价 init_handoff_json 的 planning.exploring）。
DEFAULT_SEED_STATE = {"phase": "planning", "sub_state": "exploring"}


def event_log_path(change_dir: str | Path) -> Path:
    return Path(change_dir) / EVENT_LOG_FILENAME


def workflow_state_path(change_dir: str | Path) -> Path:
    return Path(change_dir) / WORKFLOW_STATE_FILENAME


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


def append_resume_audit_reconciled_event(
    change_dir: str | Path,
    change_id: str,
    *,
    artifact_path: str,
    reason: str,
    approved_by: str,
    baseline_sha: str,
    head_sha: str,
    changed_paths_hash: str,
    changed_paths: list[str],
) -> None:
    _append_event(
        change_dir,
        {
            "event_type": RESUME_AUDIT_RECONCILED_EVENT_TYPE,
            "change_id": change_id,
            "artifact_path": artifact_path,
            "reason": reason,
            "approved_by": approved_by,
            "baseline_sha": baseline_sha,
            "head_sha": head_sha,
            "changed_paths_hash": changed_paths_hash,
            "changed_paths": list(changed_paths),
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


# ── workflow-state.json 统一投影（flow-event-projection P1）──────────────


def is_awaiting_state(state: dict[str, Any]) -> bool:
    """True when the projection state is an awaiting state (blocked.awaiting_*)."""
    return state.get("phase") == "blocked" and state.get("sub_state") in AWAITING_SUB_STATES


def project_workflow_state(change_dir: str | Path) -> dict[str, Any]:
    """Unified projection entry: derive workflow-state.json shape for any change.

    两代兼容（Q7/Q8 确认）：
    - gen-1：首事件 `initialized` + handoff.json → 走既有 handoff replay，再映射为
      `state + milestones + source_event_seq` 形状（handoff.json 不落盘为 workflow-state.json）。
    - gen-2：首事件 `change_created`（或无 seed）→ change_created 作 seed（默认
      planning.exploring），`_apply_*` 事件链驱动 state，milestones 推进器收集里程碑事件。
    - 容忍异构：无 seed 事件（如 backlog_updated 开头的老归档）同样按默认 seed 投影，不抛错。
    """
    events = _read_events(event_log_path(change_dir))
    if not events:
        raise StateMachineError("workflow-events.jsonl is empty")
    first = events[0]
    if first.get("event_type") == "initialized":
        handoff_projection = replay_handoff_projection(change_dir)
        return _map_handoff_to_workflow_state(change_dir, handoff_projection, len(events))
    return _project_new_gen(change_dir, events)


def _project_new_gen(change_dir: str | Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    change_id = events[0].get("change_id") or Path(change_dir).name
    state = dict(DEFAULT_SEED_STATE)
    milestones: list[str] = []
    for index, event in enumerate(events):
        event_type = event.get("event_type")
        if event_type == CHANGE_CREATED_EVENT_TYPE and index == 0:
            continue  # seed 已应用（默认 planning.exploring）
        if event_type in NON_STATE_EVENT_TYPES:
            continue
        if event_type in MILESTONE_EVENT_TYPES:
            if event_type not in milestones:
                milestones.append(event_type)
            continue
        if event_type == "transition_applied":
            _apply_transition_to_state(state, event)
        elif event_type == BLOCKED_EVENT_TYPE:
            _apply_blocked_to_state(state, event)
        elif event_type == UNBLOCKED_EVENT_TYPE:
            _apply_unblocked_to_state(state, event)
        elif event_type in (ROUTING_UPDATED_EVENT_TYPE, WAYFINDING_CHILDREN_EVENT_TYPE):
            continue  # 不属于 workflow-state 形状（state/milestones）
        else:
            raise StateMachineError(f"unknown workflow event type: {event_type}")
    return {
        "schema": WORKFLOW_STATE_SCHEMA,
        "change_id": change_id,
        "state": state,
        "milestones": milestones,
        "source_event_seq": len(events),
    }


def _map_handoff_to_workflow_state(
    change_dir: str | Path,
    handoff_projection: dict[str, Any],
    seq: int,
) -> dict[str, Any]:
    change_id = handoff_projection.get("change_id") or Path(change_dir).name
    return {
        "schema": WORKFLOW_STATE_SCHEMA,
        "change_id": change_id,
        "state": deepcopy(handoff_projection.get("state", {})),
        "milestones": _milestones_from_transitions(handoff_projection.get("transitions", [])),
        "source_event_seq": seq,
    }


def _milestones_from_transitions(transitions: list[dict[str, Any]]) -> list[str]:
    """gen-1 milestones：transitions 中按序到达的不同 phase（跳过 blocked）。"""
    seen: list[str] = []
    for transition in transitions:
        to_phase = transition.get("to", {}).get("phase")
        if to_phase and to_phase != "blocked" and to_phase not in seen:
            seen.append(to_phase)
    return seen


def _apply_transition_to_state(state: dict[str, Any], event: dict[str, Any]) -> None:
    transition = deepcopy(event["transition"])
    _validate_transition_dict(transition)
    state.clear()
    state.update(deepcopy(transition["to"]))


def _apply_blocked_to_state(state: dict[str, Any], event: dict[str, Any]) -> None:
    transition = deepcopy(event["transition"])
    _validate_transition_dict(transition)
    if transition["to"]["phase"] != "blocked":
        raise StateMachineError("blocked event must transition to blocked")
    state.clear()
    state.update(deepcopy(transition["to"]))


def _apply_unblocked_to_state(state: dict[str, Any], event: dict[str, Any]) -> None:
    transition = deepcopy(event["transition"])
    _validate_transition_dict(transition)
    if transition["from"]["phase"] != "blocked":
        raise StateMachineError("unblocked event must transition from blocked")
    # 不依赖 blockers 数组（Q9/代码层修正 7：无 blocked_entered 前置记录的 change 不抛错）
    state.clear()
    state.update(deepcopy(transition["to"]))


def verify_projection(change_dir: str | Path) -> list[str]:
    """两代通用校验（Q11）：可投影 + 一致性。

    - gen-1（initialized 开头）：沿用 handoff.json == replay 校验。
    - gen-2（change_created / 无 seed）：事件可投影；若磁盘有 workflow-state.json，
      校验磁盘投影 == 从事件 replay 重建的投影（D6 防自锁）。
    """
    events_path = event_log_path(change_dir)
    if not events_path.exists():
        return []
    try:
        projection = project_workflow_state(change_dir)
    except Exception as exc:
        return [f"workflow event log projection failed: {exc}"]

    first = _read_events(events_path)[0]
    if first.get("event_type") == "initialized":
        return verify_handoff_projection(change_dir)

    ws_path = Path(change_dir) / WORKFLOW_STATE_FILENAME
    if ws_path.exists():
        try:
            disk = json.loads(ws_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return [f"workflow-state.json invalid JSON: {exc}"]
        if disk != projection:
            return ["workflow-state.json projection does not match workflow-events.jsonl"]
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
