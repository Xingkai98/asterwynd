"""Command guard — lightweight command tokenizer + argv semantic validation.

This is a *guardrail, not a boundary* (per industry consensus: Claude Code's
2025 CVEs demonstrated that regex command validation is fundamentally
bypassable). The real boundary is the execution backend (ProcessBackend /
DockerBackend). The guard catches conventional bypasses: flag reordering
(``rm -fr`` vs ``rm -rf``), sensitive-path targets (``mv x /etc/passwd``),
redirects to protected paths (``> /etc/``), pipes to a shell, and arbitrary
code execution (``node -e``, ``base64 | bash``).

Design: default-allow (unknown commands pass, preserving existing workflows);
denylist patterns are kept and extended; argv semantic checks apply to
dangerous commands; high-risk sentence patterns (pipe-to-shell, redirect to
protected paths) are denied outright.

Path containment (``path`` inside a protected prefix / the workspace) is judged
by **path segment** after normalization, never by bare string prefix
(fix-issue-247): ``/various.txt`` is not under ``/var``, ``/tmp/ws-evil`` is not
inside workspace ``/tmp/ws``, and ``/tmp/ws/../etc`` normalizes out of the
workspace. Redirection / mv-cp targets that are the ``/dev/null`` family are
exempt (they are black-hole / std-stream aliases, not protected assets); the
exemption deliberately does NOT extend to rm/chmod/curl targets.
"""
from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path

from agent.tools.bash_ir import (
    INTERPRETERS,
    BashAnalysis,
    Segment,
    analyze,
    is_interpreter,
)
from agent.workspace_policy import (
    DEFAULT_DENYLIST,
    is_sensitive_dot_name,
)

#: Commands whose target an evaluator judges. A launcher "conceals" a real
#: command when one of these follows the unknown prefix (Q4 = (c')).
_WRITE_COMMANDS = frozenset({"rm", "mv", "cp", "install", "chmod", "curl", "wget", "dd", "tee"})
#: The subset that actually writes to a target position.
_TARGET_COMMANDS = frozenset({"rm", "mv", "cp", "install", "chmod", "dd", "tee"})
#: Commands whose argument is a command line to be evaluated (`eval '…'`).
_PAYLOAD_COMMANDS = frozenset({"eval"})
#: Launchers: they run their remaining argv, so they are stripped before judging.
_LAUNCHERS = frozenset(
    {
        "sudo", "doas", "nice", "flock", "chroot", "setsid", "timeout", "stdbuf",
        "taskset", "xargs", "busybox", "watch", "strace", "ltrace", "ionice",
        "chrt", "systemd-run", "runuser", "setarch", "setpriv", "nsenter",
        "unshare", "script", "perf", "env", "command", "nohup",
    }
)
#: Launcher options that consume the following token as their value. Kept small
#: and explicit: under-stripping leaves a token that reaches the strategy layer
#: (safe -> ask), while over-stripping can swallow the real command (unsafe).
_LAUNCHER_OPTS_WITH_VALUE = {
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "-n", "-p"},
    "chrt": {"-p"},
    "flock": {"-w", "-E"},
    "timeout": {"-k", "-s", "--signal", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e"},
    "watch": {"-n", "-d"},
    "strace": {"-o", "-e", "-p", "-s"},
    "ltrace": {"-o", "-e", "-p", "-s"},
    "script": {"-c", "-t"},
    "runuser": {"-u", "-g", "-s"},
    "setpriv": {"--reuid", "--regid", "--ruid", "--rgid", "--groups"},
    "systemd-run": {"-u", "--unit", "-p", "--property", "--slice"},
    "perf": {"-e", "-o"},
    "nsenter": {"-t", "--target", "-S", "-G", "--wd"},
    "unshare": {"--propagation", "--setgroups"},
    "xargs": {"-n", "-I", "-P", "-s", "-d", "-E", "-a"},
}
#: Launchers whose `-c` / `--command` option takes the command to run as its
#: value (`script -c '<cmd>'`). Scoped **per launcher**: the same flag means
#: something else elsewhere (`ionice -c 2` is a scheduling class, `grep -c` a
#: count, `cut -c` a column list), so a global `-c` rule would both swallow
#: real commands and deny ordinary searches.
_LAUNCHER_COMMAND_OPTION = {
    "script": frozenset({"-c", "--command"}),
}

# Protected paths: writing to these is always denied.
_DENY_PATHS = ("/etc", "/proc", "/sys", "/dev", "/root", "/boot", "/var")
# Device files that are black-hole / std-stream aliases rather than protected
# assets. Only exempt for redirection and mv/cp targets (fix-issue-247 Q2/Q3).
_DEVICE_EXEMPT = ("/dev/null", "/dev/stdout", "/dev/stderr")


def _normalize_path(path: str) -> str:
    """Normalize a raw command token for containment checks (issue #247).

    Resolves ``.``/``..`` segments so ``/tmp/ws/../etc`` cannot masquerade as
    a path inside ``/tmp/ws``. Relative overflows (``a/../../etc``) stay
    relative and therefore compare as "not contained" — the safe direction for
    the workspace check.
    """
    return os.path.normpath(path)


def _within(path: str, prefix: str) -> bool:
    """True when ``path`` equals ``prefix`` or sits **under** it (segment-wise).

    Bare ``startswith`` treats ``/various.txt`` as being under ``/var``; a
    segment boundary requires either exact equality or ``prefix + "/"``.
    """
    if not path or not prefix:
        return False
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def _is_device_exempt(target: str) -> bool:
    return target in _DEVICE_EXEMPT


