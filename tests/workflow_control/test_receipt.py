from __future__ import annotations

import json
import os
import stat

from workflow_control.receipt import (
    build_receipt_payload,
    ensure_workflow_signer,
    verify_workflow_receipt,
    write_workflow_receipt,
)


def _change_dir(tmp_path):
    change_dir = tmp_path / "change-1"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("# Proposal\n", encoding="utf-8")
    (change_dir / "design.md").write_text("# Design\n", encoding="utf-8")
    (change_dir / "tasks.md").write_text("- [x] done\n", encoding="utf-8")
    return change_dir


def _payload(change_dir):
    return build_receipt_payload(
        change_dir=change_dir,
        workflow_id="workflow-1",
        template_id="template-1",
        final_state={"phase": "done", "sub_state": "done"},
        final_version=7,
        events=[{"event_type": "workflow_started"}, {"event_type": "gate_approved"}],
        gates=[
            {
                "phase": "building",
                "state_version": 4,
                "decision": "approved",
                "branch": "change-1/2026-07-15",
                "head_sha": "abc123",
                "evidence_hash": "sha256:evidence",
                "gate_summary_hash": "sha256:gate",
            },
        ],
        base_branch="master",
        base_commit="base123",
    )


def test_workflow_receipt_signs_and_verifies(tmp_path) -> None:
    change_dir = _change_dir(tmp_path)
    signer = ensure_workflow_signer(tmp_path / "keys", tmp_path / ".workflow" / "trusted-signers")

    receipt_path = write_workflow_receipt(change_dir, _payload(change_dir), signer)

    assert verify_workflow_receipt(receipt_path, signer.public_key_path.parent) == []
    private_mode = stat.S_IMODE(os.stat(signer.private_key_path).st_mode)
    assert private_mode == 0o600


def test_workflow_receipt_rejects_tampering(tmp_path) -> None:
    change_dir = _change_dir(tmp_path)
    signer = ensure_workflow_signer(tmp_path / "keys", tmp_path / ".workflow" / "trusted-signers")
    receipt_path = write_workflow_receipt(change_dir, _payload(change_dir), signer)
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    data["final_version"] = 8
    receipt_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    errors = verify_workflow_receipt(receipt_path, signer.public_key_path.parent)

    assert any("signature invalid" in error for error in errors)


def test_workflow_receipt_rejects_compromised_signer(tmp_path) -> None:
    change_dir = _change_dir(tmp_path)
    signer = ensure_workflow_signer(tmp_path / "keys", tmp_path / ".workflow" / "trusted-signers")
    receipt_path = write_workflow_receipt(change_dir, _payload(change_dir), signer)
    signer_data = json.loads(signer.public_key_path.read_text(encoding="utf-8"))
    signer_data["status"] = "compromised"
    signer.public_key_path.write_text(json.dumps(signer_data), encoding="utf-8")

    errors = verify_workflow_receipt(receipt_path, signer.public_key_path.parent)

    assert "receipt signer is compromised" in errors


def test_workflow_receipt_rejects_absolute_paths_and_full_events(tmp_path) -> None:
    change_dir = _change_dir(tmp_path)
    payload = _payload(change_dir)
    payload["artifact_hashes"]["/tmp/secret"] = "sha256:value"

    try:
        build_receipt_payload(
            change_dir=change_dir,
            workflow_id="workflow-1",
            template_id="template-1",
            final_state={"phase": "done", "sub_state": "done"},
            final_version=7,
            events=[{"raw_user_message": "secret"}],
            gates=[],
            base_branch="master",
            base_commit="base123",
        )
    except ValueError as exc:
        raise AssertionError("event redaction should remove raw_user_message") from exc

    from workflow_control.receipt import _assert_receipt_minimized

    try:
        _assert_receipt_minimized(payload)
    except ValueError as exc:
        assert "absolute path" in str(exc)
    else:
        raise AssertionError("absolute path should be rejected")


def test_workflow_receipt_rejects_artifact_hash_mismatch(tmp_path) -> None:
    change_dir = _change_dir(tmp_path)
    signer = ensure_workflow_signer(tmp_path / "keys", tmp_path / ".workflow" / "trusted-signers")
    receipt_path = write_workflow_receipt(change_dir, _payload(change_dir), signer)
    (change_dir / "tasks.md").write_text("- [ ] changed\n", encoding="utf-8")

    errors = verify_workflow_receipt(receipt_path, signer.public_key_path.parent)

    assert "receipt artifact hashes do not match change files" in errors
