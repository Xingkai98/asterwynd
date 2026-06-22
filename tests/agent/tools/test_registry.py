# tests/agent/tools/test_registry.py
import pytest
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy
from agent.tools.registry import ToolRegistry
from agent.tools.base import Tool, tool_parameters, ToolCall

@tool_parameters(name="Echo", description="Echo back", parameters={"type": "object", "properties": {}})
class EchoTool(Tool):
    name = "Echo"
    description = "Echo back"
    parameters = {}
    read_only = True

    async def execute(self, **kwargs) -> str:
        return "echo!"


@tool_parameters(name="WriteLike", description="Write", parameters={"type": "object", "properties": {}})
class WriteLikeTool(Tool):
    name = "WriteLike"
    description = "Write"
    parameters = {}
    read_only = False

    def __init__(self):
        self.called = False

    async def execute(self, **kwargs) -> str:
        self.called = True
        return "wrote!"

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


def test_get_all_schemas_filters_tools_by_mode_policy():
    registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))
    )
    registry.register(EchoTool())
    registry.register(WriteLikeTool())

    names = [schema["function"]["name"] for schema in registry.get_all_schemas()]

    assert names == ["Echo"]

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


@pytest.mark.asyncio
async def test_execute_denied_by_mode_policy_returns_permission_result_without_calling_tool():
    tool = WriteLikeTool()
    registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))
    )
    registry.register(tool)

    result = await registry.execute(ToolCall(id="c1", name="WriteLike", arguments={}))

    assert "Permission denied" in result
    assert "WriteLike" in result
    assert "read_only" in result
    assert tool.called is False
