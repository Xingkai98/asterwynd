from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import workflow_control
from workflow_control import (
    AgingAction,
    AgingPolicy,
    OutputStatus,
    PhaseCommitPolicy,
    StateSnapshot,
    WorkflowOutput,
    WorkflowSnapshot,
    accept_outputs,
    build_gate_binding,
    default_coding_agent_template,
    lazy_aging_scan,
    retain_output,
)

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def test_output_acceptance_promotes_draft_and_proposed_to_durable() -> None:
    outputs = (
        WorkflowOutput(ref="draft", status=OutputStatus.DRAFT),
        WorkflowOutput(ref="proposal", status=OutputStatus.PROPOSED),
    )

    accepted = accept_outputs(outputs, refs=("draft", "proposal"))

    assert [output.status for output in accepted] == [OutputStatus.DURABLE, OutputStatus.DURABLE]


def test_retain_output_is_mini_gate_for_single_output() -> None:
    output = WorkflowOutput(ref="scope", status=OutputStatus.PROPOSED)

    retained = retain_output(output)

    assert retained.status == OutputStatus.DURABLE
    assert retained.ref == "scope"


def test_lazy_aging_scan_is_idempotent_and_abandons_only_once() -> None:
    snapshot = WorkflowSnapshot(
        workflow_id="workflow-1",
        state=StateSnapshot(phase="exploring", sub_state="chatting"),
        version=1,
        events_seen=1,
    )

    first = lazy_aging_scan(
        snapshot=snapshot,
        outputs=(),
        last_activity_at=NOW - timedelta(days=2),
        now=NOW,
        policy=AgingPolicy(ttl=timedelta(hours=24)),
        already_abandoned=False,
    )
    second = lazy_aging_scan(
        snapshot=snapshot,
        outputs=(),
        last_activity_at=NOW - timedelta(days=2),
        now=NOW,
        policy=AgingPolicy(ttl=timedelta(hours=24)),
        already_abandoned=True,
    )

    assert first.action == AgingAction.ABANDON
    assert second.action == AgingAction.KEEP
    assert second.reason == "already_abandoned"


def test_commit_policy_builds_gate_binding_and_detects_dirty_worktree() -> None:
    binding = build_gate_binding(
        policy=PhaseCommitPolicy.REQUIRED_BEFORE_HUMAN_GATE,
        phase="building",
        state_version=12,
        branch="feature/x",
        head_sha="abc123",
        evidence_hash="sha256:evidence",
        clean_worktree=True,
    )

    assert binding.phase == "building"
    assert binding.head_sha == "abc123"
    assert binding.gate_summary_hash.startswith("sha256:")

    with pytest.raises(workflow_control.WorkflowValidationError, match="clean worktree"):
        build_gate_binding(
            policy=PhaseCommitPolicy.REQUIRED_BEFORE_HUMAN_GATE,
            phase="building",
            state_version=12,
            branch="feature/x",
            head_sha="abc123",
            evidence_hash="sha256:evidence",
            clean_worktree=False,
        )


def test_workflow_control_does_not_import_agent_package() -> None:
    root = Path(workflow_control.__file__).resolve().parent
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "agent" and not alias.name.startswith("agent.")
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "agent" and not (node.module or "").startswith("agent.")


def test_default_template_has_commit_policy_objects() -> None:
    template = default_coding_agent_template()

    assert template.phase("exploring").commit_policy == PhaseCommitPolicy.NONE
    assert template.phase("requirements").commit_policy == PhaseCommitPolicy.NONE
    assert template.phase("building").commit_policy == PhaseCommitPolicy.REQUIRED_BEFORE_HUMAN_GATE
