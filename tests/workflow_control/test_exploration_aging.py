from __future__ import annotations

from datetime import datetime, timedelta, timezone

from workflow_control import (
    AgingAction,
    AgingPolicy,
    OutputStatus,
    StateSnapshot,
    WorkflowOutput,
    WorkflowSnapshot,
    evaluate_exploration_aging,
)


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def test_empty_exploration_ages_to_abandon_after_ttl() -> None:
    snapshot = WorkflowSnapshot(
        workflow_id="workflow-1",
        state=StateSnapshot(phase="exploring", sub_state="chatting"),
        version=1,
        events_seen=1,
    )

    decision = evaluate_exploration_aging(
        snapshot=snapshot,
        outputs=(),
        last_activity_at=NOW - timedelta(hours=25),
        now=NOW,
        policy=AgingPolicy(ttl=timedelta(hours=24)),
    )

    assert decision.action == AgingAction.ABANDON
    assert decision.reason == "empty_exploration_expired"


def test_draft_and_proposed_outputs_do_not_block_aging() -> None:
    snapshot = WorkflowSnapshot(
        workflow_id="workflow-1",
        state=StateSnapshot(phase="exploring", sub_state="chatting"),
        version=1,
        events_seen=1,
    )

    decision = evaluate_exploration_aging(
        snapshot=snapshot,
        outputs=(
            WorkflowOutput(ref="draft-requirements", status=OutputStatus.DRAFT),
            WorkflowOutput(ref="candidate-scope", status=OutputStatus.PROPOSED),
        ),
        last_activity_at=NOW - timedelta(days=2),
        now=NOW,
        policy=AgingPolicy(ttl=timedelta(hours=24)),
    )

    assert decision.action == AgingAction.ABANDON
    assert decision.reason == "empty_exploration_expired"


def test_durable_output_blocks_exploration_aging() -> None:
    snapshot = WorkflowSnapshot(
        workflow_id="workflow-1",
        state=StateSnapshot(phase="exploring", sub_state="chatting"),
        version=1,
        events_seen=1,
    )

    decision = evaluate_exploration_aging(
        snapshot=snapshot,
        outputs=(WorkflowOutput(ref="accepted-summary", status=OutputStatus.DURABLE),),
        last_activity_at=NOW - timedelta(days=2),
        now=NOW,
        policy=AgingPolicy(ttl=timedelta(hours=24)),
    )

    assert decision.action == AgingAction.KEEP
    assert decision.reason == "durable_output_present"


def test_requirements_phase_does_not_age_as_empty_exploration() -> None:
    snapshot = WorkflowSnapshot(
        workflow_id="workflow-1",
        state=StateSnapshot(phase="requirements", sub_state="drafting"),
        version=2,
        events_seen=2,
    )

    decision = evaluate_exploration_aging(
        snapshot=snapshot,
        outputs=(),
        last_activity_at=NOW - timedelta(days=2),
        now=NOW,
        policy=AgingPolicy(ttl=timedelta(hours=24)),
    )

    assert decision.action == AgingAction.KEEP
    assert decision.reason == "not_exploration"


def test_recent_empty_exploration_is_kept() -> None:
    snapshot = WorkflowSnapshot(
        workflow_id="workflow-1",
        state=StateSnapshot(phase="exploring", sub_state="chatting"),
        version=1,
        events_seen=1,
    )

    decision = evaluate_exploration_aging(
        snapshot=snapshot,
        outputs=(),
        last_activity_at=NOW - timedelta(hours=1),
        now=NOW,
        policy=AgingPolicy(ttl=timedelta(hours=24)),
    )

    assert decision.action == AgingAction.KEEP
    assert decision.reason == "ttl_not_expired"