#: Wrapper commands that run their remaining argv as-is. Their own options and
#: `VAR=value` assignments are skipped before looking for the real command.
_SHELL_WRAPPERS = frozenset({"env", "command", "nohup"})
#: Wrapper options that consume the following token as their value
#: (`env -u FOO …`, `env -C dir …`).
_WRAPPER_OPTS_WITH_VALUE = frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"})
#: Of those, the ones whose value *is* the command to run (`env -S '<cmd>'`),
#: so the value must stay in the token stream rather than be skipped.
_SPLIT_STRING_OPTS = frozenset({"-S", "--split-string"})
#: A short-option cluster that carries the shell's command string: `-c`, `-lc`.
#: Deliberately excludes long options (`--norc`) and `--` prefixes.
_DASH_C_FLAG = re.compile(r"-[A-Za-z]*c[A-Za-z]*\Z")
#: Shell keywords that can lead a command segment. `if true; then cp x .env; fi`
#: splits on `;`, leaving `then` in front of the command (review Round 2).
_SHELL_KEYWORDS = frozenset(
    {"then", "do", "else", "elif", "fi", "done", "esac", "in", "!", "time", "exec", "eval"}
)
#: How many nested ``<shell> -c "…"`` payloads are re-checked. Beyond this the
#: payload is skipped: nesting is unbounded in shell, and re-checking without a
#: cap recurses until the interpreter dies (review Round 2).
_MAX_NESTED_COMMAND_DEPTH = 4
#: Tokenizer output tokens that separate one command from the next. Grouping
#: punctuation is a boundary too: `(cp x .env)` and `{ cp x .env; }` run `cp`
#: as their own command (review Round 2).
_SEGMENT_SEPARATORS = frozenset(
    {"&&", "||", ";", "|", "&", "(", ")", "{", "}"}
)


def _split_command_segments(tokens: list[str]) -> list[list[str]]:
    """Split a token stream into per-command segments (fix-issue-247 I1).

    ``tokenize_command`` emits ``|``/``;``/``&``/``<``/``>`` as their own
    tokens, so ``['cd','/tmp','&','&','cp','x','y']`` becomes two segments.
    A newline is a command separator in shell but the tokenizer folds it into
    whitespace, so ``\\n`` is **pre-split on the raw command text** before
    tokenizing (review Round 2: ``cd /tmp\\ncp evil a/.env`` was a single
    segment and the ``cp`` went unchecked).

    Subshell / brace grouping is deliberately *not* modelled: this guard is a
    guardrail, not a bash parser, and the real boundary is the sandbox backend.
    """
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _SEGMENT_SEPARATORS:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


#: Raw-text command separators the tokenizer would otherwise fold away.
#: ``\r`` is included so a CRLF line ending does not leave ``\r`` glued to the
#: previous segment's last token (review Round 5: `cp evil a/.env\r\nls` kept
#: the destination as `a/.env\r`, which matched no sensitive name).
_RAW_SEPARATORS = re.compile(r"[\r\n]")


def _check_command_text(command: str) -> list[list[str]]:
    """Tokenize every newline-separated command line of ``command``."""
    segments: list[list[str]] = []
    for line in _RAW_SEPARATORS.split(command):
        segments.extend(_split_command_segments(tokenize_command(line)))
    return segments


def _shell_dash_c_payloads(tokens: list[str]) -> list[str]:
    """Every command string a ``<shell> -c <string>`` segment runs.

    A segment may carry more than one ``-c`` (``bash -c a -c b`` runs both),
    so all payloads are returned and the caller checks each. For each ``-c``
    two candidates are produced: the **first** argument on its own (a shell
    takes it as the script and the rest as ``$0``/``$1``) and the **joined**
    remainder (an unquoted `bash -c cp a b` reaches the destination only when
    joined). Both are checked — either being denied fails the segment (review
    Round 4 I-2).
    """
    payloads: list[str] = []
    # `env -S '<cmd>'` runs `<cmd>` (split on spaces) with no shell involved,
    # so its value is itself a command line. `_strip_wrappers` deliberately
    # leaves the option in the stream for this case (review Round 4 I-3).
    for i, token in enumerate(tokens):
        if token in _SPLIT_STRING_OPTS and i + 1 < len(tokens):
            payloads.append(tokens[i + 1])
    stripped = _strip_wrappers(tokens)
    if len(stripped) < 3 or stripped[0].rsplit("/", 1)[-1] not in _SHELL_INTERPRETERS:
        return payloads
    index = 1
    while index < len(stripped):
        if _DASH_C_FLAG.fullmatch(stripped[index]):
            end = next(
                (
                    i
                    for i in range(index + 1, len(stripped))
                    if _DASH_C_FLAG.fullmatch(stripped[i])
                ),
                len(stripped),
            )
            args = stripped[index + 1 : end]
            if args:
                payloads.append(args[0])
                joined = " ".join(args)
                if joined != args[0]:
                    payloads.append(joined)
            index = end
            continue
        index += 1
    return payloads


def _strip_wrappers(tokens: list[str]) -> list[str]:
    """Drop leading shell keywords and ``env``/``command``/``nohup`` wrappers.

    Both are skipped **here**, at the single entry point shared by the argv
    and payload channels: `if true; then bash -c …; fi` splits on `;` into a
    segment led by `then`, and fixing only the argv channel left the payload
    channel blind (review Round 4 I-1).
    """
    index = 0
    while index < len(tokens):
        name = tokens[index].rsplit("/", 1)[-1]
        if name not in _SHELL_KEYWORDS and name not in _SHELL_WRAPPERS:
            break
        index += 1
        # Consume this wrapper's own options / assignments. `env -S '<cmd>'`
        # is special: its value *is* the command, so that option is left in
        # the stream for the caller (review Round 4 I-3).
        while index < len(tokens) and tokens[index].startswith("-"):
            if tokens[index] in _WRAPPER_OPTS_WITH_VALUE and tokens[index] not in _SPLIT_STRING_OPTS:
                index += 1
            index += 1
        while index < len(tokens) and not tokens[index].startswith("-") and (
            "=" in tokens[index] or tokens[index] == "--"
        ):
            index += 1
    return tokens[index:]


