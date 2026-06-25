from __future__ import annotations

from pathlib import Path

import pytest

from agent.code_intelligence.config import LspConfig, LspServerConfig
from agent.lsp.client import LspClientManager
from agent.lsp.transport import FakeLspTransport
from agent.tools.builtin.edit import EditTool
from agent.tools.builtin.write import WriteTool
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
    config = LspConfig(servers=(server,), max_diagnostics_per_file=5)
    return LspClientManager(
        config=config,
        workspace_root=workspace,
        transport_factory=lambda s, w: transport,
    )


@pytest.fixture
def policy(workspace: Path) -> WorkspacePolicy:
    return WorkspacePolicy(workspace_root=workspace)


@pytest.mark.asyncio
async def test_write_appends_diagnostics_when_lsp_available(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    transport: FakeLspTransport,
    workspace: Path,
):
    transport.on(
        "textDocument/diagnostic",
        result={
            "items": [
                {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 3}},
                 "severity": 1, "message": "undefined name 'x'"},
            ]
        },
    )

    tool = WriteTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="new.py", content="x = y\n")

    assert "已写入" in result
    assert "LSP diagnostics" in result
    assert "[error]" in result
    assert "undefined name" in result


@pytest.mark.asyncio
async def test_write_no_diagnostics_when_lsp_returns_empty(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    transport: FakeLspTransport,
):
    transport.on("textDocument/diagnostic", result={"items": []})

    tool = WriteTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="new.py", content="x = 1\n")

    assert "已写入" in result
    assert "LSP diagnostics" not in result


@pytest.mark.asyncio
async def test_write_no_diagnostics_when_no_server_for_language(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
):
    # rust file, only python server configured
    tool = WriteTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="new.rs", content="fn main() {}\n")

    assert "已写入" in result
    assert "LSP diagnostics" not in result


@pytest.mark.asyncio
async def test_write_no_diagnostics_when_no_lsp_manager(policy: WorkspacePolicy):
    # WriteTool without lsp_manager — backwards compatibility
    tool = WriteTool(policy=policy, lsp_manager=None)
    result = await tool.execute(path="new.py", content="x = 1\n")

    assert "已写入" in result
    assert "LSP diagnostics" not in result


@pytest.mark.asyncio
async def test_write_lsp_error_does_not_break_write(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    transport: FakeLspTransport,
):
    transport.on("textDocument/diagnostic", error="server crashed")

    tool = WriteTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(path="new.py", content="x = 1\n")

    assert "已写入" in result
    # Diagnostics gracefully degraded away — no error surfaced
    assert "LSP diagnostics" not in result
    assert "crashed" not in result


@pytest.mark.asyncio
async def test_edit_appends_diagnostics_when_lsp_available(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    transport: FakeLspTransport,
    workspace: Path,
):
    target = workspace / "mod.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")

    transport.on(
        "textDocument/diagnostic",
        result={
            "items": [
                {"range": {"start": {"line": 2, "character": 4}, "end": {"line": 2, "character": 10}},
                 "severity": 2, "message": "unused variable"},
            ]
        },
    )

    tool = EditTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(
        path="mod.py",
        old_string="return 1",
        new_string="return 2",
    )

    assert "Replaced 1 occurrence" in result
    assert "LSP diagnostics" in result
    assert "[warning]" in result
    assert "unused variable" in result


@pytest.mark.asyncio
async def test_edit_no_diagnostics_when_no_lsp_manager(
    policy: WorkspacePolicy, workspace: Path
):
    target = workspace / "mod.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")

    tool = EditTool(policy=policy, lsp_manager=None)
    result = await tool.execute(
        path="mod.py",
        old_string="return 1",
        new_string="return 2",
    )

    assert "Replaced 1 occurrence" in result
    assert "LSP diagnostics" not in result


@pytest.mark.asyncio
async def test_edit_lsp_error_does_not_break_edit(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    transport: FakeLspTransport,
    workspace: Path,
):
    target = workspace / "mod.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")

    transport.on("textDocument/diagnostic", error="server unavailable")

    tool = EditTool(policy=policy, lsp_manager=lsp_manager)
    result = await tool.execute(
        path="mod.py",
        old_string="return 1",
        new_string="return 2",
    )

    assert "Replaced 1 occurrence" in result
    assert "LSP diagnostics" not in result


@pytest.mark.asyncio
async def test_write_didchange_synced_before_diagnostics(
    lsp_manager: LspClientManager,
    policy: WorkspacePolicy,
    transport: FakeLspTransport,
    workspace: Path,
):
    # Pre-open the document via a definition call, then Write/Edit should
    # send didChange (not re-didOpen) and then pull diagnostics.
    target = workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    # First, trigger didOpen via diagnostics tool
    transport.on("textDocument/definition", result=None)
    from agent.tools.builtin.lsp import LspDefinitionTool

    def_tool = LspDefinitionTool(policy=policy, lsp_manager=lsp_manager)
    await def_tool.execute(path="mod.py", line=1, character=1)

    # Now overwrite with new content via a fresh file (Write refuses to overwrite)
    target.write_text("y = 2\n", encoding="utf-8")

    transport.on(
        "textDocument/diagnostic",
        result={"items": []},
    )

    # Use Edit to modify in place
    edit_tool = EditTool(policy=policy, lsp_manager=lsp_manager)
    target.write_text("y = 2\n", encoding="utf-8")
    # Need original content to match
    target.write_text("y = 1\n", encoding="utf-8")
    result = await edit_tool.execute(
        path="mod.py",
        old_string="y = 1",
        new_string="y = 2",
    )

    did_change = [n for n in transport.notifications if n[0] == "textDocument/didChange"]
    assert len(did_change) >= 1
    assert "Replaced" in result
