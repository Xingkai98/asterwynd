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


class TestAttackSuiteWithWriteAllowlist:
    """配置了显式可写豁免后，攻击集仍须被拦（change: guard-write-allowlist）。

    豁免是**按路径**生效的，不是「开了开关就放行一切」：只有写下**被明确列入的
    精确路径**的那些 case 才应翻转，其余一律仍拒。下面用两组互补的断言把这条
    钉住 —— 第一组用「任何攻击命令里都不出现的路径」当豁免，证明豁免不泄漏；
    第二组显式枚举**应当**翻转的 case，避免日后被读成回归。
    """

    #: 不出现在任何攻击命令里的豁免条目（测试内自证，防止日后攻击集新增case 时
    #: 这条断言悄悄失效）。
    UNRELATED_ALLOWLIST = ("notes/local.env", "config/app.env", "secrets/app.env")

    @pytest.mark.parametrize(
        "case",
        GUARD_DENY_CASES,
        ids=[c["id"] for c in GUARD_DENY_CASES],
    )
    def test_guard_denies_attack_with_unrelated_allowlist(self, case: dict) -> None:
        guard = CommandGuard(workspace="/tmp/ws", allowed_write_paths=self.UNRELATED_ALLOWLIST)
        assert guard.check(case["command"]) is CommandVerdict.DENY, (
            f"{case['id']} ({case['category']}) not denied with allowlist: {case['command']!r}"
        )

    def test_unrelated_allowlist_entries_really_are_unrelated(self) -> None:
        for entry in self.UNRELATED_ALLOWLIST:
            assert all(entry not in c["command"] for c in ATTACKS["cases"]), entry

    def test_exempt_targets_flip_exactly_the_path_scoped_cases(self) -> None:
        """豁免 `.env` / `.env.local` 后**应当**翻转的 case 是哪些 —— 显式枚举。

        这些 case 全都在「往 `.env` / `.env.local` 写」——它们当初被收进攻击集
        是因为**目标**是凭据位，而不是因为写法（launcher / eval / 重定向）本身。
        用户显式豁免该路径后，同一些写法放行是 U1/U2 的**预期语义**。若日后这个
        集合变了（多了别的路径），说明豁免泄漏到了未列入的路径上 ⇒ 应当报警。
        """
        allow = (".env", ".env.local")
        guard = CommandGuard(workspace="/tmp/ws", allowed_write_paths=allow)
        flipped = {
            c["id"] for c in GUARD_DENY_CASES if guard.check(c["command"]) is not CommandVerdict.DENY
        }
        assert flipped == {
            "env-variant-001",
            "env-variant-006",
            "heredoc-exec-001",
            "launcher-001",
            "launcher-002",
            "launcher-003",
            "launcher-004",
            "launcher-005",
            "opt-target-001",
            "opt-target-002",
            "eval-payload-001",
        }
        # 翻转的每一个都必须真的写到被豁免的路径上
        by_id = {c["id"]: c["command"] for c in ATTACKS["cases"]}
        for case_id in sorted(flipped):
            assert ".env" in by_id[case_id], case_id

    def test_structural_targets_never_flip(self) -> None:
        """结构性 / 系统目标即便被列入也不翻转（U1 + U12）。"""
        guard = CommandGuard(
            workspace="/tmp/ws",
            allowed_write_paths=("/etc/passwd", ".ssh/authorized_keys", "id_rsa", ".git/config"),
        )
        by_id = {c["id"]: c for c in GUARD_DENY_CASES}
        for case_id in ("etc-passwd-001", "priv-esc-001", "sensitive-001"):
            case = by_id.get(case_id)
            if case is not None:
                assert guard.check(case["command"]) is CommandVerdict.DENY, case_id
