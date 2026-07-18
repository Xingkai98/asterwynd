from __future__ import annotations

import hashlib
import json

import pytest

from workflow_control import (
    Actor,
    ActorKind,
    ApprovalDecision,
    EventType,
    Gate,
    PhaseTemplate,
    ReviewResult,
    StateSnapshot,
    WorkResult,
    WorkflowEvent,
    WorkflowValidationError,
    default_coding_agent_template,
    record_gate_approved,
    record_review_result,
    record_work_completed,
    reduce_events,
    start_workflow,
)


def test_default_template_starts_in_exploration_without_worktree() -> None:
    template = default_coding_agent_template()

    assert template.initial_state == StateSnapshot(
        phase="exploring",
        sub_state="chatting",
    )
    assert template.phase("exploring").commit_policy == "none"
    assert template.phase("requirements").commit_policy == "none"
    assert template.phase("design").commit_policy == "required_before_human_gate"
    assert template.phase("building").commit_policy == "required_before_human_gate"


def test_work_completed_advances_within_template_order() -> None:
    template = default_coding_agent_template()
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent-1")
    events = [
        start_workflow("workflow-1", template),
        record_work_completed(
            "workflow-1",
            actor,
            WorkResult(output_refs=("requirements-draft",)),
        ),
    ]

    snapshot = reduce_events(events, template)

    assert snapshot.state == StateSnapshot(
        phase="requirements",
        sub_state="drafting",
    )
    assert snapshot.version == 2


def test_reducer_rejects_event_that_skips_template_order() -> None:
    template = default_coding_agent_template()
    events = [
        start_workflow("workflow-1", template),
        WorkflowEvent(
            event_id="event-2",
            workflow_id="workflow-1",
            event_type=EventType.STATE_ADVANCED,
            actor=Actor(kind=ActorKind.AGENT, actor_id="agent-1"),
            from_state=StateSnapshot(phase="exploring", sub_state="chatting"),
            to_state=StateSnapshot(phase="building", sub_state="writing_tests"),
            version=2,
        ),
    ]

    with pytest.raises(WorkflowValidationError, match="illegal transition"):
        reduce_events(events, template)


def test_gate_stops_until_human_approval_with_capability() -> None:
    template = PhaseTemplate(
        template_id="tiny",
        phases=(
            ("design", ("writing", "ready_for_review"), "required_before_human_gate"),
            ("building", ("writing_tests", "ready_for_review"), "required_before_human_gate"),
        ),
        initial_state=StateSnapshot(phase="design", sub_state="writing"),
    )
    agent = Actor(kind=ActorKind.AGENT, actor_id="agent-1")
    human = Actor(
        kind=ActorKind.HUMAN,
        actor_id="user-1",
        approval_capability=True,
    )
    events = [
        start_workflow("workflow-1", template),
        record_work_completed("workflow-1", agent, WorkResult()),
        record_gate_approved(
            "workflow-1",
            human,
            approval=_gate_for_test("workflow-1", "design", "ready_for_review", 2).approve(
                actor=human,
                decision=ApprovalDecision.APPROVED,
                client_id="test-host",
                user_message_hash="sha256:ok",
            ),
        ),
    ]

    snapshot = reduce_events(events, template)

    assert snapshot.state == StateSnapshot(
        phase="building",
        sub_state="writing_tests",
    )


def _gate_for_test(
    workflow_id: str,
    phase: str,
    sub_state: str,
    state_version: int,
) -> Gate:
    summary = json.dumps(
        {
            "workflow_id": workflow_id,
            "phase": phase,
            "sub_state": sub_state,
            "state_version": state_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return Gate(
        gate_id=f"{workflow_id}:{phase}:{state_version}",
        workflow_id=workflow_id,
        phase=phase,
        state_version=state_version,
        gate_summary_hash="sha256:" + hashlib.sha256(summary.encode("utf-8")).hexdigest(),
    )


def test_agent_cannot_approve_gate_even_with_matching_text() -> None:
    template = PhaseTemplate(
        template_id="tiny",
        phases=(
            ("design", ("writing", "ready_for_review"), "required_before_human_gate"),
            ("building", ("writing_tests", "ready_for_review"), "required_before_human_gate"),
        ),
        initial_state=StateSnapshot(phase="design", sub_state="writing"),
    )
    agent = Actor(
        kind=ActorKind.AGENT,
        actor_id="agent-1",
        approval_capability=True,
    )
    events = [
        start_workflow("workflow-1", template),
        record_work_completed("workflow-1", agent, WorkResult()),
        record_gate_approved("workflow-1", agent, raw_user_message="ok"),
    ]

    with pytest.raises(WorkflowValidationError, match="human approval capability"):
        reduce_events(events, template)


def test_work_result_does_not_accept_target_state() -> None:
    with pytest.raises(TypeError):
        WorkResult(target_state=StateSnapshot(phase="building", sub_state="writing_tests"))


def test_reviewer_cannot_review_own_execution() -> None:
    reviewer = Actor(kind=ActorKind.AGENT, actor_id="executor-1")

    with pytest.raises(WorkflowValidationError, match="self review"):
        record_review_result(
            "workflow-1",
            reviewer,
            ReviewResult.PASS,
            executor_run_id="executor-1",
        )
