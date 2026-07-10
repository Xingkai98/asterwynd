from __future__ import annotations

from pathlib import Path

from agent.lsp.client import LspClientError, LspClientManager
from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import WORKSPACE_READ_PERMISSION
from agent.workspace_policy import WorkspacePolicy


_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}


def _language_for(path: Path) -> str | None:
    return _LANGUAGE_BY_SUFFIX.get(path.suffix.lower())


def _format_no_server(language: str | None) -> str:
    if language is None:
        return "Error: no LSP server configured for this file type"
    return f"Error: no LSP server configured for language {language!r}"


def _resolve_and_check(
    path: str, policy: WorkspacePolicy
) -> tuple[Path | None, str | None]:
    """Resolve path under workspace and check denied. Returns (resolved, error)."""
    try:
        resolved = policy.assert_read_allowed(path)
    except PermissionError as exc:
        return None, f"Error: {exc}"
    if not resolved.exists():
        return None, f"Error: file not found: {path}"
    if not resolved.is_file():
        return None, f"Error: not a file: {path}"
    return resolved, None


def _line_col(params: dict, line_default: int = 0, char_default: int = 0) -> tuple[int, int]:
    line = int(params.get("line", line_default))
    col = int(params.get("character", char_default))
    # Agent-facing API uses 1-based line / 1-based column to match error
    # message conventions; convert to 0-based LSP coordinates.
    return max(line - 1, 0), max(col - 1, 0)


@tool_parameters(
    name="LspDefinition",
    description=(
        "Find where a symbol at the given position is defined. Returns "
        "file:line:col locations. Line and character are 1-based."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path in the workspace"},
            "line": {"type": "number", "description": "1-based line number"},
            "character": {"type": "number", "description": "1-based column number"},
        },
        "required": ["path", "line", "character"],
    },
)
class LspDefinitionTool(Tool):
    read_only = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        lsp_manager: LspClientManager | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.lsp_manager = lsp_manager

    async def execute(self, path: str, line: int, character: int, **kwargs) -> str:
        resolved, err = _resolve_and_check(path, self.policy)
        if err is not None:
            return err
        assert resolved is not None

        language = _language_for(resolved)
        if self.lsp_manager is None or not self.lsp_manager.has_server_for(language or ""):
            return _format_no_server(language)
        client = self.lsp_manager.get_client_for_file(resolved, language or "")
        if client is None:
            return _format_no_server(language)
        try:
            lsp_line, lsp_col = _line_col({"line": line, "character": character})
            locations = await client.definition(resolved, lsp_line, lsp_col)
        except LspClientError as exc:
            return f"Error: {exc}"
        if not locations:
            return "(no definition found)"
        root = self.lsp_manager.workspace_root
        return "\n".join(loc.format(root) for loc in locations)


@tool_parameters(
    name="LspReferences",
    description=(
        "Find all references to the symbol at the given position. Returns "
        "file:line:col locations. Line and character are 1-based."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path in the workspace"},
            "line": {"type": "number", "description": "1-based line number"},
            "character": {"type": "number", "description": "1-based column number"},
        },
        "required": ["path", "line", "character"],
    },
)
class LspReferencesTool(Tool):
    read_only = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        lsp_manager: LspClientManager | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.lsp_manager = lsp_manager

    async def execute(self, path: str, line: int, character: int, **kwargs) -> str:
        resolved, err = _resolve_and_check(path, self.policy)
        if err is not None:
            return err
        assert resolved is not None

        language = _language_for(resolved)
        if self.lsp_manager is None or not self.lsp_manager.has_server_for(language or ""):
            return _format_no_server(language)
        client = self.lsp_manager.get_client_for_file(resolved, language or "")
        if client is None:
            return _format_no_server(language)
        try:
            lsp_line, lsp_col = _line_col({"line": line, "character": character})
            locations = await client.references(resolved, lsp_line, lsp_col)
        except LspClientError as exc:
            return f"Error: {exc}"
        if not locations:
            return "(no references found)"
        root = self.lsp_manager.workspace_root
        return "\n".join(loc.format(root) for loc in locations)


@tool_parameters(
    name="LspHover",
    description=(
        "Get hover information (type signature, docs) for the symbol at "
        "the given position. Line and character are 1-based."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path in the workspace"},
            "line": {"type": "number", "description": "1-based line number"},
            "character": {"type": "number", "description": "1-based column number"},
        },
        "required": ["path", "line", "character"],
    },
)
class LspHoverTool(Tool):
    read_only = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        lsp_manager: LspClientManager | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.lsp_manager = lsp_manager

    async def execute(self, path: str, line: int, character: int, **kwargs) -> str:
        resolved, err = _resolve_and_check(path, self.policy)
        if err is not None:
            return err
        assert resolved is not None

        language = _language_for(resolved)
        if self.lsp_manager is None or not self.lsp_manager.has_server_for(language or ""):
            return _format_no_server(language)
        client = self.lsp_manager.get_client_for_file(resolved, language or "")
        if client is None:
            return _format_no_server(language)
        try:
            lsp_line, lsp_col = _line_col({"line": line, "character": character})
            hover = await client.hover(resolved, lsp_line, lsp_col)
        except LspClientError as exc:
            return f"Error: {exc}"
        if not hover:
            return "(no hover information)"
        return hover


