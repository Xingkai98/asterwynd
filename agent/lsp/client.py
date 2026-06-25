from __future__ import annotations

import asyncio
import atexit
import logging
import os
import signal
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("myagent.lsp")

from agent.code_intelligence.config import LspConfig, LspServerConfig
from agent.lsp.transport import (
    FakeLspTransport,
    LspTransport,
    LspTransportClosed,
    LspTransportError,
)


@dataclass
class LspLocation:
    path: str
    line: int  # 0-based LSP line
    character: int  # 0-based LSP character

    def format(self, workspace_root: Path) -> str:
        try:
            rel = Path(self.path).relative_to(workspace_root)
            display = rel.as_posix()
        except ValueError:
            display = self.path
        return f"{display}:{self.line + 1}:{self.character + 1}"


@dataclass
class LspDiagnostic:
    path: str
    line: int
    character: int
    end_line: int
    end_character: int
    severity: str
    message: str

    def format(self, workspace_root: Path) -> str:
        try:
            rel = Path(self.path).relative_to(workspace_root)
            display = rel.as_posix()
        except ValueError:
            display = self.path
        return f"{display}:{self.line + 1}:{self.character + 1} [{self.severity}] {self.message}"


class LspClientError(Exception):
    """Raised when an LSP capability is unavailable."""


