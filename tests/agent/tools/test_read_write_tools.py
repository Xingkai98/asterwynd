import json

import pytest
from agent.tools.builtin.bash import BashTool
from agent.tools.builtin.grep import GrepTool
from agent.tools.builtin.read import ReadTool
from agent.tools.builtin.write import WriteTool
from agent.workspace_policy import WorkspacePolicy


@pytest.mark.asyncio
async def test_read_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")

    tool = ReadTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(path=str(f))
    assert result == "hello world"


@pytest.mark.asyncio
async def test_read_file_not_found():
    tool = ReadTool()
    result = await tool.execute(path="/nonexistent/file.txt")
    assert "Error" in result or "not found" in result.lower()


@pytest.mark.asyncio
async def test_read_default_policy_uses_current_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "test.txt").write_text("hello cwd")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside")
    tool = ReadTool()

    try:
        assert await tool.execute(path="test.txt") == "hello cwd"
        result = await tool.execute(path=str(outside))
    finally:
        outside.unlink(missing_ok=True)

    assert "outside workspace" in result
    assert "outside\n" not in result


@pytest.mark.asyncio
async def test_read_directory_returns_error(tmp_path):
    tool = ReadTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute(path=str(tmp_path))
    assert "Error" in result


@pytest.mark.asyncio
async def test_read_rejects_path_outside_workspace(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret")
    tool = ReadTool(policy=WorkspacePolicy(tmp_path))

    try:
        result = await tool.execute(path=str(outside))
    finally:
        outside.unlink(missing_ok=True)

    assert "outside workspace" in result
    assert "secret" not in result


@pytest.mark.asyncio
async def test_read_rejects_denied_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=secret\n")
    tool = ReadTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute(path=".env")

    assert "denied" in result.lower()
    assert "TOKEN=secret" not in result


@pytest.mark.asyncio
async def test_write_file(tmp_path):
    tool = WriteTool()
    file_path = tmp_path / "output.txt"
    result = await tool.execute(path=str(file_path), content="hello")
    assert "已写入" in result
    assert file_path.read_text() == "hello"


@pytest.mark.asyncio
async def test_write_existing_file_is_rejected(tmp_path):
    tool = WriteTool()
    file_path = tmp_path / "output.txt"
    file_path.write_text("old")

    result = await tool.execute(path=str(file_path), content="new")

    assert "file already exists" in result
    assert file_path.read_text() == "old"


@pytest.mark.asyncio
async def test_write_existing_file_still_rejected_with_unrecognized_overwrite_kwarg(tmp_path):
    tool = WriteTool()
    file_path = tmp_path / "output.txt"
    file_path.write_text("old")

    result = await tool.execute(path=str(file_path), content="new", overwrite=True)

    assert "file already exists" in result
    assert file_path.read_text() == "old"


@pytest.mark.asyncio
async def test_write_directory_path_returns_error(tmp_path):
    tool = WriteTool()
    result = await tool.execute(path=str(tmp_path), content="hello")
    assert "Error" in result


@pytest.mark.asyncio
async def test_bash_timeout():
    tool = BashTool()
    result = await tool.execute(cmd="sleep 1", timeout=0.05)
    data = json.loads(result)
    assert data["timed_out"]


@pytest.mark.asyncio
async def test_bash_non_zero_exit():
    tool = BashTool()
    result = await tool.execute(cmd="sh -c 'echo failed >&2; exit 7'")
    data = json.loads(result)
    assert data["exit_code"] == 7
    assert data["stderr"] == "failed"


@pytest.mark.asyncio
async def test_grep_invalid_regex_returns_error(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    tool = GrepTool()
    result = await tool.execute(pattern="[", path=str(f))
    assert "Error" in result


@pytest.mark.asyncio
async def test_grep_default_policy_uses_current_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "test.txt").write_text("needle cwd\n")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("needle outside\n")
    tool = GrepTool()

    try:
        assert "needle cwd" in await tool.execute(pattern="needle", path="test.txt")
        result = await tool.execute(pattern="needle", path=str(outside))
    finally:
        outside.unlink(missing_ok=True)

    assert "outside workspace" in result
    assert "needle outside" not in result


@pytest.mark.asyncio
async def test_grep_rejects_path_outside_workspace(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret")
    tool = GrepTool(policy=WorkspacePolicy(tmp_path))

    try:
        result = await tool.execute(pattern="secret", path=str(outside))
    finally:
        outside.unlink(missing_ok=True)

    assert "outside workspace" in result
    assert "secret" not in result


@pytest.mark.asyncio
async def test_grep_recursive_skips_denied_files(tmp_path):
    (tmp_path / "visible.txt").write_text("needle visible\n")
    (tmp_path / ".env").write_text("needle secret\n")
    tool = GrepTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute(pattern="needle", path=".", recursive=True)

    assert "visible.txt" in result
    assert ".env" not in result
    assert "secret" not in result
