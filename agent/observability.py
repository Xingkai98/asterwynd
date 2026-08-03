"""Observability helpers — error classification and phase mapping.

Aligns with industry practice (OpenTelemetry GenAI / Langfuse): errors are
classified from *structured attributes* captured at the source (error_type,
finish_reason) rather than guessed from free text; text matching is only a
fallback. Semantic errors (hallucination) are intentionally not auto-classified
here — that needs an LLM judge, consistent with the benchmark judge decision.

Phase mapping converts an AgentMode (build/read_only/plan/bypass) into a
runtime phase label used for cost attribution. It deliberately does NOT reuse
the dev-workflow four phases (wayfinding/planning/building/closing) — those are
a different layer.
"""
from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    """Structured error categories for system-level failures."""

    PERMISSION_DENIED = "permission_denied"
    NETWORK_TIMEOUT = "network_timeout"
    MODEL_ERROR = "model_error"
    PARAMETER_ERROR = "parameter_error"
    UNKNOWN = "unknown"


# AgentMode -> runtime phase label (for cost attribution).
PHASE_BY_MODE: dict[str, str] = {
    "build": "building",
    "read_only": "review",
    "plan": "planning",
    "bypass": "bypass",
}

_DEFAULT_PHASE = "building"

# Structured error_type -> category (primary signal).
# error_type carries the fine-grained value from the error source (issue #89);
# categories stay coarse (four-class, spec-pinned) so the alert policy is
# stable. Approval-denied variants map to PERMISSION_DENIED (a denied tool did
# not run due to permission semantics).
_ERROR_TYPE_TO_CATEGORY: dict[str, ErrorCategory] = {
    "permission_denied": ErrorCategory.PERMISSION_DENIED,
    "permission": ErrorCategory.PERMISSION_DENIED,
    "approval_required": ErrorCategory.PERMISSION_DENIED,
    "approval_denied": ErrorCategory.PERMISSION_DENIED,
    "approval_unavailable": ErrorCategory.PERMISSION_DENIED,
    "timeout": ErrorCategory.NETWORK_TIMEOUT,
    "network_timeout": ErrorCategory.NETWORK_TIMEOUT,
    "network_error": ErrorCategory.NETWORK_TIMEOUT,
    "rate_limit": ErrorCategory.NETWORK_TIMEOUT,
    "parse_error": ErrorCategory.PARAMETER_ERROR,
    "parameter_error": ErrorCategory.PARAMETER_ERROR,
    "invalid_argument": ErrorCategory.PARAMETER_ERROR,
    "unknown_tool": ErrorCategory.PARAMETER_ERROR,
    "mcp_error": ErrorCategory.UNKNOWN,
    "resource_exhausted": ErrorCategory.UNKNOWN,
    "unavailable": ErrorCategory.UNKNOWN,
}

# Text fallback patterns -> category (used only when no structured field).
_TEXT_PATTERNS: list[tuple[tuple[str, ...], ErrorCategory]] = [
    (("[permission denied", "permission denied", "not allowed", "denied by workspace"), ErrorCategory.PERMISSION_DENIED),
    (("timeout", "timed out", "rate limit", "network unreachable", "connection"), ErrorCategory.NETWORK_TIMEOUT),
]

# Per-category alert policy.
_ALERT_LEVEL: dict[ErrorCategory, str] = {
    ErrorCategory.PERMISSION_DENIED: "immediate",
    ErrorCategory.NETWORK_TIMEOUT: "warn",
    ErrorCategory.MODEL_ERROR: "warn",
    ErrorCategory.PARAMETER_ERROR: "record",
    ErrorCategory.UNKNOWN: "record",
}


def resolve_phase(mode: str) -> str:
    """Map an AgentMode value to a runtime phase label."""
    return PHASE_BY_MODE.get(mode, _DEFAULT_PHASE)


class ErrorClassifier:
    """Classify an error into a structured category.

    Priority: structured ``error_type`` → ``finish_reason`` → text fallback.
    """

    def classify(
        self,
        *,
        error_type: str | None = None,
        finish_reason: str | None = None,
        text: str | None = None,
    ) -> ErrorCategory:
        # 1. Structured error_type maps directly.
        if error_type:
            cat = _ERROR_TYPE_TO_CATEGORY.get(error_type.lower())
            if cat is not None:
                return cat
        # 2. finish_reason implies model error (max_tokens cutoff etc).
        if finish_reason:
            if finish_reason in ("max_tokens", "length", "content_filter"):
                return ErrorCategory.MODEL_ERROR
            if finish_reason == "error":
                return ErrorCategory.PARAMETER_ERROR
        # 3. Text fallback (only when no structured signal matched).
        if text:
            lowered = text.lower()
            for keywords, cat in _TEXT_PATTERNS:
                if any(kw in lowered for kw in keywords):
                    return cat
            # Generic "[Error: ..." with no known signal → parameter error.
            if "[error:" in lowered or lowered.startswith("error:"):
                return ErrorCategory.PARAMETER_ERROR
        return ErrorCategory.UNKNOWN

    @staticmethod
    def alert_level(category: ErrorCategory) -> str:
        """Return the alert policy for a category (immediate/warn/record)."""
        return _ALERT_LEVEL.get(category, "record")
