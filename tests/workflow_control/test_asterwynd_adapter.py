from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent.result import RunResult, StopReason
from agent.workflow_adapter import AsterwyndWorkflowExecutor
from workflow_control import (
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    StateSnapshot,
    WorkflowOrchestrator,
    WorkflowOrchestratorConfig,
    default_coding_agent_template,
)


@dataclass
class FakeAgent:
    workflow_context: dict | None = None
    seen_resume_snapshot: object | None = None

    def set_workflow_context(self, workflow_id: str, version: int, work_item_id: str | None = None) -> None:
        self.workflow_context = {
            "workflow_id": workflow_id,
            "version": version,
            "work_item_id": work_item_id,
        }

    async def run(self, messages, session_id: str, run_id: str, resume_snapshot=None):
        self.seen_resume_snapshot = resume_snapshot
        assert "workflow_id" in messages[0].content
        return RunResult(
            content="agent completed work item",
            stop_reason=StopReason.END_TURN,
            tool_calls_made=[],
        )


@pytest.mark.asyncio
async def test_asterwynd_adapter_reports_work_without_session_snapshot_state_source(tmp_path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(store=store, template=default_coding_agent_template()),
    )
    agent = FakeAgent()
    stale_resume_snapshot = object()

    result = await AsterwyndWorkflowExecutor(orchestrator, agent).run_once(
        "workflow-1",
        user_message="继续",
        session_id="session-1",
        run_id="run-1",
        resume_snapshot=stale_resume_snapshot,
    )

    assert result.snapshot.state == StateSnapshot(phase="requirements", sub_state="drafting")
    assert agent.workflow_context == {
        "workflow_id": "workflow-1",
        "version": 1,
        "work_item_id": "workflow-1:1",
    }
    assert agent.seen_resume_snapshot is stale_resume_snapshot