def _strip_to_fixpoint(argv: list[str]) -> tuple[list[str], str | None]:
    """Strip wrappers and launchers **alternating to a fixpoint** (design D8).

    Returns ``(rest, unknown)``. ``unknown`` is the leading token when it is not
    a wrapper, a launcher, or a judged command -- i.e. a token that *might* be a
    launcher concealing a real command further along.
    """
    rest = list(argv)
    changed = True
    while changed and rest:
        changed = False
        name = rest[0].rsplit("/", 1)[-1]
        if name in ("env", "command", "nohup"):
            index = 1
            while index < len(rest) and rest[index].startswith("-"):
                if rest[index] in ("-u", "--unset", "-C", "--chdir", "-S", "--split-string"):
                    index += 1
                index += 1
            while index < len(rest) and (
                (("=" in rest[index]) and not rest[index].startswith("-")) or rest[index] == "--"
            ):
                index += 1
            rest = rest[index:]
            changed = True
            continue
        if name in _LAUNCHERS and name not in _WRITE_COMMANDS:
            command_options = _LAUNCHER_COMMAND_OPTION.get(name, frozenset())
            takes_value = _LAUNCHER_OPTS_WITH_VALUE.get(name, set())
            index = 1
            command_payloads: list[str] = []
            while index < len(rest) and rest[index].startswith("-"):
                if rest[index] in command_options:
                    # The value IS the command to run: it becomes the new head
                    # so the ordinary argument walks judge it, and whatever
                    # follows is treated as its arguments.
                    rest = rest[index + 1:]
                    changed = True
                    break
                if rest[index] in takes_value:
                    index += 1
                index += 1
            else:
                rest = rest[index:]
                changed = True
                continue
            continue

    if not rest:
        return rest, None
    head = rest[0].rsplit("/", 1)[-1]
    if head in _WRITE_COMMANDS or head in _LAUNCHERS or head in INTERPRETERS or head in _PAYLOAD_COMMANDS:
        return rest, None
    return rest, head


def _concealed_command_texts(argv: list[str]) -> list[str]:
    """Every command a launcher passes via a command-taking option.

    `script -c '<cmd>'` runs its `-c` value, and repeated `-c` means the *last*
    one wins -- so `script -c 'ls' -c 'cp x .env'` must be judged on `'cp x .env'`
    (all occurrences are returned; judging only the first would fail open).

    Scoped per launcher: `-c` is a command only for `script`, not for `grep`
    (count), `cut` (columns) or `ionice` (class).
    """
    if not argv:
        return []
    name = argv[0].rsplit("/", 1)[-1]
    command_options = _LAUNCHER_COMMAND_OPTION.get(name, frozenset())
    if not command_options:
        return []
    payloads: list[str] = []
    for index, token in enumerate(argv):
        if token in command_options and index + 1 < len(argv):
            payloads.append(_dequote(argv[index + 1]))
    return payloads


def _conceals_judged_command(rest: list[str]) -> bool:
    """True when a judged command sits behind the (unknown) leading token.

    Q4 = (c'): `nsenter -t 1 cp x y` asks because `cp` follows the unknown
    prefix; `terraform plan` does not, because nothing the guard judges follows.

    The scan covers the **whole** remainder, not a fixed-size window: a padding
    of filler tokens (`weird a b c d cp x .env`) must not push the real command
    out of view. Only *unquoted* tokens count -- a quoted token is data unless
    an option explicitly says its value is a command (`_concealed_command_text`).
    """
    for index, token in enumerate(rest):
        if token and token[0] in ("'", '"'):
            continue
        name = token.rsplit("/", 1)[-1]
        if name in _WRITE_COMMANDS or name in _PAYLOAD_COMMANDS:
            return True
        # An interpreter only runs a command here when given one as a string
        # (`sh -c '<cmd>'`). A bare `python` argument does not: `uv run python
        # -m pytest` is an ordinary command, not a concealed one.
        if name in INTERPRETERS and any(
            _DASH_C_FLAG.fullmatch(rest[i]) for i in range(index + 1, min(index + 3, len(rest)))
        ):
            return True
    return False


def _mask_data_heredocs(command: str, analysis: BashAnalysis) -> str:
    """Blank the bodies of heredocs that are stdin DATA, for the literal scan.

    A body bound to a non-interpreter (`cat <<EOF … EOF`) is a document; text
    inside it that happens to look like a denylisted command must not be read
    as one. Interpreter-bound bodies are left untouched -- they are code, and
    are judged by the evaluator channel anyway.
    """
    masked = command
    for heredoc in analysis.heredocs:
        if heredoc.bound_to_interpreter or not heredoc.body:
            continue
        masked = masked.replace(heredoc.body, "\n" * heredoc.body.count("\n"))
    return masked


def _dequote(token: str) -> str:
    """Drop one layer of surrounding single/double quotes from an IR token.

    The IR keeps the source spelling, so a `-c 'cp x .env'` payload arrives
    including its quotes; parsing it as a command line then sees a single
    quoted word instead of the command inside.
    """
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _source_of(args: list[str]) -> str | None:
    """The SOURCE argument of `mv`/`cp`/`install` (design D2's read side).

    Option flags are skipped, and options that consume a value (`-t <dir>`,
    `-m <mode>`, `--target-directory=<dir>`) do not leak their value as the
    source. Returns the first real positional argument.
    """
    value_options = {
        "-t", "--target-directory", "-m", "--mode", "-S", "--suffix",
        "-o", "--owner", "-g", "--group",
    }
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            index += 1
            break
        if token.startswith("-"):
            if token in value_options:
                index += 2
                continue
            index += 1
            continue
        return token
    return args[index] if index < len(args) else None


