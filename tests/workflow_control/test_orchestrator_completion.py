from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from workflow_control import (
    Actor,
    ActorKind,
    ReviewResult,
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    WorkflowOrchestrator,
    WorkflowOrchestratorConfig,
    WorkflowValidationError,
    WorkResult,
    default_coding_agent_template,
)

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def _orchestrator(tmp_path):
    return WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
        )
    )


def test_resolve_active_workflow_requires_choice_when_multiple_active(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    orchestrator.enter("workflow-1", actor)
    orchestrator.enter("workflow-2", actor)

    assert orchestrator.resolve_active_workflow(explicit_workflow_id="workflow-1") == "workflow-1"
    with pytest.raises(WorkflowValidationError, match="multiple active"):
        orchestrator.resolve_active_workflow()


def test_enter_creates_exploration_when_no_active_workflow(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)

    workflow_id = orchestrator.resolve_active_workflow(create_if_missing=True)

    assert workflow_id.startswith("exploration-")
    assert orchestrator.status(workflow_id).snapshot.state.phase == "exploring"


def test_work_item_includes_required_evidence_and_next_action(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    entered = orchestrator.enter("workflow-1", Actor(kind=ActorKind.AGENT, actor_id="agent"))

    assert entered.work_item is not None
    assert entered.work_item.next_action == "chat_until_goal_candidate"
    assert entered.work_item.required_evidence[0].kind == "workflow_output"


def test_goal_candidate_report_moves_exploration_to_requirements(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    entered = orchestrator.enter("workflow-1", actor)

    result = orchestrator.report(
        workflow_id="workflow-1",
        actor=actor,
        work_item_id=entered.work_item.work_item_id,
        result=WorkResult(output_refs=("goal_candidate",), summary="goal candidate"),
        expected_version=entered.snapshot.version,
    )

    assert result.snapshot.state.phase == "requirements"


def test_blocker_rollback_skip_and_stale_work_item(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    entered = orchestrator.enter("workflow-1", actor)

    blocked = orchestrator.block("workflow-1", actor, reason="need user")
    assert blocked.snapshot.state.phase == "blocked"
    recovered = orchestrator.rollback("workflow-1", actor, phase="exploring", sub_state="chatting")
    assert recovered.snapshot.state.phase == "exploring"

    current = orchestrator.enter("workflow-1", actor)
    orchestrator.skip("workflow-1", Actor(kind=ActorKind.HUMAN, actor_id="human", approval_capability=True))
    with pytest.raises(WorkflowValidationError, match="stale work item"):
        orchestrator.report("workflow-1", actor, current.work_item.work_item_id, WorkResult(), current.snapshot.version)


def test_lease_release_and_review_lane_changes_requested(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    entered = orchestrator.enter("workflow-1", actor, now=NOW, lease_ttl=timedelta(minutes=5))
    assert entered.lease is not None

    orchestrator.release_lease(entered.lease.lease_id)
    reclaimed = orchestrator.enter("workflow-1", Actor(kind=ActorKind.AGENT, actor_id="other"), now=NOW)
    assert reclaimed.work_item is not None
    orchestrator.rollback("workflow-1", actor, phase="code-review", sub_state="reviewing_code")

    review = orchestrator.record_review_result(
        workflow_id="workflow-1",
        actor=Actor(kind=ActorKind.AGENT, actor_id="reviewer"),
        review_result=ReviewResult.CHANGES_REQUESTED,
        executor_run_id="executor",
    )
    assert review.snapshot.state.phase == "building"
    assert review.snapshot.state.sub_state == "writing_tests"
