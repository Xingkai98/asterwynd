from __future__ import annotations

from pathlib import Path

import pytest

from agent.code_intelligence.config import LspConfig, LspServerConfig
from agent.lsp.client import LspClientManager
from agent.lsp.transport import FakeLspTransport
from agent.tools.builtin.lsp import (
    LspDefinitionTool,
    LspDocumentSymbolsTool,
    LspDiagnosticsTool,
    LspHoverTool,
    LspReferencesTool,
    LspWorkspaceSymbolsTool,
)
from agent.workspace_policy import WorkspacePolicy


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    return tmp_path


@pytest.fixture
def transport() -> FakeLspTransport:
    return FakeLspTransport()


@pytest.fixture
def lsp_manager(workspace: Path, transport: FakeLspTransport) -> LspClientManager:
    server = LspServerConfig(language="python", command=("pylsp",))
    config = LspConfig(servers=(server,), max_diagnostics_per_file=5, max_references=3)
    return LspClientManager(
        config=config,
        workspace_root=workspace,
        transport_factory=lambda s, w: transport,
    )


@pytest.fixture
def policy(workspace: Path) -> WorkspacePolicy:
    return WorkspacePolicy(workspace_root=workspace)


@pytest.fixture
def target_file(workspace: Path) -> Path:
    f = workspace / "mod.py"
    f.write_text("def foo():\n    return 1\n\nfoo()\n", encoding="utf-8")
    return f


@pytest.mark.asyncio
async def test_definition_tool_formats_location(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    target_file: Path,
    transport: FakeLspTransport,
    workspace: Path,
):
    transport.on(
        "textDocument/definition",
        result=[{
            "uri": target_file.as_uri(),
            "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 7}},
        }],
    )
    tool = LspDefinitionTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="mod.py", line=4, character=1)
    assert "mod.py:1:5" in result


@pytest.mark.asyncio
async def test_definition_tool_no_server_for_language(
    lsp_manager: LspClientManager, policy: WorkspacePolicy, workspace: Path
):
    # rust file with only python server configured
    (workspace / "x.rs").write_text("fn main() {}", encoding="utf-8")
    tool = LspDefinitionTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="x.rs", line=1, character=1)
    assert "no LSP server configured" in result


@pytest.mark.asyncio
async def test_definition_tool_file_not_found(
    lsp_manager: LspClientManager, policy: WorkspacePolicy
):
    tool = LspDefinitionTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="missing.py", line=1, character=1)
    assert "not found" in result


@pytest.mark.asyncio
async def test_definition_tool_workspace_outside_rejected(
    lsp_manager: LspClientManager, policy: WorkspacePolicy, tmp_path: Path, workspace: Path
):
    # workspace fixture == tmp_path, so go above it to get outside
    outside = workspace.parent / "outside_lsp_test.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    try:
        tool = LspDefinitionTool(policy=policy, lsp_manager=lsp_manager)
        result = await tool.execute(path=str(outside), line=1, character=1)
        assert "Error" in result
    finally:
        outside.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_references_tool_truncated(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    target_file: Path,
    transport: FakeLspTransport,
):
    transport.on(
        "textDocument/references",
        result=[
            {"uri": target_file.as_uri(), "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}},
            {"uri": target_file.as_uri(), "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 1}}},
            {"uri": target_file.as_uri(), "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 1}}},
            {"uri": target_file.as_uri(), "range": {"start": {"line": 3, "character": 0}, "end": {"line": 3, "character": 1}}},
        ],
    )
    tool = LspReferencesTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="mod.py", line=1, character=1)
    # max_references = 3
    assert len(result.strip().split("\n")) == 3


@pytest.mark.asyncio
async def test_hover_tool_returns_value(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    target_file: Path,
    transport: FakeLspTransport,
):
    transport.on(
        "textDocument/hover",
        result={"contents": {"kind": "markdown", "value": "def foo() -> int"}},
    )
    tool = LspHoverTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="mod.py", line=1, character=1)
    assert result == "def foo() -> int"


@pytest.mark.asyncio
async def test_hover_tool_no_hover_returns_marker(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    target_file: Path,
    transport: FakeLspTransport,
):
    transport.on("textDocument/hover", result=None)
    tool = LspHoverTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="mod.py", line=1, character=1)
    assert "no hover information" in result


@pytest.mark.asyncio
async def test_document_symbols_tool(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    target_file: Path,
    transport: FakeLspTransport,
):
    transport.on(
        "textDocument/documentSymbol",
        result=[
            {"name": "foo", "kind": 12, "location": {"uri": target_file.as_uri(), "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 7}}}},
        ],
    )
    tool = LspDocumentSymbolsTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="mod.py")
    assert "Function foo @ line 1:5" in result


@pytest.mark.asyncio
async def test_workspace_symbols_tool(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    target_file: Path,
    transport: FakeLspTransport,
):
    transport.on(
        "workspace/symbol",
        result=[
            {"name": "foo", "kind": 12, "location": {"uri": target_file.as_uri(), "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 7}}}},
        ],
    )
    tool = LspWorkspaceSymbolsTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(query="foo")
    assert "foo" in result
    assert "Function" in result


@pytest.mark.asyncio
async def test_diagnostics_tool_returns_diagnostics(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    target_file: Path,
    transport: FakeLspTransport,
):
    transport.on(
        "textDocument/diagnostic",
        result={
            "items": [
                {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 3}},
                 "severity": 1, "message": "undefined name"},
            ]
        },
    )
    tool = LspDiagnosticsTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="mod.py")
    assert "[error]" in result
    assert "undefined name" in result
    assert "mod.py:1" in result


@pytest.mark.asyncio
async def test_diagnostics_tool_no_diagnostics(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    target_file: Path,
    transport: FakeLspTransport,
):
    transport.on("textDocument/diagnostic", result={"items": []})
    tool = LspDiagnosticsTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="mod.py")
    assert "no diagnostics" in result


@pytest.mark.asyncio
async def test_diagnostics_tool_handles_client_error(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    target_file: Path,
    transport: FakeLspTransport,
):
    transport.on("textDocument/diagnostic", error="boom")
    tool = LspDiagnosticsTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="mod.py")
    # Falls back to published diagnostics (empty). Should not raise.
    assert "no diagnostics" in result or "Error" in result


@pytest.mark.asyncio
async def test_tools_are_read_only(lsp_manager: LspClientManager, policy: WorkspacePolicy):
    for cls in (
        LspDefinitionTool,
        LspReferencesTool,
        LspHoverTool,
        LspDocumentSymbolsTool,
        LspWorkspaceSymbolsTool,
        LspDiagnosticsTool,
    ):
        tool = cls(policy=policy, lsp_manager=lsp_manager)
        assert tool.read_only is True


@pytest.mark.asyncio
async def test_tools_registered_in_factory(
    lsp_manager: LspClientManager, policy: WorkspacePolicy
):
    from agent.tools.factory import KNOWN_BUILTIN_TOOL_NAMES

    for name in (
        "LspDefinition",
        "LspReferences",
        "LspHover",
        "LspDocumentSymbols",
        "LspWorkspaceSymbols",
        "LspDiagnostics",
    ):
        assert name in KNOWN_BUILTIN_TOOL_NAMES