def _write_target_of(name: str, args: list[str]) -> str | None:
    """The write target of a judged command, honouring option-carried targets."""
    if name in ("mv", "cp", "install"):
        for index, token in enumerate(args):
            if token in ("-t", "--target-directory") and index + 1 < len(args):
                return args[index + 1]
            if token.startswith("--target-directory="):
                return token.split("=", 1)[1]
    if name == "dd":
        for token in args:
            if token.startswith("of="):
                return token[3:]
        return None
    positional = [token for token in args if not token.startswith("-")]
    return positional[-1] if positional else None


def _expand_obfuscation(token: str) -> str:
    """Best-effort de-obfuscation of a target token (design D8, 乙类).

    Removes backslash escapes and brace/character-class syntax so that
    ``~/.{ssh}/f`` and ``~/.ss\\h/id_rsa`` normalize to a sensitive name. This is
    deliberately *widening* towards detection: an unexpanded token would slip
    past the sensitive-name check entirely.
    """
    out = token.replace("\\", "")
    # ``~/.{ssh}/f`` -> ``~/.ssh/f`` (brace alternation of a single word)
    out = re.sub(r"\{([^{}]*)\}", lambda m: m.group(1).split(",")[0], out)
    # ``~/.s[h]h/f`` -> ``~/.shh/f`` (character class -> first member)
    out = re.sub(r"\[([^\[\]]*)\]", lambda m: (m.group(1) or "")[:1], out)
    return out


def _dest_is_sensitive(dest: str) -> bool:
    """True when ``dest`` carries credentials / repo metadata (fix-issue-247 R1).

    Segment-wise: any path segment that the shared sensitive-dot-name predicate
    flags. That predicate is defined once in ``workspace_policy`` (design D12)
    so this guard and the read/write tools cannot drift: ``.env.local`` is
    sensitive (a credential variant), ``.env.example`` is not (a template).
    """
    parts = [part for part in dest.split("/") if part not in ("", ".")]
    return any(is_sensitive_dot_name(part) for part in parts)
# Shell interpreters that, when piped to, imply arbitrary code execution.
# (`bash_ir.INTERPRETERS` is the wider set used for heredoc binding.)
_SHELL_INTERPRETERS = {"sh", "bash", "zsh", "ksh", "dash", "fish"}

# Extended denylist covering known bypass variants the original regex missed.
_EXTRA_DENYLIST = (
    # rm flag reordering / split flags / -- separator
    r"\brm\s+(-[a-z]*f[a-z]*r[a-z]*|-[a-z]*r[a-z]*f[a-z]*|-[a-z]+\s+-[a-z]+)\s+--?\s*/",
    r"\brm\s+-[a-z]*[fr][a-z]*\s+--\s+/",
    # chmod octal / symbolic variants on root
    r"\bchmod\s+(0?[0-7]{3,4}|[a-z+=-]+)\s+/",
    r"\bchmod\s+-R\s+[0-7]{3,4}\s+/tmp",
    # kill signal-name variants
    r"\bkill\s+-(SIGKILL|KILL|9)\s+\d+",
    # arbitrary code execution
    r"\bnode\s+-e\b",
    r"\bdeno\s+eval\b",
    r"\bawk\s+.*system\s*\(",
    # base64 decode then execute
    r"base64\s+-d\s*\|\s*(ba)?sh",
    # mv/cp into the literal protected roots. ``/dev/`` is deliberately NOT
    # here: its device-file exemption is exact-match logic that a regex cannot
    # express without a fragile lookahead (review I2 — `\b` is not `/`-aware,
    # so `/dev/null/sda` slipped through). ``_check_mv_cp`` owns that judgment
    # segment-wise, and every command segment now reaches it (review I1).
    r"\b(mv|cp)\s+[^\s]+\s+(/etc/|/proc/|/sys/|/var/)",
    # mv/cp into a credential/repo dot-directory, matched over the **whole
    # command text** so a launcher (`nice bash -c '…'`), a herestring
    # (`bash <<< '…'`) or a pipe (`echo '…' | env -i bash`) does not hide it.
    # The dot name must be preceded by a slash: a bare `.env` is left to the
    # segment-wise `_dest_is_sensitive` (which sees `cp x .env` as a command),
    # while quoting it as data (`grep "cp x .env"`) is not a write and must not
    # match (fix-issue-247 review R7-2). The negative lookahead rejects names
    # continued by `-`/`.`/word (`.env.example`, `.gitignore`).
    r"\b(mv|cp)\s+\S+\s+\S*/\.(?:git|ssh|env|aws|gnupg|kube|docker|netrc|npmrc|pypirc)(?![\w.-])",
    # mv/cp into `/dev/…`, same whole-text reason as above. `_check_mv_cp`
    # owns the exact device exemption, but it only runs when `mv`/`cp` leads a
    # segment — an unstripped launcher never reaches it (review R7-1). The
    # lookahead must test the **delimiter that follows**, not `\b`: `\b` is not
    # `/`-aware and let `/dev/null/sda` through (review I2).
    r"\b(mv|cp)\s+\S+\s+(?:\S*/)?/dev/(?!null(?:[\s;\"'|]|$)|stdout(?:[\s;\"'|]|$)|stderr(?:[\s;\"'|]|$))",
    # exfiltration via netcat / /dev/tcp
    r"\bnc\s+\S+\s+\d+",
    r"/dev/tcp/",
    # fork bomb
    r":\(\)\s*\{",
    # IFS variable bypass
    r"\$IFS",
    # backslash escape in command name (e.g. r\m)
    r"\\[a-z]\s",
    # resource exhaustion
    r"\byes\s+>\s*/dev/null",
)


class CommandVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    #: The guard cannot decide statically. Routed to the approval layer (design
    #: D3); in a runtime without a UI handler (`FailClosedApprovalHandler`,
    #: non-TTY CLI) the approval layer refuses, so `ASK` behaves as deny there.
    ASK = "ask"


#: Severity order used when several rules fire: deny beats ask beats allow.
_SEVERITY = {CommandVerdict.ALLOW: 0, CommandVerdict.ASK: 1, CommandVerdict.DENY: 2}


def _worse(a: CommandVerdict, b: CommandVerdict) -> CommandVerdict:
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def tokenize_command(command: str) -> list[str]:
    """Lightweight shell tokenizer.

    Splits a command into argv-like tokens, handling quotes, redirects, pipes,
    and shell metacharacters. Not a full bash parser — sufficient for the
    semantic checks the guard performs.
    """
    tokens: list[str] = []
    current = ""
    in_single = False
    in_double = False
    i = 0
    while i < len(command):
        ch = command[i]
        if in_single:
            if ch == "'":
                in_single = False
            else:
                current += ch
        elif in_double:
            if ch == '"':
                in_double = False
            elif ch == "\\" and i + 1 < len(command):
                current += command[i + 1]
                i += 1
            else:
                current += ch
        elif ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch in " \t\n":
            if current:
                tokens.append(current)
                current = ""
        elif ch in "|>&;<(){}":
            if current:
                tokens.append(current)
                current = ""
            tokens.append(ch)
        else:
            current += ch
        i += 1
    if current:
        tokens.append(current)
    return tokens