@tool_parameters(
    name="LspDocumentSymbols",
    description=(
        "List symbols defined in a file (classes, functions, methods, "
        "variables). Returns one symbol per line with kind and location."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path in the workspace"},
        },
        "required": ["path"],
    },
)
class LspDocumentSymbolsTool(Tool):
    read_only = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        lsp_manager: LspClientManager | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.lsp_manager = lsp_manager

    async def execute(self, path: str, **kwargs) -> str:
        resolved, err = _resolve_and_check(path, self.policy)
        if err is not None:
            return err
        assert resolved is not None

        language = _language_for(resolved)
        if self.lsp_manager is None or not self.lsp_manager.has_server_for(language or ""):
            return _format_no_server(language)
        client = self.lsp_manager.get_client_for_file(resolved, language or "")
        if client is None:
            return _format_no_server(language)
        try:
            symbols = await client.document_symbols(resolved)
        except LspClientError as exc:
            return f"Error: {exc}"
        if not symbols:
            return "(no symbols found)"
        root = self.lsp_manager.workspace_root
        lines: list[str] = []
        for sym in symbols:
            name = sym.get("name", "<anonymous>")
            kind = _symbol_kind_name(sym.get("kind", 0))
            location = sym.get("location") or {}
            start = (location.get("range") or {}).get("start") or {}
            loc_line = int(start.get("line", 0)) + 1
            loc_col = int(start.get("character", 0)) + 1
            lines.append(f"{kind} {name} @ line {loc_line}:{loc_col}")
        return "\n".join(lines)


@tool_parameters(
    name="LspWorkspaceSymbols",
    description=(
        "Search symbols across the workspace by name. Returns matching "
        "symbols with kind and location."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Symbol name query"},
        },
        "required": ["query"],
    },
)
class LspWorkspaceSymbolsTool(Tool):
    read_only = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        lsp_manager: LspClientManager | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.lsp_manager = lsp_manager

    async def execute(self, query: str, **kwargs) -> str:
        if self.lsp_manager is None or not self.lsp_manager.config.servers:
            return "Error: no LSP servers configured"
        # Use the first configured server for workspace symbol search.
        first_server = self.lsp_manager.config.servers[0]
        client = self.lsp_manager.get_client_for_file(
            self.policy.workspace_root, first_server.language
        )
        if client is None:
            return _format_no_server(first_server.language)
        try:
            symbols = await client.workspace_symbols(query)
        except LspClientError as exc:
            return f"Error: {exc}"
        if not symbols:
            return "(no symbols found)"
        root = self.lsp_manager.workspace_root
        lines: list[str] = []
        for sym in symbols:
            name = sym.get("name", "<anonymous>")
            kind = _symbol_kind_name(sym.get("kind", 0))
            location = sym.get("location") or {}
            uri = location.get("uri", "")
            start = (location.get("range") or {}).get("start") or {}
            loc_line = int(start.get("line", 0)) + 1
            try:
                path_str = str(Path(uri[len("file://"):] if uri.startswith("file://") else uri))
                rel = Path(path_str).relative_to(root)
                display = rel.as_posix()
            except ValueError:
                display = uri
            lines.append(f"{display}:{loc_line} {kind} {name}")
        return "\n".join(lines)


@tool_parameters(
    name="LspDiagnostics",
    description=(
        "Get LSP diagnostics (errors, warnings) for a file. Returns one "
        "diagnostic per line: file:line:col [severity] message."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path in the workspace"},
        },
        "required": ["path"],
    },
)
class LspDiagnosticsTool(Tool):
    read_only = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        lsp_manager: LspClientManager | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.lsp_manager = lsp_manager

    async def execute(self, path: str, **kwargs) -> str:
        resolved, err = _resolve_and_check(path, self.policy)
        if err is not None:
            return err
        assert resolved is not None

        language = _language_for(resolved)
        if self.lsp_manager is None or not self.lsp_manager.has_server_for(language or ""):
            return _format_no_server(language)
        client = self.lsp_manager.get_client_for_file(resolved, language or "")
        if client is None:
            return _format_no_server(language)
        try:
            diagnostics = await client.diagnostics(resolved)
        except LspClientError as exc:
            return f"Error: {exc}"
        if not diagnostics:
            return "(no diagnostics)"
        root = self.lsp_manager.workspace_root
        return "\n".join(d.format(root) for d in diagnostics)


_SYMBOL_KINDS = {
    1: "File", 2: "Module", 3: "Namespace", 4: "Package", 5: "Class",
    6: "Method", 7: "Property", 8: "Field", 9: "Constructor", 10: "Enum",
    11: "Interface", 12: "Function", 13: "Variable", 14: "Constant",
    15: "String", 16: "Number", 17: "Boolean", 18: "Array", 19: "Object",
    20: "Key", 21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
    25: "Operator", 26: "TypeParameter",
}


def _symbol_kind_name(kind: int) -> str:
    return _SYMBOL_KINDS.get(int(kind), "Symbol")


__all__ = [
    "LspDefinitionTool",
    "LspDocumentSymbolsTool",
    "LspDiagnosticsTool",
    "LspHoverTool",
    "LspReferencesTool",
    "LspWorkspaceSymbolsTool",
]
