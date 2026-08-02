"""Attack suite tests — data-driven malicious command regression.

Reads ``benchmarks/attacks/attacks.json`` and asserts the command guard denies
each attack case. Sensitive-read cases are default-allow at the guard level
(guardrail, not boundary) and are isolated by the backend instead — they are
tracked separately.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.tools.command_guard import CommandGuard, CommandVerdict

ATTACKS_FILE = Path(__file__).resolve().parents[2] / "benchmarks" / "attacks" / "attacks.json"


def _load_attacks() -> dict:
    return json.loads(ATTACKS_FILE.read_text(encoding="utf-8"))


ATTACKS = _load_attacks()
# Guard-level deny cases (default-allow sensitive reads are excluded here).
GUARD_DENY_CASES = [
    c for c in ATTACKS["cases"] if c["category"] != "sensitive-read"
]
SENSITIVE_READ_CASES = [
    c for c in ATTACKS["cases"] if c["category"] == "sensitive-read"
]


class TestAttackSuite:
    def test_suite_has_50_plus_cases(self) -> None:
        assert len(ATTACKS["cases"]) >= 50, f"attack suite has only {len(ATTACKS['cases'])} cases"

    @pytest.mark.parametrize(
        "case",
        GUARD_DENY_CASES,
        ids=[c["id"] for c in GUARD_DENY_CASES],
    )
    def test_guard_denies_attack(self, case: dict) -> None:
        """每个攻击 case 都应被命令护栏拒绝。"""
        guard = CommandGuard()
        assert guard.check(case["command"]) is CommandVerdict.DENY, (
            f"{case['id']} ({case['category']}) not denied: {case['command']!r}"
        )

    @pytest.mark.parametrize(
        "case",
        SENSITIVE_READ_CASES,
        ids=[c["id"] for c in SENSITIVE_READ_CASES],
    )
    def test_sensitive_read_is_default_allow_at_guard(self, case: dict) -> None:
        """敏感读取是 default-allow（护栏不是边界），由沙箱后端隔离兜底。"""
        guard = CommandGuard()
        # 护栏不拦（default-allow），沙箱隔离负责
        assert guard.check(case["command"]) is CommandVerdict.ALLOW


class TestAttackCoverage:
    def test_all_categories_represented(self) -> None:
        """8 类攻击都有覆盖。"""
        categories = {c["category"] for c in ATTACKS["cases"]}
        expected = {
            "file-destroy", "priv-esc", "code-exec",
            "exfil", "resource", "bypass", "sensitive-read",
        }
        assert expected.issubset(categories), f"missing categories: {expected - categories}"
