# tests/agent/tools/test_registry.py
import pytest
from agent.run_config import AgentMode, AgentRunConfig, AgentRuntimeState, ModePolicy
from agent.tool_permissions import ToolCapability, ToolPermission, ToolRiskLevel
from agent.tools.factory import build_default_tool_registry
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


@tool_parameters(name="HighRisk", description="High", parameters={"type": "object", "properties": {}})
class HighRiskTool(Tool):
    name = "HighRisk"
    description = "High"
    parameters = {}
    permission = ToolPermission(
        capabilities=frozenset({ToolCapability.COMMAND_EXECUTE}),
        risk_level=ToolRiskLevel.HIGH,
    )

    def __init__(self):
        self.called = False

    async def execute(self, **kwargs) -> str:
        self.called = True
        return "high!"

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


def test_get_all_schemas_uses_latest_runtime_state_mode():
    state = AgentRuntimeState(initial_mode=AgentMode.BUILD)
    registry = ToolRegistry(
        mode_policy=ModePolicy(
            AgentRunConfig(mode=AgentMode.BUILD),
            runtime_state=state,
        )
    )
    registry.register(EchoTool())
    registry.register(WriteLikeTool())

    assert [schema["function"]["name"] for schema in registry.get_all_schemas()] == [
        "Echo",
        "WriteLike",
    ]

    state.set_mode("read_only", source="test")

    assert [schema["function"]["name"] for schema in registry.get_all_schemas()] == [
        "Echo",
    ]


def test_get_all_schemas_includes_approval_required_tools():
    registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.BUILD))
    )
    registry.register(HighRiskTool())

    assert [schema["function"]["name"] for schema in registry.get_all_schemas()] == [
        "HighRisk"
    ]

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


@pytest.mark.asyncio
async def test_execute_uses_latest_runtime_state_mode():
    state = AgentRuntimeState(initial_mode=AgentMode.BUILD)
    tool = WriteLikeTool()
    registry = ToolRegistry(
        mode_policy=ModePolicy(
            AgentRunConfig(mode=AgentMode.BUILD),
            runtime_state=state,
        )
    )
    registry.register(tool)

    state.set_mode("read_only", source="test")
    result = await registry.execute(ToolCall(id="c1", name="WriteLike", arguments={}))

    assert "Permission denied" in result
    assert "read_only" in result
    assert tool.called is False


@pytest.mark.asyncio
async def test_execute_denied_by_configured_deny_tool_returns_permission_result():
    registry = ToolRegistry(
        mode_policy=ModePolicy(
            AgentRunConfig(mode=AgentMode.BUILD),
            deny_tools_by_mode={AgentMode.BUILD: ("Echo",)},
        )
    )
    registry.register(EchoTool())

    result = await registry.execute(ToolCall(id="c1", name="Echo", arguments={}))

    assert "Permission denied" in result
    assert "Echo" in result
    assert "build" in result


@pytest.mark.asyncio
async def test_execute_approval_required_tool_fails_closed_without_approval():
    tool = HighRiskTool()
    registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.BUILD))
    )
    registry.register(tool)

    result = await registry.execute(ToolCall(id="c1", name="HighRisk", arguments={}))

    assert "Approval required" in result
    assert tool.called is False


@pytest.mark.asyncio
async def test_execute_approval_required_tool_runs_with_approval_granted():
    tool = HighRiskTool()
    registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.BUILD))
    )
    registry.register(tool)

    result = await registry.execute(
        ToolCall(id="c1", name="HighRisk", arguments={}),
        approval_granted=True,
    )

    assert result == "high!"
    assert tool.called is True


def test_factory_allows_deny_tool_known_but_not_registered_in_entrypoint():
    registry = build_default_tool_registry(
        mode_policy=ModePolicy(
            AgentRunConfig(mode=AgentMode.BUILD),
            deny_tools_by_mode={AgentMode.BUILD: ("ListFiles",)},
        )
    )

    names = [schema["function"]["name"] for schema in registry.get_all_schemas()]
    assert "Read" in names


def test_factory_rejects_unknown_deny_tool():
    with pytest.raises(ValueError, match="Unknown deny_tools"):
        build_default_tool_registry(
            mode_policy=ModePolicy(
                AgentRunConfig(mode=AgentMode.BUILD),
                deny_tools_by_mode={AgentMode.BUILD: ("Missing",)},
            )
        )
