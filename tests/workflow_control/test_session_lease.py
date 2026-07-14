from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from workflow_control import (
    Actor,
    ActorKind,
    SessionBindingRegistry,
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    WorkflowOrchestrator,
    WorkflowOrchestratorConfig,
    WorkflowValidationError,
    default_coding_agent_template,
)


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def test_session_binding_is_sticky_until_done(tmp_path) -> None:
    registry = SessionBindingRegistry()

    first = registry.bind("session-1", "workflow-1")
    second = registry.bind("session-1", "workflow-1")

    assert first.workflow_id == "workflow-1"
    assert second.workflow_id == "workflow-1"
    with pytest.raises(WorkflowValidationError, match="already bound"):
        registry.bind("session-1", "workflow-2")


def test_orchestrator_enter_claims_single_active_lease(tmp_path) -> None:
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
        ),
    )

    first = orchestrator.enter(
        "workflow-1",
        Actor(kind=ActorKind.AGENT, actor_id="agent-1"),
        now=NOW,
        lease_ttl=timedelta(minutes=5),
    )
    second = orchestrator.enter(
        "workflow-1",
        Actor(kind=ActorKind.AGENT, actor_id="agent-2"),
        now=NOW + timedelta(minutes=1),
        lease_ttl=timedelta(minutes=5),
    )

    assert first.work_item is not None
    assert first.lease is not None
    assert second.work_item is None
    assert second.blocked_reason == "work_item_already_leased"


def test_expired_lease_allows_new_claim(tmp_path) -> None:
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
        ),
    )

    orchestrator.enter(
        "workflow-1",
        Actor(kind=ActorKind.AGENT, actor_id="agent-1"),
        now=NOW,
        lease_ttl=timedelta(minutes=5),
    )
    second = orchestrator.enter(
        "workflow-1",
        Actor(kind=ActorKind.AGENT, actor_id="agent-2"),
        now=NOW + timedelta(minutes=6),
        lease_ttl=timedelta(minutes=5),
    )

    assert second.work_item is not None
    assert second.lease is not None
    assert second.lease.owner_id == "agent-2"