class LspClient:
    """A client for one (language, workspace_root) LSP server instance.

    Lazy-starts the server on first use, manages initialize handshake,
    per-file document sync, and provides read-only query methods. The
    transport is injected so tests can substitute FakeLspTransport.
    """

    def __init__(
        self,
        server_config: LspServerConfig,
        workspace_root: Path,
        config: LspConfig,
        transport: LspTransport | None = None,
    ):
        self.server_config = server_config
        self.workspace_root = workspace_root.resolve()
        self.config = config
        self._transport: LspTransport = transport or _make_stdio_transport(server_config)
        self._initialized = False
        self._unhealthy = False
        self._open_documents: dict[str, int] = {}  # path -> version
        self._published_diagnostics: dict[str, list[LspDiagnostic]] = {}
        self._lock = asyncio.Lock()
        self._registered_atexit = False
        # Register publishDiagnostics handler eagerly so server-pushed
        # diagnostics received right after didOpen are captured even
        # before any explicit diagnostics() call.
        self._transport.register_notification_handler(
            "textDocument/publishDiagnostics", self._handle_publish_diagnostics
        )

    @property
    def language(self) -> str:
        return self.server_config.language

    @property
    def transport(self) -> LspTransport:
        return self._transport

    async def ensure_initialized(self) -> None:
        if self._initialized and not self._unhealthy:
            return
        async with self._lock:
            if self._initialized and not self._unhealthy:
                return
            await self._transport.start()
            if not self._registered_atexit:
                atexit.register(self._atexit_shutdown)
                self._registered_atexit = True
            init_result = await self._send_request(
                "initialize",
                {
                    "processId": os.getpid(),
                    "rootUri": self.workspace_root.as_uri(),
                    "capabilities": {
                        "textDocument": {
                            "synchronization": {
                                "didOpen": True,
                                "didChange": True,
                                "didClose": True,
                            },
                            "publishDiagnostics": {"relatedInformation": False},
                        },
                        "workspace": {
                            "diagnostics": {"refreshSupport": False},
                        },
                    },
                },
                timeout_ms=self.server_config.initialize_timeout_ms,
            )
            self._initialized = True
            self._unhealthy = False
            await self._transport.send_notification("initialized", {})

    def _handle_publish_diagnostics(self, params: Any | None) -> None:
        if not isinstance(params, dict):
            return
        uri = params.get("uri")
        if not isinstance(uri, str):
            return
        path = _uri_to_path(uri)
        diagnostics_raw = params.get("diagnostics") or []
        if not isinstance(diagnostics_raw, list):
            return
        diagnostics: list[LspDiagnostic] = []
        for raw in diagnostics_raw:
            if not isinstance(raw, dict):
                continue
            diag = _parse_diagnostic(raw, path)
            if diag is not None:
                diagnostics.append(diag)
        self._published_diagnostics[path] = diagnostics

    async def shutdown(self) -> None:
        async with self._lock:
            try:
                if self._initialized and not self._unhealthy:
                    try:
                        await asyncio.wait_for(
                            self._transport.send_request(
                                "shutdown", None,
                                timeout_ms=self.server_config.request_timeout_ms,
                            ),
                            timeout=self.server_config.request_timeout_ms / 1000.0,
                        )
                    except (LspTransportError, asyncio.TimeoutError):
                        pass
                    try:
                        await self._transport.send_notification("exit", None)
                    except LspTransportError:
                        pass
            finally:
                await self._transport.close()
                self._initialized = False
                self._unhealthy = False
                self._open_documents.clear()
                self._published_diagnostics.clear()

    def _atexit_shutdown(self) -> None:
        """Sync atexit handler; best-effort cleanup without asyncio loop."""
        try:
            transport = self._transport
            if isinstance(transport, StdioLspTransportShim):
                return
            # Try to kill the process group directly if it's a stdio transport.
            proc = getattr(transport, "_process", None)
            if proc is not None and proc.returncode is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    try:
                        proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass

    async def _ensure_document_open(self, path: Path) -> None:
        rel = self._workspace_relative(path)
        uri = path.as_uri()
        if rel in self._open_documents:
            return
        text = self._read_text(path)
        version = 1
        self._open_documents[rel] = version
        await self._transport.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": self.server_config.language,
                    "version": version,
                    "text": text,
                }
            },
        )

    async def notify_document_changed(self, path: Path) -> None:
        """Called by Write/Edit after a successful modification."""
        if self._unhealthy or not self._initialized:
            # If not initialized yet, the next query will didOpen with fresh content.
            return
        rel = self._workspace_relative(path)
        text = self._read_text(path)
        if rel in self._open_documents:
            version = self._open_documents[rel] + 1
            self._open_documents[rel] = version
            await self._transport.send_notification(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": path.as_uri(), "version": version},
                    "contentChanges": [{"text": text}],
                },
            )
        else:
            # Document was never opened; open it now with the latest content.
            await self._ensure_document_open(path)

    def _workspace_relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.workspace_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise LspClientError(f"Cannot read {path}: {exc}") from exc

    async def _send_request(
        self, method: str, params: Any | None, *, timeout_ms: int
    ) -> Any:
        try:
            return await self._transport.send_request(
                method, params, timeout_ms=timeout_ms
            )
        except LspTransportClosed as exc:
            self._unhealthy = True
            raise LspClientError(str(exc)) from exc
        except LspTransportError as exc:
            # Mark unhealthy on timeout so next call retries initialize.
            if "timed out" in str(exc).lower():
                self._unhealthy = True
            raise LspClientError(str(exc)) from exc

    async def definition(self, path: Path, line: int, character: int) -> list[LspLocation]:
        await self.ensure_initialized()
        await self._ensure_document_open(path)
        result = await self._send_request(
            "textDocument/definition",
            _text_document_position(path, line, character),
            timeout_ms=self.server_config.request_timeout_ms,
        )
        return _parse_locations(result)

    async def references(self, path: Path, line: int, character: int) -> list[LspLocation]:
        await self.ensure_initialized()
        await self._ensure_document_open(path)
        result = await self._send_request(
            "textDocument/references",
            {
                "textDocument": {"uri": path.as_uri()},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": True},
            },
            timeout_ms=self.server_config.request_timeout_ms,
        )
        locations = _parse_locations(result)
        return locations[: self.config.max_references]

    async def hover(self, path: Path, line: int, character: int) -> str:
        await self.ensure_initialized()
        await self._ensure_document_open(path)
        result = await self._send_request(
            "textDocument/hover",
            _text_document_position(path, line, character),
            timeout_ms=self.server_config.request_timeout_ms,
        )
        return _parse_hover(result)

    async def document_symbols(self, path: Path) -> list[dict[str, Any]]:
        await self.ensure_initialized()
        await self._ensure_document_open(path)
        result = await self._send_request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": path.as_uri()}},
            timeout_ms=self.server_config.request_timeout_ms,
        )
        if not isinstance(result, list):
            return []
        return result

    async def workspace_symbols(self, query: str) -> list[dict[str, Any]]:
        await self.ensure_initialized()
        result = await self._send_request(
            "workspace/symbol",
            {"query": query},
            timeout_ms=self.server_config.request_timeout_ms,
        )
        if not isinstance(result, list):
            return []
        return result[: self.config.max_workspace_symbols]

    async def diagnostics(self, path: Path) -> list[LspDiagnostic]:
        await self.ensure_initialized()
        await self._ensure_document_open(path)
        # Prefer pull diagnostics if available; fall back to published.
        try:
            result = await self._send_request(
                "textDocument/diagnostic",
                {"textDocument": {"uri": path.as_uri()}},
                timeout_ms=self.server_config.request_timeout_ms,
            )
            if isinstance(result, dict) and isinstance(result.get("items"), list):
                diagnostics: list[LspDiagnostic] = []
                for raw in result["items"]:
                    if not isinstance(raw, dict):
                        continue
                    diag = _parse_diagnostic(raw, str(path))
                    if diag is not None:
                        diagnostics.append(diag)
                return diagnostics[: self.config.max_diagnostics_per_file]
        except LspClientError:
            pass
        # Fall back to published diagnostics (from didOpen/didChange notifications).
        published = self._published_diagnostics.get(str(path), [])
        return published[: self.config.max_diagnostics_per_file]


