from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_TREE_SITTER_MAX_FILE_BYTES = 262144

DEFAULT_LSP_INITIALIZE_TIMEOUT_MS = 5000
DEFAULT_LSP_REQUEST_TIMEOUT_MS = 3000
DEFAULT_LSP_MAX_DIAGNOSTICS_PER_FILE = 50
DEFAULT_LSP_MAX_REFERENCES = 100
DEFAULT_LSP_MAX_WORKSPACE_SYMBOLS = 100
DEFAULT_LSP_DIAGNOSTIC_MESSAGE_MAX_CHARS = 200


@dataclass(frozen=True)
class LspServerConfig:
    language: str
    command: tuple[str, ...]
    args: tuple[str, ...] = ()
    root_markers: tuple[str, ...] = ("pyproject.toml",)
    initialize_timeout_ms: int = DEFAULT_LSP_INITIALIZE_TIMEOUT_MS
    request_timeout_ms: int = DEFAULT_LSP_REQUEST_TIMEOUT_MS
    enabled: bool = True


@dataclass(frozen=True)
class LspConfig:
    servers: tuple[LspServerConfig, ...] = ()
    default_request_timeout_ms: int = DEFAULT_LSP_REQUEST_TIMEOUT_MS
    max_diagnostics_per_file: int = DEFAULT_LSP_MAX_DIAGNOSTICS_PER_FILE
    max_references: int = DEFAULT_LSP_MAX_REFERENCES
    max_workspace_symbols: int = DEFAULT_LSP_MAX_WORKSPACE_SYMBOLS
    diagnostic_message_max_chars: int = DEFAULT_LSP_DIAGNOSTIC_MESSAGE_MAX_CHARS

    def server_for(self, language: str) -> LspServerConfig | None:
        normalized = language.lower()
        for server in self.servers:
            if server.enabled and server.language.lower() == normalized:
                return server
        return None


@dataclass(frozen=True)
class CodeIntelligenceConfig:
    tree_sitter_max_file_bytes: int = DEFAULT_TREE_SITTER_MAX_FILE_BYTES
    lsp: LspConfig = field(default_factory=LspConfig)