class CommandGuard:
    """Semantic command validator: denylist + argv checks, default-allow."""

    def __init__(self, workspace: str | Path | None = None) -> None:
        self._workspace = str(Path(workspace).resolve()) if workspace else None
        # Combine the project's base denylist (dd/mkfs/sudo/shutdown/python -c/
        # curl|sh/$( )/git reset 等) with the extra bypass-variant patterns.
        self._denylist = (*DEFAULT_DENYLIST, *_EXTRA_DENYLIST)
        # Granular rejection category from the most recent check() (None when
        # allowed). Lets sandbox trace events carry a meaningful reason.
        self.last_reason: str | None = None
        # Current nesting depth of `<shell> -c "…"` re-checks (review Round 2).
        self._nested_depth = 0
        # Migration fallback (design D10): set ASTERWYND_GUARD_LEGACY=1 to drop
        # the IR-driven rules and fall back to the pre-refactor channels. Kept
        # until the old-vs-new verdict comparison is fully green; it never
        # weakens the attack set (see the guard tests).
        self.legacy = os.environ.get("ASTERWYND_GUARD_LEGACY", "").strip() not in ("", "0", "false")

    def check(self, command: str) -> CommandVerdict:
        self.last_reason = None
        cmd = command.strip()
        if not cmd:
            return CommandVerdict.ALLOW

        # Parse once; every IR-driven rule below reads this analysis.
        analysis = analyze(cmd)

        # 1. Extended denylist (conventional bypass variants).
        # ``rm`` is excluded: the base denylist's ``rm -rf /`` pattern matches
        # any path starting with ``/`` (false positive on workspace-internal
        # paths). argv semantics (step 4) judge rm precisely.
        #
        # The scan runs over the source with non-interpreter heredoc bodies
        # masked out: `cat <<'EOF' … cp x .env … EOF` is a document that
        # *mentions* a command, so its body must not be read as literal command
        # text (design D4). Interpreter-bound bodies stay, since they ARE code.
        cmd_name = cmd.split()[0] if cmd.split() else ""
        if cmd_name != "rm":
            # In legacy mode the source is scanned verbatim, exactly as before
            # the refactor -- the switch is meant to restore the old verdicts
            # (false positives included) so they can be compared.
            scanned = cmd if self.legacy else _mask_data_heredocs(cmd, analysis)
            for pattern in self._denylist:
                if re.search(pattern, scanned):
                    self.last_reason = "denylist"
                    return CommandVerdict.DENY

        # 2. High-risk sentence patterns (pipe to shell, redirect to protected).
        if self._has_pipe_to_shell(cmd):
            self.last_reason = "pipe_to_shell"
            return CommandVerdict.DENY
        if self._has_protected_redirect(analysis):
            self.last_reason = "protected_redirect"
            return CommandVerdict.DENY

        # 3. IR-driven rules (single parse pipeline, design D1/D2/D4/D8).
        ir_verdict = (
            CommandVerdict.ALLOW
            if self.legacy
            else self._check_analysis(cmd, analysis=analysis)
        )

        # 4. argv semantic checks for dangerous commands (legacy channel).
        #    Kept alongside the IR channel while the migration is in progress:
        #    `旧 DENY ⊆ 新 DENY ∪ 新 ASK` (design D10). The same data-heredoc
        #    masking applies, otherwise the old tokenizer mines the body for
        #    phantom commands (`<<` splits into two `<`, making the body a
        #    "segment").
        legacy_source = cmd if self.legacy else _mask_data_heredocs(cmd, analysis)
        tokens = tokenize_command(legacy_source)
        argv_verdict = CommandVerdict.ALLOW
        if tokens:
            argv_verdict = self._check_argv(tokens, raw=legacy_source)

        verdict = _worse(ir_verdict, argv_verdict)
        if verdict is not CommandVerdict.ALLOW and self.last_reason is None:
            self.last_reason = "ir_rule"
        return verdict

    # --- IR-driven rules (design D1/D2/D4/D8) ------------------------------

    def _check_analysis(
        self, command: str, *, analysis: BashAnalysis | None = None
    ) -> CommandVerdict:
        """Judge the parsed analysis. Fail-closed on unanalyzable input.

        Every branch here reads the IR; none of them re-splits the source.
        """
        analysis = analysis if analysis is not None else analyze(command)

        # Unanalyzable input: we do not trust the capture, so we neither deny
        # nor allow outright -- hand it to the approval layer.
        if analysis.has_errors or analysis.budget_exhausted:
            self.last_reason = "unanalyzable"
            return CommandVerdict.ASK

        verdict = CommandVerdict.ALLOW

        # heredoc bodies bound to an interpreter ARE code (design D4, Q2=(a)).
        for hd in analysis.heredocs:
            if not hd.bound_to_interpreter:
                continue
            body_verdict = self._check_body(hd.body)
            verdict = _worse(verdict, body_verdict)
            if verdict is CommandVerdict.DENY:
                return verdict

        for segment in analysis.segments:
            seg_verdict = self._check_ir_segment(segment)
            verdict = _worse(verdict, seg_verdict)
            if verdict is CommandVerdict.DENY:
                return verdict

        return verdict

    def _check_body(self, body: str) -> CommandVerdict:
        """Judge an interpreter-bound heredoc body as a command line."""
        if not body.strip():
            return CommandVerdict.ALLOW
        if self._nested_depth >= _MAX_NESTED_COMMAND_DEPTH:
            return CommandVerdict.ASK
        self._nested_depth += 1
        try:
            verdict = self._check_analysis(body)
        finally:
            self._nested_depth -= 1
        if verdict is CommandVerdict.ASK:
            self.last_reason = self.last_reason or "heredoc_body"
        return verdict

    def _check_ir_segment(self, segment: Segment) -> CommandVerdict:
        """Strip wrappers/launchers to a fixpoint, then judge the real command."""
        argv = list(segment.argv)
        if not argv:
            return CommandVerdict.ALLOW

        # A launcher option whose value IS the command (`script -c '<cmd>'`):
        # read from the ORIGINAL argv, because stripping consumes the option.
        # Every occurrence is judged -- repeated `-c` means the last one runs.
        for concealed in _concealed_command_texts(argv):
            if not concealed.strip():
                continue
            concealed_verdict = self._check_analysis(concealed)
            if concealed_verdict is not CommandVerdict.ALLOW:
                self.last_reason = "launcher_payload"
                return concealed_verdict

        rest, unknown = _strip_to_fixpoint(argv)
        if unknown is not None:
            # Unknown leading token. Ask only when a judged command sits behind
            # it (Q4 = (c')); otherwise the program is simply unknown -> allow.
            if _conceals_judged_command(rest):
                self.last_reason = "launcher_prefix"
                return CommandVerdict.ASK
            return CommandVerdict.ALLOW

        if not rest:
            return CommandVerdict.ALLOW

        name = rest[0].rsplit("/", 1)[-1]

        # Dynamic word in a write-target position (Q1 = (c) layered): normalise
        # first; a sensitive name denies, anything else goes to approval. Checked
        # before the concrete evaluators so `cp $SRC $DST` asks rather than
        # being judged against a literal `$DST` token.
        if segment.dynamic and name in _TARGET_COMMANDS:
            dynamic_verdict = self._check_dynamic_target(rest)
            if dynamic_verdict is not CommandVerdict.ALLOW:
                return dynamic_verdict

        # `mv`/`cp` also READ their source, so a sensitive source is judged
        # too (`cp .env /tmp/x` exfiltrates credentials). Flags are skipped:
        # `cp -r .env /tmp/x` and `install -m 600 .env /tmp/x` hide the source
        # behind an option otherwise. This replaces the old source-position
        # denylist regexes, which could not tell a template from a credential
        # (design D9: the IR owns "which argument is what").
        if name in ("mv", "cp", "install"):
            source = _source_of(rest[1:])
            if source is not None:
                source_verdict = self._check_target(name, source)
                if source_verdict is not CommandVerdict.ALLOW:
                    self.last_reason = f"{name}_source"
                    return source_verdict

        # The write target may be carried on an option (`cp -t <dir> x`), so
        # resolve it explicitly rather than assuming the last argument (design
        # D2 `write_targets[]`).
        if name in _TARGET_COMMANDS:
            target = _write_target_of(name, rest[1:])
            if target is not None:
                option_verdict = self._check_target(name, target)
                if option_verdict is not CommandVerdict.ALLOW:
                    return option_verdict

        # Concrete target checks on the stripped argv: the launcher no longer
        # hides the real command (design D8).
        concrete = self._check_argv_segment(rest)
        if concrete is not CommandVerdict.ALLOW:
            return concrete

        # `sh -c '<payload>'`: the payload is a nested command line.
        if name in _SHELL_INTERPRETERS:
            payload_verdict = self._check_shell_payload(rest)
            if payload_verdict is not CommandVerdict.ALLOW:
                return payload_verdict

        # `eval '<payload>'` runs its argument as a command line (design D8).
        # Shell joins the remaining words before evaluating, so both the dequoted
        # single argument (`eval 'cp x .env'`) and the joined remainder
        # (`eval cp x .env`) are candidate payloads -- check both.
        if name in _PAYLOAD_COMMANDS and len(rest) > 1:
            for candidate in (_dequote(rest[1]), " ".join(rest[1:])):
                if not candidate.strip():
                    continue
                eval_verdict = self._check_analysis(candidate)
                if eval_verdict is not CommandVerdict.ALLOW:
                    return eval_verdict

        return CommandVerdict.ALLOW

    def _check_shell_payload(self, rest: list[str]) -> CommandVerdict:
        """Re-check each `<shell> -c <string>` payload as its own command line."""
        for payload in _shell_dash_c_payloads(rest):
            if self._nested_depth >= _MAX_NESTED_COMMAND_DEPTH:
                return CommandVerdict.ASK
            self._nested_depth += 1
            try:
                verdict = self._check_analysis(_dequote(payload))
            finally:
                self._nested_depth -= 1
            if verdict is not CommandVerdict.ALLOW:
                return verdict
        return CommandVerdict.ALLOW

    def _check_target(self, name: str, target: str) -> CommandVerdict:
        """Judge one resolved write target against protected paths / dot names."""
        normalized = _normalize_path(_expand_obfuscation(target))
        if _is_device_exempt(normalized):
            return CommandVerdict.ALLOW
        if any(_within(normalized, p) for p in _DENY_PATHS) or _dest_is_sensitive(normalized):
            self.last_reason = f"{name}_target"
            return CommandVerdict.DENY
        return CommandVerdict.ALLOW

    def _check_dynamic_target(self, rest: list[str]) -> CommandVerdict:
        """A dynamic word in the write-target position of a jud/写 command.

        Q1 = (c): normalise (expand brace/glob/backslash-escapes) first; a hit
        on a sensitive name or protected path denies, anything else asks.
        """
        name = rest[0].rsplit("/", 1)[-1]
        if name not in _WRITE_COMMANDS:
            return CommandVerdict.ALLOW

        target = _write_target_of(name, rest[1:])
        if target is None:
            return CommandVerdict.ALLOW

        expanded = _expand_obfuscation(target)
        normalized = _normalize_path(expanded)
        if any(_within(normalized, p) for p in _DENY_PATHS) or _dest_is_sensitive(normalized):
            self.last_reason = f"{name}_dynamic_sensitive"
            return CommandVerdict.DENY
        self.last_reason = f"{name}_dynamic_target"
        return CommandVerdict.ASK

    # --- High-risk sentence patterns --------------------------------------

    def _has_pipe_to_shell(self, command: str) -> bool:
        """Detect ``<cmd> | sh`` / ``| bash`` chains (arbitrary code exec)."""
        parts = re.split(r"\s*\|\s*", command)
        if len(parts) < 2:
            return False
        last = parts[-1].strip()
        # ``sh``/``bash`` alone, or ``sh -c``/``bash -c`` wrapper.
        if last in _SHELL_INTERPRETERS:
            return True
        m = re.match(r"^(?:/usr/bin/env\s+)?(?:ba|z|k|d)?sh\s+-c\b", last)
        return bool(m)

    def _has_protected_redirect(self, analysis: BashAnalysis) -> bool:
        """Detect redirects (``>``/``>>``) into protected paths or sensitive names.

        Reads the IR's `redirects[]` (design D2/D9) rather than re-tokenizing the
        source: the IR already knows which token is a redirect target. Device
        files are exempt (``2>/dev/null`` is a black-hole write, not a protected
        asset), and sensitive dot names use the same shared predicate as mv/cp
        targets, so ``echo X >> .env.local`` lands here.
        """
        for redirect in analysis.redirects:
            if redirect.op not in (">", ">>"):
                continue
            target = _normalize_path(redirect.target)
            if _is_device_exempt(target):
                continue
            if any(_within(target, p) for p in _DENY_PATHS) or _dest_is_sensitive(target):
                return True
        return False

    # --- argv semantic checks ---------------------------------------------

    def _check_argv(self, tokens: list[str], *, raw: str | None = None) -> CommandVerdict:
        """Run the argv checks against **every command segment**.

        ``tokens[0]`` is only the first word of the whole line, so a chained
        command's later segments used to escape every argv check entirely:
        ``cd /tmp && cp evil ~/.ssh/authorized_keys`` was never examined for
        ``cp`` (fix-issue-247 review I1). Splitting on the tokenizer's
        separators (``&&``, ``;``, ``|``, ``&``) and checking each segment
        closes that gap; ``raw`` lets the newline case (which the tokenizer
        folds into whitespace) be split too. The ``bash -c "…"`` form is
        handled by unpacking the quoted payload and checking it as its own
        command line.
        """
        segments = (
            _check_command_text(raw)
            if raw is not None
            else _split_command_segments(tokens)
        )
        for segment in segments:
            verdict = self._check_argv_segment(segment)
            if verdict is CommandVerdict.DENY:
                return CommandVerdict.DENY
            # `bash -c "cp evil .env"`: the payload is a nested command line.
            # Bounded depth: `bash -c "bash -c '…'"` nests arbitrarily and an
            # unbounded re-check recurses until the interpreter dies (review
            # Round 2). Past the limit the payload is left unexamined — the
            # guard is a guardrail, and the sandbox backend is the boundary.
            if self._nested_depth >= _MAX_NESTED_COMMAND_DEPTH:
                continue
            for payload in _shell_dash_c_payloads(segment):
                self._nested_depth += 1
                try:
                    if self.check(payload) is CommandVerdict.DENY:
                        self.last_reason = self.last_reason or "denylist"
                        return CommandVerdict.DENY
                finally:
                    self._nested_depth -= 1
        return CommandVerdict.ALLOW

    def _check_argv_segment(self, tokens: list[str]) -> CommandVerdict:
        if not tokens:
            return CommandVerdict.ALLOW
        # Leading shell keywords / wrappers are dropped by `_strip_wrappers`,
        # the entry point shared with the payload channel (review Round 4 I-1).
        tokens = _strip_wrappers(tokens)
        if not tokens:
            return CommandVerdict.ALLOW
        # Normalize command name: strip /bin/, /usr/bin/ prefixes. Wrapper
        # commands (`env`/`command`/`nohup`) were already dropped by
        # `_strip_wrappers` above, so no wrapper branch is needed here.
        cmd_name = tokens[0]
        if cmd_name in ("/bin/rm", "/usr/bin/rm"):
            cmd_name = "rm"

        if cmd_name == "rm":
            return self._check_rm(tokens)
        if cmd_name in ("mv", "cp"):
            return self._check_mv_cp(tokens)
        if cmd_name == "chmod":
            return self._check_chmod(tokens)
        if cmd_name == "timeout":
            return self._check_timeout(tokens)
        if cmd_name in ("curl", "wget"):
            return self._check_curl_wget(tokens)
        if cmd_name == "dd":
            return self._check_dd(tokens)
        if cmd_name == "tee":
            return self._check_tee(tokens)
        return CommandVerdict.ALLOW

    def _check_rm(self, tokens: list[str]) -> CommandVerdict:
        """rm with recursive+force flags targeting a protected/outside path is denied."""
        flags = [t for t in tokens[1:] if t.startswith("-")]
        # Any flag arg containing 'r' and 'f' (e.g. -rf, -fr, -r -f) counts.
        has_recursive = any("r" in t for t in flags)
        has_force = any("f" in t for t in flags)
        targets = [t for t in tokens[1:] if not t.startswith("-")]
        if not (has_recursive and has_force):
            return CommandVerdict.ALLOW
        for target in targets:
            # $IFS expands to whitespace, so "$IFS/" is effectively "/".
            normalized = _normalize_path(target.replace("$IFS", ""))
            if normalized in ("/", "$HOME", "~") or any(
                _within(normalized, p) for p in _DENY_PATHS
            ):
                self.last_reason = "rm_target_escape"
                return CommandVerdict.DENY
            if self._workspace:
                ws = _normalize_path(self._workspace)
                if normalized.startswith("/") and not _within(normalized, ws):
                    self.last_reason = "rm_target_escape"
                    return CommandVerdict.DENY
                # Deleting the workspace root itself is as destructive as
                # escaping it (fix-issue-247 Q1).
                if normalized == ws:
                    self.last_reason = "rm_target_escape"
                    return CommandVerdict.DENY
        return CommandVerdict.ALLOW

    def _check_mv_cp(self, tokens: list[str]) -> CommandVerdict:
        """mv/cp whose destination lands in a protected path is denied.

        Segment-wise, device-exempt, and sensitive-dot-dir aware
        (fix-issue-247): ``/various.txt`` is not under ``/var``, ``cp x
        /dev/null`` is a black-hole write, and ``.gitignore`` is not ``.git``.
        """
        args = [t for t in tokens[1:] if not t.startswith("-")]
        if len(args) < 2:
            return CommandVerdict.ALLOW
        dest = _normalize_path(args[-1])
        if _is_device_exempt(dest):
            return CommandVerdict.ALLOW
        if any(_within(dest, p) for p in _DENY_PATHS) or _dest_is_sensitive(dest):
            self.last_reason = "mv_cp_dest"
            return CommandVerdict.DENY
        return CommandVerdict.ALLOW

    def _check_chmod(self, tokens: list[str]) -> CommandVerdict:
        """chmod targeting a protected path with permissive bits is denied."""
        args = [t for t in tokens[1:] if not t.startswith("-")]
        if len(args) < 2:
            return CommandVerdict.ALLOW
        mode, target = args[0], _normalize_path(args[1])
        if any(_within(target, p) for p in _DENY_PATHS):
            self.last_reason = "chmod_bits"
            return CommandVerdict.DENY
        # 0777 / 777 / a+rwx on root or /tmp.
        if mode in ("0777", "777", "a+rwx", "a=rwx") and target in ("/", "/tmp"):
            self.last_reason = "chmod_bits"
            return CommandVerdict.DENY
        return CommandVerdict.ALLOW

    def _check_dd(self, tokens: list[str]) -> CommandVerdict:
        """``dd of=<target>`` writes to ``<target>`` (design D2 `write_targets[]`).

        The target is carried on the option, not as a positional argument, so
        ``dd of=.env`` used to slip past every target check.
        """
        for token in tokens[1:]:
            if not token.startswith("of="):
                continue
            target = _normalize_path(token[3:])
            if _is_device_exempt(target):
                continue
            if any(_within(target, p) for p in _DENY_PATHS) or _dest_is_sensitive(target):
                self.last_reason = "dd_target"
                return CommandVerdict.DENY
        return CommandVerdict.ALLOW

    def _check_tee(self, tokens: list[str]) -> CommandVerdict:
        """``tee <target>`` writes to each non-option argument."""
        for token in tokens[1:]:
            if token.startswith("-"):
                continue
            target = _normalize_path(token)
            if _is_device_exempt(target):
                continue
            if any(_within(target, p) for p in _DENY_PATHS) or _dest_is_sensitive(target):
                self.last_reason = "tee_target"
                return CommandVerdict.DENY
        return CommandVerdict.ALLOW

    def _check_curl_wget(self, tokens: list[str]) -> CommandVerdict:
        """curl/wget with a ``@<protected-path>`` data arg (exfiltrating a
        sensitive file) is denied. Plain fetch/upload without a file arg passes.
        """
        for arg in tokens[1:]:
            if arg.startswith("@"):
                target = _normalize_path(arg[1:])
                if any(_within(target, p) for p in _DENY_PATHS):
                    self.last_reason = "curl_exfil"
                    return CommandVerdict.DENY
        return CommandVerdict.ALLOW

    def _check_timeout(self, tokens: list[str]) -> CommandVerdict:
        """timeout value must be a positive int within a sane range, then the
        wrapped command is checked recursively (a `timeout 5 rm -rf /` must not
        pass just because `timeout` is the first word)."""
        rest = tokens[1:]
        value_idx = next(
            (i for i, t in enumerate(rest) if not t.startswith("-")), None
        )
        if value_idx is None:
            return CommandVerdict.ALLOW
        try:
            val = float(rest[value_idx])
        except ValueError:
            # Not a numeric timeout — check the wrapped command directly.
            return self._check_argv(rest)
        if val <= 0 or val > 600:
            self.last_reason = "timeout_range"
            return CommandVerdict.DENY
        return self._check_argv(rest[value_idx + 1:])
