# tests/agent/tools/test_builtin.py
import pytest
import asyncio
from pathlib import Path
from agent.tools.builtin.read import ReadTool
from agent.tools.builtin.write import WriteTool

def test_read_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")

    tool = ReadTool()
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute(path=str(f))
    )
    assert result == "hello world"

def test_read_file_not_found():
    tool = ReadTool()
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute(path="/nonexistent/file.txt")
    )
    assert "Error" in result or "not found" in result.lower()

def test_write_file(tmp_path):
    tool = WriteTool()
    file_path = tmp_path / "output.txt"
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute(path=str(file_path), content="hello")
    )
    assert file_path.read_text() == "hello"