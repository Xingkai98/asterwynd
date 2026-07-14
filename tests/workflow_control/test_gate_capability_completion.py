from __future__ import annotations

import pytest

from workflow_control import (
    Actor,
    ActorKind,
    ApprovalDecision,
    CapabilityPolicy,
    Gate,
    GateApprovalTokenMatcher,
    GateEventType,
    HostApprovalService,
    WorkspaceWritePolicy,
    WorkflowValidationError,
)


def test_capability_policy_never_exposes_approval_to_agent() -> None:
    policy = CapabilityPolicy.for_agent()

    assert policy.can_approve_gate is False
    assert policy.allowed_commands == ("workflow enter", "workflow status", "workflow report")


def test_host_approval_service_consumes_exact_token_and_binds_gate() -> None:
    gate = Gate(
        gate_id="gate-1",
        workflow_id="workflow-1",
        phase="requirements",
        state_version=3,
        gate_summary_hash="sha256:summary",
        head_sha="abc123",
    )
    service = HostApprovalService(GateApprovalTokenMatcher())

    result = service.try_approve(
        gate=gate,
        raw_message="ok",
        user_id="human",
        client_id="cli-host",
    )

    assert result.consumed is True
    assert result.approval is not None
    assert result.approval.matches_gate(gate)
    assert result.event_type == GateEventType.APPROVED


def test_host_approval_service_rejects_non_whitelisted_message() -> None:
    gate = Gate("gate-1", "workflow-1", "requirements", 3, "sha256:summary")
    service = HostApprovalService(GateApprovalTokenMatcher())

    result = service.try_approve(gate, " ok", user_id="human", client_id="cli-host")

    assert result.consumed is False
    assert result.approval is None
    assert result.event_type == GateEventType.REACHED


def test_stale_approval_is_rejected_against_current_gate() -> None:
    old_gate = Gate("gate-1", "workflow-1", "requirements", 3, "sha256:old", head_sha="a")
    current_gate = Gate("gate-1", "workflow-1", "requirements", 4, "sha256:new", head_sha="b")
    approval = old_gate.approve(
        actor=Actor(kind=ActorKind.HUMAN, actor_id="human", approval_capability=True),
        decision=ApprovalDecision.APPROVED,
        client_id="cli-host",
        user_message_hash="sha256:ok",
    )

    with pytest.raises(WorkflowValidationError, match="stale approval"):
        HostApprovalService.validate_approval_for_gate(approval, current_gate)


def test_workspace_write_policy_fails_closed_at_gate() -> None:
    policy = WorkspaceWritePolicy()

    assert policy.can_write(phase="building", sub_state="implementing", has_active_lease=True)
    assert not policy.can_write(phase="building", sub_state="ready_for_review", has_active_lease=True)
    assert not policy.can_write(phase="building", sub_state="implementing", has_active_lease=False)
