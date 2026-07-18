from __future__ import annotations

import pytest

from workflow_control import (
    Actor,
    ActorKind,
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    WorkResult,
    WorkflowStoreConflict,
    default_coding_agent_template,
    record_work_completed,
    reduce_events,
    start_workflow,
)


def test_sqlite_store_appends_and_replays_events(tmp_path) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=db_path))
    template = default_coding_agent_template()
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent-1")

    store.append("workflow-1", start_workflow("workflow-1", template), expected_version=0)
    store.append(
        "workflow-1",
        record_work_completed("workflow-1", actor, WorkResult(output_refs=("draft",))),
        expected_version=1,
    )

    events = store.list_events("workflow-1")
    snapshot = reduce_events(events, template)

    assert db_path.exists()
    assert store.current_version("workflow-1") == 2
    assert snapshot.state.phase == "requirements"
    assert snapshot.state.sub_state == "drafting"


def test_sqlite_store_rejects_stale_expected_version(tmp_path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    template = default_coding_agent_template()

    store.append("workflow-1", start_workflow("workflow-1", template), expected_version=0)

    with pytest.raises(WorkflowStoreConflict, match="expected version 0"):
        store.append(
            "workflow-1",
            record_work_completed(
                "workflow-1",
                Actor(kind=ActorKind.AGENT, actor_id="agent-1"),
                WorkResult(),
            ),
            expected_version=0,
        )


def test_sqlite_store_separates_workflow_streams(tmp_path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    template = default_coding_agent_template()

    store.append("workflow-1", start_workflow("workflow-1", template), expected_version=0)
    store.append("workflow-2", start_workflow("workflow-2", template), expected_version=0)

    assert [event.workflow_id for event in store.list_events("workflow-1")] == ["workflow-1"]
    assert [event.workflow_id for event in store.list_events("workflow-2")] == ["workflow-2"]
