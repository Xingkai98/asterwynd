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
    RequirementsDraft,
    WorkResult,
    WorkflowEvent,
    WorkflowOrchestrator,
    WorkflowOrchestratorConfig,
    WorkflowStoreConflict,
    WorkflowValidationError,
    WorktreeCoordinator,
    WorktreeCoordinatorConfig,
    build_gate_binding,
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
    orchestrator.enter("workflow-1", actor)
    orchestrator.report("workflow-1", actor, "workflow-1:4", WorkResult(), 4)

    with pytest.raises(WorkflowValidationError, match="stale approval"):
        orchestrator.approve_gate("workflow-1", approval=approval, expected_version=5)


def test_report_requires_matching_active_lease_owner_when_leased(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    owner = Actor(kind=ActorKind.AGENT, actor_id="owner")
    intruder = Actor(kind=ActorKind.AGENT, actor_id="intruder")
    entered = orchestrator.enter("workflow-1", owner, lease_ttl=timedelta(days=1))

    with pytest.raises(WorkflowValidationError, match="lease owner"):
        orchestrator.report("workflow-1", intruder, entered.work_item.work_item_id, WorkResult(), entered.snapshot.version)


def test_changes_requested_review_returns_to_fix_substate(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    orchestrator.enter("workflow-1", actor)
    orchestrator.report("workflow-1", actor, "workflow-1:1", WorkResult(), 1)
    orchestrator.report("workflow-1", actor, "workflow-1:2", WorkResult(), 2)
    orchestrator.rollback("workflow-1", actor, "code-review", "reviewing_code")

    result = orchestrator.record_review_result("workflow-1", Actor(kind=ActorKind.AGENT, actor_id="reviewer"), ReviewResult.CHANGES_REQUESTED, "executor")

    assert result.snapshot.state.phase == "building"
    assert result.snapshot.state.sub_state == "writing_tests"


def test_review_result_is_rejected_outside_review_state(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    orchestrator.enter("workflow-1", actor)

    with pytest.raises(WorkflowValidationError, match="review state"):
        orchestrator.record_review_result(
            "workflow-1",
            Actor(kind=ActorKind.AGENT, actor_id="reviewer"),
            ReviewResult.CHANGES_REQUESTED,
            "executor",
        )
    assert len(orchestrator.config.store.list_events("workflow-1")) == 1


def test_design_gate_requires_committed_gate_binding(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo-for-gate")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "gate-worktrees"))
    workspace = coordinator.create_or_reuse_worktree("workflow-1", "2026-07-14")
    (workspace.worktree_path / "design.md").write_text("design\n", encoding="utf-8")
    phase_commit = coordinator.commit_phase(workspace.worktree_path, "design ready")
    orchestrator = _orchestrator(tmp_path)
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    human = Actor(kind=ActorKind.HUMAN, actor_id="human", approval_capability=True)
    orchestrator.enter("workflow-1", actor)
    orchestrator.report("workflow-1", actor, "workflow-1:1", WorkResult(), 1)
    orchestrator.report("workflow-1", actor, "workflow-1:2", WorkResult(), 2)
    orchestrator.approve_gate("workflow-1", expected_version=3, actor=human, raw_user_message="ok")
    design_item = orchestrator.enter("workflow-1", actor)
    orchestrator.report(
        "workflow-1",
        actor,
        design_item.work_item.work_item_id,
        WorkResult(evidence_refs=("design.md",)),
        design_item.snapshot.version,
    )

    with pytest.raises(WorkflowValidationError, match="committed gate binding"):
        orchestrator.approve_gate("workflow-1", expected_version=5, actor=human, raw_user_message="ok")

    binding = build_gate_binding(
        policy="required_before_human_gate",
        phase="design",
        state_version=5,
        branch=workspace.branch,
        head_sha=phase_commit.head_sha,
        evidence_hash="sha256:evidence",
        clean_worktree=True,
    )
    assert binding is not None
    approval = orchestrator.current_gate_for_binding("workflow-1", binding).approve(
        actor=human,
        decision=ApprovalDecision.APPROVED,
        client_id="trusted-host",
        user_message_hash="sha256:ok",
    )

    result = orchestrator.approve_gate(
        "workflow-1",
        expected_version=5,
        approval=approval,
        gate_binding=binding,
        worktree_path=workspace.worktree_path,
    )

    assert result.snapshot.state.phase == "building"


def test_requirements_gate_promotion_materializes_worktree_and_event_binding(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo-for-promotion")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "promotion-worktrees"))
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
            worktree_coordinator=coordinator,
        )
    )
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    human = Actor(kind=ActorKind.HUMAN, actor_id="human", approval_capability=True)
    orchestrator.enter("workflow-1", actor)
    orchestrator.report("workflow-1", actor, "workflow-1:1", WorkResult(), 1)
    orchestrator.report("workflow-1", actor, "workflow-1:2", WorkResult(), 2)
    draft = orchestrator.config.store.save_requirements_snapshot(
        "workflow-1",
        3,
        RequirementsDraft.empty().update_goal("workflow control"),
    )

    result = orchestrator.approve_gate(
        "workflow-1",
        expected_version=3,
        actor=human,
        raw_user_message="ok",
        requirements_draft=draft,
        change_id="change-one",
        date="2026-07-14",
        allow_local_base=True,
    )

    assert result.snapshot.state.phase == "design"
    assert (tmp_path / "promotion-worktrees" / "change-one" / "openspec" / "changes" / "change-one" / "proposal.md").exists()
    assert (tmp_path / "promotion-worktrees" / "change-one" / "openspec" / "changes" / "change-one" / "specs" / "conversation-delivery-workflow" / "spec.md").exists()
    approved_event = orchestrator.config.store.list_events("workflow-1")[-1]
    assert approved_event.workspace_binding is not None
    assert approved_event.workspace_binding.branch == "change-one/2026-07-14"
    assert approved_event.workspace_binding.base_branch == "master"
    assert approved_event.workspace_binding.base_commit is not None
    assert approved_event.workspace_binding.base_check == "local_base_override"


def test_closing_gate_approval_enters_done_phase(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo-for-closing")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "closing-worktrees"))
    workspace = coordinator.create_or_reuse_worktree("workflow-1", "2026-07-14")
    (workspace.worktree_path / "archive.txt").write_text("archive\n", encoding="utf-8")
    phase_commit = coordinator.commit_phase(workspace.worktree_path, "archive ready")
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
            worktree_coordinator=coordinator,
        )
    )
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    human = Actor(kind=ActorKind.HUMAN, actor_id="human", approval_capability=True)
    orchestrator.enter("workflow-1", actor)
    orchestrator.rollback("workflow-1", actor, "closing", "ready_for_review")
    binding = build_gate_binding(
        policy="required_before_human_gate",
        phase="closing",
        state_version=2,
        branch=workspace.branch,
        head_sha=phase_commit.head_sha,
        evidence_hash="sha256:archive",
        clean_worktree=True,
    )
    assert binding is not None
    approval = orchestrator.current_gate_for_binding("workflow-1", binding).approve(
        actor=human,
        decision=ApprovalDecision.APPROVED,
        client_id="trusted-host",
        user_message_hash="sha256:ok",
    )

    result = orchestrator.approve_gate(
        "workflow-1",
        expected_version=2,
        approval=approval,
        gate_binding=binding,
        worktree_path=workspace.worktree_path,
    )

    assert result.snapshot.state.phase == "done"
    assert result.snapshot.state.sub_state == "done"
    assert not workspace.worktree_path.exists()
    assert coordinator.binding_for_branch(workspace.branch) is None


def test_requirements_promotion_append_conflict_cleans_materialized_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo-for-conflict")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "conflict-worktrees"))
    real_store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    store = _ConflictOnGateAppendStore(real_store)
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=store,
            template=default_coding_agent_template(),
            worktree_coordinator=coordinator,
        )
    )
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    human = Actor(kind=ActorKind.HUMAN, actor_id="human", approval_capability=True)
    orchestrator.enter("workflow-1", actor)
    orchestrator.report("workflow-1", actor, "workflow-1:1", WorkResult(), 1)
    orchestrator.report("workflow-1", actor, "workflow-1:2", WorkResult(), 2)
    requirements_snapshot = real_store.save_requirements_snapshot(
        "workflow-1",
        3,
        RequirementsDraft.empty().update_goal("conflict"),
    )
    store.fail_next_gate_append = True

    with pytest.raises(WorkflowStoreConflict):
        orchestrator.approve_gate(
            "workflow-1",
            expected_version=3,
            actor=human,
            raw_user_message="ok",
            requirements_draft=requirements_snapshot,
            change_id="conflict-change",
            date="2026-07-14",
            allow_local_base=True,
        )

    assert not (tmp_path / "conflict-worktrees" / "conflict-change").exists()


