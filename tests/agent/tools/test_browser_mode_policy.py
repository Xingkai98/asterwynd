# tests/agent/tools/test_browser_mode_policy.py
"""浏览器工具模式策略测试 —— 验证在不同 AgentMode 下的可见性。"""

import pytest

from agent.run_config import AgentMode, AgentRunConfig, ModePolicy
from agent.tool_permissions import (
    BUILTIN_PERMISSION_PROFILES,
    BROWSER_READ_PERMISSION,
    PermissionDecisionType,
    ToolCapability,
    ToolOrigin,
    ToolRiskLevel,
)
from agent.tools.builtin.browser import BrowserTool
from agent.tools.builtin.browser_navigate import BrowserNavigateTool
from agent.tools.builtin.browser_tools import BROWSER_TOOL_CLASSES


def _make_policy(mode: AgentMode) -> ModePolicy:
    """为给定模式构造 ModePolicy。"""
    return ModePolicy(
        run_config=AgentRunConfig(mode=mode),
        permission_profiles_by_mode={
            AgentMode.BUILD: BUILTIN_PERMISSION_PROFILES["build_default"],
            AgentMode.READ_ONLY: BUILTIN_PERMISSION_PROFILES["read_only_default"],
            AgentMode.PLAN: BUILTIN_PERMISSION_PROFILES["plan_default"],
            AgentMode.BYPASS: BUILTIN_PERMISSION_PROFILES["fail_closed"],
        },
    )


class TestBrowserToolsInBuildMode:
    """BUILD 模式下浏览器工具可见。"""

    def test_build_mode_allows_browser_tools(self):
        """BUILD 模式的 build_default profile 允许所有能力，包括 BROWSER_CONTROL。"""
        policy = _make_policy(AgentMode.BUILD)
        tool = BrowserNavigateTool()

        decision = policy.decide_tool(tool)
        assert decision.is_visible is True
        # MEDIUM risk is auto-approved in build_default
        assert decision.can_execute_without_approval is True

    @pytest.mark.parametrize("tool_cls", BROWSER_TOOL_CLASSES)
    def test_all_browser_tools_visible_in_build(self, tool_cls):
        """所有浏览器工具在 BUILD 模式下可见。"""
        policy = _make_policy(AgentMode.BUILD)
        tool = tool_cls()

        assert policy.is_tool_allowed(tool) is True


class TestBrowserToolsInReadOnlyMode:
    """READ_ONLY 模式下浏览器工具不可见。"""

    def test_read_only_mode_denies_browser_tools(self):
        """READ_ONLY 模式的 read_only_default profile 不包含 BROWSER_CONTROL。"""
        policy = _make_policy(AgentMode.READ_ONLY)
        tool = BrowserNavigateTool()

        decision = policy.decide_tool(tool)
        assert decision.is_visible is False
        assert decision.type == PermissionDecisionType.DENY
        assert "browser_control" in decision.reason

    @pytest.mark.parametrize("tool_cls", BROWSER_TOOL_CLASSES)
    def test_all_browser_tools_denied_in_read_only(self, tool_cls):
        """所有浏览器工具在 READ_ONLY 模式下被拒绝。"""
        policy = _make_policy(AgentMode.READ_ONLY)
        tool = tool_cls()

        assert policy.is_tool_allowed(tool) is False


class TestBrowserToolsInPlanMode:
    """PLAN 模式下浏览器工具不可见。"""

    def test_plan_mode_denies_browser_tools(self):
        """PLAN 模式的 plan_default profile 不包含 BROWSER_CONTROL。"""
        policy = _make_policy(AgentMode.PLAN)
        tool = BrowserNavigateTool()

        decision = policy.decide_tool(tool)
        assert decision.is_visible is False

    @pytest.mark.parametrize("tool_cls", BROWSER_TOOL_CLASSES)
    def test_all_browser_tools_denied_in_plan(self, tool_cls):
        """所有浏览器工具在 PLAN 模式下被拒绝。"""
        policy = _make_policy(AgentMode.PLAN)
        tool = tool_cls()

        assert policy.is_tool_allowed(tool) is False


class TestBrowserToolsInBypassMode:
    """BYPASS 模式下浏览器工具不可见。"""

    def test_bypass_mode_denies_browser_tools(self):
        """BYPASS 模式的 fail_closed profile 不包含任何能力。"""
        policy = _make_policy(AgentMode.BYPASS)
        tool = BrowserNavigateTool()

        decision = policy.decide_tool(tool)
        assert decision.is_visible is False


class TestBrowserPermissionMetadata:
    """浏览器工具权限元数据验证。"""

    def test_permission_risk_level_medium(self):
        """浏览器工具风险等级为 MEDIUM。"""
        tool = BrowserNavigateTool()
        permission = tool.get_permission()

        assert permission.risk_level == ToolRiskLevel.MEDIUM

    def test_permission_origin_browser(self):
        """浏览器工具 origin 为 BROWSER。"""
        tool = BrowserNavigateTool()
        permission = tool.get_permission()

        assert permission.origin == ToolOrigin.BROWSER

    def test_permission_capability_browser_control(self):
        """浏览器工具 capability 包含 BROWSER_CONTROL。"""
        tool = BrowserNavigateTool()
        permission = tool.get_permission()

        assert ToolCapability.BROWSER_CONTROL in permission.capabilities
