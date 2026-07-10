import pytest

from agent.run_config import (
    AgentMode,
    AgentRunConfig,
    AgentRuntimeState,
    ModePolicy,
    parse_agent_mode,
)
from agent.tool_permissions import (
    PermissionDecisionType,
    ToolCapability,
    ToolPermission,
    ToolRiskLevel,
)
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


class PermissionedTool(Tool):
    name = "Permissioned"
    description = "permissioned"
    parameters = {}

    def __init__(self, permission: ToolPermission):
        self.permission = permission

    async def execute(self, **kwargs) -> str:
        return "permissioned"


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


def test_runtime_state_set_mode_updates_current_mode_and_returns_transition():
    state = AgentRuntimeState(initial_mode=AgentMode.BUILD)

    transition = state.set_mode("read-only", source="cli", reason="inspect only")

    assert state.current_mode is AgentMode.READ_ONLY
    assert transition == {
        "old_mode": "build",
        "new_mode": "read_only",
        "source": "cli",
        "reason": "inspect only",
    }


def test_runtime_state_rejects_bypass_and_keeps_current_mode():
    state = AgentRuntimeState(initial_mode=AgentMode.BUILD)

    with pytest.raises(ValueError, match="bypass"):
        state.set_mode("bypass", source="cli")

    assert state.current_mode is AgentMode.BUILD


def test_mode_policy_keeps_high_risk_tools_visible_in_build():
    policy = ModePolicy(AgentRunConfig(mode=AgentMode.BUILD))

    assert policy.is_tool_allowed(DummyTool(read_only=False, dangerous=True)) is True


def test_mode_policy_requires_approval_for_high_risk_tools_in_build():
    policy = ModePolicy(AgentRunConfig(mode=AgentMode.BUILD))

    decision = policy.decide_tool(DummyTool(read_only=False, dangerous=True))

    assert decision.type is PermissionDecisionType.REQUIRE_APPROVAL
    assert decision.permission.risk_level is ToolRiskLevel.HIGH


def test_mode_policy_denies_configured_tool_name_in_build():
    policy = ModePolicy(
        AgentRunConfig(mode=AgentMode.BUILD),
        deny_tools_by_mode={AgentMode.BUILD: ("Dummy",)},
    )

    assert policy.is_tool_allowed(DummyTool(read_only=True, dangerous=False)) is False


def test_mode_policy_reads_latest_runtime_state_mode():
    state = AgentRuntimeState(initial_mode=AgentMode.BUILD)
    policy = ModePolicy(
        AgentRunConfig(mode=AgentMode.BUILD),
        runtime_state=state,
    )

    assert policy.is_tool_allowed(DummyTool(read_only=False, dangerous=False)) is True

    state.set_mode("read_only", source="test")

    assert policy.is_tool_allowed(DummyTool(read_only=False, dangerous=False)) is False


def test_mode_policy_read_only_allows_only_read_only_non_dangerous_tools():
    policy = ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))

    assert policy.is_tool_allowed(DummyTool(read_only=True, dangerous=False)) is True
    assert policy.is_tool_allowed(DummyTool(read_only=False, dangerous=False)) is False
    assert policy.is_tool_allowed(DummyTool(read_only=True, dangerous=True)) is False


def test_mode_policy_plan_allows_agent_state_tools():
    plan = ModePolicy(AgentRunConfig(mode=AgentMode.PLAN))
    tool = PermissionedTool(
        ToolPermission(
            capabilities=frozenset({ToolCapability.AGENT_STATE}),
            risk_level=ToolRiskLevel.MEDIUM,
        )
    )

    assert plan.decide_tool(tool).type is PermissionDecisionType.ALLOW


def test_mode_policy_read_only_requires_approval_for_agent_state_tools():
    read_only = ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))
    tool = PermissionedTool(
        ToolPermission(
            capabilities=frozenset({ToolCapability.AGENT_STATE}),
            risk_level=ToolRiskLevel.MEDIUM,
        )
    )

    assert read_only.decide_tool(tool).type is PermissionDecisionType.REQUIRE_APPROVAL


def test_mode_policy_bypass_fails_closed():
    policy = ModePolicy(AgentRunConfig(mode=AgentMode.BYPASS))

    assert policy.is_tool_allowed(DummyTool(read_only=True, dangerous=False)) is False


def test_mode_policy_validates_unknown_deny_tools():
    policy = ModePolicy(
        AgentRunConfig(mode=AgentMode.BUILD),
        deny_tools_by_mode={AgentMode.BUILD: ("Missing",)},
    )

    with pytest.raises(ValueError, match="Unknown deny_tools"):
        policy.validate_known_tools(["Dummy"])
