"""Three-state verdict + IR-driven rules (design D3/D4/D8, tasks 3.1/4.2-4.5/5.1-5.6).

Covers:
  - `CommandVerdict.ASK` exists and `check` can return it
  - heredoc bound to an interpreter: body judged as code (Q2 = (a))
  - heredoc bound to a non-interpreter: body is data (control group)
  - launcher "limited ask" (Q4 = (c')): unknown prefix + judged command
  - dynamic word in a write-target position (Q1 = (c) layered)
"""
from __future__ import annotations

import pytest

from agent.tools.command_guard import CommandGuard, CommandVerdict

ASK = CommandVerdict.ASK


class TestThreeStateExists:
    def test_ask_is_a_member(self) -> None:
        assert CommandVerdict.ASK.value == "ask"

    def test_plain_commands_still_allow(self) -> None:
        for cmd in ["ls -la", "cat README.md", "git status", "pytest -q"]:
            assert CommandGuard().check(cmd) is CommandVerdict.ALLOW


class TestHeredocBoundToInterpreter:
    """Q2 = (a): the body is CODE when the heredoc feeds an interpreter."""

    @pytest.mark.parametrize(
        "command",
        [
            "bash <<EOF\ncp x .env\nEOF\n",
            "sh <<EOF\ncp x .env\nEOF\n",
            "bash -s <<EOF\ncp x .env\nEOF\n",
            "zsh <<'SH'\ncp x .env\nSH\n",
        ],
    )
    def test_body_is_judged(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            # These targets are dynamic/relative, so they are NOT "sensitive" --
            # they are exactly the cases the narrower rule (b) would have missed.
            "bash <<EOF\nrm -rf $HOME\nEOF\n",
            "bash <<EOF\ndd of=$DEST\nEOF\n",
            "bash <<EOF\ncp -t $TARGET x\nEOF\n",
        ],
    )
    def test_dynamic_bodies_are_not_silently_allowed(self, command: str) -> None:
        verdict = CommandGuard().check(command)
        assert verdict is not CommandVerdict.ALLOW, (
            f"{command!r} was allowed; rule (b) would have missed this"
        )

    @pytest.mark.parametrize(
        "command",
        [
            "bash <<'SCRIPT'\nset -e\ncd /tmp\nrm -rf build\nSCRIPT\n",
            "bash <<EOF\nnpm ci\ngit pull\nEOF\n",
        ],
    )
    def test_benign_bodies_allowed(self, command: str) -> None:
        """Control group: ordinary build-script bodies must keep working."""
        assert CommandGuard().check(command) is CommandVerdict.ALLOW


class TestHeredocBoundToNonInterpreter:
    """The body is stdin DATA when the heredoc does not feed an interpreter."""

    @pytest.mark.parametrize(
        "command",
        [
            "cat <<'EOF'\ncp x .env\nEOF\n",
            "cat <<'EOF'\nUsage: cp .env.example .env\nEOF\n",
            "grep -q x <<'EOF'\ncp x .env\nEOF\n",
        ],
    )
    def test_body_is_data(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW


class TestLauncherLimitedAsk:
    """Q4 = (c'): unknown prefix + a judged command behind it -> ask."""

    @pytest.mark.parametrize(
        "command",
        [
            "mylauncher cp x y",
            "mylauncher --flag cp x y",
            "custom-wrapper cp x y",
        ],
    )
    def test_unknown_prefix_concealing_judged_command_asks(self, command: str) -> None:
        assert CommandGuard().check(command) is ASK

    @pytest.mark.parametrize(
        "command",
        [
            "my-custom-tool --flag",
            "terraform plan",
            "./scripts/run.sh",
            "bun run dev",
            "pytest -q",
            "git status",
        ],
    )
    def test_plain_unknown_programs_still_allowed(self, command: str) -> None:
        """Control group: (c') must not turn every unknown program into an ask."""
        assert CommandGuard().check(command) is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            # A *known* launcher is stripped, so the judged command behind it is
            # evaluated normally -- a benign target stays allowed.
            "nsenter -t 1 cp x y",
            "watch -n 1 cp x y",
            "nice cp x y",
            "doas cp x y",
        ],
    )
    def test_known_launcher_benign_target_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            "nice cp x .env",
            "doas cp x .env",
            "unshare -m cp x .env",
            "nohup setsid cp x .env",
            "env -i nice cp x .env",
        ],
    )
    def test_launcher_concealing_sensitive_target_denies(self, command: str) -> None:
        """A judged command behind a launcher is judged, not merely asked."""
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "doas sh -c 'cp x .env'",
            "nice bash -c 'cp x .env'",
            "nohup setsid sh -c 'cp x .env'",
        ],
    )
    def test_launcher_before_shell_dash_c_denies(self, command: str) -> None:
        """The payload channel must strip launchers too (design D8)."""
        assert CommandGuard().check(command) is CommandVerdict.DENY


class TestDynamicWriteTarget:
    """Q1 = (c): normalise first; sensitive -> deny, otherwise -> ask."""

    @pytest.mark.parametrize(
        "command",
        [
            "cp $SRC build/",
            "cp $SRC $DST",
            "cp -t $D x",
        ],
    )
    def test_dynamic_non_sensitive_target_asks(self, command: str) -> None:
        assert CommandGuard().check(command) is ASK

    @pytest.mark.parametrize(
        "command",
        ["cp $SRC .env", "cp $SRC ~/.ssh/f", "cp x ~/.{ssh}/f"],
    )
    def test_dynamic_sensitive_target_denies(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    def test_non_target_dynamic_word_allowed(self) -> None:
        for cmd in ['echo "$PATH"', "echo $HOME"]:
            assert CommandGuard().check(cmd) is CommandVerdict.ALLOW


class TestOptionCarriedWriteTarget:
    """The write target is not always `argv[-1]` (design D2 `write_targets[]`).

    `cp -t <dir> x` / `mv --target-directory=<dir> x` / `install -t <dir> x`
    carry it on an option, so a target check that reads the last argument sees
    `x` and misses the real destination.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "cp -t .env x",
            "mv --target-directory=.env x",
            "install -t .env x",
            "cp --target-directory .env x",
        ],
    )
    def test_option_carried_sensitive_target_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        ["cp -t build x", "mv --target-directory=dist x", "cp -t .env.example x"],
    )
    def test_option_carried_benign_target_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW


class TestEvalPayload:
    """`eval <string>` runs its argument as a command line (design D8).

    `eval 'cp x .env'` used to pass while `eval cp x .env` was denied -- the
    quotes collapsed the payload into a single token that matched no command.
    """

    @pytest.mark.parametrize(
        "command",
        ["eval 'cp x .env'", "eval cp x .env", 'eval "cp x .env"'],
    )
    def test_eval_payload_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize("command", ["eval 'echo hi'", "eval 'ls -la'"])
    def test_benign_eval_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW
