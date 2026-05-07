# tests/agent/tools/test_base.py
import pytest
from agent.tools.base import Tool, tool_parameters

def test_tool_parameters_decorator():
    @tool_parameters(name="Test", description="A test tool", parameters={"type": "object"})
    class TestTool(Tool):
        name = "test"
        description = "A test tool"
        parameters = {}

        async def execute(self, **kwargs) -> str:
            return "done"

    assert TestTool.name == "test"
    assert TestTool.description == "A test tool"
    assert TestTool.parameters == {"type": "object"}

def test_tool_read_only_flag():
    @tool_parameters(name="Read", description="Read file", parameters={"type": "object"})
    class ReadTool(Tool):
        name = "Read"
        description = "Read file"
        parameters = {}
        read_only = True

        async def execute(self, **kwargs) -> str:
            return "content"

    tool = ReadTool()
    assert tool.read_only is True
    assert tool.dangerous is False