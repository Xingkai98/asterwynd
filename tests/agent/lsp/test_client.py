from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.code_intelligence.config import LspConfig, LspServerConfig
from agent.lsp.client import (
    LspClient,
    LspClientError,
    LspClientManager,
)
from agent.lsp.transport import (
    FakeLspTransport,
    LspTransportError,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    return tmp_path


@pytest.fixture
def server_config() -> LspServerConfig:
    return LspServerConfig(
        language="python",
        command=("pylsp",),
        root_markers=("pyproject.toml",),
        initialize_timeout_ms=1000,
        request_timeout_ms=1000,
    )


@pytest.fixture
def config() -> LspConfig:
    return LspConfig(
        servers=(),
        max_diagnostics_per_file=3,
        max_references=2,
        max_workspace_symbols=2,
    )


@pytest.fixture
def transport() -> FakeLspTransport:
    return FakeLspTransport()


@pytest.fixture
def client(
    workspace: Path,
    server_config: LspServerConfig,
    config: LspConfig,
    transport: FakeLspTransport,
) -> LspClient:
    return LspClient(
        server_config=server_config,
        workspace_root=workspace,
        config=config,
        transport=transport,
    )


@pytest.mark.asyncio
async def test_definition_returns_locations(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("def foo():\n    pass\n", encoding="utf-8")

    transport.on(
        "textDocument/definition",
        result=[
            {
                "uri": (workspace / "mod.py").as_uri(),
                "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 7}},
            }
        ],
    )

    locations = await client.definition(target, line=2, character=4)
    assert len(locations) == 1
    assert locations[0].path == str(workspace / "mod.py")
    assert locations[0].line == 0
    assert locations[0].character == 4
    assert "mod.py:1:5" in locations[0].format(workspace_root=workspace)


@pytest.mark.asyncio
async def test_definition_lazy_initialize(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    transport.on("textDocument/definition", result=None)

    await client.definition(target, line=0, character=0)

    # initialize must be called exactly once
    init_calls = [c for c in transport.calls if c[0] == "initialize"]
    assert len(init_calls) == 1
    # didOpen must have been sent
    didopen = [n for n in transport.notifications if n[0] == "textDocument/didOpen"]
    assert len(didopen) == 1


@pytest.mark.asyncio
async def test_definition_reuses_initialized_client(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    transport.on("textDocument/definition", result=None)

    await client.definition(target, line=0, character=0)
    await client.definition(target, line=0, character=0)

    init_calls = [c for c in transport.calls if c[0] == "initialize"]
    assert len(init_calls) == 1


@pytest.mark.asyncio
async def test_references_truncated(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    transport.on(
        "textDocument/references",
        result=[
            {"uri": target.as_uri(), "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}},
            {"uri": target.as_uri(), "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 1}}},
            {"uri": target.as_uri(), "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 1}}},
        ],
    )

    locations = await client.references(target, line=0, character=0)
    # max_references = 2 in fixture
    assert len(locations) == 2


@pytest.mark.asyncio
async def test_hover_returns_value(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    transport.on(
        "textDocument/hover",
        result={"contents": {"kind": "markdown", "value": "int: 1"}},
    )

    hover = await client.hover(target, line=0, character=0)
    assert hover == "int: 1"


@pytest.mark.asyncio
async def test_workspace_symbols_truncated(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    transport.on(
        "workspace/symbol",
        result=[
            {"name": "Foo", "kind": 12, "location": {"uri": target.as_uri(), "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 3}}}},
            {"name": "Bar", "kind": 12, "location": {"uri": target.as_uri(), "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 3}}}},
            {"name": "Baz", "kind": 12, "location": {"uri": target.as_uri(), "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 3}}}},
        ],
    )

    symbols = await client.workspace_symbols("Foo")
    # max_workspace_symbols = 2 in fixture
    assert len(symbols) == 2


@pytest.mark.asyncio
async def test_diagnostics_pull_falls_back_to_published(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = \n", encoding="utf-8")

    # textDocument/diagnostic returns an error -> client falls back to published
    transport.on("textDocument/diagnostic", error="method not found")
    # Simulate server-pushed diagnostics for the file
    target_uri = target.as_uri()
    transport.push_notification(
        "textDocument/publishDiagnostics",
        {
            "uri": target_uri,
            "diagnostics": [
                {"range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 5}},
                 "severity": 1, "message": "syntax error"},
                {"range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 5}},
                 "severity": 2, "message": "warning"},
            ],
        },
    )

    diagnostics = await client.diagnostics(target)
    assert len(diagnostics) == 2
    assert diagnostics[0].severity == "error"
    assert "syntax error" in diagnostics[0].format(workspace_root=workspace)


@pytest.mark.asyncio
async def test_diagnostics_truncated_to_max(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    transport.on(
        "textDocument/diagnostic",
        result={
            "items": [
                {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}, "severity": 1, "message": "e1"},
                {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}, "severity": 1, "message": "e2"},
                {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}, "severity": 1, "message": "e3"},
                {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}, "severity": 1, "message": "e4"},
            ]
        },
    )

    diagnostics = await client.diagnostics(target)
    # max_diagnostics_per_file = 3
    assert len(diagnostics) == 3


@pytest.mark.asyncio
async def test_request_timeout_marks_unhealthy(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    transport.on("textDocument/definition", error="LSP request textDocument/definition timed out after 1000ms")

    with pytest.raises(LspClientError, match="timed out"):
        await client.definition(target, line=0, character=0)

    assert client._unhealthy is True


@pytest.mark.asyncio
async def test_request_failure_raises_client_error(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    transport.on("textDocument/definition", error="LSP error: boom")

    with pytest.raises(LspClientError, match="boom"):
        await client.definition(target, line=0, character=0)


@pytest.mark.asyncio
async def test_document_change_after_write(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    transport.on("textDocument/definition", result=None)

    await client.definition(target, line=0, character=0)
    # First open version is 1
    didopen = [n for n in transport.notifications if n[0] == "textDocument/didOpen"][0]
    assert didopen[1]["textDocument"]["version"] == 1

    target.write_text("x = 2\n", encoding="utf-8")
    await client.notify_document_changed(target)

    didchange = [n for n in transport.notifications if n[0] == "textDocument/didChange"]
    assert len(didchange) == 1
    assert didchange[0][1]["textDocument"]["version"] == 2
    assert didchange[0][1]["contentChanges"][0]["text"] == "x = 2\n"


@pytest.mark.asyncio
async def test_manager_returns_none_when_no_server(workspace: Path):
    config = LspConfig(servers=())
    manager = LspClientManager(config=config, workspace_root=workspace)

    assert manager.has_server_for("python") is False
    assert manager.get_client_for_file(workspace / "x.py", "python") is None


@pytest.mark.asyncio
async def test_manager_caches_client_per_language(
    workspace: Path, transport: FakeLspTransport
):
    server = LspServerConfig(language="python", command=("pylsp",))
    config = LspConfig(servers=(server,))
    manager = LspClientManager(
        config=config,
        workspace_root=workspace,
        transport_factory=lambda s, w: transport,
    )

    c1 = manager.get_client_for_file(workspace / "a.py", "python")
    c2 = manager.get_client_for_file(workspace / "b.py", "python")
    assert c1 is c2

    await manager.shutdown_all()
    assert transport.closed is True


@pytest.mark.asyncio
async def test_shutdown_clears_state(
    client: LspClient, workspace: Path, transport: FakeLspTransport
):
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    transport.on("textDocument/definition", result=None)

    await client.definition(target, line=0, character=0)
    assert client._initialized is True

    await client.shutdown()
    assert client._initialized is False
    assert transport.closed is True


class TestResolveEffectiveRoot:
    def test_marker_found_within_workspace(self, tmp_path: Path):
        from agent.lsp.client import _resolve_effective_root

        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "pyproject.toml").write_text("", encoding="utf-8")
        sub = ws / "sub" / "deep"
        sub.mkdir(parents=True)
        target = sub / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")

        root = _resolve_effective_root(target, ws, ("pyproject.toml",))
        assert root == ws

    def test_marker_not_found_falls_back_to_workspace(self, tmp_path: Path):
        from agent.lsp.client import _resolve_effective_root

        ws = tmp_path / "workspace"
        ws.mkdir()
        sub = ws / "sub"
        sub.mkdir()
        target = sub / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")

        root = _resolve_effective_root(target, ws, ("pyproject.toml",))
        assert root == ws

    def test_marker_outside_workspace_falls_back_and_warns(self, tmp_path: Path, caplog):
        from agent.lsp.client import _resolve_effective_root

        ws = tmp_path / "workspace"
        ws.mkdir()
        # Put marker outside workspace
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        sub = ws / "sub"
        sub.mkdir()
        target = sub / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")

        with caplog.at_level("WARNING"):
            root = _resolve_effective_root(target, ws, ("pyproject.toml",))
        assert root == ws
        assert "outside workspace" in caplog.text

    def test_closest_marker_wins_in_nested_dirs(self, tmp_path: Path):
        from agent.lsp.client import _resolve_effective_root

        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "pyproject.toml").write_text("", encoding="utf-8")
        mid = ws / "sub"
        mid.mkdir()
        (mid / "pyproject.toml").write_text("", encoding="utf-8")
        deep = mid / "deep"
        deep.mkdir()
        target = deep / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")

        root = _resolve_effective_root(target, ws, ("pyproject.toml",))
        # Closest marker at ws/sub
        assert root == mid

    def test_multiple_markers_first_match_wins(self, tmp_path: Path):
        from agent.lsp.client import _resolve_effective_root

        ws = tmp_path / "workspace"
        ws.mkdir()
        sub = ws / "sub"
        sub.mkdir()
        (sub / "setup.cfg").write_text("", encoding="utf-8")
        target = sub / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")

        root = _resolve_effective_root(
            target, ws, ("pyproject.toml", "setup.cfg", "setup.py")
        )
        assert root == sub


class TestManagerRootResolution:
    def test_clients_keyed_by_effective_root(self, tmp_path: Path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        proj_a = ws / "proj_a"
        proj_a.mkdir()
        (proj_a / "pyproject.toml").write_text("", encoding="utf-8")
        proj_b = ws / "proj_b"
        proj_b.mkdir()
        (proj_b / "pyproject.toml").write_text("", encoding="utf-8")

        server = LspServerConfig(
            language="python",
            command=("pylsp",),
            root_markers=("pyproject.toml",),
        )
        config = LspConfig(servers=(server,))
        manager = LspClientManager(config=config, workspace_root=ws)

        c_a = manager.get_client_for_file(proj_a / "a.py", "python")
        c_b = manager.get_client_for_file(proj_b / "b.py", "python")
        # Different effective roots -> different clients
        assert c_a is not c_b
        assert c_a.workspace_root == proj_a
        assert c_b.workspace_root == proj_b

    def test_no_marker_same_client(self, tmp_path: Path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "a.py").write_text("", encoding="utf-8")
        (ws / "b.py").write_text("", encoding="utf-8")

        server = LspServerConfig(
            language="python",
            command=("pylsp",),
            root_markers=("pyproject.toml",),
        )
        config = LspConfig(servers=(server,))
        manager = LspClientManager(config=config, workspace_root=ws)

        c1 = manager.get_client_for_file(ws / "a.py", "python")
        c2 = manager.get_client_for_file(ws / "b.py", "python")
        assert c1 is c2
        assert c1.workspace_root == ws
