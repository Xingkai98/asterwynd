"""Single parse pipeline: shell source -> command IR (design D1/D2).

This is the one place that reads raw command text and turns it into structure.
Every policy evaluator consumes the resulting `BashAnalysis`; none of them
re-parses the source or re-splits tokens (design D9: "same semantics must not
have two implementations").

Parsing uses `tree-sitter-bash`. Command nodes are collected with
`QueryCursor`, never a recursive Python walk — the latter hits Python's
recursion limit on ~2,000 characters of `$(( 1+1+… ))` (design D1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from tree_sitter import Language, Parser, Query, QueryCursor

from agent.workspace_policy import is_sensitive_dot_name  # noqa: F401  (re-export for consumers)

#: Node types that make up a command's argv, in source order.
_ARG_NODE_TYPES = (
    "command_name",
    "word",
    "string",
    "raw_string",
    "ansi_c_string",
    "concatenation",
    "simple_expansion",
    "expansion",
    "command_substitution",
    "process_substitution",
    "arithmetic_expansion",
)

#: Shells / interpreters: a heredoc bound to one of these carries CODE on stdin.
#: The `-s` / `-` variants are covered by `is_interpreter`'s suffix handling.
INTERPRETERS = frozenset(
    {
        "sh", "bash", "zsh", "ksh", "dash", "fish",
        "python", "python2", "python3", "node", "deno", "perl", "ruby", "php",
        "awk", "gawk", "mawk", "busybox",
    }
)

#: Parse-budget backstop (design D4: "解析预算耗尽 -> ask"). Generous enough that
#: no realistic command hits it; it exists so a pathological input degrades to a
#: defined verdict instead of hanging.
MAX_NODES = 50_000
MAX_SOURCE_BYTES = 256 * 1024


@lru_cache(maxsize=1)
def _language() -> Language:
    import tree_sitter_bash

    return Language(tree_sitter_bash.language())


@lru_cache(maxsize=1)
def _parser() -> Parser:
    return Parser(_language())


@lru_cache(maxsize=1)
def _cmd_query() -> Query:
    return Query(_language(), "(command) @c")


@lru_cache(maxsize=1)
def _redirect_query() -> Query:
    return Query(_language(), "(file_redirect) @r")


@lru_cache(maxsize=1)
def _heredoc_query() -> Query:
    return Query(_language(), "(heredoc_redirect) @h")


def _base_name(token: str) -> str:
    """`/usr/bin/env` -> `env`; leaves bare names alone."""
    return token.rsplit("/", 1)[-1]


def is_interpreter(text: str) -> bool:
    """True when ``text`` (a command's argv[0], possibly with args) is an interpreter."""
    if not text:
        return False
    first = text.split()[0]
    return _base_name(first) in INTERPRETERS


@dataclass(frozen=True)
class Redirect:
    """A `> file` / `>> file` / `< file` redirection."""

    op: str
    target: str


@dataclass(frozen=True)
class Heredoc:
    """A heredoc redirected into a command's stdin.

    ``owner`` is the command text the body is piped into; the body is CODE when
    that owner is an interpreter and data otherwise (design D4).
    """

    delim: str
    body: str
    owner: str

    @property
    def bound_to_interpreter(self) -> bool:
        return is_interpreter(self.owner)


@dataclass(frozen=True)
class Segment:
    """One command node: its argv, plus the flags an evaluator needs."""

    argv: tuple[str, ...]
    #: True when any argument carries a variable / glob / brace expansion —
    #: the "dynamic word" signal of design D4.
    dynamic: bool

    @property
    def name(self) -> str:
        return _base_name(self.argv[0]) if self.argv else ""


@dataclass
class BashAnalysis:
    """The IR. One instance per `analyze()` call."""

    source: str
    segments: list[Segment] = field(default_factory=list)
    redirects: list[Redirect] = field(default_factory=list)
    heredocs: list[Heredoc] = field(default_factory=list)
    #: True when the tree has ERROR nodes or zero-width MISSING nodes. Callers
    #: MUST NOT trust `argv` in that case (captures degrade to garbage, e.g.
    #: `rm -rf !(keep)` -> `['rm -rf !', 'keep']`).
    has_errors: bool = False
    #: True when the input tripped MAX_NODES / MAX_SOURCE_BYTES.
    budget_exhausted: bool = False

    def __post_init__(self) -> None:
        if self.has_errors:
            # Malformed input: the argv captures are unreliable, so drop them
            # rather than let an evaluator act on garbage (design D1 constraint 2).
            self.segments = [Segment(argv=(), dynamic=False)]


def _is_dynamic(node) -> bool:
    """True when ``node``'s subtree contains a variable / expansion."""
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in (
            "simple_expansion",
            "expansion",
            "command_substitution",
            "process_substitution",
            "arithmetic_expansion",
        ):
            return True
        if n.child_count == 0 and any(ch in n.text.decode(errors="replace") for ch in "$*?[{~`"):
            return True
        stack.extend(n.children)
    return False


def _argv_of(node) -> tuple[tuple[str, ...], bool]:
    argv: list[str] = []
    dynamic = False
    for child in node.children:
        if child.type not in _ARG_NODE_TYPES:
            continue
        argv.append(child.text.decode(errors="replace"))
        if _is_dynamic(child):
            dynamic = True
    return tuple(argv), dynamic


def _has_missing(node) -> bool:
    """Zero-width MISSING nodes are an error signal too (design D1 constraint 2)."""
    stack = [node]
    while stack:
        n = stack.pop()
        if n.is_missing:
            return True
        stack.extend(n.children)
    return False


def _redirects_of(tree) -> list[Redirect]:
    out: list[Redirect] = []
    for node in QueryCursor(_redirect_query()).captures(tree.root_node).get("r", []):
        op = "<"
        target = ""
        for child in node.children:
            if child.type in (">", ">>", "<", "<<", "<>"):
                op = child.text.decode()
            elif child.type in ("word", "string", "raw_string", "concatenation",
                                "simple_expansion", "expansion"):
                target = child.text.decode(errors="replace")
        if target:
            out.append(Redirect(op=op, target=target))
    return out


def _heredocs_of(tree) -> list[Heredoc]:
    out: list[Heredoc] = []
    for node in QueryCursor(_heredoc_query()).captures(tree.root_node).get("h", []):
        delim = ""
        body = ""
        for child in node.children:
            if child.type == "heredoc_start":
                delim = child.text.decode(errors="replace").strip("'\"")
            elif child.type == "heredoc_body":
                body = child.text.decode(errors="replace")
        owner = ""
        parent = node.parent
        if parent is not None:
            for child in parent.children:
                if child.type == "command":
                    owner = child.text.decode(errors="replace")
                    break
        out.append(Heredoc(delim=delim, body=body, owner=owner))
    return out


def analyze(source: str) -> BashAnalysis:
    """Parse ``source`` into a `BashAnalysis`. Never raises (design D1)."""
    try:
        raw = source.encode("utf-8", errors="replace")
    except Exception:                                    # pragma: no cover - defensive
        return BashAnalysis(source=source, has_errors=True)

    if len(raw) > MAX_SOURCE_BYTES:
        return BashAnalysis(source=source, has_errors=True, budget_exhausted=True)

    try:
        tree = _parser().parse(raw)
    except Exception:                                    # pragma: no cover - defensive
        # tree-sitter does not raise on malformed input; if it ever does, treat
        # it as unanalyzable rather than letting it escape.
        return BashAnalysis(source=source, has_errors=True)

    root = tree.root_node
    if root.descendant_count > MAX_NODES:
        return BashAnalysis(source=source, has_errors=True, budget_exhausted=True)

    has_errors = bool(root.has_error) or _has_missing(root)

    segments: list[Segment] = []
    if not has_errors:
        for node in QueryCursor(_cmd_query()).captures(root).get("c", []):
            argv, dynamic = _argv_of(node)
            if argv:
                segments.append(Segment(argv=argv, dynamic=dynamic))

    return BashAnalysis(
        source=source,
        segments=segments,
        redirects=_redirects_of(tree),
        heredocs=_heredocs_of(tree),
        has_errors=has_errors,
    )
