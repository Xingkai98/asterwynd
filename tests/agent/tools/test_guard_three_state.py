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


class TestCommandSubstitutionEvaluatorIndependence:
    """Command substitution must be caught by the EVALUATOR, not just the
    literal channel (design D4/D9, tasks 4.2).

    These assertions run with the literal denylist muted, so a regression that
    only the regex was covering shows up here.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "echo $(rm -rf /tmp/x)",
            "echo `rm -rf /tmp/x`",
            "x=$(cp x .env)",
            "echo $(cp x .env)",
        ],
    )
    def test_denied_without_literal_channel(self, command: str) -> None:
        guard = CommandGuard(workspace="/tmp/ws")
        guard._denylist = ()
        assert guard.check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        ["$(echo rm -rf /)", "echo $(echo hi)"],
    )
    def test_echo_text_is_not_denied_without_literal_channel(self, command: str) -> None:
        """`$(echo rm -rf /)` only *prints* the text; the evaluator may allow or
        ask, but must not be the thing that denies it (the literal channel is).
        """
        guard = CommandGuard(workspace="/tmp/ws")
        guard._denylist = ()
        assert guard.check(command) is not CommandVerdict.DENY


class TestFailurePolicy:
    """Unanalyzable input asks rather than silently allowing (design D4)."""

    @pytest.mark.parametrize(
        "command",
        [
            "echo 'unclosed",
            "rm -rf !(keep)",
            "echo foo |",
            "if true; then",
        ],
    )
    def test_unanalyzable_asks(self, command: str) -> None:
        assert CommandGuard().check(command) is ASK

    def test_clean_input_does_not_ask(self) -> None:
        """Control group: a well-formed command must not become an ask."""
        assert CommandGuard().check("ls -la") is CommandVerdict.ALLOW

    def test_overlong_input_asks(self) -> None:
        assert CommandGuard().check("echo x\n" * 40000) is ASK


class TestLegacyFallbackSwitch:
    """`ASTERWYND_GUARD_LEGACY=1` restores the pre-refactor verdicts (design D10).

    The migration window needs a way back: a rewrite of a security module that
    nine review rounds stabilised must be reversible until the old-vs-new
    verdict comparison is fully green.
    """

    #: The signature difference between the two implementations: a heredoc whose
    #: body merely *mentions* a command. The old tokenizer split `<<` into two
    #: `<` and treated the body as a segment (false positive); the IR knows the
    #: body is stdin data for a non-interpreter.
    DATA_HEREDOC = "cat <<'EOF'\ncp x .env\nEOF\n"

    def test_env_var_restores_legacy_behaviour(self, monkeypatch) -> None:
        monkeypatch.setenv("ASTERWYND_GUARD_LEGACY", "1")
        guard = CommandGuard(workspace="/tmp/ws")
        assert guard.legacy is True
        assert guard.check(self.DATA_HEREDOC) is CommandVerdict.DENY

    def test_default_is_new_behaviour(self, monkeypatch) -> None:
        monkeypatch.delenv("ASTERWYND_GUARD_LEGACY", raising=False)
        guard = CommandGuard(workspace="/tmp/ws")
        assert guard.legacy is False
        assert guard.check(self.DATA_HEREDOC) is CommandVerdict.ALLOW

    def test_legacy_never_weakens_the_attack_set(self, monkeypatch) -> None:
        """Even in legacy mode the attack set must stay denied."""
        import json
        from pathlib import Path

        monkeypatch.setenv("ASTERWYND_GUARD_LEGACY", "1")
        attacks = json.loads(
            Path(__file__).resolve().parents[3]
            .joinpath("benchmarks/attacks/attacks.json")
            .read_text(encoding="utf-8")
        )["cases"]
        missed = [
            c["id"]
            for c in attacks
            if c["category"] != "sensitive-read"
            and CommandGuard(workspace="/tmp/ws").check(c["command"]) is CommandVerdict.ALLOW
        ]
        # Legacy mode predates the new cases, so allow-list the ones this change
        # introduced; everything else must remain denied.
        new_ids = {c["id"] for c in attacks if c["id"].startswith(
            ("env-variant-", "heredoc-exec-", "launcher-", "opt-target-",
             "eval-payload-", "obfuscated-"))}
        unexpected = [i for i in missed if i not in new_ids]
        assert not unexpected, f"legacy mode lost coverage: {unexpected}"


class TestCVEInspiredCases:
    """The four Claude Code 2025 CVEs, each labelled with what this layer claims.

    CVE-2025-54795 (`echo` parsing bypass) is a text-mode-vs-shell-semantics bug,
    which an AST can catch. The other three are explicitly NOT this layer's
    claims (path canonicalisation / allowlist scope / decision ordering), and are
    asserted as such so the capability declaration cannot quietly drift into
    implying otherwise.
    """

    def test_cve_2025_54795_echo_parse_bypass_denied(self) -> None:
        """`echo` + newline + a command: the second line is a real command."""
        assert CommandGuard(workspace="/tmp/ws").check(
            "echo hello\nrm -rf /"
        ) is CommandVerdict.DENY

    def test_path_prefix_collision_is_covered_by_canonicalisation(self) -> None:
        """CVE-2025-54794 class: prefix matching is not containment.

        Not the parser's doing — it is the component-boundary comparison — but
        the guard must still get it right.
        """
        guard = CommandGuard(workspace="/tmp/ws")
        assert guard.check("rm -rf /tmp/ws-evil") is CommandVerdict.DENY

    def test_traversal_is_normalised(self) -> None:
        guard = CommandGuard(workspace="/tmp/ws")
        assert guard.check("rm -rf /tmp/ws/../etc") is CommandVerdict.DENY


class TestLauncherNoFailOpen:
    """Regression: gaps found in review round 1 (fail-open paths).

    1. `script -c '<cmd>'` — like `env -S`, the `-c` VALUE is the command, so
       stripping it as an option value swallowed the command entirely.
    2. The "conceals a judged command" window was `rest[1:5]`, so four filler
       tokens pushed the real command out of view.
    """

    @pytest.mark.parametrize(
        "command",
        [
            'script -c "cp x .env"',
            "script -c 'cp x .env'",
            "script -q -c 'cp x .env' /dev/null",
        ],
    )
    def test_script_dash_c_payload_is_judged(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "weird a b c d cp x .env",
            "weird a b c d e f g mv x .env",
        ],
    )
    def test_filler_tokens_do_not_hide_the_command(self, command: str) -> None:
        """Any number of unknown tokens must not push the real command out of view."""
        verdict = CommandGuard(workspace="/tmp/ws").check(command)
        assert verdict is not CommandVerdict.ALLOW

    def test_benign_script_dash_c_allowed(self) -> None:
        """Control group: a benign script payload stays allowed."""
        assert CommandGuard().check("script -c 'echo hi' /dev/null") is CommandVerdict.ALLOW


class TestSourcePositionTemplate:
    """`cp .env.example <dest>` must be allowed (spec: template source, task 2.7).

    The two source-position denylist regexes matched `cp <src>` for any `.env*`
    source, so copying a committed template denied. They are now covered by the
    IR evaluator, which is template-aware.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "cp .env.example /tmp/backup.txt",
            "cp .env.sample docs/",
            "mv .env.template /tmp/x",
        ],
    )
    def test_template_source_allowed(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        ["cp .env /tmp/x", "mv .env.local /tmp/x", "cp ~/.ssh/id_rsa /tmp/x"],
    )
    def test_credential_source_still_denied(self, command: str) -> None:
        """Control group: a real credential as the source must stay denied."""
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY


