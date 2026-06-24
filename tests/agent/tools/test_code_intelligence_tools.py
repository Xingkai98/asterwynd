import pytest

from agent.run_config import AgentMode, AgentRunConfig, ModePolicy
from agent.tools.base import ToolCall
from agent.tools.builtin.code_intelligence import RepoMapTool, SymbolSearchTool
from agent.tools.factory import build_coding_tool_registry
from agent.workspace_policy import WorkspacePolicy


def test_code_intelligence_tool_schemas_are_read_only():
    repo_map = RepoMapTool()
    symbol_search = SymbolSearchTool()

    assert repo_map.read_only is True
    assert symbol_search.read_only is True
    assert repo_map.get_schema()["function"]["name"] == "RepoMap"
    assert symbol_search.get_schema()["function"]["name"] == "SymbolSearch"


@pytest.mark.asyncio
async def test_repo_map_tool_returns_limited_summary(tmp_path):
    (tmp_path / "a.py").write_text("def alpha():\n    pass\n")
    (tmp_path / "b.py").write_text("def beta():\n    pass\n")

    tool = RepoMapTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(max_files=1)

    assert "a.py" in result
    assert "b.py" not in result
    assert "... truncated, showing first 1 files" in result


@pytest.mark.asyncio
async def test_symbol_search_tool_finds_matching_symbols(tmp_path):
    (tmp_path / "service.py").write_text(
        "class Service:\n    def run(self):\n        pass\n"
    )

    tool = SymbolSearchTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(query="run")

    assert "service.py:2 method Service.run" in result


@pytest.mark.asyncio
async def test_symbol_search_tool_marks_tree_sitter_symbol_source(tmp_path):
    (tmp_path / "app.ts").write_text("export function run() {}\n", encoding="utf-8")

    tool = SymbolSearchTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(query="run")

    assert "app.ts:1 function run [typescript/tree-sitter-typescript]" in result


@pytest.mark.asyncio
async def test_symbol_search_tool_skips_denied_paths(tmp_path):
    (tmp_path / ".env").write_text("def secret():\n    pass\n")
    (tmp_path / "public.py").write_text("def public():\n    pass\n")

    tool = SymbolSearchTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(query="")

    assert "public.py" in result
    assert ".env" not in result
    assert "secret" not in result


def test_coding_registry_exposes_code_intelligence_tools_in_plan_mode():
    registry = build_coding_tool_registry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.PLAN))
    )

    names = {schema["function"]["name"] for schema in registry.get_all_schemas()}

    assert "RepoMap" in names
    assert "SymbolSearch" in names


@pytest.mark.asyncio
async def test_registry_executes_code_intelligence_tool_call(tmp_path):
    (tmp_path / "app.py").write_text("def main():\n    pass\n")
    registry = build_coding_tool_registry(policy=WorkspacePolicy(tmp_path))

    result = await registry.execute(
        ToolCall(id="call-1", name="SymbolSearch", arguments={"query": "main"})
    )

    assert "app.py:1 function main" in result
