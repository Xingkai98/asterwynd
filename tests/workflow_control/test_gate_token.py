from __future__ import annotations

from workflow_control import GateApprovalTokenMatcher


def test_default_gate_token_accepts_exact_ascii_ok_only() -> None:
    matcher = GateApprovalTokenMatcher()

    assert matcher.matches("ok")


def test_default_gate_token_rejects_case_and_whitespace_variants() -> None:
    matcher = GateApprovalTokenMatcher()

    assert not matcher.matches("OK")
    assert not matcher.matches("Ok")
    assert not matcher.matches(" ok")
    assert not matcher.matches("ok ")
    assert not matcher.matches("ok\n")
    assert not matcher.matches("ok，继续")


def test_gate_token_rejects_unicode_lookalikes_without_normalization() -> None:
    matcher = GateApprovalTokenMatcher()

    assert not matcher.matches("ｏｋ")
    assert not matcher.matches("o\u0301k")


def test_gate_token_uses_configured_exact_whitelist() -> None:
    matcher = GateApprovalTokenMatcher(allowed_tokens=("ok", "approve"))

    assert matcher.matches("approve")
    assert not matcher.matches("approved")
