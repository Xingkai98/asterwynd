import pytest

from agent.tools.builtin.edit import EditTool
from agent.workspace_policy import WorkspacePolicy


@pytest.fixture
def tool(tmp_path):
    return EditTool(policy=WorkspacePolicy(tmp_path))


@pytest.mark.asyncio
async def test_edit_tool_replaces_exact_single_match(tool, tmp_path):
    target = tmp_path / "app.py"
    target.write_text("hello world\n")

    result = await tool.execute("app.py", "hello", "goodbye")

    assert "Replaced 1 occurrence" in result
    assert target.read_text() == "goodbye world\n"


@pytest.mark.asyncio
async def test_edit_tool_missing_old_string_fails(tool, tmp_path):
    target = tmp_path / "app.py"
    target.write_text("hello world\n")

    result = await tool.execute("app.py", "missing", "new")

    assert "not found" in result
    assert target.read_text() == "hello world\n"


@pytest.mark.asyncio
async def test_edit_tool_multiple_matches_fail_without_replace_all(tool, tmp_path):
    target = tmp_path / "app.py"
    target.write_text("TODO\nTODO\n")

    result = await tool.execute("app.py", "TODO", "DONE")

    assert "matched 2 times" in result
    assert target.read_text() == "TODO\nTODO\n"


@pytest.mark.asyncio
async def test_edit_tool_replace_all(tool, tmp_path):
    target = tmp_path / "app.py"
    target.write_text("TODO\nTODO\n")

    result = await tool.execute("app.py", "TODO", "DONE", replace_all=True)

    assert "Replaced 2 occurrences" in result
    assert target.read_text() == "DONE\nDONE\n"


@pytest.mark.asyncio
async def test_edit_tool_rejects_denied_path(tool, tmp_path):
    target = tmp_path / ".env"
    target.write_text("SECRET=old\n")

    result = await tool.execute(".env", "old", "new")

    assert "Write denied" in result
    assert target.read_text() == "SECRET=old\n"


@pytest.mark.asyncio
async def test_edit_tool_rejects_empty_old_string(tool):
    result = await tool.execute("app.py", "", "new")

    assert "must not be empty" in result

