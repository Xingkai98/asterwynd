"""Subagent run checkpoint persistence (issue 79, decision D2).

A subagent run's transcript is in-memory only today; when the parent process
ends or a run is interrupted, the child's context is lost. This module persists
a run checkpoint as a ``SessionSnapshot`` (extended with ``objective`` /
``blockers`` / ``next_steps``) on disk, reusing the main session's
``SessionStore`` machinery — ``schema_version`` compatibility, dedup hashing,
atomic tmp+replace writes — so a checkpoint can be reloaded and resumed through
the existing ``AgentLoop.run(resume_snapshot=...)`` path.

Layout: ``<workspace_root>/.asterwynd/subagents/<run_id>/`` with the key being
the full ``run_id`` (not the 8-char ``subagent_id``) so a collision can never
silently overwrite another run's checkpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from agent.session import SessionSnapshot, SessionStore

if TYPE_CHECKING:
    from agent.subagent.manager import SubagentRunRecord, SubagentSessionRecord


class SubagentSnapshotStore:
    """Checkpoint store for subagent runs, keyed by run_id."""

    def __init__(self, root: str | Path) -> None:
        self._store = SessionStore(str(root))

    @classmethod
    def for_workspace(cls, workspace_root: str | Path) -> "SubagentSnapshotStore":
        return cls(Path(workspace_root) / ".asterwynd" / "subagents")

    def save(self, snapshot: SessionSnapshot) -> bool:
        return self._store.save(snapshot)

    def load(self, run_id: str) -> SessionSnapshot | None:
        return self._store.load(run_id)

    def remove(self, run_id: str) -> bool:
        return self._store.remove(run_id)

    def snapshot_for_run(
        self,
        session: "SubagentSessionRecord",
        run: "SubagentRunRecord",
        bus_summary: str = "",
    ) -> SessionSnapshot:
        """Build the checkpoint for a session at the given run."""
        created = (
            datetime.fromtimestamp(run.created_at, tz=timezone.utc).isoformat()
            if run.created_at
            else ""
        )
        return SessionSnapshot(
            schema_version="1.0",
            session_id=run.run_id,
            created_at=created,
            updated_at=created,
            messages=list(session.messages),
            mode=session.mode,
            todos=[],
            active_skills=[],
            run_id=run.run_id,
            iteration=_iteration_from_run(run),
            objective=run.task,
            blockers=[],
            next_steps=[],
            bus_summary=bus_summary,
        )


def _iteration_from_run(run: "SubagentRunRecord") -> int:
    trace = run.trace or {}
    steps = trace.get("steps", [])
    return sum(1 for s in steps if s.get("type") == "llm_iteration")
