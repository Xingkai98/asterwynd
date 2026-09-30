"""The "should ask" case set (design D10, Q5).

Attack cases must all be `deny`; the guard's *undecidable* shapes are `ask`.
Those live here rather than in `attacks.json` so the attack set keeps its
strict `is DENY` assertion (a case that merely asks would fail in CI under
`FailClosedApprovalHandler` but could be waved through by a human).
"""
from __future__ import annotations

import pytest

from agent.tools.command_guard import CommandGuard, CommandVerdict

ASK_CASES = [
    # (command, why the guard cannot decide statically)
    ("cp $SRC $DST", "dynamic word in the write-target position"),
    ("cp $SRC build/", "dynamic target, not sensitive"),
    ("cp -t $D x", "option-carried dynamic target"),
    ("mylauncher cp x y", "unknown prefix concealing a judged command"),
    ("custom-runner --flag cp x y", "unknown prefix concealing a judged command"),
    ("echo 'unclosed", "parse error"),
    ("rm -rf !(keep)", "zero-width MISSING node"),
]


@pytest.mark.parametrize(
    "command,reason",
    ASK_CASES,
    ids=[c for c, _ in ASK_CASES],
)
def test_undecidable_shapes_ask(command: str, reason: str) -> None:
    assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.ASK, (
        f"expected ask ({reason}): {command!r}"
    )


def test_ask_cases_are_not_attack_cases() -> None:
    """The two sets are disjoint by construction (design D10 / Q5).

    An attack case that merely asks would weaken the baseline: in CI it fails
    (FailClosed) but interactively a human might approve it.
    """
    import json
    from pathlib import Path

    attacks = json.loads(
        Path(__file__).resolve().parents[2]
        .joinpath("benchmarks/attacks/attacks.json")
        .read_text(encoding="utf-8")
    )["cases"]
    attack_commands = {c["command"] for c in attacks}
    overlap = {c for c, _ in ASK_CASES} & attack_commands
    assert not overlap, f"these appear in both sets: {overlap}"


def test_attack_suite_has_no_ask_verdicts() -> None:
    """Every guard-deny attack case must still be a hard DENY (design D10 / Q5)."""
    import json
    from pathlib import Path

    attacks = json.loads(
        Path(__file__).resolve().parents[2]
        .joinpath("benchmarks/attacks/attacks.json")
        .read_text(encoding="utf-8")
    )["cases"]
    asked = [
        c["id"]
        for c in attacks
        if c["category"] != "sensitive-read"
        and CommandGuard(workspace="/tmp/ws").check(c["command"]) is CommandVerdict.ASK
    ]
    assert not asked, f"attack cases answered with ask (must be deny): {asked}"
