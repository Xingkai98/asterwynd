from __future__ import annotations

import json

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
    import_handoff_read_only,
)


def test_pilot_shadow_record_compares_legacy_handoff_with_event_snapshot(tmp_path) -> None:
    change_id = "automate-conversation-to-delivery-workflow"
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "change_id": change_id,
                "state": {"phase": "requirements", "sub_state": "drafting"},
            },
        ),
        encoding="utf-8",
    )
    legacy = import_handoff_read_only(handoff)
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(store=store, template=default_coding_agent_template()),
    )
    actor = Actor(kind=ActorKind.AGENT, actor_id="shadow-agent")
    entered = orchestrator.enter(change_id, actor)
    snapshot = orchestrator.report(
        workflow_id=change_id,
        actor=actor,
        work_item_id=entered.work_item.work_item_id,
        result=WorkResult(summary="shadow"),
        expected_version=entered.snapshot.version,
    ).snapshot

    assert StateSnapshot(legacy.phase, legacy.sub_state) == snapshot.state