class _ConflictOnGateAppendStore:
    def __init__(self, wrapped: SQLiteEventStore) -> None:
        self.wrapped = wrapped
        self.fail_next_gate_append = False

    def append(self, workflow_id, event, expected_version):
        if self.fail_next_gate_append and event.event_type.value == "gate_approved":
            self.fail_next_gate_append = False
            raise WorkflowStoreConflict("synthetic append conflict")
        return self.wrapped.append(workflow_id, event, expected_version)

    def __getattr__(self, name):
        return getattr(self.wrapped, name)


def test_requirements_promotion_failure_blocks_workflow(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo-for-blocked-promotion")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "blocked-worktrees"))
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
            worktree_coordinator=coordinator,
        )
    )
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    human = Actor(kind=ActorKind.HUMAN, actor_id="human", approval_capability=True)
    orchestrator.enter("workflow-1", actor)
    orchestrator.report("workflow-1", actor, "workflow-1:1", WorkResult(), 1)
    orchestrator.report("workflow-1", actor, "workflow-1:2", WorkResult(), 2)

    result = orchestrator.approve_gate(
        "workflow-1",
        expected_version=3,
        actor=human,
        raw_user_message="ok",
        requirements_draft=orchestrator.config.store.save_requirements_snapshot(
            "workflow-1",
            3,
            RequirementsDraft.empty().update_goal("blocked"),
        ),
        change_id="blocked-change",
        date="2026-07-14",
        allow_local_base=False,
    )

    assert result.snapshot.state.phase == "blocked"
    assert not (tmp_path / "blocked-worktrees" / "blocked-change").exists()


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
