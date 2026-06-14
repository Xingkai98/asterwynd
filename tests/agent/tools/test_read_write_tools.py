import pytest
from agent.tools.builtin.bash import BashTool
from agent.tools.builtin.grep import GrepTool
from agent.tools.builtin.read import ReadTool
from agent.tools.builtin.write import WriteTool


@pytest.mark.asyncio
async def test_read_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")

    tool = ReadTool()
    result = await tool.execute(path=str(f))
    assert result == "hello world"


@pytest.mark.asyncio
async def test_read_file_not_found():
    tool = ReadTool()
    result = await tool.execute(path="/nonexistent/file.txt")
    assert "Error" in result or "not found" in result.lower()


@pytest.mark.asyncio
async def test_read_directory_returns_error(tmp_path):
    tool = ReadTool()
    result = await tool.execute(path=str(tmp_path))
    assert "Error" in result


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
    assert "Timeout" in result


@pytest.mark.asyncio
async def test_bash_non_zero_exit():
    tool = BashTool()
    result = await tool.execute(cmd="sh -c 'echo failed >&2; exit 7'")
    assert "[Exit 7]" in result
    assert "failed" in result


@pytest.mark.asyncio
async def test_grep_invalid_regex_returns_error(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    tool = GrepTool()
    result = await tool.execute(pattern="[", path=str(f))
    assert "Error" in result
