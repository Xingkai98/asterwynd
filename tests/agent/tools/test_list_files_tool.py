import pytest

from agent.tools.builtin.list_files import ListFilesTool
from agent.workspace_policy import WorkspacePolicy


@pytest.mark.asyncio
async def test_lists_directory_contents(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "subdir").mkdir()
    tool = ListFilesTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute(".")

    lines = result.split("\n")
    assert "a.py" in lines
    assert "b.txt" in lines
    assert "subdir/" in lines


@pytest.mark.asyncio
async def test_lists_empty_directory(tmp_path):
    tool = ListFilesTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute(".")

    assert result == "(empty directory)"


@pytest.mark.asyncio
async def test_ignores_sensitive_directories(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "README.md").write_text("")
    tool = ListFilesTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute(".")

    assert ".git" not in result
    assert "node_modules" not in result
    assert "README.md" in result


@pytest.mark.asyncio
async def test_rejects_path_outside_workspace(tmp_path):
    tool = ListFilesTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("/etc")

    assert "Error" in result


@pytest.mark.asyncio
async def test_rejects_non_directory(tmp_path):
    (tmp_path / "file.txt").write_text("")
    tool = ListFilesTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("file.txt")

    assert "not a directory" in result


@pytest.mark.asyncio
async def test_custom_ignore_patterns(tmp_path):
    (tmp_path / "custom_cache").mkdir()
    (tmp_path / "src").mkdir()
    tool = ListFilesTool(
        policy=WorkspacePolicy(tmp_path),
        ignore_patterns=("custom_cache",),
    )

    result = await tool.execute(".")

    assert "custom_cache" not in result
    assert "src/" in result


@pytest.mark.asyncio
async def test_sorts_dirs_first(tmp_path):
    (tmp_path / "zebra.py").write_text("")
    (tmp_path / "alpha").mkdir()
    tool = ListFilesTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute(".")

    lines = result.split("\n")
    assert lines[0] == "alpha/"
    assert lines[1] == "zebra.py"
