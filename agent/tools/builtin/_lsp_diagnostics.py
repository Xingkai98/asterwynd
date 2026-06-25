from __future__ import annotations

from pathlib import Path

from agent.lsp.client import LspClientError, LspClientManager


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


async def collect_diagnostics_feedback(
    lsp_manager: LspClientManager | None,
    path: Path,
) -> str:
    """Run LSP diagnostics for `path` and return a formatted summary.

    Returns an empty string when:
    - no LSP manager is configured
    - no server is configured for the file's language
    - the diagnostics call fails for any reason (graceful degradation)

    Write/Edit append the returned string to their tool result. Callers
    must NOT fail the underlying write when this function returns empty
    or errors.
    """
    if lsp_manager is None:
        return ""
    language = _language_for(path)
    if language is None:
        return ""
    if not lsp_manager.has_server_for(language):
        return ""
    client = lsp_manager.get_client_for_file(path, language)
    if client is None:
        return ""
    try:
        # Notify server of the change so diagnostics reflect the new content.
        await client.notify_document_changed(path)
        diagnostics = await client.diagnostics(path)
    except LspClientError:
        return ""
    except Exception:
        return ""
    if not diagnostics:
        return ""
    root = lsp_manager.workspace_root
    lines = [d.format(root) for d in diagnostics]
    header = f"\nLSP diagnostics ({len(diagnostics)}):"
    return header + "\n" + "\n".join(lines)


__all__ = ["collect_diagnostics_feedback"]
