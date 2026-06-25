from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path

import pytest

from agent.code_intelligence.config import LspConfig, LspServerConfig
from agent.lsp.client import LspClient, LspClientError
from agent.lsp.transport import StdioLspTransport, LspTransportError


FAKE_SERVER = Path(__file__).parent.parent.parent / "fixtures" / "fake_lsp_server.py"


def _server_config(**kw) -> LspServerConfig:
    defaults = {
        "language": "python",
        "command": ("python3",),
        "args": (str(FAKE_SERVER),),
        "root_markers": ("pyproject.toml",),
        "initialize_timeout_ms": 5000,
        "request_timeout_ms": 5000,
    }
    defaults.update(kw)
    return LspServerConfig(**defaults)


def _lsp_config(**kw) -> LspConfig:
    defaults = {
        "servers": (),
        "max_diagnostics_per_file": 10,
        "max_references": 10,
        "max_workspace_symbols": 10,
    }
    defaults.update(kw)
    return LspConfig(**defaults)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    return tmp_path


def _make_client(workspace: Path, **kw) -> LspClient:
    return LspClient(
        server_config=_server_config(**kw),
        workspace_root=workspace,
        config=_lsp_config(),
    )


@pytest.mark.asyncio
async def test_full_lifecycle_spawn_init_shutdown(workspace: Path):
    """Spawn fake server, run initialize handshake, then shutdown cleanly."""
    client = _make_client(workspace)
    try:
        await client.ensure_initialized()
        assert client._initialized is True
        assert client._unhealthy is False
    finally:
        await client.shutdown()
        assert client._initialized is False


@pytest.mark.asyncio
async def test_definition_via_stdio(workspace: Path):
    target = workspace / "mod.py"
    target.write_text("def foo():\n    pass\n", encoding="utf-8")

    client = _make_client(workspace)
    try:
        locations = await client.definition(target, line=1, character=4)
        assert len(locations) == 1
        assert locations[0].path == str(target)
        assert locations[0].line == 0
        assert locations[0].character == 0
    finally:
        await client.shutdown()


@pytest.mark.asyncio
async def test_references_via_stdio(workspace: Path):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    client = _make_client(workspace)
    try:
        refs = await client.references(target, line=0, character=0)
        assert len(refs) == 1
        assert refs[0].path == str(target)
    finally:
        await client.shutdown()


@pytest.mark.asyncio
async def test_hover_via_stdio(workspace: Path):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    client = _make_client(workspace)
    try:
        hover_text = await client.hover(target, line=0, character=0)
        assert "hover:" in hover_text
    finally:
        await client.shutdown()


@pytest.mark.asyncio
async def test_document_symbols_via_stdio(workspace: Path):
    target = workspace / "mod.py"
    target.write_text("def foo():\n    pass\n", encoding="utf-8")

    client = _make_client(workspace)
    try:
        symbols = await client.document_symbols(target)
        assert len(symbols) == 1
        assert symbols[0]["name"] == "foo"
    finally:
        await client.shutdown()


@pytest.mark.asyncio
async def test_workspace_symbols_via_stdio(workspace: Path):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    client = _make_client(workspace)
    try:
        symbols = await client.workspace_symbols("test_query")
        assert len(symbols) == 1
        assert symbols[0]["name"] == "test_query"
    finally:
        await client.shutdown()


@pytest.mark.asyncio
async def test_diagnostics_via_stdio(workspace: Path):
    target = workspace / "mod.py"
    target.write_text("x = \n", encoding="utf-8")

    client = _make_client(workspace)
    try:
        diagnostics = await client.diagnostics(target)
        assert len(diagnostics) == 1
        assert "fake diagnostic" in diagnostics[0].message
        assert diagnostics[0].severity == "error"
    finally:
        await client.shutdown()


@pytest.mark.asyncio
async def test_didopen_triggers_published_diagnostics(workspace: Path):
    """After didOpen, fake server pushes publishDiagnostics; client captures them."""
    target = workspace / "mod.py"
    target.write_text("x = \n", encoding="utf-8")

    client = _make_client(workspace)
    try:
        # Ensure initialized + didOpen (sent by _ensure_document_open via definition).
        await client.definition(target, line=0, character=0)
        # Give the fake server a moment to push publishDiagnostics.
        await asyncio.sleep(0.1)
        published = client._published_diagnostics.get(str(target), [])
        assert len(published) == 1
        assert "fake published diagnostic" in published[0].message
    finally:
        await client.shutdown()


@pytest.mark.asyncio
async def test_initialize_timeout_raises_error(workspace: Path):
    """When initialize times out, the client raises an error."""
    client = _make_client(workspace, initialize_timeout_ms=1, request_timeout_ms=1)

    # The fake server reads with readline which is fast, but 1ms timeout
    # on the client side for the full initialize round-trip should trigger.
    try:
        with pytest.raises(LspClientError):
            await client.ensure_initialized()
        assert client._unhealthy is True or client._initialized is False
    finally:
        await client.shutdown()


@pytest.mark.asyncio
async def test_didchange_updates_version(workspace: Path):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    client = _make_client(workspace)
    try:
        await client.ensure_initialized()

        # Open the document via definition
        await client.definition(target, line=0, character=0)
        assert client._open_documents.get("mod.py") == 1

        # Modify file and notify
        target.write_text("x = 2\n", encoding="utf-8")
        await client.notify_document_changed(target)
        assert client._open_documents.get("mod.py") == 2
    finally:
        await client.shutdown()


@pytest.mark.asyncio
async def test_process_group_is_cleaned_on_shutdown():
    """Verify the subprocess is gone after shutdown."""
    workspace = Path("/tmp/test_stdio_ws")
    workspace.mkdir(exist_ok=True)
    (workspace / "pyproject.toml").write_text("", encoding="utf-8")

    client = _make_client(workspace)
    try:
        await client.ensure_initialized()
        transport = client.transport
        assert isinstance(transport, StdioLspTransport)
        proc = transport._process
        assert proc is not None
        assert proc.returncode is None
        pid = proc.pid

        await client.shutdown()

        # After shutdown, the process should be gone.
        assert transport._process is None
        try:
            os.kill(pid, 0)
            # Process might still exist as zombie for a moment; wait briefly.
            time.sleep(0.5)
            os.kill(pid, 0)
            pytest.fail(f"Process {pid} still alive after shutdown")
        except ProcessLookupError:
            pass  # expected — process is gone
    except Exception:
        await client.shutdown()
        raise


@pytest.mark.asyncio
async def test_multiple_requests_on_same_client(workspace: Path):
    """Run several requests sequentially on one client without re-init."""
    target = workspace / "mod.py"
    target.write_text("def foo():\n    pass\n", encoding="utf-8")

    client = _make_client(workspace)
    try:
        locs = await client.definition(target, line=0, character=4)
        assert len(locs) == 1

        refs = await client.references(target, line=0, character=0)
        assert len(refs) == 1

        hov = await client.hover(target, line=0, character=4)
        assert "hover:" in hov
    finally:
        await client.shutdown()
