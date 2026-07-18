from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from workflow_control import (
    Actor,
    ActorKind,
    ApprovalDecision,
    Evidence,
    Gate,
    Lease,
    StateSnapshot,
    WorkItem,
    WorkspaceBinding,
    WorkflowValidationError,
)


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def test_gate_approval_binds_state_version_and_summary() -> None:
    gate = Gate(
        gate_id="gate-1",
        workflow_id="workflow-1",
        phase="design",
        state_version=7,
        gate_summary_hash="sha256:summary",
        head_sha="abc123",
    )
    actor = Actor(kind=ActorKind.HUMAN, actor_id="user-1", approval_capability=True)

    approval = gate.approve(
        actor=actor,
        decision=ApprovalDecision.APPROVED,
        client_id="cli-host",
        user_message_hash="sha256:ok",
    )

    assert approval.workflow_id == "workflow-1"
    assert approval.gate_id == "gate-1"
    assert approval.phase == "design"
    assert approval.state_version == 7
    assert approval.gate_summary_hash == "sha256:summary"
    assert approval.head_sha == "abc123"
    assert approval.matches_gate(gate)


def test_agent_cannot_create_gate_approval() -> None:
    gate = Gate(
        gate_id="gate-1",
        workflow_id="workflow-1",
        phase="design",
        state_version=7,
        gate_summary_hash="sha256:summary",
    )
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent-1", approval_capability=True)

    with pytest.raises(WorkflowValidationError, match="human approval capability"):
        gate.approve(
            actor=actor,
            decision=ApprovalDecision.APPROVED,
            client_id="prompt-adapter",
            user_message_hash="sha256:ok",
        )


def test_approval_detects_stale_gate_binding() -> None:
    gate = Gate(
        gate_id="gate-1",
        workflow_id="workflow-1",
        phase="design",
        state_version=7,
        gate_summary_hash="sha256:summary",
        head_sha="abc123",
    )
    changed_gate = Gate(
        gate_id="gate-1",
        workflow_id="workflow-1",
        phase="design",
        state_version=8,
        gate_summary_hash="sha256:changed",
        head_sha="def456",
    )
    actor = Actor(kind=ActorKind.HUMAN, actor_id="user-1", approval_capability=True)

    approval = gate.approve(
        actor=actor,
        decision=ApprovalDecision.APPROVED,
        client_id="cli-host",
        user_message_hash="sha256:ok",
    )

    assert approval.matches_gate(changed_gate) is False


def test_work_item_carries_allowed_actions_and_required_evidence() -> None:
    item = WorkItem(
        work_item_id="work-1",
        workflow_id="workflow-1",
        state=StateSnapshot(phase="building", sub_state="writing_tests"),
        allowed_actions=("write_tests", "run_tests"),
        required_evidence=(
            Evidence(ref="pytest-output", kind="test_result"),
        ),
    )

    assert item.allows("write_tests")
    assert not item.allows("approve_gate")
    assert item.required_evidence[0].kind == "test_result"


def test_lease_expiration_and_renewal() -> None:
    lease = Lease(
        lease_id="lease-1",
        work_item_id="work-1",
        owner_id="agent-1",
        expires_at=NOW + timedelta(minutes=5),
    )

    renewed = lease.renew(NOW + timedelta(minutes=10))

    assert lease.is_active_at(NOW)
    assert not lease.is_active_at(NOW + timedelta(minutes=6))
    assert renewed.expires_at == NOW + timedelta(minutes=10)


def test_workspace_binding_normalizes_worktree_path(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    binding = WorkspaceBinding(
        workflow_id="workflow-1",
        branch="automate-conversation-to-delivery-workflow/2026-07-14",
        worktree_path=worktree,
        head_sha="abc123",
    )

    assert binding.worktree_path == worktree.resolve()
