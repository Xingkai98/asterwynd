import pytest

from agent.run_config import AgentMode, AgentRunConfig, ModePolicy, parse_agent_mode
from agent.tools.base import Tool


class DummyTool(Tool):
    name = "Dummy"
    description = "dummy"
    parameters = {}

    def __init__(self, *, read_only: bool, dangerous: bool):
        self.read_only = read_only
        self.dangerous = dangerous

    async def execute(self, **kwargs) -> str:
        return "dummy"


def test_parse_agent_mode_accepts_supported_user_values():
    assert parse_agent_mode("build") is AgentMode.BUILD
    assert parse_agent_mode("read_only") is AgentMode.READ_ONLY
    assert parse_agent_mode("read-only") is AgentMode.READ_ONLY
    assert parse_agent_mode("plan") is AgentMode.PLAN


def test_parse_agent_mode_rejects_bypass_for_user_input():
    with pytest.raises(ValueError, match="bypass"):
        parse_agent_mode("bypass")


def test_parse_agent_mode_can_allow_internal_bypass():
    assert parse_agent_mode("bypass", allow_bypass=True) is AgentMode.BYPASS


def test_agent_run_config_defaults_to_build():
    assert AgentRunConfig().mode is AgentMode.BUILD


def test_mode_policy_allows_all_registered_tools_in_build():
    policy = ModePolicy(AgentRunConfig(mode=AgentMode.BUILD))

    assert policy.is_tool_allowed(DummyTool(read_only=False, dangerous=True)) is True


def test_mode_policy_read_only_allows_only_read_only_non_dangerous_tools():
    policy = ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))

    assert policy.is_tool_allowed(DummyTool(read_only=True, dangerous=False)) is True
    assert policy.is_tool_allowed(DummyTool(read_only=False, dangerous=False)) is False
    assert policy.is_tool_allowed(DummyTool(read_only=True, dangerous=True)) is False


def test_mode_policy_plan_matches_read_only_policy():
    plan = ModePolicy(AgentRunConfig(mode=AgentMode.PLAN))
    read_only = ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))
    tool = DummyTool(read_only=True, dangerous=False)

    assert plan.is_tool_allowed(tool) == read_only.is_tool_allowed(tool)


def test_mode_policy_bypass_fails_closed():
    policy = ModePolicy(AgentRunConfig(mode=AgentMode.BYPASS))

    assert policy.is_tool_allowed(DummyTool(read_only=True, dangerous=False)) is False