class TestLauncherRound2:
    """Review round 2: the round-1 `-c` fix was over-broad and under-complete."""

    @pytest.mark.parametrize(
        "command",
        [
            # repeated `-c`: the LAST one is what runs
            "script -c 'ls' -c 'cp x .env'",
            "script -c 'echo ok' -c 'cp x .env'",
        ],
    )
    def test_repeated_command_option_judged(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "grep -c 'cp x .env' f",
            "cut -c1 f",
            "head -c 10 f",
            "ls -c",
            "sort -c f",
            "ionice -c 2 cp x y",
        ],
    )
    def test_other_launchers_dash_c_is_not_a_command(self, command: str) -> None:
        """`-c` means a command only for launchers where it does (design: scoped).

        `grep -c` counts, `cut -c` selects columns, `ionice -c 2` is a class —
        treating those as "value is a command" both denies ordinary searches
        and swallows the real command.
        """
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.ALLOW

    def test_ionice_dash_c_class_then_sensitive_target_denies(self) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(
            "ionice -c 2 cp x .env"
        ) is CommandVerdict.DENY


class TestSourceBehindFlags:
    """A sensitive SOURCE hidden behind option flags must still be judged."""

    @pytest.mark.parametrize(
        "command",
        [
            "cp -r .env /tmp/x",
            "cp -a .env /tmp/x",
            "cp -p .env /tmp/x",
            "cp -rf .env /tmp/x",
            "mv -f .env /tmp/x",
            "mv -f .env.local /tmp/x",
            "install -m 600 .env /tmp/x",
            "cp -r .git/config /tmp/x",
        ],
    )
    def test_flagged_sensitive_source_denied(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        ["cp -r src/ /tmp/x", "mv -f old.txt new.txt", "install -m 600 app.py /tmp/x"],
    )
    def test_flagged_benign_source_allowed(self, command: str) -> None:
        """Control group: flags must not turn every copy into a denial."""
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.ALLOW


