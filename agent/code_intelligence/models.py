from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    line: int
    source: str = "python-ast"


@dataclass(frozen=True)
class ImportSummary:
    name: str
    line: int


@dataclass(frozen=True)
class FileSummary:
    path: str
    language: str
    category: str
    lines: int
    bytes: int
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportSummary] = field(default_factory=list)
    parse_error: str | None = None


@dataclass(frozen=True)
class RepoMap:
    root: str
    files: list[FileSummary]
    scanned_files: int
    skipped_files: int = 0
    truncated: bool = False
    max_files: int = 0
