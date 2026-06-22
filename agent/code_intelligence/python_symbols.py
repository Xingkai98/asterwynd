from __future__ import annotations

import ast
from pathlib import Path

from agent.code_intelligence.models import FileSummary, ImportSummary, Symbol


def extract_python_summary(path: Path, rel_path: str) -> FileSummary:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.count("\n") + (0 if text == "" else 1)
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError as exc:
        return FileSummary(
            path=rel_path,
            language="python",
            category="source",
            lines=lines,
            bytes=path.stat().st_size,
            parse_error=f"{exc.msg} at line {exc.lineno}",
        )

    imports: list[ImportSummary] = []
    symbols: list[Symbol] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(
                ImportSummary(
                    name=f"{alias.name} as {alias.asname}" if alias.asname else alias.name,
                    line=node.lineno,
                )
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            imports.extend(
                ImportSummary(
                    name=f"{module}.{alias.name}" if module else alias.name,
                    line=node.lineno,
                )
                for alias in node.names
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(Symbol(name=node.name, kind="function", line=node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol(name=node.name, kind="class", line=node.lineno))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(
                        Symbol(
                            name=f"{node.name}.{child.name}",
                            kind="method",
                            line=child.lineno,
                        )
                    )

    return FileSummary(
        path=rel_path,
        language="python",
        category="source",
        lines=lines,
        bytes=path.stat().st_size,
        symbols=symbols,
        imports=imports,
    )