class TestInterpreterArgsAreNotConcealedCommands:
    """An interpreter argument is not a concealed command unless it takes one.

    `uv run python -m pytest tests/` is an ordinary way to run the test suite;
    treating the bare `python` as "a command is hidden behind this prefix" turned
    it into an ask. Only `sh -c '<cmd>'` actually conceals one.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "uv run python -m pytest tests/ -q",
            "uv run python -m pytest tests/agent -q",
            "python3 -m pytest tests/",
            "uv run python scripts/check_openspec_artifacts.py",
        ],
    )
    def test_python_dash_m_is_not_concealment(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.ALLOW

    def test_shell_dash_c_behind_unknown_prefix_still_asks(self) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(
            "weird sh -c 'cp x .env'"
        ) is ASK


class TestLauncherRound3:
    """Review round 3: two fail-open regressions introduced by the round-2 fix."""

    @pytest.mark.parametrize(
        "command",
        [
            "nice script -c 'cp .env /tmp/leak'",
            "env -i script -c 'cp .env /tmp/leak'",
            "timeout 5 script -c 'cp .env /tmp/leak'",
            "nohup script -c 'cp .env /tmp/leak'",
            "nice script -c 'cp x .env'",
        ],
    )
    def test_script_dash_c_behind_a_launcher_is_judged(self, command: str) -> None:
        """`script -c '<cmd>'` must be judged even when another launcher leads.

        Round 2 deleted the post-strip payload path, so only `argv[0]` was
        inspected -- `nice script -c '…'` fell through and the payload ran.
        """
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "watch -d cp .env /tmp/leak",
            "watch -d -n 1 cp .env /tmp/leak",
        ],
    )
    def test_watch_dash_d_is_a_boolean_flag(self, command: str) -> None:
        """`watch -d` highlights differences; it takes no value.

        Treating `-d` as value-taking swallowed the real command.
        """
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        ["script -c 'echo hi' /dev/null", "watch -d ls", "watch -n 1 ls"],
    )
    def test_benign_still_allowed(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.ALLOW


class TestLegacySourceCoverage:
    """The rollback path must keep the source-position denials (review R4).

    The old `DEFAULT_DENYLIST` carried two `(mv|cp)\\s+<source>` regexes. They
    moved to per-argument judgement, which the legacy channel must also run --
    otherwise rolling back silently drops `cp .env backup.env`.
    """

    @pytest.mark.parametrize(
        "command",
        ["cp .env backup.env", "mv .env backup.env", "mv .git/config config.backup"],
    )
    def test_legacy_mode_still_denies_sensitive_source(
        self, command: str, monkeypatch
    ) -> None:
        monkeypatch.setenv("ASTERWYND_GUARD_LEGACY", "1")
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY

    def test_legacy_mode_still_allows_benign_source(self, monkeypatch) -> None:
        monkeypatch.setenv("ASTERWYND_GUARD_LEGACY", "1")
        assert CommandGuard(workspace="/tmp/ws").check(
            "cp src/a.txt dst/b.txt"
        ) is CommandVerdict.ALLOW


class TestAttachedOptionValues:
    """`-c'<cmd>'` (no space) is the same option as `-c '<cmd>'` (review R5-1).

    tree-sitter keeps the attached form as one token (`"-c'cp .env /tmp/x'"`),
    so an exact token comparison misses it entirely and the payload ran.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "script -c'cp -r .env /tmp/leak'",
            "script -c'cp .env /tmp/x'",
            'script -c"cp .env /tmp/x"',
            "script --command='cp .env /tmp/x'",
            "script --command='mv .git/config /tmp/x'",
            # sensitive command not first, so the source-position channel misses it
            "script -c'cp a b; cp .env /tmp/x'",
        ],
    )
    def test_attached_script_command_option_denied(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        ["env -S'cp x .env'", "env -S'cp -r .env /tmp/x'"],
    )
    def test_attached_env_split_string_denied(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        ["script -c'echo hi' /dev/null", "env -S'echo hi'"],
    )
    def test_attached_benign_allowed(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.ALLOW


class TestAttachedShellDashC:
    """`bash -c'<cmd>'` (attached) is the same as `bash -c '<cmd>'`.

    The tokenizer drops the quotes, so the token arrives as `-ccp x .env`; both
    the exact-token check and the `len < 3` bound missed it.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "bash -c'cp x .env'",
            'bash -lc"cp x .env"',
            "sh -c'cp -r .env /tmp/x'",
            "bash -c'rm -rf /'",
        ],
    )
    def test_attached_shell_dash_c_denied(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize("command", ["bash -c'echo hi'", 'bash -lc"ls"'])
    def test_attached_benign_allowed(self, command: str) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(command) is CommandVerdict.ALLOW

    def test_separated_form_still_denied(self) -> None:
        assert CommandGuard(workspace="/tmp/ws").check(
            'bash -c "cp x .env"'
        ) is CommandVerdict.DENY