class LspClientManager:
    """Cache of LspClient instances keyed by (language, workspace_root).

    Created per agent run; close() shuts down all clients. Use
    get_or_create to lazily start a server for a language.
    """

    def __init__(
        self,
        config: LspConfig,
        workspace_root: Path,
        transport_factory: Callable[[LspServerConfig, Path], LspTransport] | None = None,
    ):
        self.config = config
        self.workspace_root = workspace_root.resolve()
        self._clients: dict[tuple[str, str], LspClient] = {}
        self._lock = threading.Lock()
        self._transport_factory = transport_factory

    def has_server_for(self, language: str) -> bool:
        return self.config.server_for(language) is not None

    def get_client_for_file(self, path: Path, language: str) -> LspClient | None:
        server = self.config.server_for(language)
        if server is None:
            return None
        effective_root = _resolve_effective_root(
            path=path,
            workspace_root=self.workspace_root,
            root_markers=server.root_markers,
        )
        key = (server.language.lower(), str(effective_root))
        with self._lock:
            client = self._clients.get(key)
            if client is None:
                transport = None
                if self._transport_factory is not None:
                    transport = self._transport_factory(server, effective_root)
                client = LspClient(
                    server_config=server,
                    workspace_root=effective_root,
                    config=self.config,
                    transport=transport,
                )
                self._clients[key] = client
            return client

    async def shutdown_all(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            try:
                await client.shutdown()
            except Exception:
                pass


class StdioLspTransportShim:
    """Marker class used by atexit logic to detect stdio transports.

    The real stdio transport is agent.lsp.transport.StdioLspTransport;
    atexit checks isinstance via duck-typing on _process instead, so
    this shim is only a placeholder for future extension.
    """


def _make_stdio_transport(server: LspServerConfig) -> LspTransport:
    from agent.lsp.transport import StdioLspTransport

    return StdioLspTransport(server.command, server.args)


def _resolve_effective_root(
    path: Path,
    workspace_root: Path,
    root_markers: tuple[str, ...],
) -> Path:
    """Walk up from path looking for root_marker files.

    Returns the directory containing the first marker found within
    workspace_root. If a marker is found outside workspace_root, falls
    back to workspace_root and logs a warning. If no marker is found at
    all, returns workspace_root.
    """
    workspace_root = workspace_root.resolve()
    current = path.resolve().parent

    while True:
        for marker in root_markers:
            if current.joinpath(marker).exists():
                try:
                    current.relative_to(workspace_root)
                except ValueError:
                    logger.warning(
                        "root_marker %r found at %s outside workspace %s; "
                        "falling back to workspace root",
                        marker, current, workspace_root,
                    )
                    return workspace_root
                return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    return workspace_root


def _text_document_position(path: Path, line: int, character: int) -> dict[str, Any]:
    return {
        "textDocument": {"uri": path.as_uri()},
        "position": {"line": line, "character": character},
    }


def _parse_locations(result: Any) -> list[LspLocation]:
    if result is None:
        return []
    if isinstance(result, dict):
        result = [result]
    if not isinstance(result, list):
        return []
    locations: list[LspLocation] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        loc = _parse_location(item)
        if loc is not None:
            locations.append(loc)
    return locations


def _parse_location(item: dict[str, Any]) -> LspLocation | None:
    if "uri" not in item or "range" not in item:
        return None
    range_ = item.get("range") or {}
    start = range_.get("start") or {}
    path = _uri_to_path(item["uri"])
    return LspLocation(
        path=path,
        line=int(start.get("line", 0)),
        character=int(start.get("character", 0)),
    )


def _parse_hover(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, dict):
        contents = result.get("contents")
        if isinstance(contents, dict):
            value = contents.get("value")
            if isinstance(value, str):
                return value
        if isinstance(contents, list):
            parts: list[str] = []
            for item in contents:
                if isinstance(item, dict):
                    value = item.get("value")
                    if isinstance(value, str):
                        parts.append(value)
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        if isinstance(contents, str):
            return contents
    return ""


def _parse_diagnostic(raw: dict[str, Any], path: str) -> LspDiagnostic | None:
    range_ = raw.get("range") or {}
    start = range_.get("start") or {}
    end = range_.get("end") or {}
    severity_code = raw.get("severity", 3)
    severity_names = {
        1: "error",
        2: "warning",
        3: "info",
        4: "hint",
    }
    severity = severity_names.get(int(severity_code), "info")
    message = str(raw.get("message", ""))
    return LspDiagnostic(
        path=path,
        line=int(start.get("line", 0)),
        character=int(start.get("character", 0)),
        end_line=int(end.get("line", 0)),
        end_character=int(end.get("character", 0)),
        severity=severity,
        message=message,
    )


def _uri_to_path(uri: str) -> str:
    if uri.startswith("file://"):
        return uri[len("file://"):]
    return uri


__all__ = [
    "FakeLspTransport",
    "LspClient",
    "LspClientError",
    "LspClientManager",
    "LspDiagnostic",
    "LspLocation",
]
