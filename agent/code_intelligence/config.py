from __future__ import annotations

from dataclasses import dataclass


DEFAULT_TREE_SITTER_MAX_FILE_BYTES = 262144


@dataclass(frozen=True)
class CodeIntelligenceConfig:
    tree_sitter_max_file_bytes: int = DEFAULT_TREE_SITTER_MAX_FILE_BYTES
