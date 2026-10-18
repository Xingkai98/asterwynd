#!/usr/bin/env python3
"""Bash-only PreToolUse write guard.

This is a *local checkpoint*, not an adversarial sandbox. It intercepts direct
file-writing Bash commands that target:

- managed paths from ``.witnessloop/policy.json`` (``require_change_for``), and
- protected artifacts from the same policy (``protected_paths``).

``Write|Edit`` is intentionally left to the witnessloop plugin guard. VCS
commands are handled separately: ``git rm`` / ``git mv`` are allowed (otherwise
files could not be deleted or renamed through any channel), explicit-path
``git restore`` / ``git checkout --`` and non-dry-run ``git apply`` are blocked,
and merge/rebase/cherry-pick/stash/am are documented as known content-write
bypasses.

Usage:
  python3 scripts/bash_write_guard.py            # Claude Code PreToolUse hook (stdin JSON)
  python3 scripts/bash_write_guard.py --command 'echo x > agent/y'
  python3 scripts/bash_write_guard.py --root /path/to/repo --command '...'

Exit codes: 0 allow, 2 block (Claude Code hook convention). Parser/internal
errors fail open with a warning; the CI gate remains the final authority.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

EMBEDDED_REQUIRE_CHANGE_FOR = ["agent/**", "scripts/**", "web/**"]
EMBEDDED_PROTECTED_PATHS = [
    "openspec/specs/**",
    ".witnessloop/**",
    "docs/known-issues.md",
    "docs/known-debt.md",
    "docs/openspec-change-backlog.md",
]

_POLICY_REL = Path(".witnessloop") / "policy.json"
_REDIRECT_OPS = {">", ">>", "&>", ">&", ">|"}
_HERE_OPS = {"<<", "<<<"}
_PREFIXES = {"sudo", "doas", "env", "timeout", "nohup", "command", "builtin", "nice"}
_NESTED_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_MAX_DEPTH = 6

_WRITE_CALL_RE = re.compile(
    r"\b(?:open|write_text|write_bytes|write|dump|save|remove|unlink|mkdir|"
    r"rmdir|rename|replace|shutil\.\w+|os\.system|subprocess\.\w+)\s*\("
)
_HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)\s*(?:-)?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


# ── policy / path matching ──────────────────────────────────────────


def _load_policy(root: Path) -> tuple[list[str], list[str]]:
    """Load managed/protected patterns; malformed/missing policy uses defaults."""

    path = root / _POLICY_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return list(EMBEDDED_REQUIRE_CHANGE_FOR), list(EMBEDDED_PROTECTED_PATHS)
    except (OSError, ValueError) as exc:
        print(
            f"Bash write guard: cannot read {path} ({exc}); using embedded defaults.",
            file=sys.stderr,
        )
        return list(EMBEDDED_REQUIRE_CHANGE_FOR), list(EMBEDDED_PROTECTED_PATHS)

    if not isinstance(data, dict):
        print(
            f"Bash write guard: {path} must be a JSON object; using embedded defaults.",
            file=sys.stderr,
        )
        return list(EMBEDDED_REQUIRE_CHANGE_FOR), list(EMBEDDED_PROTECTED_PATHS)

    require = data.get("require_change_for")
    protected = data.get("protected_paths")
    if not (
        isinstance(require, list)
        and isinstance(protected, list)
        and all(isinstance(item, str) and item for item in require)
        and all(isinstance(item, str) and item for item in protected)
    ):
        print(
            f"Bash write guard: {path} has invalid require_change_for/protected_paths; "
            "using embedded defaults.",
            file=sys.stderr,
        )
        return list(EMBEDDED_REQUIRE_CHANGE_FOR), list(EMBEDDED_PROTECTED_PATHS)
    return list(require), list(protected)


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    cached = _GLOB_CACHE.get(pattern)
    if cached is not None:
        return cached
    pat = pattern.replace("\\", "/")
    out: list[str] = []
    i = 0
    while i < len(pat):
        ch = pat[i]
        if ch == "*":
            if i + 1 < len(pat) and pat[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if ch == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(ch))
        i += 1
    compiled = re.compile("^" + "".join(out) + "$")
    _GLOB_CACHE[pattern] = compiled
    return compiled


def _matches(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        candidates = [pattern]
        # `agent/**` also covers the directory itself (`rm -rf agent`).
        if pattern.endswith("/**"):
            candidates.append(pattern[:-3])
        if any(_glob_to_regex(candidate).match(normalized) for candidate in candidates):
            return True
    return False


def _normalize_target(target: str, cwd: Path, root: Path) -> str | None:
    """Return a repo-relative path, an absolute outside path, or None (unknown)."""

    if not target:
        return None
    if "$" in target or "`" in target or target.startswith("~"):
        # Variable/backtick/home expansion is not statically decidable.
        return None
    target = target.replace("\\", "/")
    if target in {"-", "&1", "&2", "&-", "/dev/null", "/dev/stdout", "/dev/stderr"}:
        return None
    if target.startswith("/dev/fd/"):
        return None
    if re.fullmatch(r"&[0-9-]+", target):
        return None

    if target.startswith("/"):
        candidate = Path(os.path.normpath(target))
    else:
        candidate = Path(os.path.normpath(str(cwd / target)))
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()


# ── shell scanning ──────────────────────────────────────────────────


def _strip_heredocs(command: str) -> str:
    """Remove here-doc bodies; keep the header line (its redirection is analyzed)."""

    lines = command.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        match = _HEREDOC_RE.search(line)
        index += 1
        if not match:
            continue
        delimiter = match.group(2)
        while index < len(lines):
            if lines[index].strip() == delimiter:
                index += 1
                break
            index += 1
    return "\n".join(kept)


def _collect_substitutions(command: str) -> list[str]:
    """Collect ``$(...)`` and backtick command substitutions outside single quotes."""

    found: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(command):
        ch = command[i]
        if quote == "'":
            if ch == "'":
                quote = None
            i += 1
            continue
        if quote == '"':
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                quote = None
                i += 1
                continue
        else:
            if ch in ("'", '"'):
                quote = ch
                i += 1
                continue
            if ch == "`":
                end = command.find("`", i + 1)
                if end != -1:
                    found.append(command[i + 1 : end])
                    i = end + 1
                    continue
                i += 1
                continue
        if command.startswith("$(", i):
            depth = 0
            start = i + 2
            j = start
            while j < len(command):
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    if depth == 0:
                        found.append(command[start:j])
                        i = j + 1
                        break
                    depth -= 1
                j += 1
            else:
                i += 1
            continue
        i += 1
    return found


def _split_commands(text: str) -> list[str]:
    segments: list[str] = []
    buf: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if text.startswith("&&", i) or text.startswith("||", i):
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch in ";\n":
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        if ch == "|" and not "".join(buf).rstrip().endswith(">"):
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return [segment.strip() for segment in segments if segment.strip()]


def _tokenize(segment: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    buf: list[str] = []
    i = 0
    quote: str | None = None

    def flush() -> None:
        if buf:
            tokens.append(("word", "".join(buf)))
            buf.clear()

    while i < len(segment):
        ch = segment[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(segment):
                buf.append(segment[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < len(segment):
            buf.append(segment[i + 1])
            i += 2
            continue
        if ch.isspace():
            flush()
            i += 1
            continue
        matched = None
        for op in ("<<<", "&&", "||", ">>", "<<", "&>", ">&", ">|", ">", "<", "|", ";"):
            if segment.startswith(op, i):
                matched = op
                break
        if matched:
            flush()
            tokens.append(("op", matched))
            i += len(matched)
            continue
        buf.append(ch)
        i += 1
    flush()
    return tokens


def _clean_word(word: str) -> str:
    return re.sub(r"""(?<!\\)['"]""", "", word).replace("\\\\", "\\")


def _non_option_args(args: list[str]) -> list[str]:
    return [arg for arg in args if not arg.startswith("-") or arg == "-"]


def _dest_arg(args: list[str], *, short: str = "-t", long: str = "--target-directory") -> list[str]:
    for index, arg in enumerate(args):
        if arg in {short, long} and index + 1 < len(args):
            return [args[index + 1]]
        if arg.startswith(long + "="):
            return [arg.split("=", 1)[1]]
    positional = _non_option_args(args)
    return positional[-1:] if positional else []


def _all_paths(args: list[str]) -> list[str]:
    return _non_option_args(args)


def _sed_files(args: list[str]) -> list[str]:
    has_in_place = any(
        arg.startswith("-i") or arg == "--in-place" or arg.startswith("--in-place=")
        for arg in args
    )
    if not has_in_place:
        return []
    files: list[str] = []
    skip_next = False
    script_seen = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in {"-e", "-f"}:
            skip_next = True
            script_seen = True
            continue
        if arg.startswith("-") and arg != "-":
            continue
        if not script_seen:
            script_seen = True
            continue
        files.append(arg)
    return files


def _perl_files(args: list[str]) -> list[str]:
    if not any(
        arg == "--in-place"
        or (arg.startswith("-") and "i" in arg[1:])
        for arg in args
    ):
        return []
    files: list[str] = []
    skip_next = False
    script_seen = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in {"-e", "-E"}:
            skip_next = True
            script_seen = True
            continue
        if arg.startswith("-") and arg != "-":
            continue
        if not script_seen:
            script_seen = True
            continue
        files.append(arg)
    return files


def _output_arg(args: list[str], flags: set[str]) -> list[str]:
    for index, arg in enumerate(args):
        if arg in flags and index + 1 < len(args):
            return [args[index + 1]]
        for flag in flags:
            if flag.startswith("--") and arg.startswith(flag + "="):
                return [arg.split("=", 1)[1]]
            if not flag.startswith("--") and arg.startswith(flag) and len(arg) > len(flag):
                return [arg[len(flag):]]
    return []


def _git_targets(args: list[str]) -> tuple[list[str], str | None]:
    """Return (explicit write targets, hard-block reason)."""

    if not args:
        return [], None
    sub = args[0]
    rest = args[1:]
    if sub in {"rm", "mv"}:
        return [], None
    if sub == "restore":
        if "--staged" in rest and "--worktree" not in rest:
            return [], None
        if "--" in rest:
            return rest[rest.index("--") + 1 :], None
        return [arg for arg in rest if not arg.startswith("-")], None
    if sub == "checkout":
        if "--" in rest:
            return rest[rest.index("--") + 1 :], None
        return [], None
    if sub == "apply":
        if any(
            arg in {"--check", "--stat", "--numstat", "--summary", "--name-only"}
            for arg in rest
        ):
            return [], None
        return [], "`git apply` 的 patch 目标无法静态检查"
    if sub in {"merge", "rebase", "cherry-pick", "stash", "am"}:
        return [], None
    return [], None


def _python_code_targets(args: list[str]) -> list[str]:
    if "-c" not in args:
        return []
    index = args.index("-c")
    if index + 1 >= len(args):
        return []
    code = args[index + 1]
    if not _WRITE_CALL_RE.search(code):
        return []
    return re.findall(
        r"(?<![A-Za-z0-9_])(?:(?:agent|scripts|web)(?:/[A-Za-z0-9_.@%+\-/]*)?"
        r"|(?:openspec|docs)/[A-Za-z0-9_.@%+\-/]*)(?![A-Za-z0-9_])",
        code,
    )


_PREFIX_VALUE_FLAGS = {
    "sudo": {
        "-u", "--user", "-g", "--group", "-p", "--prompt", "-h", "--host",
        "-r", "--role", "-t", "--type", "-U", "--other-user", "-C",
        "--close-from", "-D", "--chdir", "-R", "--chroot", "-T",
        "--command-timeout",
    },
    "doas": {"-u", "-C"},
    "nice": {"-n", "--adjustment"},
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
}


def _unwrap_prefixes(words: list[str]) -> list[str]:
    words = list(words)
    while words:
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words.pop(0)
        if not words:
            break
        prefix = Path(words[0]).name
        if prefix not in _PREFIXES:
            break
        words.pop(0)
        if prefix == "timeout":
            while words and words[0].startswith("-"):
                option = words.pop(0)
                if option in _PREFIX_VALUE_FLAGS["timeout"] and words:
                    words.pop(0)
            if words:
                words.pop(0)  # duration
            continue
        if prefix == "nice":
            while words and words[0].startswith("-"):
                option = words.pop(0)
                if option in _PREFIX_VALUE_FLAGS["nice"] and words:
                    words.pop(0)
            continue
        if prefix in _PREFIX_VALUE_FLAGS:
            while words and words[0].startswith("-"):
                option = words.pop(0)
                if option in _PREFIX_VALUE_FLAGS[prefix] and words:
                    words.pop(0)
            continue
        while words and words[0].startswith("-"):
            words.pop(0)
    return words


def _nested_shell_code(words: list[str]) -> str | None:
    if not words or Path(words[0]).name not in _NESTED_SHELLS:
        return None
    for index, arg in enumerate(words[1:], start=1):
        if arg.startswith("-") and "c" in arg[1:]:
            tail = arg[arg.index("c") + 1 :]
            if tail:
                return tail
            if index + 1 < len(words):
                return words[index + 1]
    return None


def _command_targets(words: list[str]) -> tuple[list[str], str | None]:
    if not words:
        return [], None
    words = _unwrap_prefixes(words)
    if not words:
        return [], None

    command = Path(words[0]).name
    args = words[1:]

    if command == "cp":
        return _dest_arg(args), None
    if command == "install":
        return _dest_arg(args), None
    if command == "ln":
        return _dest_arg(args), None
    if command == "rsync":
        if any(arg in {"-n", "--dry-run"} for arg in args):
            return [], None
        return _dest_arg(args), None
    if command in {"mv", "rm", "rmdir", "unlink", "truncate", "touch", "mkdir"}:
        return _all_paths(args), None
    if command == "tee":
        return _all_paths(args), None
    if command in {"chmod", "chown"}:
        positional = _non_option_args(args)
        return positional[1:], None
    if command == "sed":
        return _sed_files(args), None
    if command in {"perl", "ruby"}:
        return _perl_files(args), None
    if command == "dd":
        return [arg[3:] for arg in args if arg.startswith("of=")], None
    if command == "curl":
        return _output_arg(args, {"-o", "--output"}), None
    if command == "wget":
        return _output_arg(args, {"-O", "--output-document"}), None
    if command in {"python", "python3"}:
        return _python_code_targets(args), None
    if command == "git":
        while args:
            head = args[0]
            if head in {"-C", "--git-dir", "--work-tree", "-c"}:
                args = args[2:] if len(args) > 1 else []
                continue
            if head.startswith(("--git-dir=", "--work-tree=")) or (
                head.startswith("-C") and len(head) > 2
            ):
                args = args[1:]
                continue
            break
        return _git_targets(args)
    return [], None


def _analyze(
    command: str,
    root: Path,
    cwd: Path,
    depth: int = 0,
    patterns: list[str] | None = None,
) -> list[str]:
    if depth > _MAX_DEPTH or not command.strip():
        return []
    if patterns is None:
        require, protected = _load_policy(root)
        patterns = [*require, *protected]

    reasons: list[str] = []
    for inner in _collect_substitutions(command):
        reasons.extend(_analyze(inner, root, cwd, depth + 1, patterns))

    stripped = _strip_heredocs(command)
    for segment in _split_commands(stripped):
        tokens = _tokenize(segment)
        words: list[str] = []
        redirect_targets: list[str] = []
        index = 0
        while index < len(tokens):
            kind, value = tokens[index]
            if kind == "op" and value in _REDIRECT_OPS:
                if index + 1 < len(tokens) and tokens[index + 1][0] == "word":
                    redirect_targets.append(_clean_word(tokens[index + 1][1]))
                    index += 2
                    continue
                index += 1
                continue
            if kind == "op" and value in _HERE_OPS:
                index += 2
                continue
            if kind == "word":
                words.append(_clean_word(value))
            index += 1

        if words and Path(words[0]).name in {"cd", "pushd"}:
            if len(words) >= 2:
                target = words[1]
                if not target.startswith("~") and "$" not in target:
                    cwd = Path(os.path.normpath(str(cwd / target)))
            continue

        words = _unwrap_prefixes(words)
        nested_code = _nested_shell_code(words)
        if nested_code is not None:
            reasons.extend(_analyze(nested_code, root, cwd, depth + 1, patterns))
            continue
        if words and Path(words[0]).name == "eval":
            reasons.extend(_analyze(" ".join(words[1:]), root, cwd, depth + 1, patterns))
            continue

        command_targets, hard_reason = _command_targets(words)
        if hard_reason:
            reasons.append(hard_reason)

        for raw in [*redirect_targets, *command_targets]:
            normalized = _normalize_target(raw, cwd, root)
            if normalized and _matches(normalized, patterns):
                reasons.append(f"写入受管/受保护路径：{normalized}")
    return reasons


def evaluate_command(command: str, root: Path | str | None = None) -> list[str]:
    """Return blocking reasons; an empty list means allow."""

    root_path = Path(root).resolve() if root is not None else REPO_ROOT
    try:
        return sorted(set(_analyze(command, root_path, root_path)))
    except Exception as exc:  # local checkpoint: fail open, CI is authoritative
        print(f"Bash write guard: parser error ({exc}); allowing command.", file=sys.stderr)
        return []


# ── entry points ────────────────────────────────────────────────────


def run_hook(payload: dict, root: Path | str | None = None) -> int:
    tool_name = str(payload.get("tool_name", ""))
    if tool_name.split(":")[-1] != "Bash":
        return 0
    command = str(payload.get("tool_input", {}).get("command", ""))
    reasons = evaluate_command(command, root)
    if not reasons:
        return 0
    print("⛔ Bash 写前拦截：受管/受保护路径不可由 Bash 直接写入。", file=sys.stderr)
    for reason in reasons[:5]:
        print(f"  - {reason}", file=sys.stderr)
    print(
        "请改用 Write/Edit（由 witnessloop guard 求值），或用 git rm / git mv 做删除/改名。",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", help="Analyze this command instead of reading hook JSON")
    parser.add_argument("--root", help="Repository root (default: script's parent repo)")
    args = parser.parse_args(argv)

    root = Path(
        args.root
        or os.environ.get("BASH_WRITE_GUARD_ROOT")
        or REPO_ROOT
    )

    if args.command is not None:
        reasons = evaluate_command(args.command, root)
        if not reasons:
            return 0
        print("⛔ Bash 写前拦截：受管/受保护路径不可由 Bash 直接写入。", file=sys.stderr)
        for reason in reasons[:5]:
            print(f"  - {reason}", file=sys.stderr)
        return 2

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("Bash write guard: invalid hook JSON; allowing.", file=sys.stderr)
        return 0
    return run_hook(payload, root)


if __name__ == "__main__":
    raise SystemExit(main())
