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

from agent.workspace_policy import DEFAULT_DENYLIST

# Protected paths: writing to these is always denied.
_DENY_PATHS = ("/etc", "/proc", "/sys", "/dev", "/root", "/boot", "/var")
# Device files that are black-hole / std-stream aliases rather than protected
# assets. Only exempt for redirection and mv/cp targets (fix-issue-247 Q2/Q3).
_DEVICE_EXEMPT = ("/dev/null", "/dev/stdout", "/dev/stderr")
# Dot-directories carrying credentials or repo metadata. Compared per path
# **segment** (never by prefix), so `.gitignore` / `.github/` / `.env.example`
# pass while `.git/config` and `src/.git/hooks/x` are caught.
_SENSITIVE_DOTDIRS = frozenset(
    {".git", ".ssh", ".env", ".aws", ".gnupg", ".kube", ".docker", ".netrc", ".npmrc", ".pypirc"}
)
_SENSITIVE_DOTFILES = frozenset(
    {".env", ".netrc", ".npmrc", ".pypirc", ".gitconfig", ".git-credentials"}
)


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


def _dest_is_sensitive(dest: str) -> bool:
    """True when ``dest`` carries credentials / repo metadata (fix-issue-247 R1).

    Segment-wise: any path segment equal to a sensitive dot-directory, or a
    basename equal to a sensitive dot-file.
    """
    parts = [part for part in dest.split("/") if part not in ("", ".")]
    if any(part in _SENSITIVE_DOTDIRS for part in parts):
        return True
    return bool(parts) and parts[-1] in _SENSITIVE_DOTFILES
# Shell interpreters that, when piped to, imply arbitrary code execution.
_SHELL_INTERPRETERS = {"sh", "bash", "zsh", "ksh", "dash", "fish"}
# Arbitrary code execution interpreters.
_CODE_EXEC_INTERPRETERS = {"python", "python3", "node", "deno", "perl", "ruby", "php", "awk"}

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

    def check(self, command: str) -> CommandVerdict:
        self.last_reason = None
        cmd = command.strip()
        if not cmd:
            return CommandVerdict.ALLOW

        # 1. Extended denylist (conventional bypass variants).
        # ``rm`` is excluded: the base denylist's ``rm -rf /`` pattern matches
        # any path starting with ``/`` (false positive on workspace-internal
        # paths). argv semantics (step 3) judge rm precisely.
        cmd_name = cmd.split()[0] if cmd.split() else ""
        if cmd_name != "rm":
            for pattern in self._denylist:
                if re.search(pattern, cmd):
                    self.last_reason = "denylist"
                    return CommandVerdict.DENY

        # 2. High-risk sentence patterns (pipe to shell, redirect to protected).
        if self._has_pipe_to_shell(cmd):
            self.last_reason = "pipe_to_shell"
            return CommandVerdict.DENY
        if self._has_protected_redirect(cmd):
            self.last_reason = "protected_redirect"
            return CommandVerdict.DENY

        # 3. argv semantic checks for dangerous commands.
        tokens = tokenize_command(cmd)
        if not tokens:
            return CommandVerdict.ALLOW
        argv_verdict = self._check_argv(tokens, raw=cmd)
        if argv_verdict is CommandVerdict.DENY:
            return CommandVerdict.DENY

        # Default-allow.
        return CommandVerdict.ALLOW

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

    def _has_protected_redirect(self, command: str) -> bool:
        """Detect redirects (``>``/``>>``) into protected paths.

        Segment-wise and device-exempt: ``2>/dev/null`` is a black-hole write,
        not a protected asset, and ``/various.txt`` is not under ``/var``.
        """
        tokens = tokenize_command(command)
        for i, tok in enumerate(tokens):
            if tok in (">", ">>") and i + 1 < len(tokens):
                target = _normalize_path(tokens[i + 1])
                if _is_device_exempt(target):
                    continue
                if any(_within(target, p) for p in _DENY_PATHS):
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
