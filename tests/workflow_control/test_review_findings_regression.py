from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

import agent.main as cli
from workflow_control import (
    Actor,
    ActorKind,
    ApprovalDecision,
    Gate,
    ReviewResult,
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    WorkResult,
    WorkflowEvent,
    WorkflowOrchestrator,
    WorkflowOrchestratorConfig,
    WorkflowStoreConflict,
    WorkflowValidationError,
    WorktreeCoordinator,
    WorktreeCoordinatorConfig,
    default_coding_agent_template,
    record_work_completed,
    start_workflow,
)

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def _orchestrator(tmp_path: Path) -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
        )
    )


def test_cli_gate_approve_requires_trusted_host_env(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    runner = CliRunner()
    runner.invoke(cli.app, ["workflow", "enter", "--workflow", "workflow-1", "--db", str(db_path)])
    runner.invoke(cli.app, ["workflow", "report", "--workflow", "workflow-1", "--db", str(db_path), "--work-item-id", "workflow-1:1", "--expected-version", "1"])
    runner.invoke(cli.app, ["workflow", "report", "--workflow", "workflow-1", "--db", str(db_path), "--work-item-id", "workflow-1:2", "--expected-version", "2"])

    denied = runner.invoke(cli.app, ["workflow", "gate", "approve", "--workflow", "workflow-1", "--db", str(db_path), "--message", "ok"])
    assert denied.exit_code == 1
    assert "trusted host" in denied.stderr

    monkeypatch.setenv("ASTERWYND_WORKFLOW_TRUSTED_HOST", "1")
    monkeypatch.setenv("ASTERWYND_WORKFLOW_AGENT_CONTEXT", "1")
    still_denied = runner.invoke(cli.app, ["workflow", "gate", "approve", "--workflow", "workflow-1", "--db", str(db_path), "--message", "ok"])
    assert still_denied.exit_code == 1


def test_orchestrator_gate_approval_binds_current_gate_and_rejects_stale(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    orchestrator.enter("workflow-1", actor)
    orchestrator.report("workflow-1", actor, "workflow-1:1", WorkResult(), 1)
    orchestrator.report("workflow-1", actor, "workflow-1:2", WorkResult(), 2)
    old_gate = orchestrator.current_gate("workflow-1")
    approval = old_gate.approve(
        actor=Actor(kind=ActorKind.HUMAN, actor_id="human", approval_capability=True),
        decision=ApprovalDecision.APPROVED,
        client_id="cli-host",
        user_message_hash="sha256:ok",
    )

    # Drift the state version so the old approval no longer matches current gate.
    orchestrator.rollback("workflow-1", actor, "requirements", "drafting")
    orchestrator.report("workflow-1", actor, "workflow-1:4", WorkResult(), 4)

    with pytest.raises(WorkflowValidationError, match="stale approval"):
        orchestrator.approve_gate("workflow-1", approval=approval, expected_version=5)


def test_report_requires_matching_active_lease_owner_when_leased(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    owner = Actor(kind=ActorKind.AGENT, actor_id="owner")
    intruder = Actor(kind=ActorKind.AGENT, actor_id="intruder")
    entered = orchestrator.enter("workflow-1", owner, now=NOW, lease_ttl=timedelta(minutes=5))

    with pytest.raises(WorkflowValidationError, match="lease owner"):
        orchestrator.report("workflow-1", intruder, entered.work_item.work_item_id, WorkResult(), entered.snapshot.version)


def test_changes_requested_review_returns_to_fix_substate(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    orchestrator.enter("workflow-1", actor)
    orchestrator.report("workflow-1", actor, "workflow-1:1", WorkResult(), 1)
    orchestrator.report("workflow-1", actor, "workflow-1:2", WorkResult(), 2)

    result = orchestrator.record_review_result("workflow-1", Actor(kind=ActorKind.AGENT, actor_id="reviewer"), ReviewResult.CHANGES_REQUESTED, "executor")

    assert result.snapshot.state.phase == "requirements"
    assert result.snapshot.state.sub_state == "drafting"


def test_store_rejects_event_payload_for_different_workflow(tmp_path: Path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    template = default_coding_agent_template()

    with pytest.raises(WorkflowValidationError, match="workflow id mismatch"):
        store.append("workflow-1", start_workflow("workflow-2", template), expected_version=0)


def test_snapshot_replay_rejects_corrupt_stored_versions(tmp_path: Path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    template = default_coding_agent_template()
    store.append("workflow-1", start_workflow("workflow-1", template), expected_version=0)
    with pytest.raises(WorkflowStoreConflict):
        store.append("workflow-1", record_work_completed("workflow-1", Actor(kind=ActorKind.AGENT, actor_id="agent"), WorkResult()), expected_version=0)


def test_dirty_worktree_cleanup_is_blocked_and_branch_drift_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "worktrees"))
    binding = coordinator.create_or_reuse_worktree("change-one", "2026-07-14")
    (binding.worktree_path / "dirty.txt").write_text("dirty", encoding="utf-8")

    with pytest.raises(WorkflowValidationError, match="dirty worktree"):
        coordinator.cleanup_worktree(binding.worktree_path)

    _git(binding.worktree_path, "checkout", "-b", "drift")
    with pytest.raises(WorkflowValidationError, match="branch drift"):
        coordinator.create_or_reuse_worktree("change-one", "2026-07-14")


def _init_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("# repo\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")
    return path


def _git(cwd: Path, *args: str) -> str:
    import subprocess
    return subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()
