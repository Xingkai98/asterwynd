from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agent.code_intelligence.config import CodeIntelligenceConfig
from agent.code_intelligence.models import FileSummary
from agent.code_intelligence.python_symbols import extract_python_summary
from agent.code_intelligence.tree_sitter_symbols import TreeSitterExtractor


class SymbolExtractor(Protocol):
    def supports(self, path: Path, language: str) -> bool:
        ...

    def extract(self, path: Path, rel_path: str, language: str) -> FileSummary:
        ...


class PythonAstExtractor:
    def supports(self, path: Path, language: str) -> bool:
        return language == "python"

    def extract(self, path: Path, rel_path: str, language: str) -> FileSummary:
        return extract_python_summary(path, rel_path)


def build_default_extractors(
    config: CodeIntelligenceConfig | None = None,
) -> tuple[SymbolExtractor, ...]:
    return (PythonAstExtractor(), TreeSitterExtractor(config=config))


DEFAULT_EXTRACTORS: tuple[SymbolExtractor, ...] = build_default_extractors()
