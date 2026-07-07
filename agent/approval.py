from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from agent.tool_permissions import PermissionDecision


SENSITIVE_KEY_PATTERN = re.compile(
    r"(key|token|secret|password|credential|authorization|api_key)",
    re.IGNORECASE,
)
SENSITIVE_STRING_PATTERNS = (
    re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"(?i)(api_key=)[^&\s]+"),
)
REDACTED = "[redacted]"
ARGUMENT_SUMMARY_LIMIT = 2000


class ApprovalDecisionStatus(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    tool_call_id: str
    tool_name: str
    mode: str
    capability: list[str]
    risk: str
    origin: str
    reason: str
    profile_name: str
    redacted_args: dict[str, Any]
    args_summary: str
    session_id: str | None = None
    run_id: str | None = None

    def to_event_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "approval_id": self.approval_id,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "mode": self.mode,
            "capability": self.capability,
            "risk": self.risk,
            "origin": self.origin,
            "reason": self.reason,
            "profile_name": self.profile_name,
            "redacted_args": self.redacted_args,
            "args_summary": self.args_summary,
        }
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.run_id is not None:
            data["run_id"] = self.run_id
        return data


@dataclass(frozen=True)
class ApprovalResponse:
    approval_id: str
    status: ApprovalDecisionStatus
    reason: str = ""

    @property
    def approved(self) -> bool:
        return self.status is ApprovalDecisionStatus.APPROVED


class ApprovalHandler(Protocol):
    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        ...


class FailClosedApprovalHandler:
    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        return ApprovalResponse(
            approval_id=request.approval_id,
            status=ApprovalDecisionStatus.UNAVAILABLE,
            reason="approval is unavailable in this runtime",
        )


class CliApprovalHandler:
    def __init__(self, *, interactive: bool):
        self.interactive = interactive

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        if not self.interactive or not sys.stdin.isatty():
            return ApprovalResponse(
                approval_id=request.approval_id,
                status=ApprovalDecisionStatus.UNAVAILABLE,
                reason="approval requires interactive TTY",
            )

        print(_render_cli_prompt(request), file=sys.stderr)
        answer = input("Approve? [y/N] ").strip().lower()
        if answer in {"y", "yes"}:
            return ApprovalResponse(
                approval_id=request.approval_id,
                status=ApprovalDecisionStatus.APPROVED,
                reason="approved by user",
            )
        return ApprovalResponse(
            approval_id=request.approval_id,
            status=ApprovalDecisionStatus.DENIED,
            reason="denied by user",
        )


def build_approval_request(
    *,
    tool_call_id: str,
    arguments: dict[str, Any],
    decision: PermissionDecision,
    mode: Any,
    session_id: str | None = None,
    run_id: str | None = None,
) -> ApprovalRequest:
    redacted_args = redact_value(arguments)
    if not isinstance(redacted_args, dict):
        redacted_args = {}
    return ApprovalRequest(
        approval_id=str(uuid.uuid4()),
        tool_call_id=tool_call_id,
        tool_name=decision.tool_name,
        mode=mode.value,
        capability=sorted(capability.value for capability in decision.permission.capabilities),
        risk=decision.permission.risk_level.value,
        origin=decision.permission.origin.value,
        reason=decision.reason,
        profile_name=decision.profile_name,
        redacted_args=redacted_args,
        args_summary=summarize_arguments(redacted_args),
        session_id=session_id,
        run_id=run_id,
    )


def summarize_arguments(arguments: dict[str, Any]) -> str:
    encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    if len(encoded) <= ARGUMENT_SUMMARY_LIMIT:
        return encoded
    suffix = f"... [truncated {len(encoded) - ARGUMENT_SUMMARY_LIMIT} chars]"
    return encoded[: ARGUMENT_SUMMARY_LIMIT - len(suffix)] + suffix


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if SENSITIVE_KEY_PATTERN.search(key_text):
                redacted[key_text] = REDACTED
            else:
                redacted[key_text] = redact_value(child)
        return redacted
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in SENSITIVE_STRING_PATTERNS:
            redacted = pattern.sub(_redact_string_match, redacted)
        return redacted
    return value


def _redact_string_match(match: re.Match[str]) -> str:
    if match.re.pattern.startswith("(?i)(api_key=)"):
        return f"{match.group(1)}{REDACTED}"
    return REDACTED


def _render_cli_prompt(request: ApprovalRequest) -> str:
    payload = {
        "tool": request.tool_name,
        "mode": request.mode,
        "capability": request.capability,
        "risk": request.risk,
        "origin": request.origin,
        "reason": request.reason,
        "args": request.redacted_args,
    }
    return "Approval required:\n" + summarize_arguments(payload)
