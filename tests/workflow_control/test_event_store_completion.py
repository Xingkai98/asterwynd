from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from workflow_control import (
    Actor,
    ActorKind,
    RequirementsDraft,
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    WorkResult,
    WorkflowHistoryCorrupt,
    WorkflowStoreConflict,
    default_coding_agent_template,
    project_event_store_path,
    record_work_completed,
    replay_history,
    start_workflow,
)


def test_project_event_store_path_is_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    data_root = tmp_path / "data"
    repo.mkdir()

    db_path = project_event_store_path(repo_root=repo, data_root=data_root)

    assert data_root in db_path.parents
    assert repo not in db_path.parents
    assert db_path.name == "workflow.sqlite3"


def test_sqlite_store_records_schema_version_and_uses_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    SQLiteEventStore(SQLiteEventStoreConfig(db_path=db_path))

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert version >= 1
    assert journal_mode == "wal"


def test_requirements_draft_versions_and_markdown_projection() -> None:
    draft = RequirementsDraft.empty()
    updated = draft.update_goal("prevent agents from skipping workflow")
    frozen = updated.freeze()

    assert updated.version == 2
    assert "prevent agents" in updated.to_markdown()
    assert frozen.frozen is True
    with pytest.raises(ValueError, match="frozen"):
        frozen.update_goal("new goal")


def test_replay_history_rejects_corrupt_event_version(tmp_path: Path) -> None:
    template = default_coding_agent_template()
    event = start_workflow("workflow-1", template)
    corrupt = record_work_completed(
        "workflow-1",
        Actor(kind=ActorKind.AGENT, actor_id="agent-1"),
        WorkResult(),
    )

    with pytest.raises(WorkflowHistoryCorrupt, match="non-contiguous"):
        replay_history([event, corrupt], template)


def test_concurrent_cas_conflict_is_reported(tmp_path: Path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    template = default_coding_agent_template()
    store.append("workflow-1", start_workflow("workflow-1", template), expected_version=0)
    event = record_work_completed(
        "workflow-1",
        Actor(kind=ActorKind.AGENT, actor_id="agent-1"),
        WorkResult(),
    )

    store.append("workflow-1", event, expected_version=1)
    with pytest.raises(WorkflowStoreConflict):
        store.append("workflow-1", event, expected_version=1)
