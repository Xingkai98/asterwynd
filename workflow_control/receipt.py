from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)


RECEIPT_FILE = "workflow-receipt.json"
RECEIPT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class WorkflowSigner:
    key_id: str
    private_key_path: Path
    public_key_path: Path
    status: str = "active"


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def event_chain_root(events: list[dict[str, Any]]) -> str:
    redacted_events = []
    for event in events:
        redacted = {
            key: value
            for key, value in event.items()
            if key not in {"raw_user_message", "messages", "transcript", "tool_output"}
        }
        redacted_events.append(redacted)
    return "sha256:" + sha256_hex(canonical_json_bytes({"events": redacted_events}))


def ensure_workflow_signer(key_dir: Path, trusted_signers_dir: Path, key_id: str = "local-workflow") -> WorkflowSigner:
    key_dir.mkdir(parents=True, exist_ok=True)
    trusted_signers_dir.mkdir(parents=True, exist_ok=True)
    private_path = key_dir / f"{key_id}.key"
    public_path = trusted_signers_dir / f"{key_id}.json"
    if private_path.exists():
        private_key = load_pem_private_key(private_path.read_bytes(), password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("workflow signer private key is not Ed25519")
    else:
        private_key = Ed25519PrivateKey.generate()
        private_path.write_bytes(
            private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.PKCS8,
                encryption_algorithm=NoEncryption(),
            ),
        )
        os.chmod(private_path, 0o600)
    public_key = private_key.public_key()
    public_path.write_text(
        json.dumps(
            {
                "key_id": key_id,
                "algorithm": "Ed25519",
                "status": "active",
                "public_key": base64.b64encode(
                    public_key.public_bytes(
                        encoding=Encoding.Raw,
                        format=PublicFormat.Raw,
                    ),
                ).decode("ascii"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return WorkflowSigner(
        key_id=key_id,
        private_key_path=private_path,
        public_key_path=public_path,
    )


def artifact_hashes(change_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(change_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(change_dir).as_posix()
        if rel == RECEIPT_FILE:
            continue
        if rel.startswith("."):
            continue
        hashes[rel] = "sha256:" + sha256_hex(path.read_bytes())
    return hashes


def build_receipt_payload(
    *,
    change_dir: Path,
    workflow_id: str,
    template_id: str,
    final_state: dict[str, str],
    final_version: int,
    events: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    base_branch: str,
    base_commit: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "change_id": change_dir.name,
        "template_id": template_id,
        "final_state": final_state,
        "final_version": final_version,
        "event_chain_root": event_chain_root(events),
        "base": {
            "branch": base_branch,
            "commit": base_commit,
        },
        "gates": gates,
        "artifact_hashes": artifact_hashes(change_dir),
    }
    _assert_receipt_minimized(payload)
    return payload


def sign_receipt_payload(payload: dict[str, Any], signer: WorkflowSigner) -> dict[str, Any]:
    private_key = load_pem_private_key(signer.private_key_path.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("workflow signer private key is not Ed25519")
    signed = dict(payload)
    signed["signer"] = {
        "key_id": signer.key_id,
        "algorithm": "Ed25519",
    }
    signature = private_key.sign(canonical_json_bytes(signed))
    signed["signature"] = {
        "key_id": signer.key_id,
        "algorithm": "Ed25519",
        "value": base64.b64encode(signature).decode("ascii"),
    }
    return signed


def write_workflow_receipt(change_dir: Path, payload: dict[str, Any], signer: WorkflowSigner) -> Path:
    receipt = sign_receipt_payload(payload, signer)
    path = change_dir / RECEIPT_FILE
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def verify_workflow_receipt(receipt_path: Path, trusted_signers_dir: Path, *, allow_retired: bool = True) -> list[str]:
    errors: list[str] = []
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid receipt JSON: {exc}"]
    signature = receipt.get("signature")
    if not isinstance(signature, dict):
        return ["receipt missing signature"]
    key_id = signature.get("key_id")
    signature_value = signature.get("value")
    signer_path = trusted_signers_dir / f"{key_id}.json"
    if not signer_path.exists():
        return [f"receipt signer is not trusted: {key_id}"]
    signer = json.loads(signer_path.read_text(encoding="utf-8"))
    status = signer.get("status")
    if status == "compromised":
        errors.append("receipt signer is compromised")
    if status == "retired" and not allow_retired:
        errors.append("retired signer cannot sign new receipt")
    if status not in {"active", "retired", "compromised"}:
        errors.append(f"unknown signer status: {status}")
    unsigned = dict(receipt)
    unsigned.pop("signature", None)
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(signer["public_key"]))
        public_key.verify(base64.b64decode(signature_value), canonical_json_bytes(unsigned))
    except (InvalidSignature, KeyError, ValueError) as exc:
        errors.append(f"receipt signature invalid: {exc}")
    errors.extend(_validate_receipt_contents(receipt_path.parent, receipt))
    return errors


def _validate_receipt_contents(change_dir: Path, receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        _assert_receipt_minimized(receipt)
    except ValueError as exc:
        errors.append(str(exc))
    expected_hashes = artifact_hashes(change_dir)
    if receipt.get("artifact_hashes") != expected_hashes:
        errors.append("receipt artifact hashes do not match change files")
    if not receipt.get("event_chain_root", "").startswith("sha256:"):
        errors.append("receipt missing event-chain root")
    for gate in receipt.get("gates", []):
        for field in ("phase", "state_version", "decision", "branch", "head_sha", "evidence_hash", "gate_summary_hash"):
            if field not in gate:
                errors.append(f"receipt gate missing field: {field}")
    return errors


def _assert_receipt_minimized(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False)
    forbidden = ("raw_user_message", "transcript", "messages", "tool_output", "approval_secret")
    for token in forbidden:
        if token in encoded:
            raise ValueError(f"receipt contains forbidden field: {token}")
    for key, value in _walk_items(payload):
        if isinstance(key, str) and key.startswith("/"):
            raise ValueError("receipt contains absolute path")
        if isinstance(value, str) and value.startswith("/") and "path" in str(key):
            raise ValueError("receipt contains absolute path")


def _walk_items(value: Any, key: str = ""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield child_key, child
            yield from _walk_items(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            yield from _walk_items(child, key)
