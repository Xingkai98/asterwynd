from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from agent.code_intelligence.config import CodeIntelligenceConfig
from agent.code_intelligence.extractors import build_default_extractors, SymbolExtractor
from agent.code_intelligence.models import FileSummary, RepoMap, Symbol
from agent.workspace_policy import WorkspacePolicy


DEFAULT_IGNORE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".md": "markdown",
    ".rst": "rst",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".ini": "ini",
    ".cfg": "ini",
}

SOURCE_LANGUAGES = {
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
    "kotlin",
    "c",
    "cpp",
}

DOC_LANGUAGES = {"markdown", "rst"}
CONFIG_LANGUAGES = {"toml", "yaml", "json", "ini"}


def build_repo_map(
    *,
    policy: WorkspacePolicy | None = None,
    path: str = ".",
    ignore_patterns: tuple[str, ...] = (),
    max_files: int = 200,
    extractors: tuple[SymbolExtractor, ...] | None = None,
    code_intelligence_config: CodeIntelligenceConfig | None = None,
) -> RepoMap:
    policy = policy or WorkspacePolicy()
    extractors = extractors or build_default_extractors(code_intelligence_config)
    root = policy.assert_read_allowed(path)
    if not root.exists():
        raise FileNotFoundError(f"path not found: {path}")

    files: list[FileSummary] = []
    scanned_files = 0
    skipped_files = 0
    truncated = False
    candidates = [root] if root.is_file() else _iter_files(root, policy, ignore_patterns)

    for file_path in candidates:
        if len(files) >= max_files:
            truncated = True
            break
        try:
            policy.assert_read_allowed(file_path)
        except PermissionError:
            skipped_files += 1
            continue
        if not _is_supported_file(file_path):
            skipped_files += 1
            continue

        scanned_files += 1
        rel_path = policy.relative_path(file_path)
        files.append(_summarize_file(file_path, rel_path, extractors))

    return RepoMap(
        root=policy.relative_path(root) if root != policy.workspace_root else ".",
        files=files,
        scanned_files=scanned_files,
        skipped_files=skipped_files,
        truncated=truncated,
        max_files=max_files,
    )


def search_symbols(repo_map: RepoMap, query: str = "", max_results: int = 50) -> list[tuple[FileSummary, Symbol]]:
    needle = query.lower()
    results: list[tuple[FileSummary, Symbol]] = []
    for file_summary in repo_map.files:
        for symbol in file_summary.symbols:
            if not needle or needle in symbol.name.lower():
                results.append((file_summary, symbol))
                if len(results) >= max_results:
                    return results
    return results


def format_repo_map(repo_map: RepoMap, *, max_symbols_per_file: int = 12) -> str:
    if not repo_map.files:
        return "(no supported files found)"

    lines = [
        f"Repo map: {repo_map.root}",
        f"Files: {len(repo_map.files)} shown"
        + (f" (truncated at {repo_map.max_files})" if repo_map.truncated else ""),
    ]
    for entry in repo_map.files:
        lines.append(
            f"- {entry.path} [{entry.language} {entry.category}, {entry.lines} lines]"
        )
        for symbol in entry.symbols[:max_symbols_per_file]:
            suffix = "" if symbol.source == "python-ast" else f" [{symbol.source}]"
            lines.append(f"  - {symbol.kind} {symbol.name}:{symbol.line}{suffix}")
        if len(entry.symbols) > max_symbols_per_file:
            remaining = len(entry.symbols) - max_symbols_per_file
            lines.append(f"  - ... {remaining} more symbols")
        if entry.parse_error:
            lines.append(f"  - parse_error: {entry.parse_error}")
    if repo_map.truncated:
        lines.append(f"... truncated, showing first {repo_map.max_files} files")
    return "\n".join(lines)


def _iter_files(root: Path, policy: WorkspacePolicy, ignore_patterns: tuple[str, ...]):
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames)
            if not _should_ignore(current / dirname, policy, ignore_patterns)
        ]
        for filename in sorted(filenames):
            yield current / filename


def _should_ignore(path: Path, policy: WorkspacePolicy, ignore_patterns: tuple[str, ...]) -> bool:
    if path.name in DEFAULT_IGNORE_DIRS:
        return True
    try:
        rel = policy.relative_path(path)
        if policy.is_denied(path):
            return True
    except PermissionError:
        return True
    return any(
        fnmatch.fnmatchcase(path.name, pattern)
        or fnmatch.fnmatchcase(rel, pattern)
        or fnmatch.fnmatchcase(rel, pattern.strip("/"))
        for pattern in ignore_patterns
    )


def _is_supported_file(path: Path) -> bool:
    return path.suffix.lower() in LANGUAGE_BY_SUFFIX


def _summarize_file(
    path: Path,
    rel_path: str,
    extractors: tuple[SymbolExtractor, ...],
) -> FileSummary:
    language = LANGUAGE_BY_SUFFIX[path.suffix.lower()]
    for extractor in extractors:
        if extractor.supports(path, language):
            summary = extractor.extract(path, rel_path, language)
            return FileSummary(
                path=summary.path,
                language=summary.language,
                category=_category_for_path(rel_path, summary.language),
                lines=summary.lines,
                bytes=summary.bytes,
                symbols=summary.symbols,
                imports=summary.imports,
                parse_error=summary.parse_error,
            )

    return _summarize_file_without_symbols(path, rel_path, language)


def _summarize_file_without_symbols(
    path: Path,
    rel_path: str,
    language: str,
) -> FileSummary:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.count("\n") + (0 if text == "" else 1)
    return FileSummary(
        path=rel_path,
        language=language,
        category=_category_for_path(rel_path, language),
        lines=lines,
        bytes=path.stat().st_size,
    )


def _category_for_path(rel_path: str, language: str) -> str:
    parts = rel_path.split("/")
    name = parts[-1].lower()
    if (
        "tests" in parts
        or "test" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.ts")
        or name.endswith(".spec.ts")
    ):
        return "test"
    if language in DOC_LANGUAGES:
        return "docs"
    if language in CONFIG_LANGUAGES:
        return "config"
    if language in SOURCE_LANGUAGES:
        return "source"
    return "other"
