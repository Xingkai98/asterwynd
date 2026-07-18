from __future__ import annotations

from workflow_control import (
    Actor,
    ActorKind,
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    StateSnapshot,
    WorkResult,
    WorkflowOrchestrator,
    WorkflowOrchestratorConfig,
    default_coding_agent_template,
    record_work_completed,
    start_workflow,
)


def test_status_rebuilds_snapshot_from_event_store(tmp_path) -> None:
    template = default_coding_agent_template()
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    store.append("workflow-1", start_workflow("workflow-1", template), expected_version=0)
    store.append(
        "workflow-1",
        record_work_completed(
            "workflow-1",
            Actor(kind=ActorKind.AGENT, actor_id="agent-1"),
            WorkResult(output_refs=("draft",)),
        ),
        expected_version=1,
    )
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(store=store, template=template),
    )

    status = orchestrator.status("workflow-1")

    assert status.snapshot.state == StateSnapshot(phase="requirements", sub_state="drafting")
    assert status.snapshot.version == 2


def test_enter_starts_new_workflow_and_returns_work_item(tmp_path) -> None:
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
        ),
    )

    enter = orchestrator.enter("workflow-1", Actor(kind=ActorKind.AGENT, actor_id="agent-1"))

    assert enter.waiting_for_human is False
    assert enter.work_item is not None
    assert enter.work_item.state == StateSnapshot(phase="exploring", sub_state="chatting")
    assert enter.work_item.allows("report_work")
    assert enter.snapshot.version == 1


def test_report_advances_state_without_executor_chosen_target(tmp_path) -> None:
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
        ),
    )
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent-1")
    entered = orchestrator.enter("workflow-1", actor)

    reported = orchestrator.report(
        workflow_id="workflow-1",
        actor=actor,
        work_item_id=entered.work_item.work_item_id,
        result=WorkResult(output_refs=("requirements-draft",)),
        expected_version=entered.snapshot.version,
    )

    assert reported.snapshot.state == StateSnapshot(phase="requirements", sub_state="drafting")
    assert reported.snapshot.version == 2


def test_enter_at_gate_returns_waiting_for_human(tmp_path) -> None:
    template = default_coding_agent_template()
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent-1")
    store.append("workflow-1", start_workflow("workflow-1", template), expected_version=0)
    store.append("workflow-1", record_work_completed("workflow-1", actor, WorkResult()), expected_version=1)
    store.append("workflow-1", record_work_completed("workflow-1", actor, WorkResult()), expected_version=2)
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(store=store, template=template),
    )

    enter = orchestrator.enter("workflow-1", actor)

    assert enter.waiting_for_human is True
    assert enter.work_item is None
    assert enter.snapshot.state == StateSnapshot(phase="requirements", sub_state="ready_for_review")
