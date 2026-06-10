# tests/agent/tools/test_registry.py
import pytest
from agent.tools.registry import ToolRegistry
from agent.tools.base import Tool, tool_parameters, ToolCall

@tool_parameters(name="Echo", description="Echo back", parameters={"type": "object", "properties": {}})
class EchoTool(Tool):
    name = "Echo"
    description = "Echo back"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return "echo!"

def test_register_tool():
    registry = ToolRegistry()
    registry.register(EchoTool())
    assert "Echo" in registry._tools

def test_get_schema():
    registry = ToolRegistry()
    registry.register(EchoTool())
    schema = registry.get_schema("Echo")
    assert schema["function"]["name"] == "Echo"

def test_get_sandbox_flag():
    registry = ToolRegistry()
    registry.register(EchoTool())
    assert registry.get_sandbox("Echo") is False

@pytest.mark.asyncio
async def test_execute_found():
    registry = ToolRegistry()
    registry.register(EchoTool())
    call = ToolCall(id="c1", name="Echo", arguments={})
    result = await registry.execute(call)
    assert result == "echo!"


@pytest.mark.asyncio
async def test_execute_not_found():
    registry = ToolRegistry()
    call = ToolCall(id="c1", name="NonExistent", arguments={})
    with pytest.raises(KeyError):
        await registry.execute(call)
